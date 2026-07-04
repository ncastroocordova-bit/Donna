"""LEGACY — dormido. NO registrar en brain sin migrarlo primero.

La hoja `MetasSemanales` no existe en el workbook Donna; las metas vigentes son
financieras y viven en `fin_metas` (modules/finanzas.py, hoja `Metas`). Este
módulo se desregistró del brain (fix/tools-legacy) porque colisionaba con
`fin_metas` (descripciones casi idénticas → el LLM llamaba la equivocada, y
`metas_actualizar` reventaba contra una hoja inexistente). Se conserva como
referencia; su reemplazo real es `Semanal` + `fin_metas`.

Tools `metas_*`. Metas vs avance real por semana.
Hoja MetasSemanales: Semana, Fechas, Dias_Tesis, Meta_Tesis, Dias_Delivery, Meta_Delivery,
Horas_Proy, Meta_HProy, Tareas_Noomi, Meta_Tareas, Notas.
"""
import logging
from datetime import date, datetime

from config import settings
from core import sheets

logger = logging.getLogger(__name__)

# campo conversacional → (columna de avance real, columna de meta)
CAMPOS = {
    "dias_tesis": ("Dias_Tesis", "Meta_Tesis"),
    "dias_delivery": ("Dias_Delivery", "Meta_Delivery"),
    "horas_proy": ("Horas_Proy", "Meta_HProy"),
    "tareas_noomi": ("Tareas_Noomi", "Meta_Tareas"),
    "notas": ("Notas", None),
}


def _semana_actual() -> str:
    hoy = datetime.now(settings.tz).date()
    n = (hoy - date(hoy.year, 1, 1)).days // 7 + 1
    return f"Sem {n:02d}"


async def _fila_semana(sem: str) -> dict | None:
    filas = await sheets.get_dicts("MetasSemanales")
    return next((f for f in filas if str(f.get("Semana", "")).strip() == sem), None)


async def _get_semana(inp: dict) -> str:
    sem = _semana_actual()
    try:
        f = await _fila_semana(sem)
        if not f:
            return f"No tengo metas cargadas para {sem}."
        lineas = []
        for campo, (act, meta) in CAMPOS.items():
            if meta is None:
                continue
            a, m = str(f.get(act, "0") or "0"), str(f.get(meta, "") or "")
            etiqueta = campo.replace("_", " ")
            lineas.append(f"{etiqueta}: {a}/{m}")
        return f"Metas de {sem}:\n" + "\n".join(lineas)
    except Exception:
        logger.exception("metas_get_semana falló")
        return "No pude leer las metas de la semana."


async def _actualizar(inp: dict) -> str:
    campo = str(inp.get("campo", "")).lower()
    if campo not in CAMPOS:
        return f"No conozco la meta '{campo}'. Son: {', '.join(CAMPOS)}."
    valor = inp.get("valor", "")
    sem = _semana_actual()
    try:
        col = CAMPOS[campo][0]
        estado = await sheets.upsert_por_clave("MetasSemanales", "Semana", sem, col, valor)
        return f"{campo.replace('_', ' ')} de {sem} actualizado a {valor} ({estado})."
    except Exception:
        logger.exception("metas_actualizar falló")
        return "No pude actualizar la meta ahora."


async def senal_metas() -> str:
    """Para el brief: avance de la semana respecto a las metas."""
    try:
        sem = _semana_actual()
        f = await _fila_semana(sem)
        if not f:
            return ""
        flojas = []
        for campo, (act, meta) in CAMPOS.items():
            if meta is None:
                continue
            try:
                a, m = float(f.get(act, 0) or 0), float(f.get(meta, 0) or 0)
            except (ValueError, TypeError):
                continue
            if m > 0 and a < m:
                flojas.append(f"{campo.replace('_', ' ')} {a:g}/{m:g}")
        return f"Metas {sem}: vas atrás en " + ", ".join(flojas) + "." if flojas else ""
    except Exception:
        logger.exception("senal_metas falló")
        return ""


TOOLS = [
    {
        "name": "metas_get_semana",
        "description": "OBLIGATORIO cuando Nico pregunta por sus metas de la semana o cómo va con ellas. Lee la fila real de la semana actual. No inventes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "metas_actualizar",
        "description": "OBLIGATORIO cuando Nico reporta avance de una meta semanal (días de tesis, días de delivery, horas de proyectos, tareas de Noomi). Actualiza la semana actual.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campo": {"type": "string", "enum": list(CAMPOS), "description": "Qué meta"},
                "valor": {"type": "string", "description": "El nuevo valor real"},
            },
            "required": ["campo", "valor"],
        },
    },
]

HANDLERS = {
    "metas_get_semana": _get_semana,
    "metas_actualizar": _actualizar,
}
