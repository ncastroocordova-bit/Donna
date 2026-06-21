"""Módulo Finanzas — el delta de v7. Tools y flujos `fin_*`. Contrato de módulo (§7).

Tres sub-flujos (Plan_Construccion_v7 Paso 1.5):

(A) Registro pasivo durante el día, en CONTEXTO AISLADO (una llamada Claude por ítem):
    `procesar_correo(raw)` y `procesar_foto(img)` extraen {fecha,tipo,categoria,comercio,
    monto,medio} con su mejor apuesta de categoría y los acumulan en el BUFFER del día
    (Supabase) con ID_Único anti-duplicado. NO escriben a Sheets todavía.

(B) Digest nocturno: `armar_digest()` devuelve la lista del día pre-categorizada marcando
    las dudosas; `confirmar_digest(correcciones)` aplica los cambios y ESCRIBE a la hoja
    Transacciones. La UI (panel + "Aceptar todo" / tap por línea) vive en flows.py.

(C) Faro de deuda: `estado_deuda()` lee las celdas ya calculadas de 'Tarjetas y Deuda'
    (faro en el encabezado: deuda real B4, intereses muertos B5, % utilización B6, semáforo
    B7, total a pagar B8). La deuda real INCLUYE la línea de crédito. Es el FRENO: antes de
    cualquier compra en cuotas, Donna muestra el costo real de la deuda.

El saldo del mes y el presupuesto se leen del 'Dashboard' (la planilla los calcula sola).

Capa de datos canónica: el esquema de las hojas lo fija Donna_Canonico.xlsx. El aprendizaje
(perfil + inferencias) se persiste en Supabase vía `sembrar_espina()`, nunca en el Sheet.
"""
import base64
import json
import logging
import re
from datetime import datetime

from anthropic import AsyncAnthropic

from config import settings
from core import correo, memory, sheets

logger = logging.getLogger(__name__)
_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)

# ───────────────────────── Remitentes de gasto que Donna entiende ─────────────────────────
# Cada uno: dominios del remitente + medio de pago + pista para el extractor.
SENDERS = [
    {
        "nombre": "Banco de Chile",
        "dominios": ["bancochile.cl", "bancoedwards.cl"],
        "medio": "Banco de Chile",
        "hint": ("Banco de Chile avisa compras y cargos con tarjeta y transferencias. El asunto suele decir "
                 "'Realizaste una compra', 'Cargo en tu cuenta' o 'Comprobante de transferencia'. Saca el monto "
                 "en pesos, el comercio, la fecha y, si está, los 4 últimos dígitos de la tarjeta (a subcategoria)."),
    },
    {
        "nombre": "Mach",
        "dominios": ["machbank.cl", "mail.machbank.cl", "somosmach.com", "mach.cl"],
        "medio": "Mach",
        "hint": ("MachBank (BCI) manda 'Comprobante de compra/pago' con Comercio, Monto (pagado/CLP), "
                 "últimos 4 dígitos de la tarjeta y Fecha y hora. Compra = Gasto. Si el dinero ENTRA "
                 "(te transfirieron/abono) es Ingreso."),
    },
    {
        "nombre": "Copec Pay",
        "dominios": ["copec.cl", "copecpay.cl"],
        "medio": "Copec Pay",
        "hint": ("Copec Pay confirma cargas de combustible y compras en estaciones/tienda Copec. Suele ser "
                 "categoría Transporte/Combustible. Saca monto, estación o comercio, y fecha."),
    },
    {
        "nombre": "MercadoPago",
        "dominios": ["mercadopago.com", "mercadopago.cl", "mercadolibre.com"],
        "medio": "MercadoPago",
        "hint": ("MercadoPago avisa pagos y cobros: 'Pagaste $X', 'Compraste', 'Te enviaron dinero'. Si entra "
                 "plata es Ingreso. Ignora correos de promoción/marketing (esos no son transacción: monto 0)."),
    },
    {
        "nombre": "Itaú",
        "dominios": ["itau.cl"],
        "medio": "Transferencia recibida",
        "hint": ("Itaú avisa transferencias RECIBIDAS hacia las cuentas de Nico: 'nuestro cliente X ha instruido "
                 "una transferencia ... Titular Cuenta: Nico ... Monto: $'. Eso es INGRESO (te transfieren/te pagan)."),
    },
]
_DOMINIOS = [d for s in SENDERS for d in s["dominios"]]


def gmail_query_gastos() -> str:
    return "from:(" + " OR ".join(_DOMINIOS) + ")"


def _detectar_sender(remitente: str) -> dict | None:
    rem = (remitente or "").lower()
    for s in SENDERS:
        if any(d in rem for d in s["dominios"]):
            return s
    return None

HOJA_TX = "Transacciones"
HOJA_CAT = "Categorias"
HOJA_DASH = "Dashboard"
HOJA_TARJETAS = "Tarjetas y Deuda"

# Celdas fijas del faro (la planilla las calcula; Donna solo las lee). Layout canónico
# de 'Tarjetas y Deuda' (Donna_Canonico.xlsx): el faro vive en el encabezado (A3 "🔦 FARO
# DE DEUDA"). La deuda real INCLUYE la línea (B4 = tarjetas BCh + Mach + línea).
CELDA_DEUDA_REAL = "B4"         # =B29+B40+B44 → tarjetas + línea ($2.028.091)
CELDA_INTERESES_MUERTOS = "B5"  # =B25+B37+B45 → interés rotativo + línea: plata que no baja deuda ($48.236)
CELDA_UTILIZACION = "B6"        # deuda total ÷ cupo total (fracción; se pasa a %)
CELDA_SEMAFORO = "B7"           # 🔴 Alto / 🟡 Medio / 🟢 OK
CELDA_TOTAL_PAGAR = "B8"        # =B27+B38+B45 → cuotas + rotativo + mantención + línea

# Celdas del Dashboard canónico (saldo del mes corriendo; la planilla los calcula).
CELDA_INGRESOS = "B4"
CELDA_GASTOS = "B5"
CELDA_BALANCE = "B6"
CELDA_LLEGO_FIN_MES = "B8"      # texto: "Te sobran $…" / "Negativo por $…"


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


def _num(v) -> float:
    if isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)  # lectura sin formato: ya es número, no lo toques
    try:
        # String con formato chileno ("$2.028.091" / "1.500,50"): punto = miles, coma = decimal.
        return float(str(v).replace("$", "").replace(".", "").replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


def clp(v) -> str:
    """Pesos chilenos como los lee Nico: separador de miles con punto. 2028091 → '$2.028.091'."""
    return "$" + f"{int(round(_num(v))):,.0f}".replace(",", ".")


def _id_unico(fecha: str, monto, comercio: str) -> str:
    return f"{fecha}_{int(_num(monto))}_{(comercio or '')[:20].strip()}"


# ───────────────────────── (A) Registro pasivo → buffer (contexto aislado) ─────────────────────────

EXTRACTOR_SYSTEM = (
    "Extraes datos de boletas, transferencias y avisos de transacción chilenos (Banco de Chile, "
    "Mach, MercadoPago). Devuelve SOLO un JSON, sin texto extra, con estos campos: "
    "tipo ('Gasto' o 'Ingreso'), monto (número entero en pesos, sin separadores), "
    "categoria (tu mejor apuesta), subcategoria, comercio, medio (Banco de Chile/Mach/MP/débito/crédito/transferencia), "
    "dudosa (true si NO estás seguro de la categoría), motivo_duda (si dudosa: la pregunta corta, ej '¿Tecnología o Suscripción?'). "
    "Si no logras leer un monto, devuelve monto 0."
)


def _parse_json(texto: str) -> dict:
    t = texto.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(t)


def _aplicar_reglas_comercio(comercio: str, categoria: str, reglas: list[dict] | None) -> tuple[str, str]:
    """Si el comercio crudo del banco calza con una regla aprendida, lo renombra a su nombre
    amigable y aplica su categoría (ej. 'MERCADOPAGO*SANVA' → 'negocio San Vale' / Alimentación)."""
    c = (comercio or "").lower()
    for r in reglas or []:
        patron = (r.get("patron") or "").lower()
        if patron and patron in c:
            return (r.get("nombre") or comercio), (r.get("categoria") or categoria)
    return comercio, categoria


async def _bufferizar(datos: dict, fuente: str, reglas: list[dict] | None = None) -> dict | None:
    """Normaliza la extracción y la mete al buffer del día. Aplica las reglas de comercio
    aprendidas (nombre amigable + categoría). Devuelve el dict guardado o None."""
    monto = datos.get("monto", 0)
    if _num(monto) <= 0:
        return None
    fecha = datos.get("fecha") or _hoy()
    comercio_raw = datos.get("comercio", "")
    if reglas is None:
        try:
            reglas = await memory.get_comercios()
        except Exception:
            reglas = []
    comercio, categoria = _aplicar_reglas_comercio(comercio_raw, datos.get("categoria", "Otros"), reglas)
    tx = {
        "fecha": fecha,
        "tipo": "Ingreso" if str(datos.get("tipo", "")).lower().startswith("ing") else "Gasto",
        "categoria": categoria,
        "subcategoria": datos.get("subcategoria", ""),
        "comercio": comercio,
        "monto": int(_num(monto)),
        "medio": datos.get("medio", ""),
        "fuente": fuente,
        "id_unico": _id_unico(fecha, monto, comercio_raw),  # id sobre el comercio CRUDO → estable ante reglas nuevas
        "dudosa": bool(datos.get("dudosa", False)),
        "motivo_duda": datos.get("motivo_duda", ""),
    }
    nuevo = await memory.buffer_agregar(tx)
    return tx if nuevo else None


# ───────────────────── Parsers deterministas por banco (sin LLM) ─────────────────────
# Contrato de costos: lo determinista va PRIMERO. Regex exacto para los formatos conocidos
# de Banco de Chile y MachBank → cero tokens. El LLM queda solo para el residuo (formato
# desconocido). Construidos sobre correos reales de Nico.

_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
          "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}

# Mejor apuesta de categoría sin LLM (Nico corrige en el digest si hace falta).
_CATEGORIAS_KW = [
    ("Alimentación",  ["isabel", "jumbo", "lider", "unimarc", "tottus", "acuenta", "mayorista", "minimarket", "supermerc"]),
    ("Chanchería",    ["uber eats", "rappi", "pedidosya", "mcdonald", "doggis", "burger", "kfc", "sushi", "pizza"]),
    ("Transporte",    ["uber", "cabify", "didi", "copec", "shell", "petrobras", "combustible"]),
    ("Suscripciones", ["netflix", "spotify", "disney", "hbo", "prime", "youtube", "icloud", "google one", "openai", "claude"]),
    ("Salud",         ["farmacia", "cruz verde", "salcobrand", "ahumada", "clinica", "consulta"]),
    ("Hogar",         ["sodimac", "easy", "construmart", "homecenter"]),
]


def _categoria_de(comercio: str) -> str:
    c = (comercio or "").lower()
    for cat, kws in _CATEGORIAS_KW:
        if any(k in c for k in kws):
            return cat
    return "Otros"


def _fecha_iso(s: str) -> str:
    s = (s or "").strip()
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)          # 20/06/2026 o 18-06-2026
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", s.lower())  # 20 de junio de 2026
    if m and m.group(2) in _MESES:
        return f"{m.group(3)}-{_MESES[m.group(2)]:02d}-{int(m.group(1)):02d}"
    return _hoy()


def _rut_norm(r: str) -> str:
    return re.sub(r"[.\-\s]", "", str(r or "")).lower()


TIPO_CAMBIO_USD = 1000  # estimación CLP/US$ (el correo solo trae US$); la compra se marca dudosa para confirmar.


def _parse_bch_cargo(texto: str) -> dict | None:
    """BCh compra/cargo. Cubre 'con cargo a Cuenta ****5502' (débito) y 'con Tarjeta de Crédito
    ****9371' (crédito), en pesos ('$12.520') o dólares ('US$10,00')."""
    m = re.search(
        r"(?:compra|cargo|pago|giro)\s+por\s+(US)?\$\s*([\d.,]+)\s+con\s+"
        r"(?:cargo a Cuenta|Tarjeta de Cr[ée]dito|Tarjeta de D[ée]bito)\s+\*+(\d{4})\s+en\s+(.+?)\s+el\s+(\d{2}/\d{2}/\d{4})",
        texto, re.IGNORECASE)
    if not m:
        return None
    es_usd = bool(m.group(1))
    valor = _num(m.group(2))
    comercio = m.group(4).strip()
    tx = {
        "tipo": "Gasto", "categoria": _categoria_de(comercio), "subcategoria": f"****{m.group(3)}",
        "comercio": comercio, "medio": "Banco de Chile", "fecha": _fecha_iso(m.group(5)),
        "dudosa": False, "motivo_duda": "",
    }
    if es_usd:  # el cargo real en pesos no viene en el correo → estimo y marco para confirmar.
        tx["monto"] = int(round(valor * TIPO_CAMBIO_USD))
        tx["medio"] = "Banco de Chile crédito (USD)"
        tx["dudosa"] = True
        tx["motivo_duda"] = f"Compra en US${m.group(2)} — confirma el monto en pesos"
    else:
        tx["monto"] = int(valor)
    return tx


def _parse_itau_recibida(texto: str) -> dict | None:
    """Itaú avisa transferencias RECIBIDAS: 'nuestro cliente X ha instruido una transferencia ...
    Titular Cuenta: Nico ... Monto: $150.000' → Ingreso (te transfieren / te pagan)."""
    if "instruido una transferencia" not in texto.lower():
        return None
    mm = re.search(r"Monto:?\s*\$\s*([\d.]+)", texto)
    if not mm:
        return None
    origen = re.search(r"cliente\s+(.+?)\s*,?\s+ha instruido", texto, re.IGNORECASE)
    coment = re.search(r"coment[ao]rio:\s*(.+?)(?:\s+Importante|\s+Itau|$)", texto, re.IGNORECASE)
    fecha = re.search(r"con fecha\s+(\d{2}/\d{2}/\d{4})", texto)
    return {
        "tipo": "Ingreso", "monto": int(_num(mm.group(1))), "categoria": "Ingreso",
        "subcategoria": (coment.group(1).strip()[:40] if coment else ""),
        "comercio": (origen.group(1).strip() if origen else "Transferencia recibida"),
        "medio": "Transferencia recibida (Itaú)", "fecha": _fecha_iso(fecha.group(1)) if fecha else _hoy(),
    }


def _parse_bch_transferencia(texto: str, dueno_rut: str) -> dict | None:
    """BCh transferencia saliente. Si el RUT del destino es el de Nico → movimiento interno."""
    mm = re.search(r"Monto\s+\$\s*([\d.]+)", texto)
    if not mm:
        return None
    monto = int(_num(mm.group(1)))
    mname = re.search(r"Destino\s+Nombre y Apellido\s+(.+?)\s+Rut", texto)
    mrut = re.search(r"Rut\s+([\d.]+-?[\dkK])", texto)
    nombre = mname.group(1).strip() if mname else ""
    rut_dest = mrut.group(1) if mrut else ""
    mfh = re.search(r"Fecha y Hora:\s*(.+?)\s+Transacci", texto)
    fecha = _fecha_iso(mfh.group(1)) if mfh else _hoy()
    if dueno_rut and rut_dest and _rut_norm(rut_dest) == _rut_norm(dueno_rut):
        return {"_interno": True, "comercio": nombre, "monto": monto}  # entre tus cuentas
    return {
        "tipo": "Gasto", "monto": monto, "categoria": "Transferencia",
        "subcategoria": f"Rut {rut_dest}" if rut_dest else "",
        "comercio": nombre or "Transferencia a terceros",
        "medio": "Banco de Chile transferencia", "fecha": fecha,
    }


def _parse_mach_compra(texto: str) -> dict | None:
    """MachBank compra (crédito o débito): 'Comercio X Monto pagado/CLP $Y ... Fecha y hora ...'."""
    mc = re.search(r"Comercio\s+(.+?)\s+Monto", texto)
    mm = re.search(r"Monto pagado\s+\$\s*([\d.]+)", texto) or re.search(r"Monto CLP\s+\$\s*([\d.]+)", texto)
    if not (mc and mm):
        return None
    m4 = re.search(r"[Úu]ltimos 4 d[íi]gitos de la tarjeta\s+(\d{4})", texto)
    mfh = re.search(r"Fecha y hora\s+(\d{2}[/-]\d{2}[/-]\d{4})", texto)
    comercio = mc.group(1).strip()
    medio = "Mach crédito" if re.search(r"Cr[ée]dito", texto) else "Mach débito"
    return {
        "tipo": "Gasto", "monto": int(_num(mm.group(1))),
        "categoria": _categoria_de(comercio), "subcategoria": f"****{m4.group(1)}" if m4 else "",
        "comercio": comercio, "medio": medio, "fecha": _fecha_iso(mfh.group(1)) if mfh else _hoy(),
    }


def _parsear_determinista(remitente: str, asunto: str, texto: str, dueno_rut: str = "") -> dict | None:
    """Intenta extraer SIN LLM. Devuelve el dict de la transacción, o {'_interno': True} si es
    transferencia entre cuentas propias (se ignora), o None si no reconoce el formato (→ LLM)."""
    sender = _detectar_sender(remitente)
    if not sender:
        return None
    if sender["nombre"] == "Banco de Chile":
        if "transferencia" in (asunto + " " + texto[:200]).lower():
            return _parse_bch_transferencia(texto, dueno_rut)
        return _parse_bch_cargo(texto)
    if sender["nombre"] == "Mach":
        return _parse_mach_compra(texto)
    if sender["nombre"] == "Itaú":
        return _parse_itau_recibida(texto)
    return None  # Copec / MercadoPago / desconocido → LLM


async def procesar_foto(image_bytes: bytes, media_type: str = "image/jpeg") -> dict | None:
    """Vision AISLADA sobre una boleta → buffer del día. Degrada a None si falla."""
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    try:
        r = await _anthropic.messages.create(
            model=settings.model_cheap,
            max_tokens=300,
            system=EXTRACTOR_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": "Extrae los datos de este comprobante."},
                ],
            }],
        )
        return await _bufferizar(_parse_json(r.content[0].text), "foto")
    except Exception:
        logger.exception("procesar_foto falló")
        return None


async def procesar_correo(raw: str, remitente: str = "", asunto: str = "", dueno_rut: str = "",
                          reglas: list[dict] | None = None) -> dict | None:
    """Parseo AISLADO de un correo de gasto → buffer del día. PRIMERO intenta el parser
    determinista del banco (regex, cero tokens); solo si no reconoce el formato cae al LLM.
    Las transferencias entre cuentas propias de Nico (mismo RUT) se ignoran (no son gasto)."""
    det = _parsear_determinista(remitente, asunto, raw, dueno_rut)
    if det is not None:
        if det.get("_interno"):
            logger.info("Transferencia interna detectada (no es gasto): %s $%s",
                        det.get("comercio", ""), det.get("monto", 0))
            return None
        return await _bufferizar(det, "correo", reglas)
    # Residuo: formato no reconocido → LLM (con la pista del remitente).
    sender = _detectar_sender(remitente)
    system = EXTRACTOR_SYSTEM + (f"\n\nContexto del remitente ({sender['nombre']}): {sender['hint']}" if sender else "")
    contenido = (f"Remitente: {remitente}\nAsunto: {asunto}\n\n{raw}").strip()
    try:
        r = await _anthropic.messages.create(
            model=settings.model_cheap,
            max_tokens=300,
            system=system,
            messages=[{"role": "user", "content": f"Extrae la transacción de este correo:\n\n{contenido}"}],
        )
        datos = _parse_json(r.content[0].text)
        if sender and not str(datos.get("medio", "")).strip():
            datos["medio"] = sender["medio"]  # el medio de pago sale del remitente
        return await _bufferizar(datos, "correo", reglas)
    except Exception:
        logger.exception("procesar_correo falló")
        return None


async def ingerir_gastos_email(max_n: int = 25) -> dict:
    """Trae los correos de gasto recientes (Gmail + Outlook), saltando los ya vistos,
    los parsea en contexto aislado y los deja en el buffer del día. Devuelve {revisados, nuevos}."""
    if not correo.disponible():
        return {"revisados": 0, "nuevos": 0}
    try:
        msgs = await correo.obtener_gastos(gmail_query_gastos(), max_n)
    except Exception:
        logger.exception("ingerir_gastos_email: no pude leer los correos")
        return {"revisados": 0, "nuevos": 0}
    dueno_rut = ""
    try:
        dueno_rut = (await memory.get_perfil()).get("rut", "")
    except Exception:
        logger.exception("ingerir_gastos_email: no pude leer el RUT del perfil")
    try:
        reglas = await memory.get_comercios()  # cargadas UNA vez para todo el lote
    except Exception:
        logger.exception("ingerir_gastos_email: no pude leer las reglas de comercios")
        reglas = []
    nuevos = 0
    for m in msgs:
        try:
            if await memory.correo_visto(m["proveedor"], m["id"]):
                continue
            datos = await procesar_correo(m["texto"], m.get("remitente", ""), m.get("asunto", ""), dueno_rut, reglas)
            await memory.marcar_correo_visto(m["proveedor"], m["id"], "gasto")
            if datos:
                nuevos += 1
        except Exception:
            logger.exception("ingerir_gastos_email: falló un correo")
    if nuevos:
        logger.info("Correos de gasto ingeridos al buffer: %d nuevos de %d revisados.", nuevos, len(msgs))
    return {"revisados": len(msgs), "nuevos": nuevos}


# ───────────────────────── (B) Digest nocturno ─────────────────────────

async def armar_digest(fecha: str | None = None) -> dict:
    """Lista de movimientos por confirmar. Por defecto muestra TODOS los pendientes (no solo
    los de hoy): cada gasto trae su fecha REAL de compra, que puede ser de días pasados, y
    igual hay que confirmarlos. Devuelve:
    {movimientos: [{id, tipo, categoria, comercio, monto, medio, dudosa, motivo_duda}],
     total: int, n: int, n_dudosas: int}."""
    try:
        pendientes = await memory.buffer_pendientes(fecha)  # fecha=None → todos los pendientes
    except Exception:
        logger.exception("armar_digest: no pude leer el buffer")
        return {"movimientos": [], "total": 0, "n": 0, "n_dudosas": 0}
    movimientos = [{
        "id": p["id"],
        "tipo": p.get("tipo", "Gasto"),
        "categoria": p.get("categoria", "Otros"),
        "comercio": p.get("comercio", ""),
        "monto": int(_num(p.get("monto"))),
        "medio": p.get("medio", ""),
        "dudosa": bool(p.get("dudosa")),
        "motivo_duda": p.get("motivo_duda", ""),
    } for p in pendientes]
    total = sum(m["monto"] for m in movimientos if m["tipo"] == "Gasto")
    return {
        "movimientos": movimientos,
        "total": total,
        "n": len(movimientos),
        "n_dudosas": sum(1 for m in movimientos if m["dudosa"]),
    }


def _norm_hdr(s) -> str:
    return str(s).strip().lower().replace("ú", "u").replace("í", "i")


async def _ids_transacciones() -> set[str]:
    """ID_Único ya escritos en Transacciones (anti-duplicado a nivel planilla). Degrada
    a set vacío si no puede leer: en el peor caso confía en el UNIQUE del buffer.

    La hoja canónica trae un banner en la fila 1 y los headers en la 2, y la columna
    se llama 'ID_Único' (con tilde). Por eso ubicamos la columna por su header en vez de
    asumir que está en la fila 1."""
    try:
        filas = await sheets.get_rows(HOJA_TX, "A:I", sheet_id=sheets.fin_id())
    except Exception:
        logger.exception("_ids_transacciones: no pude leer Transacciones")
        return set()
    col = fila_hdr = None
    for i, fila in enumerate(filas):
        for j, celda in enumerate(fila):
            if _norm_hdr(celda) == "id_unico":
                col, fila_hdr = j, i
                break
        if col is not None:
            break
    if col is None:
        return set()
    return {str(f[col]).strip() for f in filas[fila_hdr + 1:] if len(f) > col and str(f[col]).strip()}


def _planificar_digest(pendientes: list[dict], correcciones: dict, ya_en_planilla: set[str]) -> dict:
    """Decide qué hacer con cada pendiente SIN tocar red (puro → testeable): escribir,
    descartar, o saltar por duplicado. Anti-duplicado contra la planilla Y entre líneas
    del mismo digest (un id_unico repetido se escribe una sola vez)."""
    a_escribir, a_descartar, duplicadas = [], [], []
    seen = set(ya_en_planilla)
    for p in pendientes:
        corr = correcciones.get(p["id"], {})
        if corr.get("descartar"):
            a_descartar.append(p)
            continue
        idu = str(p.get("id_unico", "")).strip()
        if idu and idu in seen:
            duplicadas.append(p)
            continue
        if idu:
            seen.add(idu)
        a_escribir.append({
            "p": p,
            "categoria": corr.get("categoria", p.get("categoria", "Otros")),
            "monto": corr.get("monto", p.get("monto", 0)),
        })
    return {"a_escribir": a_escribir, "a_descartar": a_descartar, "duplicadas": duplicadas}


async def confirmar_digest(correcciones: dict | None = None) -> dict:
    """Aplica correcciones (por id de buffer: {categoria, monto, descartar}) y ESCRIBE las
    confirmadas a Transacciones. Anti-duplicado en DOS niveles: el UNIQUE del buffer (ingreso)
    y el ID_Único ya presente en la planilla (acá). Devuelve {escritas, descartadas, duplicadas}."""
    correcciones = correcciones or {}
    pendientes = await memory.buffer_pendientes()  # TODOS los pendientes (cada uno con su fecha real)
    ya_en_planilla = await _ids_transacciones()
    plan = _planificar_digest(pendientes, correcciones, ya_en_planilla)
    for p in plan["a_descartar"]:
        await memory.buffer_marcar(p["id"], "descartada")
    for p in plan["duplicadas"]:
        # Ya está en la planilla: sale del buffer sin escribir otra fila (no duplica).
        await memory.buffer_marcar(p["id"], "confirmada")
    escritas = 0
    for item in plan["a_escribir"]:
        p = item["p"]
        try:
            await sheets.append_row(HOJA_TX, [
                p.get("fecha") or _hoy(), p.get("tipo", "Gasto"), item["categoria"],
                p.get("subcategoria", ""), p.get("comercio", ""), int(_num(item["monto"])),
                p.get("medio", ""), p.get("fuente", ""), p.get("id_unico", ""),
            ], sheet_id=sheets.fin_id())
            await memory.buffer_marcar(p["id"], "confirmada")
            escritas += 1
        except Exception:
            logger.exception("confirmar_digest: no pude escribir una transacción")
    return {"escritas": escritas, "descartadas": len(plan["a_descartar"]), "duplicadas": len(plan["duplicadas"])}


# ───────────────────────── (C) Faro de deuda (el freno) ─────────────────────────

async def estado_deuda() -> dict:
    """Lee el faro (B4:B8 de 'Tarjetas y Deuda') en UN solo request — más robusto que 5
    lecturas sueltas (la API de Sheets falla a veces una celda aislada) y más barato.
    Orden del bloque: B4 deuda real · B5 intereses muertos · B6 utilización · B7 semáforo ·
    B8 total a pagar. Degrada a ceros si el bloque entero no se puede leer."""
    try:
        filas = await sheets.get_rows(HOJA_TARJETAS, "B4:B8", sheet_id=sheets.fin_id(), value_render="UNFORMATTED_VALUE")
    except Exception:
        logger.exception("estado_deuda: no pude leer el faro")
        filas = []
    vals = [(f[0] if f else "") for f in filas] + [""] * 5  # rellena celdas vacías/faltantes
    deuda = _num(vals[0])
    intereses = _num(vals[1])
    util = _num(vals[2])
    if 0 < util <= 1:  # por si viene como fracción (0.79) en vez de 79
        util *= 100
    semaforo = str(vals[3]).strip() or ("🔴" if util > 70 else "🟡" if util > 30 else "🟢")
    total_pagar = _num(vals[4])
    return {
        "deuda_total_real": deuda,
        "intereses_muertos": intereses,
        "utilizacion": util,
        "semaforo": semaforo,
        "total_a_pagar": total_pagar,
    }


def formatear_deuda(d: dict) -> str:
    return (
        f"Deuda real {clp(d['deuda_total_real'])}. De este mes, {clp(d['intereses_muertos'])} "
        f"son solo interés — plata que pagas y no baja ni un peso de la deuda. "
        f"Utilización {d['utilizacion']:.0f}% {d['semaforo']}. Total a pagar {clp(d['total_a_pagar'])}."
    )


# ───────────────────────── Saldo del mes / presupuesto (lectura del Dashboard) ─────────────────────────

async def saldo_mes() -> dict:
    """Lee el saldo del mes del Dashboard (B4:B8) en UN request. Orden del bloque:
    B4 ingresos · B5 gastos · B6 balance · B7 tasa ahorro (se ignora) · B8 ¿llego a fin
    de mes? (texto). Degrada a ceros si no se puede leer."""
    try:
        filas = await sheets.get_rows(HOJA_DASH, "B4:B8", sheet_id=sheets.fin_id(), value_render="UNFORMATTED_VALUE")
    except Exception:
        logger.exception("saldo_mes: no pude leer el Dashboard")
        filas = []
    vals = [(f[0] if f else "") for f in filas] + [""] * 5
    return {
        "ingresos": _num(vals[0]),
        "gastos": _num(vals[1]),
        "balance": _num(vals[2]),
        "llego_fin_mes": str(vals[4]).strip(),
    }


# ───────────────────────── La espina (escribe a Supabase) ─────────────────────────

async def sembrar_espina() -> dict:
    """Espina del Módulo 1 (nace mínima): siembra en `perfil` los hechos de plata que ya
    sabemos (deuda real, intereses muertos, utilización) y, SOLO si el dato lo sostiene,
    deja UNA inferencia validada de deuda — siempre con su dato, idempotente (no la repite
    ni insiste con lo descartado). Capa de datos: el aprendizaje va a Supabase, nunca al Sheet.
    Degrada elegante: si el faro o Supabase fallan, no rompe el cierre. Sin correlación aún."""
    sembrado = {"perfil": 0, "inferencias": 0}
    try:
        d = await estado_deuda()
    except Exception:
        logger.exception("sembrar_espina: no pude leer el faro")
        return sembrado
    if d["deuda_total_real"] <= 0:
        return sembrado  # sin dato real, Donna no afirma nada
    try:
        await memory.set_perfil("deuda_total_real", clp(d["deuda_total_real"]), "finanzas")
        await memory.set_perfil("intereses_muertos_mes", f"{clp(d['intereses_muertos'])}/mes", "finanzas")
        await memory.set_perfil("utilizacion_tarjetas", f"{d['utilizacion']:.0f}% {d['semaforo']}", "finanzas")
        sembrado["perfil"] = 3
    except Exception:
        logger.exception("sembrar_espina: no pude sembrar el perfil de plata")
    # Inferencia validada (con su dato), solo cuando la deuda aprieta de verdad.
    if d["intereses_muertos"] > 0 and d["utilizacion"] >= 70:
        contenido = (
            f"Estás operando muy cerca del tope del cupo (utilización {d['utilizacion']:.0f}%), y por eso "
            f"se te van {clp(d['intereses_muertos'])} al mes solo en intereses — plata que no baja la deuda."
        )
        try:
            if await memory.crear_inferencia_si_nueva(contenido, "finanzas"):
                sembrado["inferencias"] = 1
        except Exception:
            logger.exception("sembrar_espina: no pude crear la inferencia de deuda")
    return sembrado


# ───────────────────────── Handlers de tools ─────────────────────────

async def _t_registrar_gasto(inp: dict) -> str:
    """Ad-hoc por chat: 'gasté X'. Va al BUFFER del día (no a Sheets); se confirma en el cierre."""
    monto = _num(inp.get("monto", 0))
    if monto <= 0:
        return "¿Cuánto fue? Pásame el monto y lo dejo listo para el cierre."
    tipo = "Ingreso" if str(inp.get("tipo", "")).lower().startswith("ing") else "Gasto"
    fecha = _hoy()
    comercio = inp.get("comercio", "")
    tx = {
        "fecha": fecha, "tipo": tipo, "categoria": inp.get("categoria", "Otros"),
        "comercio": comercio, "monto": int(monto), "medio": inp.get("medio", ""),
        "fuente": "manual", "id_unico": _id_unico(fecha, monto, comercio),
    }
    try:
        nuevo = await memory.buffer_agregar(tx)
        verbo = "Ingreso" if tipo == "Ingreso" else "Gasto"
        if not nuevo:
            return f"Ese {verbo.lower()} ya lo tenía anotado para hoy. No lo duplico."
        return f"{verbo} de {clp(monto)} anotado. Lo confirmas en el cierre de hoy junto al resto."
    except Exception:
        logger.exception("fin_registrar_gasto falló")
        return "No pude anotarlo ahora. Reintenta en un rato."


async def _t_saldo_mes(inp: dict) -> str:
    try:
        s = await saldo_mes()
        # Armo la cola con formato chileno propio (el texto del sheet trae coma US).
        cola = f"Te sobran {clp(s['balance'])}." if s["balance"] >= 0 else f"Vas negativo por {clp(-s['balance'])}."
        return f"Este mes: ingresos {clp(s['ingresos'])}, gastos {clp(s['gastos'])}, balance {clp(s['balance'])}. {cola}"
    except Exception:
        logger.exception("fin_saldo_mes falló")
        return "No pude leer el saldo del mes ahora."


async def _t_presupuesto(inp: dict) -> str:
    try:
        # Bloque "GASTO POR CATEGORÍA" del Dashboard canónico: A=Categoría, C=Gastado, D=% Usado.
        # Sin formato: gastado llega como número y % como fracción (0.15) → lo formateo yo.
        filas = await sheets.get_rows(HOJA_DASH, "A12:D29", sheet_id=sheets.fin_id(), value_render="UNFORMATTED_VALUE")
        lineas = []
        for f in filas:
            if not f or not str(f[0]).strip():
                continue
            cat = f[0]
            gastado = _num(f[2]) if len(f) > 2 else 0
            pct_raw = f[3] if len(f) > 3 else ""
            pct = f"{pct_raw * 100:.0f}%" if isinstance(pct_raw, (int, float)) else str(pct_raw)
            lineas.append(f"{cat}: {clp(gastado)} ({pct})")
        return "Presupuesto del mes:\n" + "\n".join(lineas) if lineas else "Aún no hay gastos contra presupuesto este mes."
    except Exception:
        logger.exception("fin_presupuesto falló")
        return "No pude leer el presupuesto ahora."


async def _t_estado_deuda(inp: dict) -> str:
    try:
        return formatear_deuda(await estado_deuda())
    except Exception:
        logger.exception("fin_estado_deuda falló")
        return "No pude leer el estado de la deuda ahora."


async def _t_armar_digest(inp: dict) -> str:
    d = await armar_digest()
    if d["n"] == 0:
        return "Hoy no detecté movimientos. El digest está limpio."
    lineas = [
        f"- {m['comercio'] or m['categoria']}: {clp(m['monto'])} → {m['categoria']}"
        + (f"  ⚠️ {m['motivo_duda']}" if m["dudosa"] else "")
        for m in d["movimientos"]
    ]
    return f"Tienes {d['n']} movimiento(s) por confirmar ({clp(d['total'])}):\n" + "\n".join(lineas)


# ───────────────────────── Señal destilada (brief) ─────────────────────────

async def senal_finanzas() -> str:
    """Conclusión corta para el brief: saldo corriendo + señal de deuda si aprieta."""
    partes = []
    try:
        s = await saldo_mes()
        if s["ingresos"] or s["gastos"]:
            partes.append(f"balance del mes {clp(s['balance'])}")
    except Exception:
        logger.exception("senal_finanzas: saldo falló")
    try:
        d = await estado_deuda()
        if d["intereses_muertos"] > 0:
            partes.append(f"intereses muertos {clp(d['intereses_muertos'])} {d['semaforo']}")
    except Exception:
        logger.exception("senal_finanzas: deuda falló")
    return "Plata: " + "; ".join(partes) + "." if partes else ""


# ───────────────────────── Registro de tools ─────────────────────────

TOOLS = [
    {
        "name": "fin_registrar_gasto",
        "description": (
            "OBLIGATORIO cuando Nico cuenta por chat que gastó o recibió plata ('gasté X', 'pagué X en Y', "
            "'me pagaron'). Lo anota en el BUFFER del día — NO se escribe a la planilla todavía: Nico lo "
            "confirma en el digest del cierre de las 22:00. Por defecto es Gasto; tipo='Ingreso' solo si la plata ENTRA."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["Gasto", "Ingreso"]},
                "monto": {"type": "number", "description": "Monto en pesos, sin separadores"},
                "categoria": {"type": "string"},
                "comercio": {"type": "string"},
                "medio": {"type": "string", "description": "Banco de Chile, Mach, MP, efectivo, débito, crédito, transferencia"},
            },
            "required": ["monto"],
        },
    },
    {
        "name": "fin_saldo_mes",
        "description": "OBLIGATORIO antes de hablar del saldo o balance del mes. Lee el Dashboard ya calculado (ingresos, gastos, balance, si llega a fin de mes). No inventes cifras.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fin_presupuesto",
        "description": "OBLIGATORIO cuando Nico pregunta cómo va respecto al presupuesto o si se está pasando en una categoría. Lee el bloque por categoría del Dashboard. No inventes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fin_estado_deuda",
        "description": (
            "OBLIGATORIO cuando Nico pregunta por su deuda/tarjetas/cupo, Y OBLIGATORIO antes de que se "
            "comprometa con cualquier compra EN CUOTAS (es el freno). Devuelve deuda real, intereses muertos "
            "del mes, % de utilización y total a pagar. No inventes montos."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fin_armar_digest",
        "description": "Muestra el digest del día (movimientos pendientes de confirmar) si Nico lo pide antes del cierre.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "fin_registrar_gasto": _t_registrar_gasto,
    "fin_saldo_mes": _t_saldo_mes,
    "fin_presupuesto": _t_presupuesto,
    "fin_estado_deuda": _t_estado_deuda,
    "fin_armar_digest": _t_armar_digest,
}
