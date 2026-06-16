"""Módulo Salud. Mismo contrato de módulo (Plan v5 §8). Tools con prefijo `salud_`.

Datos en Google Sheets. Hojas: REGISTROS (fecha, habito), donde cada fila es un
toque de un hábito (ejercicio, meditación, ayuno, sueño).
"""
import logging
from datetime import datetime, timedelta

import sheets
from config import settings

logger = logging.getLogger(__name__)

HABITOS = ("ejercicio", "meditacion", "ayuno", "sueno")


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


# ───────────────────────── Handlers de tools ─────────────────────────

async def _marcar_habito(inp: dict) -> str:
    habito = inp.get("habito", "").lower()
    if habito not in HABITOS:
        return f"No conozco el hábito '{habito}'. Son: {', '.join(HABITOS)}."
    try:
        await sheets.append_row("REGISTROS", [_hoy(), habito])
        racha = await _calcular_racha(habito)
        return f"Listo, {habito} marcado. Racha: {racha} día(s)."
    except Exception:
        logger.exception("salud_marcar_habito falló")
        return "No pude marcar el hábito ahora."


async def _get_racha(inp: dict) -> str:
    habito = inp.get("habito", "").lower()
    try:
        racha = await _calcular_racha(habito)
        return f"Racha de {habito}: {racha} día(s) seguidos."
    except Exception:
        logger.exception("salud_get_racha falló")
        return "No pude calcular la racha."


async def _resumen_semana(inp: dict) -> str:
    try:
        return await _resumen() or "Sin registros esta semana."
    except Exception:
        logger.exception("salud_resumen_semana falló")
        return "No pude armar el resumen."


# ───────────────────────── Cálculos ─────────────────────────

async def _calcular_racha(habito: str) -> int:
    registros = await sheets.get_dicts("REGISTROS")
    dias = {r.get("fecha") for r in registros if r.get("habito", "").lower() == habito}
    racha = 0
    d = datetime.now(settings.tz).date()
    while d.strftime("%Y-%m-%d") in dias:
        racha += 1
        d -= timedelta(days=1)
    return racha


async def _resumen(dias: int = 7) -> str:
    registros = await sheets.get_dicts("REGISTROS")
    desde = (datetime.now(settings.tz).date() - timedelta(days=dias)).strftime("%Y-%m-%d")
    recientes = [r for r in registros if str(r.get("fecha", "")) >= desde]
    conteo = {h: sum(1 for r in recientes if r.get("habito", "").lower() == h) for h in HABITOS}
    return ", ".join(f"{h}: {n}/{dias}" for h, n in conteo.items() if n)


# ───────────────────────── Señal destilada ─────────────────────────

async def senal_salud() -> str:
    """Rachas y caídas para el brief/cierre. No datos crudos."""
    try:
        alertas = []
        for h in HABITOS:
            racha = await _calcular_racha(h)
            if racha >= 3:
                alertas.append(f"{h} en racha de {racha}")
        # Caída de sueño: ¿no marcó 'sueno' las últimas noches?
        sueno_racha = await _calcular_racha("sueno")
        if sueno_racha == 0:
            alertas.append("sueño cortado; ojo con el patrón sueño→ánimo")
        return "Salud: " + "; ".join(alertas) + "." if alertas else ""
    except Exception:
        logger.exception("senal_salud falló")
        return ""


# ───────────────────────── Registro de tools ─────────────────────────

TOOLS = [
    {
        "name": "salud_marcar_habito",
        "description": "OBLIGATORIO: llama esta herramienta cuando Nico dice que cumplió un hábito — 'fui al gym', 'hice ejercicio', 'medité', 'ayuné', 'dormí bien'. Sin esta llamada el hábito NO queda registrado. Jamás confirmes el registro sin haberla ejecutado.",
        "input_schema": {
            "type": "object",
            "properties": {"habito": {"type": "string", "enum": list(HABITOS)}},
            "required": ["habito"],
        },
    },
    {
        "name": "salud_get_racha",
        "description": "OBLIGATORIO: llama esta herramienta antes de responder cualquier pregunta sobre rachas o días seguidos. El número que digas sin llamarla es inventado. Jamás cites días sin obtener el dato real aquí.",
        "input_schema": {
            "type": "object",
            "properties": {"habito": {"type": "string", "enum": list(HABITOS)}},
            "required": ["habito"],
        },
    },
    {
        "name": "salud_resumen_semana",
        "description": "Resume cuántas veces cumplió cada hábito en la semana. Úsala para una mirada general de la salud reciente.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "salud_marcar_habito": _marcar_habito,
    "salud_get_racha": _get_racha,
    "salud_resumen_semana": _resumen_semana,
}
