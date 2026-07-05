"""Módulo Recordatorios. Tools `rec_`.

Sobre la hoja `Recordatorios` del workbook Donna. Schema REAL de la planilla
(verificado contra Donna_Canonico.xlsx / setup_sheets.py TABS):

    Recordatorio · Tipo · Día / Fecha · Monto aprox · Estado · Posposiciones · Última acción · Activo

Tres tipos:
- mensual: cae un día del mes (ej. la contadora el 5, el IVA el 12).
- anual: cae una fecha fija que se repite (ej. una patente, un cumpleaños).
- única: una fecha que NO se repite (ej. la revisión técnica) — puede quedar vencida.

`rec_proximos(dias)` devuelve los activos, no-hechos, cuya próxima ocurrencia cae
dentro de la ventana, INCLUYENDO los vencidos (falta negativa). `Estado` distingue
pendiente/hecho/pospuesto; `Última acción` registra el último aviso.
"""
import json
import logging
import unicodedata
from datetime import datetime

from anthropic import AsyncAnthropic

from config import settings
from core import sheets

logger = logging.getLogger(__name__)
_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)

HOJA = "Recordatorios"
ACTIVO_OK = ("sí", "si", "true", "x", "1", "")  # vacío = activo por defecto

# Nombres EXACTOS de las columnas reales (con tildes/espacios). upsert_por_clave falla con
# "columna desconocida" si no calzan al carácter — por eso el dict, no literales sueltos.
COLS = {
    "recordatorio": "Recordatorio", "tipo": "Tipo", "dia_fecha": "Día / Fecha",
    "monto": "Monto aprox", "estado": "Estado", "posposiciones": "Posposiciones",
    "ultima_accion": "Última acción", "activo": "Activo",
}


def _hoy():
    return datetime.now(settings.tz).date()


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if not unicodedata.combining(c))


def _num(v) -> int:
    try:
        return int(float(str(v).replace("$", "").replace(".", "").replace(",", ".").strip()))
    except (ValueError, TypeError):
        return 0


def _dias_hasta(rec: dict) -> int | None:
    """Días desde hoy hasta la próxima ocurrencia. None si no se puede parsear.
    Para 'única' NO hace rollover de año: devuelve negativo si ya venció."""
    hoy = _hoy()
    tipo = _sin_acentos(rec.get(COLS["tipo"], "")).strip().lower()
    valor = str(rec.get(COLS["dia_fecha"], "")).strip()
    if not valor:
        return None
    try:
        if tipo.startswith("mens"):
            dia = int(_num(valor) or int(valor))
            # próxima ocurrencia de ese día del mes
            cand = hoy.replace(day=min(dia, 28))
            if cand < hoy:
                mes = cand.month % 12 + 1
                anio = cand.year + (1 if mes == 1 else 0)
                cand = cand.replace(year=anio, month=mes)
            return (cand - hoy).days
        if tipo.startswith("anu"):
            # acepta 'DD-MM', 'DD/MM' o 'YYYY-MM-DD'; rollover al próximo año si ya pasó
            partes = valor.replace("/", "-").split("-")
            if len(partes) == 3:
                d = datetime.strptime(valor.replace("/", "-"), "%Y-%m-%d").date()
                d = d.replace(year=hoy.year)
            else:
                dd, mm = int(partes[0]), int(partes[1])
                d = datetime(hoy.year, mm, dd).date()
            if d < hoy:
                d = d.replace(year=hoy.year + 1)
            return (d - hoy).days
        if tipo.startswith("un"):  # única/unica: fecha que no se repite → puede estar vencida
            d = datetime.strptime(valor.replace("/", "-"), "%Y-%m-%d").date()
            return (d - hoy).days  # sin rollover; negativo = vencido
    except (ValueError, TypeError):
        return None
    return None


def _activo(rec: dict) -> bool:
    return str(rec.get(COLS["activo"], "")).strip().lower() in ACTIVO_OK


def _hecho(rec: dict) -> bool:
    return str(rec.get(COLS["estado"], "")).strip().lower().startswith("hecho")


# ───────────────────────── Lectura ─────────────────────────

async def proximos(dias: int = 3) -> list[dict]:
    """Recordatorios activos, no-hechos, cuya próxima ocurrencia cae dentro de `dias`.
    Los vencidos (falta < 0) siempre entran (insisten hasta marcarse Hecho)."""
    filas = await sheets.get_dicts(HOJA)
    out = []
    for r in filas:
        if not str(r.get(COLS["recordatorio"], "")).strip() or not _activo(r) or _hecho(r):
            continue
        falta = _dias_hasta(r)
        if falta is None:
            continue
        if falta <= dias:  # vencidos (falta<0) siempre; futuros dentro de la ventana
            out.append({**r, "_falta": falta})
    out.sort(key=lambda r: r["_falta"])
    return out


async def _marcar_avisado(recordatorio: str) -> None:
    try:
        await sheets.upsert_por_clave(
            HOJA, COLS["recordatorio"], recordatorio, COLS["ultima_accion"],
            f"avisado {_hoy().strftime('%Y-%m-%d')}",
        )
    except Exception:
        logger.exception("No pude marcar Última acción de %s", recordatorio)


async def texto_proximos(dias: int = 3, marcar: bool = False) -> str:
    """Frase lista para el brief. Si marcar=True, registra Última acción para dejar traza."""
    try:
        prox = await proximos(dias)
    except Exception:
        logger.exception("rec_proximos falló")
        return ""
    if not prox:
        return ""
    lineas = []
    for r in prox:
        falta = r["_falta"]
        if falta < 0:
            n = abs(falta)
            cuando = f"venció hace {n} día{'s' if n != 1 else ''}"
        elif falta == 0:
            cuando = "hoy"
        elif falta == 1:
            cuando = "mañana"
        else:
            cuando = f"en {falta} días"
        monto = _num(r.get(COLS["monto"]))
        cola = f" (~${monto:,.0f})" if monto else ""
        lineas.append(f"{r[COLS['recordatorio']]} {cuando}{cola}")
        if marcar:
            await _marcar_avisado(r[COLS["recordatorio"]])
    return "Recordatorios: " + "; ".join(lineas) + "."


async def vencidos() -> list[dict]:
    """Solo los vencidos (falta < 0), para el push del brief con botón ✅ Hecho. Forma limpia
    {nombre, falta} para no filtrar columnas crudas hacia el flujo de Telegram."""
    try:
        return [
            {"nombre": r.get(COLS["recordatorio"], ""), "falta": r["_falta"]}
            for r in await proximos(0) if r["_falta"] < 0
        ]
    except Exception:
        logger.exception("vencidos falló")
        return []


async def marcar_hecho(nombre: str) -> None:
    """Marca un recordatorio como Hecho (deja de insistir) + registra la Última acción."""
    try:
        await sheets.upsert_por_clave(HOJA, COLS["recordatorio"], nombre, COLS["estado"], "Hecho")
        await sheets.upsert_por_clave(
            HOJA, COLS["recordatorio"], nombre, COLS["ultima_accion"], f"hecho {_hoy().strftime('%Y-%m-%d')}",
        )
    except Exception:
        logger.exception("No pude marcar Hecho el recordatorio %s", nombre)


# ───────────────────────── Handlers de tools ─────────────────────────

async def _t_proximos(inp: dict) -> str:
    dias = _num(inp.get("dias", 7)) or 7
    txt = await texto_proximos(dias)
    return txt or f"No hay recordatorios en los próximos {dias} días."


async def _t_agregar(inp: dict) -> str:
    texto = str(inp.get("texto", "")).strip()
    if not texto:
        return "¿Qué te recuerdo y cuándo?"
    try:
        r = await _anthropic.messages.create(
            model=settings.model_cheap,
            max_tokens=200,
            system=(
                "Extraes un recordatorio de una frase en español chileno. Devuelve SOLO JSON con: "
                "recordatorio (string corto), tipo ('mensual' si es un día del mes que se repite, "
                "'anual' si es una fecha fija que se repite cada año, 'única' si es una fecha puntual "
                "que no se repite), dia_fecha (para mensual: el día del mes como número; para anual: "
                "'DD-MM'; para única: 'YYYY-MM-DD'), monto_aprox (número o 0)."
            ),
            messages=[{"role": "user", "content": texto}],
        )
        d = json.loads(r.content[0].text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
        # Orden REAL de la hoja: Recordatorio · Tipo · Día / Fecha · Monto aprox · Estado ·
        # Posposiciones · Última acción · Activo (8 columnas).
        await sheets.append_row(HOJA, [
            d.get("recordatorio", texto), d.get("tipo", "mensual"), str(d.get("dia_fecha", "")),
            d.get("monto_aprox", 0) or "", "Pendiente", 0, "", "Sí",
        ])
        return f"Anotado: te recuerdo '{d.get('recordatorio', texto)}'. Yo me encargo."
    except Exception:
        logger.exception("rec_agregar falló")
        return "No pude crear el recordatorio ahora. Reintenta en un rato."


TOOLS = [
    {
        "name": "rec_proximos",
        "description": "OBLIGATORIO cuando Nico pregunta qué recordatorios o pagos tiene cerca. Lee los reales y devuelve los que caen dentro del aviso, incluyendo los vencidos. No inventes.",
        "input_schema": {"type": "object", "properties": {"dias": {"type": "integer", "description": "Ventana en días (default 7)"}}},
    },
    {
        "name": "rec_agregar",
        "description": "OBLIGATORIO cuando Nico pide que le recuerdes algo ('recuérdame X el 5', 'avísame del pago de Y'). Crea el recordatorio.",
        "input_schema": {
            "type": "object",
            "properties": {"texto": {"type": "string", "description": "La frase tal cual la dijo Nico"}},
            "required": ["texto"],
        },
    },
]

HANDLERS = {
    "rec_proximos": _t_proximos,
    "rec_agregar": _t_agregar,
}
