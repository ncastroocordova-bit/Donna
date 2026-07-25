"""Estados de cuenta (Finanzas v4). Tools/flujos `fin_`.

Baja del correo los estados de cuenta (PDF), los descifra (Mach = RUT; BCh = clave del .env),
extrae las cifras de DEUDA con el LLM (el texto sale muy sucio para regex), y:
  1) actualiza el FARO vivo (celdas-input de 'Tarjetas y Deuda' — las fórmulas se recalculan solas),
  2) lleva el historial mes a mes en la hoja `Deuda_Mensual` (registro visible),
  3) reconcilia las transacciones del estado contra `Transacciones` (1×/mes) → marca posibles faltantes,
  4) arma un reporte para que Donna avise cuando llegan y cuánto avanzó la deuda.

Solo DEUDA: BCh tarjeta + línea, Mach tarjeta. Invariantes: correo jamás borra (solo lee/baja);
la clave del PDF vive en env, nunca en el Sheet/repo/chat; el worker destila, no vuelca el PDF crudo.
"""
import io
import json
import logging
from datetime import datetime, timedelta

import pypdf
from anthropic import AsyncAnthropic

from config import settings
from core import email_gmail as gmail
from core import memory, sheets
from modules import finanzas

logger = logging.getLogger(__name__)
_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)

HOJA_TARJETAS = "Tarjetas y Deuda"
HOJA_HIST = "Deuda_Mensual"
HOJA_TX = "Transacciones"
HIST_COLS = ["Mes", "Banco", "Producto", "Deuda", "Cupo", "Interés mes", "Pago mínimo", "Fecha estado", "Actualizado"]

QUERY = "from:bancochile.cl OR from:machbank.cl OR from:mach.cl OR subject:(estado de cuenta OR cartola)"

# (banco, producto) → celdas-input de 'Tarjetas y Deuda'. Devuelve (fila_1based, col_0based, valor).
# Las fórmulas del faro (B4:B8) NO se tocan: se recalculan de estas.
#   col B = inputs de siempre (deuda, cupo, interés de la línea).
#   col C = interés REPORTADO por el estado de cuenta de la tarjeta. B25/B37 son
#           =IF(N(Cxx)>0;Cxx;tasa*rotativa), así que el dato del banco MANDA y el cálculo
#           queda solo de respaldo. Sin esto el faro subreportaba: Mach declara $5.310 de
#           interés y el faro calculaba $0 porque su tasa-input es 0 (auditoría 2026-07-23).
_COL_B, _COL_C = 1, 2


def _celdas_faro(banco: str, producto: str, d: dict) -> list[tuple[int, int, float]]:
    out = []
    if producto == "tarjeta_credito":
        f_deuda, f_cupo, f_interes = (29, 28, 25) if banco == "bch" else (40, 39, 37)
        if d.get("deuda_total"):
            out.append((f_deuda, _COL_B, int(d["deuda_total"])))
        if d.get("cupo"):
            out.append((f_cupo, _COL_B, int(d["cupo"])))
        if d.get("interes_mes"):
            out.append((f_interes, _COL_C, int(d["interes_mes"])))
    elif producto == "linea_credito" and d.get("deuda_total"):
        out.append((44, _COL_B, int(d["deuda_total"])))   # monto utilizado de la línea
    elif producto == "linea_interes" and d.get("interes_mes"):
        out.append((45, _COL_B, int(d["interes_mes"])))
    return out


def _banco(remitente: str, asunto: str) -> str:
    s = (remitente + " " + asunto).lower()
    if "bancochile" in s or "banco de chile" in s:
        return "bch"
    if "mach" in s:
        return "mach"
    return "otro"


def _producto(asunto: str, filename: str) -> str:
    s = (asunto + " " + filename).lower()
    if "sobregiro" in s:
        return "sobregiro"                                   # interés de sobregiro c/c (menor, se ignora)
    if ("liqint" in s or "liquidac" in s) and ("ldc" in s or "linea" in s or "línea" in s):
        return "linea_interes"                               # interés de la línea → B45
    if "linea" in s or "línea" in s or "ldc" in s:
        return "linea_credito"                               # monto utilizado de la línea → B44
    # Ola 5 (F5.1): cartola de CUENTA CORRIENTE — débito. Va DESPUÉS de los checks de línea porque
    # "cartola" también aparece en "Cartola Línea de Crédito Mensual". No es un documento de deuda:
    # NO debe pasar por _celdas_faro ni _upsert_historial (corrompería el faro) — solo alimenta la
    # reconciliación (F5.3) y, si trae abonos, los ingresos (F5.7).
    if "cuenta corriente" in s or "ctacte" in s:
        return "cartola_cuenta_corriente"
    if "tarjeta" in s or "eecc" in s or "estado de cuenta" in s:
        return "tarjeta_credito"
    return "otro"


def _clave(banco: str) -> str:
    """Clave del PDF: Mach abre con el RUT; BCh con el código del .env. Nunca se loguea."""
    if banco == "mach":
        return (settings.__dict__.get("banco_pdf_password_mach") or "").strip() or _rut_num()
    return settings.banco_pdf_password_bch


def _rut_num() -> str:
    return "20255435"  # RUT sin dígito ni puntos (Mach lo usa como clave); fallback si no hay env


def _texto_pdf(pdf_bytes: bytes, clave: str) -> str:
    """Descifra y extrae el texto. '' si la clave no abre o no hay texto."""
    try:
        r = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if r.is_encrypted and not r.decrypt(clave or ""):
            return ""
        return " ".join(" ".join((p.extract_text() or "").split()) for p in r.pages)
    except Exception:
        logger.exception("estados_cuenta: no pude leer el PDF")
        return ""


# Ola 5: schema único para los tres formatos (tarjeta, línea, cartola de cuenta corriente). En vez de
# pedirle al LLM que ya venga clasificando "esto es una compra, esto es un cobro del banco" (juicio que
# se presta a error y es caro de verificar), el LLM solo EXTRAE los movimientos crudos con su signo
# (cargo/abono); la clasificación compra/cobro/abono la hace después Python de forma determinista
# (`_clasificar_movimientos`, reutiliza `_NO_COMPRA`) — más barato y más fácil de testear sin red.
_EXTRACTOR_SYS = (
    "Lees estados de cuenta y cartolas de bancos chilenos (tarjeta de crédito, línea de crédito o "
    "cuenta corriente/cartola). Devuelve SOLO un JSON, sin texto extra, con: "
    "fecha (YYYY-MM-DD de emisión del estado), "
    "periodo_desde, periodo_hasta (YYYY-MM-DD del período que factura/cubre el documento, o null si no "
    "se indica claramente), "
    "deuda_total (entero CLP; para una TARJETA = el 'CUPO UTILIZADO'; para una LÍNEA DE CRÉDITO = el "
    "valor de la etiqueta 'MONTO UTILIZADO' —no el saldo de movimientos—; null si no aplica o es cartola "
    "de cuenta corriente), "
    "cupo (entero CLP o null), interes_mes (entero CLP del interés/'TOTAL INTERESES' del período o null), "
    "pago_minimo (entero CLP o null), "
    "saldo_final (entero CLP: SOLO para cartola de cuenta corriente, el saldo al cierre del período; "
    "null para tarjeta/línea), "
    "movimientos (lista de TODOS los movimientos individuales del período — compras, pagos, intereses, "
    "comisiones, cuotas Y abonos/depósitos, sin filtrar nada — cada uno: "
    "{fecha (YYYY-MM-DD), descripcion (comercio o glosa del banco tal como aparece), "
    "monto (entero CLP, siempre positivo), tipo ('cargo' si sale plata, 'abono' si entra), "
    "rut_contraparte (RUT del destinatario/emisor si el documento lo trae, o null)}). "
    "Números sin separador de miles."
)


async def _extraer(texto: str, producto: str) -> dict | None:
    try:
        # Ola 5: el schema único (`movimientos` con TODOS los cargos/abonos, sin filtrar) puede ser
        # largo en una cartola de cuenta corriente con muchos movimientos — 900 tokens (el límite de
        # cuando el extractor solo devolvía deuda+compras filtradas) cortaba el JSON a mitad de un
        # string y la extracción fallaba SIEMPRE en cartolas reales (verificado 2026-07-23 contra los
        # PDF de BCh y Mach: incluso 4000 se cortó — `stop_reason == "max_tokens"` con un mes normal
        # de movimientos de cuenta corriente). El costo es por tokens generados, no por el tope, así
        # que subir el techo no cuesta más salvo que la respuesta lo use de verdad.
        r = await _anthropic.messages.create(
            model=settings.model_cheap, max_tokens=8000, system=_EXTRACTOR_SYS,
            messages=[{"role": "user", "content": f"Documento tipo '{producto}'. Extrae:\n\n{texto[:12000]}"}],
        )
        t = r.content[0].text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(t)
    except Exception:
        logger.exception("estados_cuenta: extracción falló")
        return None


# ───────────────────────── Historial mes a mes (Deuda_Mensual) ─────────────────────────

async def _upsert_historial(reg: dict) -> None:
    """Una fila por (Mes, Banco, Producto). Si existe, la actualiza; si no, la agrega."""
    fid = sheets.fin_id()
    filas = await sheets.get_rows(HOJA_HIST, sheet_id=fid)
    h_idx, headers = sheets._fila_headers(filas)
    if h_idx < 0:
        headers = HIST_COLS
        h_idx = 0
    idx = {c: headers.index(c) for c in HIST_COLS if c in headers}
    fila_vals = [reg.get("mes", ""), reg.get("banco", ""), reg.get("producto", ""),
                 reg.get("deuda_total") or "", reg.get("cupo") or "", reg.get("interes_mes") or "",
                 reg.get("pago_minimo") or "", reg.get("fecha", ""), _hoy()]
    # ¿existe ya la fila (mes+banco+producto)?
    for n, fila in enumerate(filas[h_idx + 1:], start=h_idx + 2):
        def g(c):
            i = idx.get(c, -1)
            return str(fila[i]).strip() if 0 <= i < len(fila) else ""
        if g("Mes") == reg.get("mes") and g("Banco") == reg.get("banco") and g("Producto") == reg.get("producto"):
            for col, val in zip(HIST_COLS, fila_vals):
                if col in idx:
                    await sheets.set_cell(HOJA_HIST, n, idx[col], val, sheet_id=fid)
            return
    await sheets.append_row(HOJA_HIST, fila_vals, sheet_id=fid)


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


# ───────────────────────── Saldo mensual (Ola 5 · F5.7, hoja propia) ─────────────────────────
# Hoja PROPIA, no `Deuda_Mensual`: un saldo de cuenta corriente no es deuda. Si se guardara en la
# misma hoja/columna que la deuda, `_deuda_por_mes` lo sumaría junto con la deuda real y corrompería
# el progreso mes a mes que ya lee `fin_progreso_deuda`.
HOJA_SALDOS = "Saldos"
SALDO_COLS = ["Mes", "Banco", "Saldo", "Fecha estado", "Actualizado"]


async def _upsert_saldo(banco: str, mes: str, saldo: int, fecha: str) -> None:
    """Una fila por (Mes, Banco). Auto-escribe SIN toque de Nico — mismo criterio que el faro: es
    un dato informativo que trae el documento, no un gasto que haya que confirmar (D11: excepción
    al canon de 'no saldos automáticos' porque sale gratis de un documento que Donna ya lee, no
    requiere que Nico mantenga nada)."""
    fid = sheets.fin_id()
    filas = await sheets.get_rows(HOJA_SALDOS, sheet_id=fid)
    h_idx, headers = sheets._fila_headers(filas)
    if h_idx < 0:
        headers = SALDO_COLS
        h_idx = 0
    idx = {c: headers.index(c) for c in SALDO_COLS if c in headers}
    vals = [mes, banco, int(saldo), fecha, _hoy()]
    for n, fila in enumerate(filas[h_idx + 1:], start=h_idx + 2):
        def g(c):
            i = idx.get(c, -1)
            return str(fila[i]).strip() if 0 <= i < len(fila) else ""
        if g("Mes") == mes and g("Banco") == banco:
            for col, val in zip(SALDO_COLS, vals):
                if col in idx:
                    await sheets.set_cell(HOJA_SALDOS, n, idx[col], val, sheet_id=fid)
            return
    await sheets.append_row(HOJA_SALDOS, vals, sheet_id=fid)


# ───────────────────────── F5.5 + F5.7: candidatos al buffer del digest ─────────────────────────
# Ni las compras que faltan ni los ingresos se escriben directo a Transacciones: entran al MISMO
# buffer que usa cualquier gasto de correo/foto, y salen en el próximo digest con sus chips para
# confirmar con un toque. Cero UI nueva — reusa el digest vivo completo (mensaje anclado, chips,
# commit único) y respeta el invariante "Sheets nunca escribe sin OK de Nico".

# (banco, producto del documento) → medio canónico. El documento SIEMPRE sabe de qué producto es
# —por eso se llama estado de tarjeta o cartola de cuenta corriente— y ese dato antes se perdía:
# `_registrar_faltantes` anotaba solo el banco ('Banco de Chile'), así que las compras rescatadas
# de un estado de TARJETA quedaban indistinguibles de un cargo a la cuenta corriente. Las 11 filas
# mal etiquetadas de junio salieron de acá. Ahora el producto viaja con el banco.
_MEDIO_DOC = {
    ("bch", "tarjeta_credito"): "Banco de Chile crédito",
    ("bch", "cartola_cuenta_corriente"): "Banco de Chile débito",
    ("mach", "tarjeta_credito"): "Mach crédito",
    ("mach", "cartola_cuenta_corriente"): "Mach débito",
}


def _medio_de_documento(banco: str, producto: str) -> str:
    """Medio de pago que corresponde a un documento. Si el par no está mapeado devuelve el banco
    pelado y `finanzas.normalizar_medio` lo mandará a 'Otro' — visible, no adivinado."""
    return _MEDIO_DOC.get((banco, producto), banco)


async def _registrar_faltantes(diffs: list[dict]) -> int:
    """F5.5: las compras que un diferencial marcó como 'falta anotar' → candidatas al buffer."""
    n = 0
    for d in diffs:
        medio = _medio_de_documento(d.get("banco", ""), d.get("producto", ""))
        for f in d.get("faltantes", []):
            datos = {
                "fecha": f["fecha"], "tipo": "Gasto",
                "categoria": finanzas._categoria_de(f.get("comercio", "")),
                "comercio": f.get("comercio", ""), "monto": f["monto"], "medio": medio,
                "subcategoria": f"Rut {f['rut_contraparte']}" if f.get("rut_contraparte") else "",
            }
            if await finanzas._bufferizar(datos, "estado_cuenta"):
                n += 1
    return n


# Abonos que ENTRAN a la cuenta pero NO son ingreso real (2026-07-23, contra cartolas reales):
#   · "línea de crédito" → es deuda que sacas, no plata que ganas (infla tasa de ahorro con préstamo)
#   · "reembolso"/"reverso"/"devolución"/"anulación" → devuelven un GASTO, no generan ingreso nuevo
# Análogo a `_NO_COMPRA` para los cargos.
_NO_INGRESO = ("linea de credi", "línea de credi", "linea de créd", "reembolso", "reverso",
               "devolucion", "devolución", "anulacion", "anulación")

# Bajo este monto, un abono es ruido (cashback, intereses de ahorro, vueltos) — no entra al digest.
# Decidido con Nico el 2026-07-23; ajustable.
_INGRESO_MINIMO = 1000


async def _registrar_abonos(banco: str, abonos: list[dict], dueno_rut: str) -> int:
    """F5.7: los abonos de una cartola → candidatos de Ingreso. Tres filtros:
      1. Regla del RUT propio (D12): un abono desde una cuenta de Nico es traslado, no ingreso.
      2. `_NO_INGRESO`: plata de la línea de crédito (deuda) o reembolsos (devuelven un gasto).
      3. Umbral `_INGRESO_MINIMO`: los abonos triviales (cashback de $4) son ruido, no ingreso.
    Lo que pasa los tres entra al buffer como candidato de Ingreso, a confirmar en el digest."""
    n = 0
    propios = finanzas._dueno_nombres()
    # Un abono siempre entra a la cuenta corriente, nunca a una tarjeta de crédito.
    medio = _medio_de_documento(banco, "cartola_cuenta_corriente")
    for a in abonos:
        desc = str(a.get("descripcion", "")).strip()
        rut = str(a.get("rut_contraparte") or "")
        if a["monto"] < _INGRESO_MINIMO:
            continue
        if finanzas.es_contraparte_propia(desc, rut, dueno_rut, propios):
            continue
        if any(k in desc.lower() for k in _NO_INGRESO):
            continue
        datos = {
            "fecha": str(a.get("fecha", "")) or _hoy(), "tipo": "Ingreso", "categoria": "Otro Ingreso",
            "comercio": desc or "Abono", "monto": a["monto"], "medio": medio,
            "subcategoria": f"Rut {rut}" if rut else "",
        }
        if await finanzas._bufferizar(datos, "estado_cuenta"):
            n += 1
    return n


# ───────────────────────── Reconciliación por documento (Ola 5: F5.1-F5.4) ─────────────────────────

# Descripciones que NO son compras a comercio (son mecanismos de deuda/pago) → fuera de "compras",
# se agrupan como "cobros del banco" en el diferencial (F5.3) en vez de descartarse en silencio.
# Debe cubrir todo lo que `_BUCKETS_COBRO` sabe agrupar — si un cargo cae aquí pero no calza con
# ningún bucket, `_bucket_cobro` lo manda a "otros cobros" (no rompe), pero si falta una palabra
# clave que SÍ tiene bucket (como pasaba con "mantenc" antes de este fix), el cargo se cuela como
# compra en vez de cobro y ensucia el diferencial.
_NO_COMPRA = ("avance", "cuota", "interes", "interés", "mantenc", "pago", "abono", "amortiz",
              "impuesto", "comision", "comisión", "cancelado", "transferencia")

# Bucket de cobro por palabra clave, para agrupar el diferencial de forma legible en vez de listar
# cada glosa del banco suelta. Orden importa: la primera que calza gana.
_BUCKETS_COBRO = (
    ("interes", "interés"), ("interés", "interés"), ("mantenc", "mantención"), ("cuota", "cuotas"),
    ("impuesto", "impuestos"), ("comision", "comisiones"), ("comisión", "comisiones"),
)


def _bucket_cobro(descripcion: str) -> str:
    d = (descripcion or "").lower()
    for kw, etiqueta in _BUCKETS_COBRO:
        if kw in d:
            return etiqueta
    return "otros cobros"


def _es_propio(dueno_rut: str, dueno_nombres: list[str]):
    """Predicado (descripcion, rut) → ¿la contraparte es el propio Nico? Cierra sobre la config
    para pasarlo a `_clasificar_movimientos`/`diferencial` sin que esos tengan que conocerla."""
    def _p(descripcion, rut) -> bool:
        return finanzas.es_contraparte_propia(str(descripcion or ""), str(rut or ""),
                                              dueno_rut, dueno_nombres)
    return _p


def _clasificar_movimientos(movimientos: list[dict] | None, es_propio=None
                            ) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Los `movimientos` crudos del extractor → (compras, cobros_banco, abonos, traslados).
    Determinista, sin LLM: el modelo solo extrae fecha/descripción/monto/tipo; la clasificación de
    QUÉ es cada cargo la hace `_NO_COMPRA` (ya probado desde Finanzas v4).

    `es_propio(desc, rut)` (opcional): un movimiento entre cuentas de Nico —salga o entre plata— es
    **traslado**, ni gasto ni ingreso (regla del RUT propio, D1+D12). Va a `traslados`, fuera del
    diferencial. Sin este filtro, los 'TRASPASO A:/DE: Nicolas Castro' de la cartola se contaban
    como compra faltante o como ingreso (encontrado con datos reales 2026-07-23)."""
    compras, cobros, abonos, traslados = [], [], [], []
    for m in movimientos or []:
        monto = int(finanzas._num(m.get("monto", 0)))
        if monto <= 0:
            continue
        fila = {**m, "monto": monto}
        if es_propio and es_propio(m.get("descripcion", ""), m.get("rut_contraparte")):
            traslados.append(fila)
        elif str(m.get("tipo", "")).strip().lower() == "abono":
            abonos.append(fila)
        elif any(k in str(m.get("descripcion", "")).lower() for k in _NO_COMPRA):
            cobros.append(fila)
        else:
            compras.append(fila)
    return compras, cobros, abonos, traslados


def _cerca(f1: str, f2: str, dias: int = 5) -> bool:
    try:
        d1 = datetime.strptime(f1[:10], "%Y-%m-%d").date()
        d2 = datetime.strptime(f2[:10], "%Y-%m-%d").date()
        return abs((d1 - d2).days) <= dias
    except (ValueError, TypeError):
        return False


def _en_rango(fecha: str, desde, hasta) -> bool:
    try:
        d = datetime.strptime(str(fecha)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    return desde <= d <= hasta


def diferencial(doc: dict, planilla: list[dict], hoy=None, es_propio=None) -> dict:
    """F5.2 + F5.3: el diferencial en plata de UN documento (un estado/cartola). Puro — no toca red,
    no escribe nada — para poder testearlo sin mocks de Sheets/Gmail/LLM.

    `doc` = lo que devuelve `_extraer` (+ banco/producto/fecha ya anotados por `procesar`).
    `planilla` = filas de `Transacciones` ya leídas (UNFORMATTED_VALUE), UNA sola vez por corrida —
    no por documento, para no releer la hoja N veces.
    `es_propio` (opcional): predicado que excluye los traslados entre cuentas de Nico de las compras
    (regla del RUT propio) — sin él, un 'TRASPASO A:Nicolas Castro' se reportaría como compra faltante.

    Compara SOLO compras (nunca cobros del banco, nunca abonos, nunca traslados propios) contra la
    planilla, en el RANGO del propio documento (`periodo_desde`/`periodo_hasta`); si el documento no
    trae período legible, cae a una ventana de respaldo de 45 días y lo marca `periodo_estimado` —
    nunca presenta un cuadre como exacto cuando el rango se adivinó."""
    hoy = hoy or datetime.now(settings.tz).date()
    compras, cobros, _, _ = _clasificar_movimientos(doc.get("movimientos"), es_propio)
    desde_raw, hasta_raw = doc.get("periodo_desde"), doc.get("periodo_hasta")
    estimado = not (desde_raw and hasta_raw)
    if estimado:
        try:
            hasta_d = datetime.strptime(str(doc.get("fecha") or hoy.isoformat())[:10], "%Y-%m-%d").date()
        except ValueError:
            hasta_d = hoy
        desde_d = hasta_d - timedelta(days=45)
    else:
        try:
            desde_d = datetime.strptime(str(desde_raw)[:10], "%Y-%m-%d").date()
            hasta_d = datetime.strptime(str(hasta_raw)[:10], "%Y-%m-%d").date()
        except ValueError:
            estimado = True
            hasta_d = hoy
            desde_d = hoy - timedelta(days=45)

    # sheets.fecha_iso: la planilla se lee con UNFORMATTED_VALUE → Fecha llega como número de
    # serie de Sheets (46177), no como "2026-06-11". Sin esto, TODO comparaba mal y "Anotado por
    # Donna" daba $0 en cualquier documento (verificado 2026-07-23 contra los estados reales).
    montos_planilla = [(sheets.fecha_iso(t.get("Fecha", "")), int(finanzas._num(t.get("Monto", 0))))
                       for t in planilla]
    compras_periodo = [c for c in compras if _en_rango(c.get("fecha"), desde_d, hasta_d)]
    faltantes = []
    anotado_n = 0
    for c in compras_periodo:
        if any(pm == c["monto"] and _cerca(pf, str(c.get("fecha", ""))) for pf, pm in montos_planilla):
            anotado_n += 1
        else:
            faltantes.append({"fecha": str(c.get("fecha", "")), "comercio": c.get("descripcion", ""),
                              "monto": c["monto"], "rut_contraparte": c.get("rut_contraparte")})
    compras_total = sum(c["monto"] for c in compras_periodo)
    faltan_total = sum(f["monto"] for f in faltantes)

    cobros_por_bucket: dict[str, int] = {}
    for c in cobros:
        if _en_rango(c.get("fecha"), desde_d, hasta_d):
            b = _bucket_cobro(c.get("descripcion", ""))
            cobros_por_bucket[b] = cobros_por_bucket.get(b, 0) + c["monto"]

    return {
        "banco": doc.get("banco", ""), "producto": doc.get("producto", ""),
        "periodo_desde": desde_d.isoformat(), "periodo_hasta": hasta_d.isoformat(),
        "periodo_estimado": estimado,
        "compras_total": compras_total, "compras_n": len(compras_periodo),
        "anotado_total": compras_total - faltan_total, "anotado_n": anotado_n,
        "faltantes": faltantes,
        "cobros": cobros_por_bucket,
    }


def texto_diferencial(d: dict) -> str:
    """Renderiza UN diferencial (F5.3). Dos cuadres separados, nunca mezclados: compras (lo que
    importa: un descuadre ahí = gasto perdido) y cobros del banco (Donna nunca los captura por
    correo — mezclarlos con las compras garantizaría un descuadre permanente sin significado)."""
    nb = {"bch": "BCh", "mach": "Mach"}
    np_ = {"tarjeta_credito": "tarjeta", "linea_credito": "línea", "cartola_cuenta_corriente": "cuenta corriente"}
    banco = nb.get(d["banco"], d["banco"])
    prod = np_.get(d["producto"], d["producto"])
    l = [f"📄 Estado {banco} {prod} · {d['periodo_desde']} → {d['periodo_hasta']}"
         + (" (período estimado)" if d.get("periodo_estimado") else "")]
    l.append(f"   Compras del estado      {finanzas.clp(d['compras_total'])}  ({d['compras_n']} movimientos)")
    l.append(f"   Anotado por Donna       {finanzas.clp(d['anotado_total'])}  ({d['anotado_n']} movimientos)")
    if d["faltantes"]:
        l.append(f"   ⚠️ Falta anotar          {finanzas.clp(sum(f['monto'] for f in d['faltantes']))}"
                 f"  ({len(d['faltantes'])} compra(s))")
    else:
        l.append("   ✓ cuadra")
    if d.get("cobros"):
        partes = " · ".join(f"{k} {finanzas.clp(v)}" for k, v in d["cobros"].items())
        l.append(f"   Cobros del banco (no son gasto que se te olvidó): {partes}")
    return "\n".join(l)


# ───────────────────────── Orquestación ─────────────────────────

async def procesar(max_n: int = 40, reconciliar: bool = True, forzar: bool = False) -> dict:
    """Baja los estados nuevos, extrae, actualiza faro + historial (docs de deuda) o reconcilia +
    registra ingresos/saldo (cartolas), y arma el diferencial por documento (Ola 5). Devuelve el
    resumen para el reporte. Cada (correo+adjunto) se procesa una sola vez (dedup en memoria);
    `forzar=True` reprocesa todo (para backfill/validación)."""
    resumen = {"nuevos": 0, "bancos": set(), "registros": [], "reconciliaciones": [],
               "faltantes_agregados": 0, "ingresos_agregados": 0,
               "deuda_actual": 0, "delta": None, "procedencia": []}
    if not gmail.disponible():
        return resumen
    msgs = await gmail.buscar_estados(QUERY, max_n)
    # Se leen UNA vez por corrida (no por documento) — varios estados pueden llegar el mismo día.
    planilla, dueno_rut = [], ""
    if reconciliar:
        try:
            planilla = await sheets.get_dicts(HOJA_TX, sheet_id=sheets.fin_id(), value_render="UNFORMATTED_VALUE")
        except Exception:
            logger.exception("procesar: no pude leer Transacciones para reconciliar")
        try:
            dueno_rut = (await memory.get_perfil()).get("rut", "")
        except Exception:
            pass
    es_propio = _es_propio(dueno_rut, finanzas._dueno_nombres())  # regla del RUT propio (D1+D12)
    for m in msgs:
        banco = _banco(m["remitente"], m["asunto"])
        if banco == "otro":
            continue
        for adj in m["adjuntos"]:
            producto = _producto(m["asunto"], adj["filename"])
            if producto in ("otro", "sobregiro"):
                continue
            clave_dedup = f"{m['id']}:{adj['filename']}"
            if not forzar:
                try:
                    if await memory.correo_visto("estadocta", clave_dedup):
                        continue
                except Exception:
                    pass
            pdf = await gmail.descargar_adjunto(m["id"], adj["attachment_id"])
            if not pdf:
                continue
            texto = _texto_pdf(pdf, _clave(banco))
            if not texto:
                logger.warning("estados_cuenta: %s no abrió (clave %s?).", adj["filename"], banco)
                continue
            datos = await _extraer(texto, producto)
            if not datos:
                continue
            datos.update({"banco": banco, "producto": producto,
                          "mes": str(datos.get("fecha", ""))[:7]})
            if producto == "linea_interes":  # doc de interés: NO aporta deuda (evita fantasma en el historial)
                datos["deuda_total"] = None
                datos["cupo"] = None
            resumen["registros"].append(datos)
            resumen["bancos"].add(banco)
            resumen["nuevos"] += 1
            # Faro + historial: SOLO documentos de deuda. Una cartola de cuenta corriente NO lo es
            # (F5.1.3) — si entrara acá, corrompería el faro.
            if producto != "cartola_cuenta_corriente":
                try:
                    await _upsert_historial(datos)
                    for fila, col, val in _celdas_faro(banco, producto, datos):
                        await sheets.set_cell(HOJA_TARJETAS, fila, col, val, sheet_id=sheets.fin_id())
                except Exception:
                    logger.exception("estados_cuenta: no pude actualizar faro/historial")
            # Diferencial por documento (F5.2/F5.3): tarjeta y cartola tienen movimientos
            # comparables contra Transacciones; una línea de crédito no tiene "compras".
            if reconciliar and producto in ("tarjeta_credito", "cartola_cuenta_corriente"):
                try:
                    diff = diferencial(datos, planilla, es_propio=es_propio)
                    resumen["reconciliaciones"].append(diff)
                    resumen["faltantes_agregados"] += await _registrar_faltantes([diff])
                except Exception:
                    logger.exception("estados_cuenta: no pude reconciliar un documento")
            # F5.7: ingresos + saldo, solo cartola (única fuente con abonos/saldo de cuenta).
            if producto == "cartola_cuenta_corriente":
                try:
                    _, _, abonos, _ = _clasificar_movimientos(datos.get("movimientos"), es_propio)
                    resumen["ingresos_agregados"] += await _registrar_abonos(banco, abonos, dueno_rut)
                except Exception:
                    logger.exception("estados_cuenta: no pude registrar los abonos")
                if datos.get("saldo_final") is not None and datos.get("mes"):
                    try:
                        await _upsert_saldo(banco, datos["mes"],
                                            int(finanzas._num(datos["saldo_final"])), datos.get("fecha", ""))
                    except Exception:
                        logger.exception("estados_cuenta: no pude guardar el saldo")
            try:
                await memory.marcar_correo_visto("estadocta", clave_dedup, "estado_cuenta")
            except Exception:
                pass
    # faro recalculado + delta vs mes anterior + de qué mes es cada cifra
    try:
        faro = await finanzas.estado_deuda()
        resumen["deuda_actual"] = faro["deuda_total_real"]
        resumen["delta"] = await _delta_mes_anterior(faro["deuda_total_real"])
    except Exception:
        logger.exception("estados_cuenta: no pude leer el faro")
    try:
        resumen["procedencia"] = procedencia(
            await sheets.get_dicts(HOJA_HIST, sheet_id=sheets.fin_id(), value_render="UNFORMATTED_VALUE"))
    except Exception:
        logger.exception("estados_cuenta: no pude leer la procedencia")
        resumen["procedencia"] = []
    return resumen


def _deuda_por_mes(filas: list[dict]) -> dict[str, float]:
    """Suma la deuda por mes, contando SOLO filas con deuda > 0 (excluye docs de interés que no
    aportan deuda). Así el mes-a-mes no se infla ni cuenta un mes fantasma."""
    por_mes: dict[str, float] = {}
    for f in filas:
        mes = str(f.get("Mes", "")).strip()
        deuda = finanzas._num(f.get("Deuda", 0))
        if mes and deuda > 0:
            por_mes[mes] = por_mes.get(mes, 0) + deuda
    return por_mes


async def _delta_mes_anterior(deuda_actual: float) -> float | None:
    """Deuda actual menos la del mes anterior (de Deuda_Mensual). None si no hay ≥2 meses."""
    try:
        filas = await sheets.get_dicts(HOJA_HIST, sheet_id=sheets.fin_id(), value_render="UNFORMATTED_VALUE")
    except Exception:
        return None
    por_mes = _deuda_por_mes(filas)
    meses = sorted(por_mes)
    if len(meses) < 2:
        return None
    return deuda_actual - por_mes[meses[-2]]


# ───────────────────────── Procedencia de las cifras del faro ─────────────────────────

_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _mes_nombre(mes: str) -> str:
    try:
        return _MESES[int(str(mes)[5:7]) - 1]
    except (ValueError, IndexError):
        return str(mes)


def procedencia(filas: list[dict]) -> list[dict]:
    """De qué mes es cada cifra que suma el faro. El faro mezcla productos cuyos estados llegan en
    fechas distintas (p. ej. BCh de junio + Mach de julio, porque el de BCh todavía no sale).
    Presentar el total con fecha implícita sería afirmar sin mostrar el dato — va contra el
    invariante de inferencia validada. Devuelve una entrada por (banco, producto) con su mes más
    reciente y si quedó atrás del mes en curso."""
    mes_actual = _hoy()[:7]
    ultimo: dict[tuple[str, str], str] = {}
    for f in filas or []:
        banco = str(f.get("Banco", "")).strip()
        producto = str(f.get("Producto", "")).strip()
        mes = str(f.get("Mes", "")).strip()
        if not (banco and producto and mes):
            continue
        k = (banco, producto)
        if mes > ultimo.get(k, ""):          # 'YYYY-MM' ordena bien como texto
            ultimo[k] = mes
    return [{"banco": b, "producto": p, "mes": m, "atrasado": m < mes_actual}
            for (b, p), m in sorted(ultimo.items())]


def texto_procedencia(procs: list[dict]) -> str:
    """Una línea que dice de cuándo es cada cifra y nombra lo que aún no llega."""
    if not procs:
        return ""
    nb = {"bch": "BCh", "mach": "Mach"}
    np_ = {"tarjeta_credito": "tarjeta", "linea_credito": "línea", "linea_interes": "interés línea"}
    partes = [f"{nb.get(p['banco'], p['banco'])} {np_.get(p['producto'], p['producto'])} de "
              f"{_mes_nombre(p['mes'])}" for p in procs]
    linea = "Cifras de: " + " · ".join(partes) + "."
    atras = [p for p in procs if p["atrasado"]]
    if atras:
        q = ", ".join(f"{nb.get(p['banco'], p['banco'])} {np_.get(p['producto'], p['producto'])}"
                      for p in atras)
        linea += f" Aún no llega el estado de este mes de: {q}."
    return linea


# ───────────────────────── Reporte + progreso ─────────────────────────

def texto_reporte(r: dict) -> str:
    if not r["nuevos"]:
        return ""
    bancos = ", ".join({"bch": "Banco de Chile", "mach": "Mach"}.get(b, b) for b in r["bancos"])
    l = [f"Llegaron estados de cuenta ({bancos}). Los leí y actualicé tu deuda."]
    l.append(f"Deuda total ahora: {finanzas.clp(r['deuda_actual'])}.")
    if r.get("delta") is not None:
        d = r["delta"]
        if d < 0:
            l.append(f"Bajó {finanzas.clp(abs(d))} respecto al mes anterior. 👏")
        elif d > 0:
            l.append(f"Subió {finanzas.clp(d)} respecto al mes anterior.")
        else:
            l.append("Quedó igual que el mes anterior.")
    # detalle por producto
    det = []
    for reg in r["registros"]:
        nom = {"tarjeta_credito": "tarjeta", "linea_credito": "línea", "linea_interes": "interés línea"}.get(reg["producto"], reg["producto"])
        banco = {"bch": "BCh", "mach": "Mach"}.get(reg["banco"], reg["banco"])
        val = reg.get("deuda_total") or reg.get("interes_mes")
        if val:
            det.append(f"{banco} {nom} {finanzas.clp(val)}")
    if det:
        l.append("Detalle: " + " · ".join(det) + ".")
    proc = texto_procedencia(r.get("procedencia") or [])
    if proc:
        l.append(proc)
    for diff in r.get("reconciliaciones") or []:
        l.append("")
        l.append(texto_diferencial(diff))
    avisos = []
    if r.get("faltantes_agregados"):
        avisos.append(f"📥 {r['faltantes_agregados']} compra(s) que faltaban quedaron en tu próximo "
                      "digest para confirmar.")
    if r.get("ingresos_agregados"):
        avisos.append(f"💰 {r['ingresos_agregados']} ingreso(s) detectado(s), también en el digest.")
    if avisos:
        l.append("")
        l.extend(avisos)
    return "\n".join(l)


async def procesar_y_reportar(bot, chat_id: int) -> None:
    """Job mensual: procesa los estados nuevos y, si hubo, manda el reporte a Nico."""
    r = await procesar()
    texto = texto_reporte(r)
    if texto:
        await bot.send_message(chat_id, texto)
        logger.info("Estados de cuenta: reporte enviado (%d nuevos).", r["nuevos"])


async def _t_progreso(inp: dict) -> str:
    """Tool: '¿cómo va mi deuda?' — lee Deuda_Mensual y resume la tendencia mes a mes."""
    try:
        filas = await sheets.get_dicts(HOJA_HIST, sheet_id=sheets.fin_id(), value_render="UNFORMATTED_VALUE")
    except Exception:
        return "No pude leer tu historial de deuda ahora."
    por_mes = _deuda_por_mes(filas)
    if not por_mes:
        return "Todavía no tengo estados de cuenta cargados para mostrarte el progreso."
    meses = sorted(por_mes)[-6:]
    lineas = [f"{m}: {finanzas.clp(por_mes[m])}" for m in meses]
    cola = ""
    if len(meses) >= 2:
        d = por_mes[meses[-1]] - por_mes[meses[-2]]
        cola = f"\nÚltimo mes: {'bajó' if d < 0 else 'subió' if d > 0 else 'igual'} {finanzas.clp(abs(d))}."
    return "Progreso de tu deuda (mes a mes):\n" + "\n".join(lineas) + cola


async def _t_cuadrar_estado(inp: dict) -> str:
    """Tool (F5.6): 'cuadra el último estado' / 'revisa mis estados de cuenta' a demanda — no
    espera al job diario. Mismo `procesar()` que corre solo a las 9:30; el dedup interno hace que
    no vuelva a bajar/gastar tokens en documentos ya procesados, solo trae los nuevos si los hay."""
    r = await procesar()
    if not r["nuevos"]:
        return "No hay estados de cuenta nuevos desde la última vez que revisé."
    return texto_reporte(r)


TOOLS = [
    {
        "name": "fin_progreso_deuda",
        "description": "OBLIGATORIO cuando Nico pregunta cómo va su deuda, si ha bajado, o por el progreso mes a mes. Lee el historial real (Deuda_Mensual). No inventes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fin_cuadrar_estado",
        "description": "Cuando Nico pide revisar/cuadrar sus estados de cuenta o cartolas a demanda (ej. 'cuadra el último estado', 'revisa si me falta anotar algo del banco'), en vez de esperar al job automático de las 9:30. Procesa cualquier documento nuevo y devuelve el diferencial.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {"fin_progreso_deuda": _t_progreso, "fin_cuadrar_estado": _t_cuadrar_estado}
