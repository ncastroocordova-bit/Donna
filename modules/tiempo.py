"""Módulo Tiempo. Tools `tiempo_*`. Registro de horas de trabajo por proyecto.
Hoja Tiempo: Fecha, Proyecto, Actividad, Descripcion, Inicio, Fin, Horas, Categoria, Foco, Semana, Notas.
"""
import logging
from datetime import date, datetime

import sheets
from config import settings

logger = logging.getLogger(__name__)


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


def _semana_actual() -> str:
    hoy = datetime.now(settings.tz).date()
    n = (hoy - date(hoy.year, 1, 1)).days // 7 + 1
    return f"Sem {n:02d}"


def _num(v) -> float:
    try:
        return float(str(v).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


async def _registrar(inp: dict) -> str:
    proyecto = str(inp.get("proyecto", "")).strip()
    horas = inp.get("horas")
    if not proyecto or horas in (None, ""):
        return "Necesito el proyecto y las horas."
    try:
        await sheets.append_row("Tiempo", [
            _hoy(), proyecto, inp.get("actividad", ""), inp.get("descripcion", ""),
            inp.get("inicio", ""), inp.get("fin", ""), horas, inp.get("categoria", ""),
            inp.get("foco", ""), _semana_actual(), inp.get("notas", ""),
        ])
        return f"Registradas {_num(horas):g}h en {proyecto}."
    except Exception:
        logger.exception("tiempo_registrar falló")
        return "No pude registrar las horas ahora."


async def _resumen(inp: dict) -> str:
    try:
        filas = await sheets.get_dicts("Tiempo")
        sem = _semana_actual()
        de_sem = [f for f in filas if str(f.get("Semana", "")) == sem]
        if not de_sem:
            return f"Sin horas registradas esta semana ({sem})."
        por_proy: dict[str, float] = {}
        for f in de_sem:
            por_proy[f.get("Proyecto", "?")] = por_proy.get(f.get("Proyecto", "?"), 0) + _num(f.get("Horas"))
        total = sum(por_proy.values())
        detalle = ", ".join(f"{p}: {h:g}h" for p, h in por_proy.items())
        return f"Esta semana ({sem}): {total:g}h totales — {detalle}."
    except Exception:
        logger.exception("tiempo_resumen falló")
        return "No pude armar el resumen de horas."


TOOLS = [
    {
        "name": "tiempo_registrar",
        "description": "OBLIGATORIO cuando Nico dice que trabajó X horas en un proyecto. Registra la sesión. Sin esta llamada no queda.",
        "input_schema": {
            "type": "object",
            "properties": {
                "proyecto": {"type": "string"},
                "horas": {"type": "number"},
                "actividad": {"type": "string"},
                "descripcion": {"type": "string"},
                "foco": {"type": "string", "description": "Nivel de foco 1-5"},
            },
            "required": ["proyecto", "horas"],
        },
    },
    {
        "name": "tiempo_resumen",
        "description": "OBLIGATORIO cuando Nico pregunta cuánto trabajó esta semana o en qué. Suma las horas reales por proyecto. No inventes.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "tiempo_registrar": _registrar,
    "tiempo_resumen": _resumen,
}
