"""Módulo Salud. Contrato de módulo. Tools `sal_` (Plan_Construccion_v7 Paso 1.4).

Sobre la hoja `Diario` de Vida_v6: una fila por día. Donna busca/crea la fila del día
y setea la columna. Salud es el eje #1 (el sueño es salud).

Columnas (Guía Parte B): Fecha · Ejercicio · Meditacion · Ultima_Comida · Sueno_7h ·
Animo · Hora_Dormi · MITs · Brief · Cierre · Excepcion · Notas.
"""
import logging
from datetime import datetime, timedelta

from config import settings
from core import sheets

logger = logging.getLogger(__name__)

HOJA = "Diario"

# campo conversacional → columna real en la hoja.
COLS = {
    "ejercicio": "Ejercicio",
    "meditacion": "Meditacion",
    "ultima_comida": "Ultima_Comida",
    "sueno_7h": "Sueno_7h",
    "animo": "Animo",
    "hora_dormi": "Hora_Dormi",
    "mits": "MITs",
    "brief": "Brief",
    "cierre": "Cierre",
    "excepcion": "Excepcion",
    "notas": "Notas",
}
# Hábitos binarios (presencia = cumplido) → admiten racha y default "Sí".
BINARIOS = ("ejercicio", "meditacion")
# Hábitos que el cierre pregunta por toque (Guía Parte A).
HABITOS_TOQUE = ("ejercicio", "meditacion", "ultima_comida")


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


async def _set(campo: str, valor, fecha: str | None = None) -> str:
    fecha = fecha or _hoy()
    return await sheets.upsert_por_clave(HOJA, "Fecha", fecha, COLS[campo], valor)


# ───────────────────────── Funciones directas (botones del panel) ─────────────────────────

async def marcar_habito(campo: str, valor=None) -> str:
    campo = campo.lower()
    if campo not in COLS:
        return f"No conozco el hábito '{campo}'."
    if valor in (None, ""):
        valor = "Sí" if campo in BINARIOS else valor
    estado = await _set(campo, valor)
    if estado not in ("actualizado", "creado"):
        return f"No pude anotar {campo}: {estado}."
    extra = f" Racha: {await calcular_racha(campo)} día(s)." if campo in BINARIOS else ""
    return f"Anotado: {campo.replace('_', ' ')} ({valor}).{extra}"


async def registrar_animo(valor) -> str:
    await _set("animo", valor)
    return f"Ánimo {valor}/4 anotado."


async def registrar_sueno(horas_7plus, hora_dormi: str = "") -> str:
    await _set("sueno_7h", horas_7plus)
    if hora_dormi:
        await _set("hora_dormi", hora_dormi)
    return "Sueño anotado."


async def registrar_mits(texto: str) -> str:
    await _set("mits", texto)
    return "MITs de mañana anotados."


async def marcar_excepcion() -> str:
    await _set("excepcion", "Sí")
    return "Día de excepción marcado. La racha no se rompe."


async def marcar_brief() -> None:
    await _set("brief", "✓")


async def marcar_cierre() -> None:
    await _set("cierre", "✓")


# ───────────────────────── Cálculos ─────────────────────────

async def calcular_racha(campo: str) -> int:
    """Días consecutivos hasta hoy con la columna del hábito no vacía."""
    filas = await sheets.get_dicts(HOJA)
    col = COLS[campo]
    hechos = {str(f.get("Fecha", "")) for f in filas if str(f.get(col, "")).strip()}
    racha = 0
    d = datetime.now(settings.tz).date()
    while d.strftime("%Y-%m-%d") in hechos:
        racha += 1
        d -= timedelta(days=1)
    return racha


async def _ultimos(dias: int) -> list[dict]:
    filas = await sheets.get_dicts(HOJA)
    desde = (datetime.now(settings.tz).date() - timedelta(days=dias)).strftime("%Y-%m-%d")
    return [f for f in filas if str(f.get("Fecha", "")) >= desde]


# ───────────────────────── Handlers de tools ─────────────────────────

async def _t_marcar_habito(inp: dict) -> str:
    try:
        return await marcar_habito(str(inp.get("habito", "")), inp.get("valor"))
    except Exception:
        logger.exception("sal_marcar_habito falló")
        return "No pude escribir el hábito ahora."


async def _t_registrar_animo(inp: dict) -> str:
    try:
        return await registrar_animo(inp.get("valor"))
    except Exception:
        logger.exception("sal_registrar_animo falló")
        return "No pude anotar el ánimo ahora."


async def _t_registrar_sueno(inp: dict) -> str:
    try:
        return await registrar_sueno(inp.get("horas_7plus", inp.get("valor", "")), inp.get("hora_dormi", ""))
    except Exception:
        logger.exception("sal_registrar_sueno falló")
        return "No pude anotar el sueño ahora."


async def _t_racha(inp: dict) -> str:
    campo = str(inp.get("habito", "")).lower()
    if campo not in COLS:
        return f"No conozco el hábito '{campo}'."
    try:
        return f"Racha de {campo.replace('_', ' ')}: {await calcular_racha(campo)} día(s) seguidos."
    except Exception:
        logger.exception("sal_racha falló")
        return "No pude calcular la racha."


async def _t_resumen_semana(inp: dict) -> str:
    try:
        recientes = await _ultimos(7)
        partes = []
        for c in ("ejercicio", "meditacion"):
            n = sum(1 for f in recientes if str(f.get(COLS[c], "")).strip())
            partes.append(f"{c}: {n}/7")
        n_sueno = sum(1 for f in recientes if str(f.get(COLS["sueno_7h"], "")).strip().lower() in ("sí", "si", "true", "x"))
        partes.append(f"sueño 7h+: {n_sueno}/7")
        animos = [float(f.get(COLS["animo"], 0) or 0) for f in recientes if str(f.get(COLS["animo"], "")).strip()]
        if animos:
            partes.append(f"ánimo prom {sum(animos) / len(animos):.1f}/4")
        return "Últimos 7 días — " + ", ".join(partes) + "." if partes else "Sin registros esta semana."
    except Exception:
        logger.exception("sal_resumen_semana falló")
        return "No pude armar el resumen."


# ───────────────────────── Señal destilada (el eje #1) ─────────────────────────

async def senal_salud() -> str:
    """Cruza sueño × ánimo y devuelve una frase corta. Esta es la señal madre de Donna."""
    try:
        recientes = await _ultimos(5)
        recientes.sort(key=lambda f: str(f.get("Fecha", "")))
        noches_tarde = 0
        for f in reversed(recientes):  # racha de noches recientes con poco sueño
            val = str(f.get(COLS["sueno_7h"], "")).strip().lower()
            if val and val not in ("sí", "si", "true", "x", "1"):
                noches_tarde += 1
            elif val:
                break
        if noches_tarde >= 3:
            return f"{noches_tarde}ª noche seguida con poco sueño; el patrón sueño→ánimo se está activando."
        for h in BINARIOS:
            r = await calcular_racha(h)
            if r >= 3:
                return f"{h.replace('_', ' ')} en racha de {r} días."
        return ""
    except Exception:
        logger.exception("senal_salud falló")
        return ""


# ───────────────────────── Registro de tools ─────────────────────────

TOOLS = [
    {
        "name": "sal_marcar_habito",
        "description": (
            "OBLIGATORIO cuando Nico dice que cumplió un hábito del día: ejercicio, meditación o a qué hora "
            "comió por última vez (ayuno). Anota en la fila del día. Sin esta llamada NO queda registrado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "habito": {"type": "string", "enum": list(HABITOS_TOQUE)},
                "valor": {"type": "string", "description": "Para ultima_comida: la hora (ej '21:30'). Ejercicio/meditación: omitir."},
            },
            "required": ["habito"],
        },
    },
    {
        "name": "sal_registrar_animo",
        "description": "OBLIGATORIO cuando Nico reporta su ánimo. Anota el ánimo del día (1 a 4).",
        "input_schema": {
            "type": "object",
            "properties": {"valor": {"type": "integer", "minimum": 1, "maximum": 4}},
            "required": ["valor"],
        },
    },
    {
        "name": "sal_registrar_sueno",
        "description": "OBLIGATORIO cuando Nico cuenta cuánto durmió o a qué hora se acostó. Anota si durmió 7h+ y la hora en que se durmió.",
        "input_schema": {
            "type": "object",
            "properties": {
                "horas_7plus": {"type": "string", "description": "'Sí' si durmió 7h o más, 'No' si menos"},
                "hora_dormi": {"type": "string", "description": "Hora a la que se durmió (ej '01:15')"},
            },
            "required": ["horas_7plus"],
        },
    },
    {
        "name": "sal_racha",
        "description": "OBLIGATORIO antes de decir cuántos días seguidos lleva con un hábito (ejercicio, meditación). Lo computa real. No inventes el número.",
        "input_schema": {
            "type": "object",
            "properties": {"habito": {"type": "string", "enum": list(BINARIOS)}},
            "required": ["habito"],
        },
    },
    {
        "name": "sal_resumen_semana",
        "description": "Resume cuántos días de los últimos 7 cumplió cada hábito + ánimo promedio. Para una mirada general.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "sal_marcar_habito": _t_marcar_habito,
    "sal_registrar_animo": _t_registrar_animo,
    "sal_registrar_sueno": _t_registrar_sueno,
    "sal_racha": _t_racha,
    "sal_resumen_semana": _t_resumen_semana,
}
