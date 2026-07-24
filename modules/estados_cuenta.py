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
from datetime import datetime

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


_EXTRACTOR_SYS = (
    "Lees estados de cuenta y cartolas de bancos chilenos. Devuelve SOLO un JSON, sin texto extra, con: "
    "fecha (YYYY-MM-DD del estado de cuenta), "
    "deuda_total (entero CLP; para una TARJETA = el 'CUPO UTILIZADO'; para una LÍNEA DE CRÉDITO = el "
    "valor de la etiqueta 'MONTO UTILIZADO' —no el saldo de movimientos—; null si no aplica), "
    "cupo (entero CLP o null), interes_mes (entero CLP del interés/‘TOTAL INTERESES’ del período o null), "
    "pago_minimo (entero CLP o null), "
    "transacciones (lista de COMPRAS reales del período: {fecha (YYYY-MM-DD), comercio, monto (entero CLP)}; "
    "NO incluyas pagos, abonos, intereses, impuestos ni amortizaciones — solo compras a comercios). "
    "Números sin separador de miles."
)


async def _extraer(texto: str, producto: str) -> dict | None:
    try:
        r = await _anthropic.messages.create(
            model=settings.model_cheap, max_tokens=900, system=_EXTRACTOR_SYS,
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


# ───────────────────────── Reconciliación (1×/mes) ─────────────────────────

# Descripciones que NO son compras a comercio (son mecanismos de deuda/pago) → fuera de la reconciliación.
_NO_COMPRA = ("avance", "cuota", "interes", "interés", "pago", "abono", "amortiz", "impuesto",
              "comision", "comisión", "cancelado", "transferencia")


async def _reconciliar(transacciones: list[dict], dias_recientes: int = 45) -> list[dict]:
    """Compara las COMPRAS del estado con `Transacciones` de la planilla. Devuelve las del estado
    que NO están registradas (posibles gastos que se pasaron). Match por monto exacto + fecha ±5d.
    Filtra ruido: salta avances/cuotas/pagos/intereses y compras viejas (cuotas ya conocidas).
    No escribe nada (invariante): solo señala para que Nico revise."""
    try:
        planilla = await sheets.get_dicts(HOJA_TX, sheet_id=sheets.fin_id(), value_render="UNFORMATTED_VALUE")
    except Exception:
        logger.exception("_reconciliar: no pude leer Transacciones")
        return []
    montos_planilla = [(str(t.get("Fecha", "")).strip(), int(finanzas._num(t.get("Monto", 0)))) for t in planilla]
    hoy = datetime.now(settings.tz).date()
    faltan = []
    for tx in transacciones or []:
        monto = int(finanzas._num(tx.get("monto", 0)))
        comercio = str(tx.get("comercio", "")).strip()
        if monto <= 0 or any(k in comercio.lower() for k in _NO_COMPRA):
            continue
        fecha = str(tx.get("fecha", "")).strip()
        try:
            d = datetime.strptime(fecha[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if (hoy - d).days > dias_recientes:
            continue  # cuota vieja de una compra ya conocida, no un gasto que falte
        if not any(pm == monto and _cerca(pf, fecha) for pf, pm in montos_planilla):
            faltan.append({"fecha": fecha, "comercio": comercio, "monto": monto})
    return faltan


def _cerca(f1: str, f2: str, dias: int = 5) -> bool:
    try:
        d1 = datetime.strptime(f1[:10], "%Y-%m-%d").date()
        d2 = datetime.strptime(f2[:10], "%Y-%m-%d").date()
        return abs((d1 - d2).days) <= dias
    except (ValueError, TypeError):
        return False


# ───────────────────────── Orquestación ─────────────────────────

async def procesar(max_n: int = 40, reconciliar: bool = True, forzar: bool = False) -> dict:
    """Baja los estados nuevos, extrae, actualiza faro + historial, reconcilia. Devuelve el
    resumen para el reporte. Cada (correo+adjunto) se procesa una sola vez (dedup en memoria);
    `forzar=True` reprocesa todo (para backfill/validación)."""
    resumen = {"nuevos": 0, "bancos": set(), "registros": [], "faltantes": [], "deuda_actual": 0,
               "delta": None, "procedencia": []}
    if not gmail.disponible():
        return resumen
    msgs = await gmail.buscar_estados(QUERY, max_n)
    tx_para_reconciliar = []
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
            # historial + faro
            try:
                await _upsert_historial(datos)
                for fila, col, val in _celdas_faro(banco, producto, datos):
                    await sheets.set_cell(HOJA_TARJETAS, fila, col, val, sheet_id=sheets.fin_id())
            except Exception:
                logger.exception("estados_cuenta: no pude actualizar faro/historial")
            if producto == "tarjeta_credito":
                tx_para_reconciliar += datos.get("transacciones") or []
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
    if reconciliar and tx_para_reconciliar:
        resumen["faltantes"] = await _reconciliar(tx_para_reconciliar)
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
    if r.get("faltantes"):
        n = len(r["faltantes"])
        muestra = "; ".join(f"{finanzas.clp(x['monto'])} en {x['comercio']}" for x in r["faltantes"][:3])
        l.append(f"⚠️ {n} cargo(s) del banco que no tengo registrados (revisa si se te pasaron): {muestra}"
                 + (" …" if n > 3 else "") + ".")
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


TOOLS = [
    {
        "name": "fin_progreso_deuda",
        "description": "OBLIGATORIO cuando Nico pregunta cómo va su deuda, si ha bajado, o por el progreso mes a mes. Lee el historial real (Deuda_Mensual). No inventes.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {"fin_progreso_deuda": _t_progreso}
