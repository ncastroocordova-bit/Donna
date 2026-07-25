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
import time
import unicodedata
from datetime import datetime, timedelta

from anthropic import AsyncAnthropic

from config import settings
from core import correo, espera, memory, sheets

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
HOJA_METAS = "Metas"
HOJA_DETALLE = "Compras_Detalle"

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


# ── Montos dictados en palabras/slang (Nico dice "mil pesos", "3 lucas") ──
# El parser de _num solo lee dígitos; cuando Nico dicta el monto en palabras no quedaba nada
# registrado. Esto cubre los casos comunes chilenos sin LLM (contrato de costos).
_UNIDADES = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiuno": 21, "veintiun": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
}
_CIENTOS = {
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300, "cuatrocientos": 400,
    "quinientos": 500, "seiscientos": 600, "setecientos": 700, "ochocientos": 800, "novecientos": 900,
}
_SLANG = {"luca": 1000, "lucas": 1000, "palo": 1_000_000, "palos": 1_000_000,
          "gamba": 100, "gambas": 100, "quina": 500, "quinas": 500}


def _palabras_a_numero(texto: str) -> int | None:
    """Convierte un número dicho en palabras ('dos mil quinientos') a entero. Ignora el ruido
    alrededor. 'un/una/uno' cuentan como 1 solo si preceden a una escala/centena ('un millón');
    sueltos ('una compota') son artículo y se saltan. None si no hay ningún número."""
    tokens = [t for t in re.split(r"[\s\-]+", _norm(texto)) if t and t != "y"]
    total, actual, visto = 0, 0, False
    for i, t in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if t in ("un", "uno", "una"):
            if nxt in ("mil", "millon", "millones") or nxt in _CIENTOS:
                actual += 1; visto = True          # 'un millón' → número; 'una compota' → artículo (skip)
        elif t in _UNIDADES:
            actual += _UNIDADES[t]; visto = True
        elif t in _CIENTOS:
            actual += _CIENTOS[t]; visto = True
        elif t == "mil":
            actual = (actual or 1) * 1000; total += actual; actual = 0; visto = True
        elif t in ("millon", "millones"):
            actual = (actual or 1) * 1_000_000; total += actual; actual = 0; visto = True
        # el ruido (palabras no numéricas) se salta sin cortar: agarra el número aunque venga
        # rodeado de texto ('una compota que costó mil pesos' → 1000).
    return (total + actual) if visto else None


def _num_es(texto) -> int:
    """Monto en pesos desde texto libre: dígitos ('$1.290', '1290'), slang ('3 lucas', 'medio
    palo') o palabras ('mil quinientos'). 0 si no encuentra nada. Números ya numéricos pasan directo."""
    if isinstance(texto, bool):
        return 0
    if isinstance(texto, (int, float)):
        return int(texto)
    s = _norm(texto)
    m = re.search(r"(\d+(?:[.,]\d+)?|medio|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+"
                  r"(luca|lucas|palo|palos|gamba|gambas|quina|quinas)", s)
    if m:
        base, mult = m.group(1), _SLANG[m.group(2)]
        factor = 0.5 if base == "medio" else (_UNIDADES[base] if base in _UNIDADES else float(base.replace(",", ".")))
        return int(round(factor * mult))
    md = re.search(r"\$?\s*\d[\d.]*", s)   # dígitos con formato chileno de miles
    if md:
        return int(_num(md.group()))
    n = _palabras_a_numero(s)
    return int(n) if n else 0


# Gasto dictado sin monto legible: queda esperando a que Nico diga cuánto (patrón de estado
# de un solo usuario, igual que spam._PENDIENTE). Lo completa main.py con el próximo mensaje.
# Vive en un global de proceso (no en user_data) porque este tool se llama desde el loop de tools
# del cerebro, sin contexto de Telegram — sigue las mismas reglas que core.espera (cancelable,
# valida antes de aceptar, expira sola) aplicadas localmente al no poder reusar ese motor.
TTL_GASTO_INCOMPLETO = 15 * 60  # pasado esto, deja de insistir con un gasto que ya se enfrió

_gasto_incompleto: dict | None = None


def hay_gasto_incompleto() -> bool:
    global _gasto_incompleto
    if _gasto_incompleto is None:
        return False
    if time.time() - _gasto_incompleto.get("creado", 0) > TTL_GASTO_INCOMPLETO:
        _gasto_incompleto = None  # expiró: no lo pesco con el próximo número que aparezca
        return False
    return True


def limpiar_gasto_incompleto() -> None:
    global _gasto_incompleto
    _gasto_incompleto = None


# Filtro de "¿esto parece plata?" para no capturar cualquier dígito suelto de un mensaje que
# habla de otra cosa ('recuérdame pagar el agua el 15', 'dormí 7 horas', 'reunión a las 10').
_MONTO_FILLER = {
    "eran", "fueron", "fue", "costo", "costó", "salio", "salió", "como", "unos", "unas",
    "aprox", "aproximadamente", "pesos", "peso", "clp", "el", "la", "de", "en", "total",
    "monto", "y", "un", "una", "uno", "mil", "millon", "millones",
}
_MONTO_NO_KW = ("recuerda", "recuerdame", "avisa", "avisame", "agenda", "agendame", "record")


def parece_monto(texto: str) -> bool:
    """¿Esta respuesta parece EL MONTO que Donna preguntó, y no un mensaje sobre otra cosa que
    de casualidad trae un número? Exige que, sacando el número y el relleno normal ('eran',
    'pesos'...), no quede casi nada más — un mensaje sobre otra cosa deja palabras de contenido
    de sobra, y las frases con pinta de otra intención (recordatorio, agenda) se rechazan directo."""
    t = _norm(texto)
    if not t or "?" in texto:
        return False
    if any(kw in t for kw in _MONTO_NO_KW):
        return False
    if _num_es(texto) <= 0:
        return False
    palabras = [w for w in re.split(r"[\s,]+", t) if w]
    resto = [w for w in palabras
             if w not in _MONTO_FILLER and w not in _UNIDADES and w not in _CIENTOS and w not in _SLANG
             and not re.fullmatch(r"\$?\d[\d.,]*", w)]
    return len(resto) <= 1


async def completar_gasto_incompleto(texto: str) -> str | None:
    """Nico respondió con el monto del gasto que quedó pendiente ('eran 3 mil'). Lo registra en
    el buffer. 'cancelar'/'olvídalo' lo bota sin anotar nada. Devuelve None si el mensaje no
    parece el monto (no era la respuesta) → main.py limpia el estado y sigue normal."""
    global _gasto_incompleto
    if _gasto_incompleto is None:
        return None
    if espera.es_cancelacion(texto):
        _gasto_incompleto = None
        return "Ok, no anoto ese gasto."
    if not parece_monto(texto):
        return None  # no era el monto → main.py limpia y sigue normal
    monto = _num_es(texto)
    ctx, _gasto_incompleto = _gasto_incompleto, None
    fecha = _hoy()
    comercio = ctx.get("comercio", "")
    tx = {
        "fecha": fecha, "tipo": ctx.get("tipo", "Gasto"), "categoria": ctx.get("categoria", "Otros"),
        "comercio": comercio, "monto": int(monto), "medio": ctx.get("medio", ""),
        "fuente": "manual", "id_unico": _id_unico(fecha, monto, comercio),
        "intencion": ctx.get("intencion") or _intencion_de(ctx.get("categoria", "Otros")),
    }
    try:
        nuevo = await memory.buffer_agregar(tx)
    except Exception:
        logger.exception("completar_gasto_incompleto falló")
        return "Tengo el monto pero no pude anotarlo ahora. Reintenta en un rato."
    verbo = "Ingreso" if tx["tipo"] == "Ingreso" else "Gasto"
    if not nuevo:
        return f"Ese {verbo.lower()} ya lo tenía anotado para hoy. No lo duplico."
    donde = f" en {comercio}" if comercio else ""
    return f"{verbo} de {clp(monto)}{donde} anotado. Lo confirmas en el cierre de hoy."


# ───────────────────────── (A) Registro pasivo → buffer (contexto aislado) ─────────────────────────

EXTRACTOR_SYSTEM = (
    "Extraes datos de boletas, transferencias y avisos de transacción chilenos (Banco de Chile, "
    "Mach, MercadoPago). Devuelve SOLO un JSON, sin texto extra, con estos campos: "
    "tipo ('Gasto' o 'Ingreso'), monto (número entero en pesos, sin separadores), "
    "categoria (tu mejor apuesta), subcategoria, comercio, medio (Banco de Chile/Mach/MP/débito/crédito/transferencia), "
    "intencion ('Necesario' = indispensable como comida/transporte/cuentas/salud; 'Inversion' = algo que rinde "
    "como cursos/herramientas/publicidad o insumos de Ñoomi; 'Deseo' = gusto como comida rápida/ropa/entretención), "
    "dudosa (true si NO estás seguro de la categoría), motivo_duda (si dudosa: la pregunta corta, ej '¿Tecnología o Suscripción?'). "
    "Si no logras leer un monto, devuelve monto 0."
)

# Visión por ÍTEM (v3): cuando la boleta lista productos, queremos el detalle, no solo el total.
EXTRACTOR_ITEMS_SYSTEM = (
    "Lees boletas/facturas chilenas de compras (supermercado, almacén). Devuelve SOLO un JSON, sin "
    "texto extra, con: tipo ('Gasto'), comercio, fecha (YYYY-MM-DD si está), total (entero en pesos, "
    "sin separadores), medio si aparece, e items: una lista donde cada elemento es "
    "{item (nombre del producto), cantidad (entero, 1 si no dice), precio (entero en pesos del total "
    "de esa línea), categoria (tu mejor apuesta: Alimentación, Limpieza, Bebidas, Chanchería, etc.)}. "
    "Incluye TODAS las líneas de producto que puedas leer. La suma de los precios debe acercarse al "
    "total. Si la boleta NO lista productos (solo un monto), devuelve items: [] y el total. "
    "Si no logras leer el total, devuelve total 0."
)


def _parse_json(texto: str) -> dict:
    t = texto.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # El LLM a veces agrega texto antes/después del JSON → tomo el primer objeto válido.
        i = t.find("{")
        if i >= 0:
            obj, _ = json.JSONDecoder().raw_decode(t[i:])
            return obj
        raise


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
    comercio, categoria = _aplicar_reglas_comercio(comercio_raw, datos.get("categoria", "Otro Gasto"), reglas)
    # Validación C1: la categoría debe existir en la hoja Categorias. Si no, cae a 'Otro Gasto' y
    # se marca dudosa para que el digest la pregunte (nunca se escribe una categoría huérfana).
    cat_previa = categoria
    categoria, cat_valida = await _validar_categoria(categoria)
    es_dudosa = bool(datos.get("dudosa", False)) or not cat_valida
    motivo_duda = datos.get("motivo_duda", "")
    if not cat_valida and not motivo_duda:
        motivo_duda = f"'{cat_previa}' no está en tus categorías — ¿cuál va?"
    items_raw = datos.get("items") or None
    items = [_linea_detalle(l, comercio) for l in items_raw] if items_raw else None
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
        # Intención: si hay detalle, es el resumen de las líneas (Mixto si difieren); si no, la de la categoría.
        "intencion": _intencion_resumen(items) if items else (datos.get("intencion") or _intencion_de(categoria)),
        "items": items,                            # detalle ítem-a-ítem (v3) o None
        "dudosa": es_dudosa,
        "motivo_duda": motivo_duda,
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
    ("Alimentación",  ["isabel", "jumbo", "lider", "unimarc", "tottus", "acuenta", "mayorista", "minimarket", "supermerc", "san vale", "sanva", "agroconcepcio"]),
    ("Chanchería",    ["chancher", "uber eats", "rappi", "pedidosya", "mcdonald", "doggis", "burger", "kfc", "sushi", "pizza", "fiambre"]),
    ("Transporte",    ["uber", "cabify", "didi", "copec", "shell", "petrobras", "combustible"]),
    ("Tecnología",    ["anthropic", "github", "railway", "vercel", "supabase", "google cloud"]),
    ("Suscripciones", ["netflix", "spotify", "disney", "hbo", "prime", "youtube", "icloud", "google one", "openai", "claude"]),
    ("Salud",         ["farmacia", "cruz verde", "salcobrand", "ahumada", "clinica", "consulta"]),
    ("Hogar",         ["sodimac", "easy", "construmart", "homecenter", "super ganga"]),
]


def _categoria_de(comercio: str) -> str:
    c = (comercio or "").lower()
    for cat, kws in _CATEGORIAS_KW:
        if any(k in c for k in kws):
            return cat
    return "Otro Gasto"


# ───────────────── Validación de categoría contra la hoja Categorias (C1) ─────────────────
# Regla dura: toda categoría que se escriba debe existir en `Categorias`, o pasar por un toque
# de Nico en el digest (marcada dudosa). El mapeador determinista da la mejor apuesta; esto es
# la red de seguridad para que no entren categorías huérfanas ("Otros", "Supermercado", …).

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


# Grafías/sinónimos conocidos → categoría canónica real (decisión de Nico 2026-07-04).
_CAT_SINONIMOS = {
    "otros": "Otro Gasto", "supermercado": "Alimentación", "negocio": "Alimentación",
    "cosas casa": "Hogar", "software": "Tecnología",
    "transferencia a mi mismo": "Transferencias", "transferencias": "Transferencias",
}

_cache_categorias: dict | None = None  # {norm: nombre_canonico}


async def _categorias_reales() -> dict:
    """Lee la hoja Categorias una vez por proceso → {norm: nombre_canonico}. Degrada a {} si falla."""
    global _cache_categorias
    if _cache_categorias is not None:
        return _cache_categorias
    try:
        filas = await sheets.get_dicts(HOJA_CAT, sheet_id=sheets.fin_id())
        _cache_categorias = {
            _norm(f.get("Categoría", "")): str(f.get("Categoría", "")).strip()
            for f in filas if str(f.get("Categoría", "")).strip()
        }
    except Exception:
        logger.exception("_categorias_reales: no pude leer Categorias")
        _cache_categorias = {}
    return _cache_categorias


async def categorias_lista() -> list[str]:
    """El catálogo real de categorías, en el orden de la hoja `Categorias` (el orden de Nico).
    Es la fuente de los chips del digest: el callback lleva el ÍNDICE en esta lista (tope de
    64 bytes de callback_data; un nombre con tilde no cabe con el uuid al lado)."""
    return list((await _categorias_reales()).values())


async def sugerencias_categoria(comercio: str, actual: str = "") -> list[str]:
    """Top-3 de categorías para corregir una línea del digest, sin teclado. Prioridad:
    (1) lo APRENDIDO de este comercio (tabla `comercios`, por frecuencia — cada corrección de
    Nico la alimenta, así que esto acierta más con el uso), (2) el match por keywords,
    (3) el catálogo en su orden. **Excluye la categoría actual**: si Nico está corrigiendo,
    la actual es justo la equivocada."""
    todas = await categorias_lista()
    candidatas: list[str] = []
    c = _norm(comercio)
    if c:
        try:
            for r in await memory.get_comercios():
                patron = _norm(r.get("patron", ""))
                if patron and patron in c and r.get("categoria"):
                    candidatas.append(str(r["categoria"]).strip())
        except Exception:
            logger.exception("sugerencias_categoria: no pude leer comercios (sigo sin aprendidas)")
    candidatas.append(_categoria_de(comercio))
    candidatas += todas
    actual_n = _norm(actual)
    out: list[str] = []
    for cat in candidatas:
        canon = (await _validar_categoria(cat))[0] if cat else ""
        if canon and canon not in out and _norm(canon) != actual_n and canon in todas:
            out.append(canon)
        if len(out) == 3:
            break
    return out


async def _validar_categoria(cat: str) -> tuple[str, bool]:
    """(categoria_canonica, era_valida). Match exacto contra Categorias (sin tildes/mayúsculas),
    luego sinónimos conocidos; si no calza, cae a 'Otro Gasto' con era_valida=False → el digest
    lo pregunta. Degrada elegante: si no se pudo leer Categorias, no invalida (passthrough)."""
    reales = await _categorias_reales()
    if not reales:
        return (str(cat).strip() or "Otro Gasto"), True  # sin poder validar, no molestar
    n = _norm(cat)
    if not n:
        return "Otro Gasto", False
    if n in reales:
        return reales[n], True
    if n in _CAT_SINONIMOS:
        return _CAT_SINONIMOS[n], True  # mapeo conocido y confiable
    return "Otro Gasto", False  # desconocida → cajón + toque de Nico en el digest


# Intención del gasto (v2): por qué se gastó, no solo en qué. Mejor apuesta por categoría;
# Nico la confirma/corrige en el digest. Orden: Inversión gana, luego Deseo, luego Necesario.
_INTENCION_KW = [
    ("Inversion", ["curso", "herramienta", "publicidad", "marketing", "educac", "libro",
                   "software", "insumo", "capacit", "ñoomi", "noomi"]),
    ("Deseo",     ["chancher", "delivery", "uber eats", "rappi", "pedidosya", "restau",
                   "comida rapida", "ropa", "entreten", "suscrip", "juego", "bar", "cafe",
                   "cine", "antojo"]),
    ("Necesario", ["aliment", "supermerc", "transporte", "combustible", "bencina", "salud",
                   "farmacia", "hogar", "cuenta", "servicio", "luz", "agua", "gas",
                   "arriendo", "abarrote", "limpieza"]),
]


def _intencion_de(categoria: str) -> str:
    """Necesario (indispensable) / Inversión (rinde) / Deseo (gusto). Default conservador:
    Necesario. Es solo la mejor apuesta — se confirma en el digest."""
    c = (categoria or "").lower()
    for intencion, kws in _INTENCION_KW:
        if any(k in c for k in kws):
            return intencion
    return "Necesario"


# ───────────────────────── Vocabulario canónico de `Medio` (2026-07-24) ─────────────────────────
# Antes cada parser escribía su propia etiqueta y la hoja terminó con OCHO valores que mezclaban
# tres ejes: banco ('Banco de Chile'), producto ('Tarjeta crédito' — sin decir de qué banco) y
# operación ('Mach' a secas eran las transferencias). Con ese vocabulario era imposible cortar el
# gasto por medio de pago: 'Banco de Chile' x18 no distinguía débito de crédito, y el único dato
# que lo desambiguaba (el nº de tarjeta) vivía en `Detalle_Medio`, una columna que nadie leía.
#
# Ahora hay UN eje —de qué cuenta salió la plata— y la normalización corre en UN solo lugar (al
# escribir a la planilla), no repartida entre los seis parsers. Así un parser nuevo no puede
# reintroducir un valor suelto: pase lo que pase, a la hoja llega uno de estos seis.
MEDIOS_CANON = ("Mach débito", "Mach crédito", "BCh débito", "BCh crédito", "Transferencia", "Otro")

# Los 4 últimos dígitos → la cuenta exacta. Es la señal MÁS confiable que existe: el banco los
# manda en cada correo de compra, y a diferencia del texto del medio no dependen de que el parser
# de turno se acuerde de anotar el producto. Sembrado desde las transacciones reales (2026-07-24).
# Para agregar una tarjeta nueva basta una línea acá; lo que no esté mapeado NO se adivina.
MEDIO_POR_TARJETA = {
    "5502": "BCh débito",     # cuenta corriente BCh ("con cargo a Cuenta ****5502")
    "9371": "BCh crédito",    # tarjeta de crédito BCh (la de las compras en USD)
    "1969": "Mach débito",
    "6867": "Mach débito",
    "7160": "Mach crédito",
    "4846": "Mach crédito",
}


def normalizar_medio(medio: str, detalle: str = "") -> str:
    """Cualquier etiqueta de medio de pago → el vocabulario canónico. `detalle` es el antiguo
    `subcategoria` (nº de tarjeta o glosa): sigue llegando en el dict de la transacción aunque ya
    no se escriba a la planilla, y es lo que desambigua los casos que el medio solo no resuelve
    (ej. medio='Mach' + detalle='Transferencia a terceros' → Transferencia, no Mach débito).

    El orden de los chequeos importa por dos razones:
      1. 'Banco de Chile transferencia' calza con banco Y con transferencia — manda la operación,
         porque la plata sale de la cuenta corriente igual.
      2. El nº de tarjeta manda sobre el texto: el texto depende de que el parser se acordara de
         anotar el producto, el número no.

    **No adivina.** Si sabe el banco pero no el producto (ej. 'Banco de Chile' pelado, sin nº de
    tarjeta), devuelve 'Otro' en vez de asumir débito. Esa suposición callada es exactamente lo que
    dejó 11 filas etiquetadas mal en junio: eran una mezcla de BCh y Mach, crédito las dos, y
    nadie se enteró hasta la auditoría de columnas. Un 'Otro' en la planilla es una pregunta
    visible; un 'BCh débito' inventado es una respuesta falsa."""
    blob = _norm(f"{medio} {detalle}")
    if not blob.strip():
        return "Otro"
    if "transferencia" in blob or "traspaso" in blob:
        return "Transferencia"
    tarjeta = re.search(r"\*{2,}\s*(\d{4})|\b(\d{4})\s*$", str(detalle or "").strip())
    if tarjeta:
        mapeado = MEDIO_POR_TARJETA.get(tarjeta.group(1) or tarjeta.group(2))
        if mapeado:
            return mapeado
    if "credito" in blob:
        if "mach" in blob:
            return "Mach crédito"
        if "banco de chile" in blob or "bch" in blob or "edwards" in blob:
            return "BCh crédito"
    if "debito" in blob or "cuenta corriente" in blob or "cargo a cuenta" in blob:
        if "mach" in blob:
            return "Mach débito"
        if "banco de chile" in blob or "bch" in blob or "edwards" in blob:
            return "BCh débito"
    logger.warning("normalizar_medio: no pude resolver el producto de medio=%r detalle=%r → 'Otro'",
                   medio, detalle)
    return "Otro"


def _progreso(actual, objetivo) -> int | None:
    """% de avance de una meta (0-100, con tope). None si el objetivo no es positivo."""
    o = _num(objetivo)
    if o <= 0:
        return None
    return max(0, min(100, round(_num(actual) / o * 100)))


# ───────────────────────── (v3) Detalle de compra: predecible, desglose, correlación ─────────────────────────

# Predecible = despensa/reposición (entra al futuro predictor de Compras Fase 2). Lo cotidiano
# y perecible queda fuera POR DISEÑO (no molestar con reposición espuria). NO gana al PREDECIBLE.
_NO_PREDECIBLE_KW = ["pan", "marraqueta", "hallulla", "dobladita", "chancher", "fiambre", "verdura",
                     "fruta", "palta", "tomate", "lechuga", "platano", "plátano", "comida preparada",
                     "almuerzo", "completo", "sushi", "pizza", "delivery", "helado", "pastel"]
# Auditoría 2026-07-24: la lista estaba afinada para una despensa genérica y no sabía que Nico
# tiene un hijo. El caso que lo delató: 'pañales emilio' × $29.340 salió `predecible=no` — el ítem
# de reposición por excelencia (recurrente, previsible, no perecible). Se agregan las dos familias
# que faltaban: lo de guagua y lo de aseo/casa que se repone sí o sí.
_PREDECIBLE_KW = ["arroz", "atun", "atún", "fideo", "tallarin", "aceite", "azucar", "azúcar", "sal ",
                  "harina", "papel", "higienic", "higiénic", "confort", "toalla nova", "cloro",
                  "detergente", "lavaloza", "jabon", "jabón", "shampoo", "pasta de diente", "conserva",
                  "legumbre", "lenteja", "poroto", "garbanzo", "te ", "cafe", "café", "leche en polvo",
                  "mermelada", "salsa de tomate", "ketchup", "mayonesa", "servilleta", "desodorante",
                  "limpieza", "abarrote", "despensa", "arvej",
                  # Emilio: reposición pura, y de las caras — no puede quedar fuera del predictor.
                  "pañal", "panal", "toallita", "formula", "fórmula", "colado", "cereal infantil",
                  "mamadera", "chupete", "crema de coche", "talco",
                  # Aseo/casa recurrente que faltaba.
                  "bolsa de basura", "esponja", "cera", "desinfectante", "suavizante", "escoba",
                  "traperos", "virutilla", "alcohol gel", "cloro gel"]
# `leche` sola es ambigua (la líquida es perecible, la en polvo es despensa) y `leche en polvo`
# ya está arriba. Se deja fuera a propósito: si Nico la marca con el chip, el lookup la aprende.

def _norm_item(s: str) -> str:
    """Minúsculas + sin tildes, PERO sin tocar los espacios. No usa `_norm` a propósito: ese hace
    `.strip()`, y varias keywords dependen del espacio final para no dar falsos positivos
    ('sal ' no debe calzar con 'salsa', 'te ' no debe calzar con 'tetera')."""
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


# Las listas se comparan ya normalizadas: si el texto pierde las tildes, las keywords también
# tienen que perderlas o 'atún'/'jabón'/'pañal' no calzarían nunca.
_NO_PREDECIBLE_N = [_norm_item(k) for k in _NO_PREDECIBLE_KW]
_PREDECIBLE_N = [_norm_item(k) for k in _PREDECIBLE_KW]

_items_aprendidos: dict[str, bool] = {}   # patrón → predecible; lo llena `refrescar_predecibles()`
_predecibles_cargados = False


async def refrescar_predecibles(forzar: bool = False) -> dict[str, bool]:
    """Trae de Supabase lo que Nico ya corrigió con el chip 📦/🥖 y lo deja en cache de módulo.
    `_predecible` es síncrona (la llaman parsers sin loop), por eso el lookup se precarga acá.

    Carga UNA vez por proceso, igual que `_categorias_reales`: los puntos que la llaman
    (`fin_desglose`, `procesar_foto`) corren varias veces al día y no tiene sentido un viaje a
    Supabase en cada uno. `aprender_predecible` mantiene la cache caliente cuando Nico corrige,
    así que no se desactualiza sola. Degrada a lo que haya en cache si Supabase falla."""
    global _items_aprendidos, _predecibles_cargados
    if _predecibles_cargados and not forzar:
        return _items_aprendidos
    try:
        _items_aprendidos = await memory.get_items_predecibles()
        _predecibles_cargados = True
    except Exception:
        logger.exception("refrescar_predecibles: no pude leer items_predecibles")
    return _items_aprendidos


def _predecible(texto: str) -> bool:
    """¿Es un ítem de despensa/reposición (sí) o cotidiano/perecible (no)? Recibe el nombre del
    ítem y/o su categoría. Conservador: si no calza con la despensa, NO es predecible.

    Lo APRENDIDO manda sobre la heurística: si Nico ya corrigió ese ítem con el chip 📦/🥖, esa
    es la respuesta y las palabras clave no se consultan. Antes la corrección vivía solo dentro
    del digest en curso y se perdía, así que la misma pregunta volvía cada semana."""
    t = _norm_item(texto)
    for patron, valor in _items_aprendidos.items():
        if patron and patron in t:
            return valor
    # Gana la coincidencia MÁS ESPECÍFICA (la keyword más larga), no la lista que se revise
    # primero. Antes el NO ganaba siempre y eso rompía los compuestos: 'salsa de tomate' es
    # despensa, pero calzaba con 'tomate' (perecible) y salía `no`. Mismo caso: 'leche en polvo'.
    no_kw = max((len(k) for k in _NO_PREDECIBLE_N if k in t), default=0)
    si_kw = max((len(k) for k in _PREDECIBLE_N if k in t), default=0)
    return si_kw > no_kw


async def aprender_predecible(item: str, predecible: bool) -> None:
    """Persiste la corrección del chip 📦/🥖 y actualiza el cache en caliente, para que el mismo
    digest ya use el criterio nuevo en los ítems que queden por clasificar.

    El patrón que se guarda es la PRIMERA palabra significativa del ítem, no la frase entera:
    de 'pañales emilio' se aprende 'pañales', que es lo que se repite entre compras. Guardar la
    frase completa haría un lookup que casi nunca vuelve a calzar."""
    nombre = _norm_item(item).strip()   # misma normalización que `_predecible`, o el patrón no calza
    if not nombre:
        return
    patron = next((p for p in nombre.split() if len(p) >= 4), nombre.split()[0] if nombre.split() else "")
    if not patron:
        return
    await memory.upsert_item_predecible(patron, predecible)
    _items_aprendidos[patron] = predecible


def _intencion_resumen(items: list[dict] | None) -> str:
    """Intención a nivel de transacción a partir de las líneas: 'Mixto' si hay ≥2 distintas,
    la única si todas coinciden, '' si no hay detalle."""
    ints = {str(l.get("intencion", "")).strip() for l in (items or []) if l.get("intencion")}
    ints.discard("")
    if not ints:
        return ""
    return next(iter(ints)) if len(ints) == 1 else "Mixto"


def _categoria_item(nombre: str, categoria_padre: str = "") -> str:
    """Categoría de una línea de detalle. Usa el mapa de comercios si calza ('chanchería'→Chanchería);
    si no, hereda la de la transacción padre; si tampoco hay, 'Otro Gasto'.

    NUNCA inventa una categoría con el nombre del ítem. Hasta la auditoría del 2026-07-23 hacía
    `nombre.capitalize()`, y eso metió 6 categorías fantasma en `Compras_Detalle` ('Compota', 'Pan',
    'Pago movida', 'Calzado', 'Bebidas', 'entretenimiento') que no existen en `Categorias` — y por lo
    tanto suman $0 en cualquier métrica por categoría."""
    cat = _categoria_de(nombre)
    if cat != "Otro Gasto":
        return cat
    return str(categoria_padre or "").strip() or "Otro Gasto"


def _linea_detalle(raw: dict, comercio: str = "", categoria_padre: str = "") -> dict:
    """Normaliza una línea de detalle (de foto o desglose) con categoría/intención/predecible.
    La categoría acá es la MEJOR APUESTA; la validación contra `Categorias` ocurre al escribir,
    en `_filas_detalle` (que es async y sí puede leer el catálogo)."""
    nombre = str(raw.get("item") or raw.get("nombre") or "").strip()
    categoria = str(raw.get("categoria") or "").strip() or _categoria_item(nombre, categoria_padre)
    blob = f"{nombre} {categoria}"
    return {
        "item": nombre,
        "cantidad": raw.get("cantidad", ""),
        "precio": int(_num(raw.get("precio", raw.get("monto", 0)))),
        "categoria": categoria,
        "intencion": str(raw.get("intencion") or "").strip() or _intencion_de(blob),
        "predecible": bool(raw.get("predecible")) if "predecible" in raw else _predecible(blob),
    }


def _desglose_determinista(texto: str, total=None) -> list[dict]:
    """Parsea un desglose dictado SIN LLM. Reconoce:
      · 'arroz 1290, leche 990, chocolate 2000'   (nombre monto)
      · '2000 en chanchería, el resto pan'         (monto en/de nombre + 'resto')
    El 'resto' cuadra al total. Devuelve líneas enriquecidas (categoría/intención/predecible)."""
    chunks = re.split(r",|;|\s+y\s+", (texto or "").strip())
    lineas, resto_nombre, suma = [], None, 0
    for ch in chunks:
        ch = ch.strip().rstrip(".")
        if not ch:
            continue
        m_resto = re.match(r"(?:el\s+|lo\s+)?resto\s+(?:fue\s+|en\s+|de\s+|para\s+|pa\s+)?(.+)", ch, re.I)
        if m_resto:
            resto_nombre = m_resto.group(1).strip()
            continue
        m1 = re.match(r"\$?\s*([\d.]+)\s+(?:en|de|para|pa)\s+(.+)", ch, re.I)        # "2000 en chanchería"
        m2 = re.match(r"(.+?)\s+\$?\s*([\d.]+)\s*$", ch)                              # "arroz 1290"
        if m1:
            monto, nombre = _num(m1.group(1)), m1.group(2).strip()
        elif m2:
            nombre, monto = m2.group(1).strip(), _num(m2.group(2))
        else:
            continue
        lineas.append(_linea_detalle({"item": nombre, "precio": monto}))
        suma += monto
    if resto_nombre is not None and total:
        resto = _num(total) - suma
        if resto > 0:
            lineas.append(_linea_detalle({"item": resto_nombre, "precio": resto}))
    return lineas


def _fecha_cerca(f1: str, f2: str, dias: int = 2) -> bool:
    try:
        d1 = datetime.strptime(f1[:10], "%Y-%m-%d")
        d2 = datetime.strptime(f2[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    return abs((d1 - d2).days) <= dias


def fin_correlacionar(pendientes: list[dict]) -> list[dict]:
    """Aparea las entradas del buffer CON detalle (foto/dictado, traen `items`) con la entrada
    del CORREO del mismo gasto (sin detalle) por monto total + fecha (±2 días). El correo es el
    total canónico (medio + monto bancario); el detalle aporta los ítems. Resultado: instrucciones
    de merge `{keep, drop, items}` — keep = la del correo enriquecida; drop = la de detalle. Así
    NUNCA se cuenta dos veces. Puro y testeable (no toca red)."""
    con_detalle = [p for p in pendientes if p.get("items")]
    correos = [p for p in pendientes if not p.get("items") and str(p.get("fuente", "")).startswith("correo")]
    usados, merges = set(), []
    for d in con_detalle:
        match = next(
            (c for c in correos
             if c["id"] not in usados
             and int(_num(c.get("monto"))) == int(_num(d.get("monto")))
             and _fecha_cerca(str(c.get("fecha", "")), str(d.get("fecha", "")))),
            None,
        )
        if match:
            usados.add(match["id"])
            merges.append({"keep": match["id"], "drop": d["id"], "items": d.get("items")})
    return merges


def fin_correlacionar_registradas(pendientes: list[dict], registradas: list[dict]) -> list[dict]:
    """Segunda pasada de la correlación: aparea una entrada CON detalle (foto/dictado) contra una
    transacción **ya escrita** en `Transacciones`.

    Por qué hace falta: `fin_correlacionar` solo mira el buffer, y el buffer se vacía en el digest
    de cada noche. Si el cargo llega por correo el día 15 y Nico dicta la misma compra el 16, el
    correo YA está en la planilla y no queda contra qué aparear → se cuenta DOS VECES. Es
    exactamente el caso de los $4.340 de San Valentín (auditoría 2026-07-23), que el canon prohíbe.

    Aparea por monto exacto + fecha ±2 días, igual que la primera pasada. Salta las transacciones
    que YA tienen detalle: si una compra ya está itemizada, un dictado posterior es una compra
    distinta que casualmente costó lo mismo, no la misma.

    Devuelve `{drop, adjuntar_a, items}`: `drop` = la entrada del buffer (no crea transacción
    nueva); `adjuntar_a` = el `ID_Único` de la transacción registrada, que se queda con los ítems.
    Puro y testeable (no toca red)."""
    usados = set()
    out = []
    for d in [p for p in pendientes if p.get("items")]:
        match = next(
            (t for t in registradas
             if t.get("id") and t["id"] not in usados and not t.get("tiene_detalle")
             and int(_num(t.get("monto"))) == int(_num(d.get("monto")))
             and _fecha_cerca(str(t.get("fecha", "")), str(d.get("fecha", "")))),
            None,
        )
        if match:
            usados.add(match["id"])
            out.append({"drop": d["id"], "adjuntar_a": match["id"], "items": d.get("items")})
    return out


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


def _dueno_nombres() -> list[str]:
    """Identidades propias de Nico desde la config (coma-separadas)."""
    return [x.strip() for x in str(getattr(settings, "dueno_nombres", "") or "").split(",") if x.strip()]


def _nombre_norm(n: str) -> str:
    """Nombre comparable, tokenizable: sin tildes, en minúsculas, y con la PUNTUACIÓN convertida a
    espacio. Ese último paso importa: las cartolas escriben la contraparte pegada al conector —
    'TRASPASO A:Nicolas Castro', 'TRASPASO DE:NICOLAS EMILIO CASTRO' — y sin separar el ':' el token
    queda 'a:nicolas'/'de:nicolas', que no coincide con 'nicolas' y hace que la regla del RUT propio
    NO reconozca los traslados de Nico entre sus cuentas (encontrado con datos reales 2026-07-23)."""
    s = unicodedata.normalize("NFKD", str(n or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def es_contraparte_propia(nombre: str, rut: str, dueno_rut: str = "",
                          dueno_nombres: list[str] | None = None) -> bool:
    """¿La contraparte del movimiento es el propio Nico?

    **Regla del RUT propio (D1 + D12 del realineamiento):** un movimiento entre cuentas de Nico no
    es gasto ni es ingreso — es traslado. Solo cuenta lo que cruza hacia (o desde) un tercero.

    Se compara por RUT cuando el banco lo trae (BCh) y por NOMBRE cuando no (Mach solo manda
    'Nicolas Castro'). Por eso los 5 traspasos de Mach entraron como Gasto e inflaron julio en
    $40.500 hasta la auditoría del 2026-07-23.

    El nombre se compara por **subconjunto de palabras**, no por igualdad exacta: las cartolas de
    cuenta corriente (Ola 5) traen el nombre envuelto en la glosa del banco y a veces con el segundo
    nombre — 'Transferencia de Nicolas Emilio Castro', 'TRASPASO DE: NICOLAS EMILIO CASTRO INTERNET'
    — que con igualdad exacta contra 'Nicolas Castro' NO matchea, y esos abonos (que son él mismo
    moviendo plata entre sus propias cuentas) se habrían colado como ingreso de terceros (verificado
    contra las cartolas reales de BCh y Mach, 2026-07-23). Basta que TODAS las palabras del nombre
    configurado aparezcan entre las palabras de la contraparte — bajo riesgo de falso positivo,
    porque exige coincidencia de nombre Y apellido, no solo una palabra suelta."""
    if dueno_rut and rut and _rut_norm(rut) == _rut_norm(dueno_rut):
        return True
    tokens_contraparte = set(_nombre_norm(nombre).split())
    if not tokens_contraparte:
        return False
    for propio in dueno_nombres or []:
        tokens_propio = set(_nombre_norm(propio).split())
        if tokens_propio and tokens_propio <= tokens_contraparte:
            return True
    return False


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
    # El correo YA dice el producto ('con cargo a Cuenta' = débito · 'con Tarjeta de Crédito' =
    # crédito) y antes se tiraba: los tres casos salían como 'Banco de Chile' a secas y después
    # nadie podía distinguir débito de crédito. Ahora viaja en el medio desde el origen.
    frase = _norm(m.group(0))
    producto = "crédito" if "tarjeta de credito" in frase else "débito"
    tx = {
        "tipo": "Gasto", "categoria": _categoria_de(comercio), "subcategoria": f"****{m.group(3)}",
        "comercio": comercio, "medio": f"Banco de Chile {producto}", "fecha": _fecha_iso(m.group(5)),
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
    if es_contraparte_propia(nombre, rut_dest, dueno_rut, _dueno_nombres()):
        # Entre cuentas propias: NO es gasto, pero sí se registra (Tipo=Transferencia) para que el
        # movimiento sea visible. El Dashboard filtra por Tipo="Gasto", así que queda fuera solo.
        return {
            "_interno": True, "tipo": "Transferencia", "monto": monto, "categoria": "Transferencias",
            "subcategoria": f"Rut {rut_dest}" if rut_dest else "", "comercio": nombre or "Traspaso propio",
            "medio": "Banco de Chile transferencia", "fecha": fecha,
        }
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


def _cuadrar_resto(items: list[dict], total) -> list[dict]:
    """Si la suma de los ítems no llega al total, agrega una línea 'Resto' que cuadra (no
    predecible). Si se pasa, no inventa: deja el detalle tal cual (Nico corrige en el digest)."""
    total = int(_num(total))
    suma = sum(int(_num(l.get("precio"))) for l in items)
    if total and 0 < total - suma:
        items = items + [_linea_detalle({"item": "Resto", "precio": total - suma, "categoria": "Otros"})]
    return items


async def leer_boleta(image_bytes: bytes, media_type: str = "image/jpeg") -> dict | None:
    """Vision AISLADA sobre una boleta → {comercio, total, items, fecha, medio}. SIN tocar el
    buffer: separado de `procesar_foto` para que la foto pueda ir a un cargo que YA existe
    (`adjuntar_foto_a_cargo`) en vez de crear una entrada nueva que después haya que correlacionar.
    Devuelve None si no logra leerla."""
    await refrescar_predecibles()   # las correcciones del chip 📦/🥖 mandan sobre las keywords
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    try:
        r = await _anthropic.messages.create(
            model=settings.model_cheap,
            max_tokens=800,
            system=EXTRACTOR_ITEMS_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": "Extrae el comercio, el total y la lista de ítems de esta boleta."},
                ],
            }],
        )
        d = _parse_json(r.content[0].text)
        total = d.get("total", d.get("monto", 0))
        items = [_linea_detalle(l) for l in (d.get("items") or []) if _num(l.get("precio", l.get("monto", 0))) > 0]
        return {
            "comercio": d.get("comercio", ""), "total": total, "items": items,
            "fecha": d.get("fecha", ""), "medio": d.get("medio", ""),
            "categoria": d.get("categoria", "Otros"),
        }
    except Exception:
        logger.exception("leer_boleta falló")
        return None


async def procesar_foto(image_bytes: bytes, media_type: str = "image/jpeg") -> dict | None:
    """Boleta suelta (no es respuesta a una pregunta por un cargo concreto) → buffer del día,
    ÍTEM POR ÍTEM cuando se puede (v3). El correo del banco sigue siendo el total canónico; estos
    ítems se correlacionan con él en el cierre (fin_correlacionar). Degrada: si no logra itemizar,
    queda como un solo total."""
    d = await leer_boleta(image_bytes, media_type)
    if d is None:
        return None
    try:
        total, items = d["total"], d["items"]
        if items:
            items = _cuadrar_resto(items, total)
        datos = {
            "tipo": "Gasto", "monto": total, "comercio": d["comercio"],
            "fecha": d["fecha"], "medio": d["medio"],
            "categoria": (items[0]["categoria"] if items else d["categoria"]),
            "items": items or None,
        }
        return await _bufferizar(datos, "foto")
    except Exception:
        logger.exception("procesar_foto falló")
        return None


async def adjuntar_foto_a_cargo(buffer_id: str, image_bytes: bytes,
                                media_type: str = "image/jpeg") -> str:
    """La foto es la respuesta a un *"¿qué compraste?"* por un cargo concreto: sus ítems van a ESE
    cargo, no a una entrada nueva.

    Es la diferencia con `procesar_foto`, que buffea aparte y confía en que la correlación
    monto+fecha+comercio los junte después. Ahí el emparejamiento puede fallar —la boleta dice
    'ALMACEN SAN VALENTIN' y el banco 'MERCADOPAGO*SANVA'—, y cuando falla quedan dos entradas
    del mismo gasto. Acá el vínculo lo puso Nico al tocar el botón: no hay nada que adivinar.

    El total manda es el del CARGO (el banco es la fuente canónica del monto), no el que leyó la
    Vision: si la boleta suma menos, `_cuadrar_resto` completa la diferencia."""
    try:
        cargo = next((p for p in await memory.buffer_pendientes() if p["id"] == buffer_id), None)
    except Exception:
        logger.exception("adjuntar_foto_a_cargo: no pude leer el buffer")
        cargo = None
    if not cargo:
        return "Ese cargo ya no está pendiente. Mándame la foto suelta y la cruzo igual."
    d = await leer_boleta(image_bytes, media_type)
    if d is None or not d["items"]:
        return "No pude sacar los ítems de esa foto. Dímelos por texto («2000 chanchería, resto pan») o la dejamos así."
    items = _cuadrar_resto(d["items"], cargo.get("monto"))
    try:
        await memory.buffer_actualizar(buffer_id, {"items": items,
                                                   "intencion": _intencion_resumen(items)})
    except Exception:
        logger.exception("adjuntar_foto_a_cargo: no pude guardar el detalle")
        return "Leí la boleta pero no pude guardarla ahora. Reintenta en un rato."
    n_pred = sum(1 for i in items if i.get("predecible"))
    extra = f" {n_pred} de reposición 📦." if n_pred else ""
    return (f"Leí la boleta: {len(items)} ítem(s) en {cargo.get('comercio') or 'ese cargo'}.{extra} "
            "Lo confirmas en el digest del cierre.")


async def procesar_correo(raw: str, remitente: str = "", asunto: str = "", dueno_rut: str = "",
                          reglas: list[dict] | None = None) -> dict | None:
    """Parseo AISLADO de un correo de gasto → buffer del día. PRIMERO intenta el parser
    determinista del banco (regex, cero tokens); solo si no reconoce el formato cae al LLM.
    Las transferencias entre cuentas propias de Nico (mismo RUT) se ignoran (no son gasto)."""
    det = _parsear_determinista(remitente, asunto, raw, dueno_rut)
    if det is not None:
        if det.get("_interno"):
            # Traspaso entre cuentas propias: se REGISTRA con Tipo=Transferencia (queda visible)
            # pero no cuenta como gasto. Antes se descartaba en silencio y el movimiento se perdía.
            logger.info("Traspaso propio detectado (no es gasto, se registra): %s $%s",
                        det.get("comercio", ""), det.get("monto", 0))
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
    # Tras ingerir, cruza foto/dictado con su cargo del correo (no doble conteo).
    correlacionados = await fin_aplicar_correlacion()
    return {"revisados": len(msgs), "nuevos": nuevos, "correlacionados": correlacionados}


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
        "intencion": (_intencion_resumen(p["items"]) if p.get("items")
                      else (p.get("intencion") or _intencion_de(p.get("categoria", "Otros")))),
        "items": p.get("items") or [],
        "n_items": len(p.get("items") or []),
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
    asumir que está en la fila 1.

    El rango es `A:Z`, no `A:I`: con `A:I` la guardia dependía de que `ID_Único` no pasara de la
    columna I, donde estaba justo al borde. Agregar UNA columna a su izquierda la empujaba a J,
    fuera del rango leído → la función devolvía un set vacío, el anti-duplicado se apagaba solo
    y el digest empezaba a escribir transacciones repetidas sin que nada avisara."""
    try:
        filas = await sheets.get_rows(HOJA_TX, "A:Z", sheet_id=sheets.fin_id())
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
        categoria = corr.get("categoria", p.get("categoria", "Otros"))
        items = p.get("items")
        # Intención: override explícito gana; con detalle, es el resumen de las líneas (Mixto si
        # difieren); si corrigen la categoría se re-deriva; si no, la guardada o la derivada.
        if "intencion" in corr:
            intencion = corr["intencion"]
        elif items:
            intencion = _intencion_resumen(items)
        elif "categoria" in corr:
            intencion = _intencion_de(categoria)
        else:
            intencion = p.get("intencion") or _intencion_de(categoria)
        a_escribir.append({
            "p": p,
            "categoria": categoria,
            "monto": corr.get("monto", p.get("monto", 0)),
            "intencion": intencion,
            "items": items,
        })
    return {"a_escribir": a_escribir, "a_descartar": a_descartar, "duplicadas": duplicadas}


async def _filas_detalle(p: dict, items: list[dict], categoria_padre: str = "",
                         intencion_padre: str = "") -> list[list]:
    """Filas de `Compras_Detalle` para una transacción confirmada (ID_Tx = id_unico).

    Cuatro garantías (Olas 2-3 del realineamiento, 2026-07-23) — de ellas depende que las métricas
    de gasto por categoría, que salen de ESTA hoja, no mientan:

    0. **Solo los GASTOS dejan detalle.** Un traspaso entre cuentas propias o un ingreso no son
       compras; si dejaran línea, sumarían en el gasto por categoría (el SUMIFS de esta hoja no
       puede filtrar por `Tipo`, que vive en `Transacciones`).
    1. **Todo gasto deja al menos una línea** (D10). Un cargo sin ítems (bencina, la revisión
       técnica) escribe UNA línea por el monto completo heredando categoría e intención del padre.
       Lo que no esté en esta hoja es invisible para las métricas.
    2. **Ninguna categoría fuera del catálogo** (F2.2). Cada línea pasa por `_validar_categoria`,
       igual que `Transacciones`. Antes no lo hacía: por ahí entraron las 6 categorías fantasma.
    3. **Las líneas SIEMPRE suman el total del padre.** Si el desglose viene corto (Nico detalló
       parte y no dijo "el resto"), se agrega una línea `(sin detallar)` por la diferencia en vez de
       dejar plata fuera. Sin esto, `SUM(detalle por ID_Tx) == Monto` no se cumple y el Dashboard
       pierde plata en silencio cuando cambie de fuente (F3.5).

    7 columnas (antes 10). El 2026-07-24 se retiraron `Cantidad` (0 de 65 filas llenas: solo la
    llenaba la foto ítem-a-ítem, que nunca se usó), `Intención` y `Fuente` (copias exactas del
    padre, recuperables con un lookup por `ID_Tx`). `Predecible` se mantiene aunque hoy sea 'no'
    en el 100% de las filas: está vacía por la misma razón que `Cantidad` —falta la foto—, y es
    el insumo de Compras Fase 2 por canon.
    """
    if str(p.get("tipo", "Gasto")).strip().lower() not in ("", "gasto"):
        return []       # traspasos e ingresos no son compras: no van a la hoja de detalle de gasto
    fecha, comercio = p.get("fecha") or _hoy(), p.get("comercio", "")
    idu = p.get("id_unico", "")
    total = int(_num(p.get("monto")))
    lineas = list(items or [])
    if not lineas:                                    # (1) sin desglose → una línea por el total
        lineas = [{"item": comercio or "(sin detalle)", "precio": total,
                   "categoria": categoria_padre, "intencion": intencion_padre}]
    elif total > 0:                                   # (3) el desglose debe cuadrar con el total
        resto = total - sum(int(_num(l.get("precio"))) for l in lineas)
        if resto > 0:
            lineas.append({"item": "(sin detallar)", "precio": resto,
                           "categoria": categoria_padre, "intencion": intencion_padre})
    filas = []
    for l in lineas:
        cat, _ = await _validar_categoria(l.get("categoria") or categoria_padre)   # (2)
        filas.append([
            fecha, comercio, l.get("item", ""), int(_num(l.get("precio"))), cat,
            "sí" if l.get("predecible") else "no", idu,
        ])
    return filas


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
            # 9 columnas (antes 10): `Detalle_Medio` se retiró de la planilla el 2026-07-24 —
            # nadie la leía y mezclaba nº de tarjeta, RUT y glosa en la misma celda. El dato
            # sigue viviendo en `subcategoria` dentro del buffer/Supabase, y acá se usa para
            # desambiguar el medio antes de descartarlo.
            await sheets.append_row(HOJA_TX, [
                p.get("fecha") or _hoy(), p.get("tipo", "Gasto"), item["categoria"],
                p.get("comercio", ""), int(_num(item["monto"])),
                normalizar_medio(p.get("medio", ""), p.get("subcategoria", "")),
                p.get("fuente", ""), p.get("id_unico", ""), item["intencion"],
            ], sheet_id=sheets.fin_id())
            # Detalle a Compras_Detalle, ligado por ID_Tx = id_unico. SIEMPRE ≥1 línea (D10): las
            # métricas de gasto por categoría salen de esa hoja, no de esta.
            for fila in await _filas_detalle(p, item.get("items") or [],
                                             item["categoria"], item["intencion"]):
                try:
                    await sheets.append_row(HOJA_DETALLE, fila, sheet_id=sheets.fin_id())
                except Exception:
                    logger.exception("confirmar_digest: no pude escribir una línea de detalle")
            await memory.buffer_marcar(p["id"], "confirmada")
            escritas += 1
        except Exception:
            logger.exception("confirmar_digest: no pude escribir una transacción")
    # append_row agrega al final → la hoja queda desordenada por fecha (las tandas de correo
    # traen compras de días previos). Reordeno por Fecha tras escribir para dejarla cronológica.
    if escritas:
        try:
            await sheets.ordenar_por_columna(HOJA_TX, "Fecha", sheet_id=sheets.fin_id())
        except Exception:
            logger.exception("confirmar_digest: no pude reordenar Transacciones por fecha")
    return {"escritas": escritas, "descartadas": len(plan["a_descartar"]), "duplicadas": len(plan["duplicadas"])}


# ───────────────────────── (v3) Desglose dictado + correlación aplicada ─────────────────────────

DESGLOSE_SYSTEM = (
    "Conviertes un desglose de compra dictado en JSON. Devuelve SOLO {items: [{item, precio, "
    "categoria}]}, precios enteros en pesos. Ej: 'gasté 2000 en chanchería y el resto pan' con "
    "total 5000 → [{item:'chanchería', precio:2000, categoria:'Chanchería'}, {item:'pan', "
    "precio:3000, categoria:'Alimentación'}]. Si dan un total y un 'resto', el resto cuadra al total."
)


async def fin_desglose(texto: str, total=None) -> list[dict]:
    """Desglose dictado → líneas de detalle. Determinista primero (regex, cero tokens); si no
    saca nada, cae al LLM. Cada línea trae categoría/intención/predecible."""
    await refrescar_predecibles()   # las correcciones del chip 📦/🥖 mandan sobre las keywords
    lineas = _desglose_determinista(texto, total)
    if lineas:
        return lineas
    try:
        sys = DESGLOSE_SYSTEM + (f"\n\nEl total de la compra es {int(_num(total))}." if total else "")
        r = await _anthropic.messages.create(
            model=settings.model_cheap, max_tokens=400, system=sys,
            messages=[{"role": "user", "content": f"Desglosa esta compra:\n\n{texto}"}],
        )
        d = _parse_json(r.content[0].text)
        return [_linea_detalle(l) for l in (d.get("items") or []) if _num(l.get("precio", 0)) > 0]
    except Exception:
        logger.exception("fin_desglose LLM falló")
        return []


async def desglosar_cargo(buffer_id: str, texto: str) -> str:
    """Aplica un desglose (texto) a un cargo del buffer detectado sin detalle (respuesta a la
    pregunta '¿qué compraste?'). Usa el monto del cargo como total para cuadrar el 'resto'."""
    try:
        cargo = next((p for p in await memory.buffer_pendientes() if p["id"] == buffer_id), None)
    except Exception:
        cargo = None
    if not cargo:
        return "Ese cargo ya no está pendiente."
    lineas = await fin_desglose(texto, cargo.get("monto"))
    if not lineas:
        return "No te entendí el desglose. Dímelo como '2000 chanchería, resto pan' o mándame la foto."
    try:
        await memory.buffer_actualizar(buffer_id, {"items": lineas, "intencion": _intencion_resumen(lineas)})
    except Exception:
        logger.exception("desglosar_cargo: no pude guardar el detalle")
        return "No pude guardar el detalle ahora. Reintenta en un rato."
    return f"Anotado: {len(lineas)} ítem(s). Queda en el digest del cierre para confirmar."


async def fin_aplicar_correlacion() -> int:
    """Corre la correlación sobre el buffer y aplica los merges: el cargo del correo se queda con
    los ítems del detalle (foto/dictado); la entrada de detalle se descarta. Evita doble conteo.
    Devuelve cuántos correlacionó. Se llama tras cada ingesta de correos."""
    try:
        pend = await memory.buffer_pendientes()
    except Exception:
        return 0
    n = 0
    for m in fin_correlacionar(pend):
        try:
            await memory.buffer_actualizar(m["keep"], {
                "items": m["items"], "intencion": _intencion_resumen(m["items"]),
            })
            await memory.buffer_marcar(m["drop"], "descartada")
            n += 1
        except Exception:
            logger.exception("fin_aplicar_correlacion: no pude aplicar un merge")
    if n:
        logger.info("Correlación: %d gasto(s) foto/dictado cruzados con su cargo del correo.", n)
    n += await _correlacionar_contra_planilla()
    return n


async def _transacciones_registradas() -> list[dict]:
    """`Transacciones` como {id, fecha, monto, tiene_detalle} para la 2ª pasada de correlación.
    `tiene_detalle` sale de los ID_Tx presentes en `Compras_Detalle`. Degrada a [] si no puede leer:
    sin esto la correlación se salta, no rompe la ingesta."""
    fid = sheets.fin_id()
    try:
        tx = await sheets.get_dicts(HOJA_TX, sheet_id=fid, value_render="UNFORMATTED_VALUE")
    except Exception:
        logger.exception("_transacciones_registradas: no pude leer Transacciones")
        return []
    try:
        det = await sheets.get_dicts(HOJA_DETALLE, sheet_id=fid, value_render="UNFORMATTED_VALUE")
        con_detalle = {str(d.get("ID_Tx", "")).strip() for d in det}
    except Exception:
        logger.exception("_transacciones_registradas: no pude leer Compras_Detalle")
        con_detalle = set()
    out = []
    for t in tx:
        idu = str(t.get("ID_Único", "")).strip()
        if not idu:
            continue
        # sheets.fecha_iso: UNFORMATTED_VALUE devuelve la Fecha como serie de Sheets (46177), no
        # "2026-06-11" — sin esto, _fecha_cerca() nunca matcheaba y la 2ª pasada de correlación
        # (evita el doble conteo dictado↔correo del canon) nunca encontraba nada en producción.
        out.append({"id": idu, "fecha": sheets.fecha_iso(t.get("Fecha", "")),
                    "monto": _num(t.get("Monto", 0)), "tiene_detalle": idu in con_detalle})
    return out


async def _correlacionar_contra_planilla() -> int:
    """Aplica `fin_correlacionar_registradas`: adjunta los ítems a la transacción YA registrada y
    descarta la entrada del buffer, en vez de escribir una segunda transacción por el mismo gasto."""
    try:
        pend = await memory.buffer_pendientes()
    except Exception:
        return 0
    if not any(p.get("items") for p in pend):
        return 0
    registradas = await _transacciones_registradas()
    if not registradas:
        return 0
    por_id = {t["id"]: t for t in registradas}
    n = 0
    for m in fin_correlacionar_registradas(pend, registradas):
        t = por_id[m["adjuntar_a"]]
        p = next((x for x in pend if x["id"] == m["drop"]), {})
        try:
            filas = await _filas_detalle(
                {"fecha": t["fecha"], "comercio": p.get("comercio", ""), "id_unico": t["id"],
                 "fuente": p.get("fuente", ""), "monto": t["monto"]},
                m["items"], p.get("categoria", ""), p.get("intencion", ""))
            for fila in filas:
                await sheets.append_row(HOJA_DETALLE, fila, sheet_id=sheets.fin_id())
            await memory.buffer_marcar(m["drop"], "descartada")
            n += 1
        except Exception:
            logger.exception("_correlacionar_contra_planilla: no pude adjuntar el detalle")
    if n:
        logger.info("Correlación 2ª pasada: %d detalle(s) adjuntados a transacciones ya escritas "
                    "(evita el doble conteo del canon).", n)
    return n


# Comercios "de compras": despensa/almacén donde tiene sentido itemizar. Por categoría o por
# el flag aprendido `es_compras` de la regla de comercio.
_CATEGORIAS_COMPRAS = {"alimentación", "alimentacion", "supermercado", "hogar", "almacén",
                       "almacen", "limpieza", "despensa", "abarrotes"}


# Sobre este monto, una compra "de compras" ya no es un ítem: es una vuelta al súper. La pregunta
# abierta ("¿qué compraste?") invita a la respuesta de una línea, y eso es justo lo que pasó —
# $29.340 en Santa Isabel se contestó con "pañales emilio", una sola línea para 15 productos. Y la
# despensa (arroz, atún, detergente: lo ÚNICO que alimenta el predictor de Compras Fase 2) vive
# precisamente en esas vueltas grandes, no en el pan diario del almacén. Sobre el umbral Donna
# pide la BOLETA, que es el único camino que itemiza de verdad sin que Nico dicte 15 productos.
UMBRAL_FOTO = 15000


def pedir_foto(monto) -> bool:
    """¿Este cargo amerita pedir la boleta en vez de preguntar abierto?"""
    return int(_num(monto)) >= UMBRAL_FOTO


def _es_compras(p: dict, reglas: list[dict] | None = None) -> bool:
    if str(p.get("categoria", "")).strip().lower() in _CATEGORIAS_COMPRAS:
        return True
    comercio = str(p.get("comercio", "")).lower()
    for r in reglas or []:
        if r.get("es_compras") and ((r.get("patron") or "").lower() in comercio
                                    or (r.get("nombre") or "").lower() in comercio):
            return True
    return False


async def cargos_sin_detalle() -> list[dict]:
    """Cargos pendientes de comercios 'de compras' SIN detalle y SIN preguntar aún. Insumo del
    poll de 5h: por cada uno, Donna pregunta '¿qué compraste?'."""
    try:
        pend = await memory.buffer_pendientes()
        reglas = await memory.get_comercios()
    except Exception:
        logger.exception("cargos_sin_detalle: no pude leer buffer/comercios")
        return []
    return [p for p in pend
            if str(p.get("tipo", "Gasto")) == "Gasto" and not p.get("items")
            and not p.get("preguntado_en") and _es_compras(p, reglas)]


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

async def gasto_por_dia(dias: int = 60) -> dict:
    """{fecha: total_gasto} de los últimos `dias`, leído de Transacciones SIN formato (para que
    la coma de miles no rompa la suma). Interfaz pública para el correlador de la espina."""
    try:
        filas = await sheets.get_dicts(HOJA_TX, sheet_id=sheets.fin_id(), value_render="UNFORMATTED_VALUE")
    except Exception:
        logger.exception("gasto_por_dia: no pude leer Transacciones")
        return {}
    desde = (datetime.now(settings.tz).date() - timedelta(days=dias)).strftime("%Y-%m-%d")
    out: dict[str, float] = {}
    for f in filas:
        if not str(f.get("Tipo", "")).strip().lower().startswith("gasto"):
            continue
        # sheets.fecha_iso: sin esto, "Fecha" llegaba como serie de Sheets (ej. "46177"). Como
        # string, "46177" > "2026-06-24" (compara por el primer carácter, '4' > '2'), así que el
        # filtro `fecha < desde` NUNCA saltaba una fila — el correlador sueño↔gasto agregaba el
        # gasto bajo una clave de fecha basura que jamás calzaba con las fechas reales de Salud.
        fecha = sheets.fecha_iso(f.get("Fecha", ""))
        if fecha < desde:
            continue
        out[fecha] = out.get(fecha, 0.0) + _num(f.get("Monto", 0))
    return out


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

MIN_DATOS_INFERENCIA = 20  # mínimo de transacciones registradas antes de afirmar patrones (evita inferir con N chico).


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
    # Umbral de datos: no inferir patrones hasta tener historial suficiente (N chico = ruido).
    # Las cifras de perfil son lectura directa del faro y sí se siembran; la INFERENCIA espera.
    try:
        n_tx = len(await _ids_transacciones())
    except Exception:
        n_tx = 0
    if n_tx < MIN_DATOS_INFERENCIA:
        logger.info("Espina: %d/%d transacciones — aún no infiero (junto datos).", n_tx, MIN_DATOS_INFERENCIA)
        return sembrado
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


# ───────────────────────── (D) Metas financieras (v2 — sin input diario) ─────────────────────────

async def metas_estado() -> list[dict]:
    """Lee la hoja `Metas` y calcula el progreso de cada meta (Actual/Objetivo). El % es una
    LECTURA derivada; el dato vive en las celdas Objetivo/Actual que Nico ve y edita."""
    try:
        filas = await sheets.get_dicts(HOJA_METAS, sheet_id=sheets.fin_id(), value_render="UNFORMATTED_VALUE")
    except Exception:
        logger.exception("metas_estado: no pude leer Metas")
        return []
    out = []
    for f in filas:
        meta = str(f.get("Meta", "")).strip()
        if not meta:
            continue
        obj, act = _num(f.get("Objetivo")), _num(f.get("Actual"))
        out.append({"meta": meta, "objetivo": obj, "actual": act, "progreso": _progreso(act, obj)})
    return out


async def aportar_meta(nombre: str, monto) -> str:
    """Suma un aporte al Actual de una meta y recalcula el Progreso en la hoja. Manual (sin
    doble-entrada): el avance lo reporta Nico ('aboné 50k al fondo'), no se deduce de saldos."""
    monto = _num(monto)
    if monto <= 0:
        return "¿Cuánto aportaste? Pásame el monto y lo sumo a la meta."
    metas = await metas_estado()
    if not metas:
        return "Todavía no tienes metas cargadas. Dime una (nombre + objetivo) y la dejo en la hoja Metas."
    m = next((x for x in metas if nombre.lower() in x["meta"].lower()), None)
    if not m:
        return f"No encuentro esa meta. Tienes: {', '.join(x['meta'] for x in metas)}."
    nuevo = m["actual"] + monto
    prog = _progreso(nuevo, m["objetivo"])
    try:
        await sheets.upsert_por_clave(HOJA_METAS, "Meta", m["meta"], "Actual", int(nuevo), sheet_id=sheets.fin_id())
        if prog is not None:
            await sheets.upsert_por_clave(HOJA_METAS, "Meta", m["meta"], "Progreso", f"{prog}%", sheet_id=sheets.fin_id())
    except Exception:
        logger.exception("aportar_meta: no pude actualizar la meta")
        return "No pude actualizar la meta ahora. Reintenta en un rato."
    cola = f" — vas {prog}%" if prog is not None else ""
    return f"Aboné {clp(monto)} a «{m['meta']}». Llevas {clp(nuevo)} de {clp(m['objetivo'])}{cola}."


# ───────────────────────── Handlers de tools ─────────────────────────

async def _t_registrar_gasto(inp: dict) -> str:
    """Ad-hoc por chat: 'gasté X'. Va al BUFFER del día (no a Sheets); se confirma en el cierre."""
    global _gasto_incompleto
    monto = _num_es(inp.get("monto", 0))  # entiende número, palabras ('mil') o slang ('3 lucas')
    tipo = "Ingreso" if str(inp.get("tipo", "")).lower().startswith("ing") else "Gasto"
    if monto <= 0:
        # Sin monto legible: no lo pierdo — queda esperando a que Nico diga cuánto (main.py lo completa).
        _gasto_incompleto = {"tipo": tipo, "categoria": inp.get("categoria", "Otros"),
                             "comercio": inp.get("comercio", ""), "medio": inp.get("medio", ""),
                             "creado": time.time()}
        return "¿Cuánto fue? Dímelo y lo dejo listo para el cierre (o «cancelar»)."
    _gasto_incompleto = None
    fecha = _hoy()
    comercio = inp.get("comercio", "")
    tx = {
        "fecha": fecha, "tipo": tipo, "categoria": inp.get("categoria", "Otros"),
        "comercio": comercio, "monto": int(monto), "medio": inp.get("medio", ""),
        "fuente": "manual", "id_unico": _id_unico(fecha, monto, comercio),
        "intencion": _intencion_de(inp.get("categoria", "Otros")),
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
        + (f" · {m['intencion']}" if m.get("intencion") else "")
        + (f"  ⚠️ {m['motivo_duda']}" if m["dudosa"] else "")
        for m in d["movimientos"]
    ]
    return f"Tienes {d['n']} movimiento(s) por confirmar ({clp(d['total'])}):\n" + "\n".join(lineas)


async def _t_metas(inp: dict) -> str:
    metas = await metas_estado()
    if not metas:
        return ("Aún no tienes metas financieras cargadas. Dime una (ej. «fondo de emergencia, "
                "objetivo 3 millones») y la dejo en la hoja Metas.")
    lineas = []
    for m in metas:
        barra = f"{m['progreso']}%" if m["progreso"] is not None else "—"
        lineas.append(f"• {m['meta']}: {clp(m['actual'])} de {clp(m['objetivo'])} ({barra})")
    return "Tus metas:\n" + "\n".join(lineas)


async def _t_aportar_meta(inp: dict) -> str:
    nombre = str(inp.get("meta", "")).strip()
    if not nombre:
        return "¿A qué meta aportaste? (fondo de emergencia, pagar la tarjeta, terreno…)"
    return await aportar_meta(nombre, inp.get("monto", 0))


async def _t_compra_detallada(inp: dict) -> str:
    """Nico dicta una compra CON detalle ('compré en el súper arroz 1290, leche 990'). Guarda el
    detalle en el buffer; el cargo del correo se cruza luego por monto+fecha (no doble conteo)."""
    comercio = str(inp.get("comercio", "")).strip()
    total = inp.get("total")
    items_in = inp.get("items")
    if items_in:
        lineas = [_linea_detalle(l, comercio) for l in items_in if _num(l.get("precio", l.get("monto", 0))) > 0]
    else:
        lineas = await fin_desglose(str(inp.get("desglose", "")), total)
    if not lineas:
        # No pude sacar montos del desglose: no lo pierdo — pido el total y lo anoto como gasto simple.
        global _gasto_incompleto
        _gasto_incompleto = {"tipo": "Gasto", "categoria": "Otros", "comercio": comercio, "medio": "",
                             "creado": time.time()}
        return "No te pillé los montos. ¿Cuánto fue en total? Dímelo y lo anoto para el cierre (o «cancelar»)."
    suma = sum(int(_num(l["precio"])) for l in lineas)
    monto = int(_num(total)) or suma
    guardado = await _bufferizar(
        {"tipo": "Gasto", "monto": monto, "comercio": comercio, "fecha": _hoy(), "items": lineas}, "dictado")
    if not guardado:
        return "Esa compra ya la tenía anotada para hoy. No la duplico."
    return (f"Anotado: {comercio or 'compra'} {clp(monto)}, {len(lineas)} ítem(s). "
            "En un rato lo cruzo con el cargo de tu correo para no contarlo dos veces; lo confirmas en el cierre.")


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


async def senal_pendientes_digest() -> str:
    """Para el brief: si quedaron gastos sin confirmar de cierres anteriores, lo recuerda (así no
    se acumulan pendientes que nunca llegan a la planilla). Silencio si no hay ninguno."""
    try:
        n = len(await memory.buffer_pendientes())
    except Exception:
        logger.exception("senal_pendientes_digest falló")
        return ""
    if n == 0:
        return ""
    return f"Tienes {n} movimiento(s) sin confirmar del cierre — cuando quieras, /digest y los cierro contigo."


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
                "medio": {"type": "string", "description": (
                    "Banco y producto juntos, uno de: 'Mach débito', 'Mach crédito', 'BCh débito', "
                    "'BCh crédito', 'Transferencia'. El PRODUCTO (débito/crédito) es obligatorio: "
                    "sin él no se puede saber de qué cuenta salió la plata. Si el texto no lo dice, "
                    "deja el campo vacío en vez de adivinar.")},
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
    {
        "name": "fin_metas",
        "description": (
            "OBLIGATORIO cuando Nico pregunta por sus metas financieras (fondo de emergencia, pagar la "
            "tarjeta, ahorro para algo) o cómo va con ellas. Lee la hoja Metas y muestra avance vs objetivo. No inventes."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fin_aportar_meta",
        "description": (
            "OBLIGATORIO cuando Nico dice que aportó/abonó/ahorró hacia una meta financiera ('aboné 50 mil al "
            "fondo', 'pagué 100 mil de la meta de la tarjeta'). Suma el aporte al avance de esa meta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "meta": {"type": "string", "description": "Nombre de la meta (fondo de emergencia, pagar tarjeta, terreno…)"},
                "monto": {"type": "number", "description": "Monto aportado en pesos, sin separadores"},
            },
            "required": ["meta", "monto"],
        },
    },
    {
        "name": "fin_compra_detallada",
        "description": (
            "OBLIGATORIO cuando Nico cuenta una compra CON su detalle por ítem o por categoría ('compré en el "
            "súper arroz 1290, leche 990 y chocolate 2000', 'en San Valentín gasté 2000 en chanchería y el resto "
            "pan'). Guarda el detalle; Donna lo cruza después con el cargo del banco para no contarlo dos veces. "
            "Distinto de fin_registrar_gasto (ese es un gasto simple sin desglose)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "comercio": {"type": "string", "description": "Dónde compró (súper, San Valentín, etc.)"},
                "desglose": {"type": "string", "description": "El desglose tal cual lo dijo Nico, ej 'arroz 1290, leche 990'"},
                "total": {"type": "number", "description": "Total de la compra si lo dijo, en pesos sin separadores (opcional)"},
            },
            "required": ["desglose"],
        },
    },
]

HANDLERS = {
    "fin_registrar_gasto": _t_registrar_gasto,
    "fin_saldo_mes": _t_saldo_mes,
    "fin_presupuesto": _t_presupuesto,
    "fin_estado_deuda": _t_estado_deuda,
    "fin_armar_digest": _t_armar_digest,
    "fin_metas": _t_metas,
    "fin_aportar_meta": _t_aportar_meta,
    "fin_compra_detallada": _t_compra_detallada,
}
