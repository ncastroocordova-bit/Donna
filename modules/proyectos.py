"""Módulo Proyectos + Tareas. Tools `proy_*` y `tarea_*`.

Rediseñado sobre la planilla real de Nico (hojas Proyectos y Tareas en Sheets).
El %Avance se computa desde Tareas (completadas/total). Degradación elegante.
"""
import logging
from datetime import datetime

from config import settings
from core import sheets

logger = logging.getLogger(__name__)

ACTIVOS = ("en curso", "planificación", "planificacion", "activo", "en progreso")
HECHO = ("completada", "completado", "hecha", "hecho", "sí", "si", "x", "true")


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


def _coincide(query: str, nombre: str) -> bool:
    return query.lower().strip() in str(nombre).lower()


async def _buscar_proyecto(query: str) -> dict | None:
    proys = await sheets.get_dicts("Proyectos")
    # match por ID exacto o por nombre (substring)
    for p in proys:
        if str(p.get("ID", "")).lower() == query.lower().strip():
            return p
    for p in proys:
        if _coincide(query, p.get("Proyecto", "")):
            return p
    return None


async def _avance(id_proy: str) -> tuple[int, int]:
    tareas = await sheets.get_dicts("Tareas")
    de_proy = [t for t in tareas if str(t.get("ID_Proy", "")) == str(id_proy)]
    hechas = sum(1 for t in de_proy if str(t.get("Estado", "")).lower() in HECHO or str(t.get("Completada", "")).strip().lower() in HECHO)
    return hechas, len(de_proy)


# ───────────────────────── Proyectos ─────────────────────────

async def _proy_listar(inp: dict) -> str:
    try:
        proys = await sheets.get_dicts("Proyectos")
        activos = [p for p in proys if str(p.get("Estado", "")).lower() in ACTIVOS]
        if not activos:
            return "No hay proyectos activos."
        lineas = []
        for p in activos:
            h, tot = await _avance(p.get("ID", ""))
            pct = f"{h}/{tot} tareas ({h*100//tot}%)" if tot else "sin tareas"
            lineas.append(f"[{p.get('Estado')}] {p.get('Proyecto')} — {pct} · prioridad {p.get('Prioridad', '?')}")
        return "\n".join(lineas)
    except Exception:
        logger.exception("proy_listar falló")
        return "No pude listar los proyectos ahora."


async def _proy_crear(inp: dict) -> str:
    nombre = str(inp.get("nombre", "")).strip()
    if not nombre:
        return "Necesito un nombre para el proyecto."
    try:
        proys = await sheets.get_dicts("Proyectos")
        nums = [int(str(p.get("ID", "P0"))[1:]) for p in proys if str(p.get("ID", "")).startswith("P") and str(p.get("ID"))[1:].isdigit()]
        nuevo_id = f"P{(max(nums) + 1) if nums else 1:03d}"
        await sheets.append_row("Proyectos", [
            nuevo_id, nombre, inp.get("descripcion", ""), "Planificación",
            _hoy(), inp.get("sem_estimadas", ""), inp.get("prioridad", "Media"), "",
        ])
        return f"Proyecto '{nombre}' creado ({nuevo_id})."
    except Exception:
        logger.exception("proy_crear falló")
        return "No pude crear el proyecto ahora."


async def _proy_actualizar(inp: dict) -> str:
    query = str(inp.get("nombre", "")).strip()
    p = await _buscar_proyecto(query)
    if not p:
        return f"No encontré un proyecto que coincida con '{query}'."
    try:
        for campo, col in (("estado", "Estado"), ("prioridad", "Prioridad"), ("notas", "Notas")):
            if inp.get(campo):
                await sheets.upsert_por_clave("Proyectos", "ID", p["ID"], col, inp[campo])
        return f"Proyecto '{p.get('Proyecto')}' actualizado."
    except Exception:
        logger.exception("proy_actualizar falló")
        return "No pude actualizar el proyecto ahora."


async def _proy_cerrar(inp: dict) -> str:
    query = str(inp.get("nombre", "")).strip()
    p = await _buscar_proyecto(query)
    if not p:
        return f"No encontré un proyecto que coincida con '{query}'."
    try:
        await sheets.upsert_por_clave("Proyectos", "ID", p["ID"], "Estado", "Completado")
        return f"Proyecto '{p.get('Proyecto')}' marcado como completado."
    except Exception:
        logger.exception("proy_cerrar falló")
        return "No pude cerrar el proyecto ahora."


# ───────────────────────── Tareas ─────────────────────────

async def _tarea_listar(inp: dict) -> str:
    try:
        tareas = await sheets.get_dicts("Tareas")
        query = str(inp.get("proyecto", "")).strip()
        if query:
            tareas = [t for t in tareas if _coincide(query, t.get("Proyecto", "")) or str(t.get("ID_Proy", "")).lower() == query.lower()]
        pendientes = [t for t in tareas if str(t.get("Estado", "")).lower() not in HECHO and str(t.get("Completada", "")).strip().lower() not in HECHO]
        if not pendientes:
            return "No hay tareas pendientes." + ("" if query else " (especifica un proyecto si buscas alguno puntual)")
        lineas = [f"[{t.get('Estado', '?')}] {t.get('Proyecto')} · {t.get('Descripcion')} (prioridad {t.get('Prioridad', '?')})" for t in pendientes[:12]]
        return "\n".join(lineas)
    except Exception:
        logger.exception("tarea_listar falló")
        return "No pude listar las tareas ahora."


async def _tarea_crear(inp: dict) -> str:
    query = str(inp.get("proyecto", "")).strip()
    desc = str(inp.get("descripcion", "")).strip()
    if not desc:
        return "Necesito la descripción de la tarea."
    p = await _buscar_proyecto(query) if query else None
    try:
        tareas = await sheets.get_dicts("Tareas")
        id_proy = p["ID"] if p else (inp.get("id_proy", ""))
        nombre_proy = p["Proyecto"] if p else query
        num = sum(1 for t in tareas if str(t.get("ID_Proy", "")) == str(id_proy)) + 1
        await sheets.append_row("Tareas", [
            id_proy, nombre_proy, inp.get("fase", ""), num, desc,
            inp.get("sem_inicio", ""), inp.get("sem_fin", ""), "Pendiente",
            inp.get("prioridad", "Media"), "", "",
        ])
        return f"Tarea agregada a '{nombre_proy}': {desc}."
    except Exception:
        logger.exception("tarea_crear falló")
        return "No pude crear la tarea ahora."


async def _tarea_completar(inp: dict) -> str:
    query = str(inp.get("proyecto", "")).strip()
    desc = str(inp.get("descripcion", "")).strip()
    try:
        filas = await sheets.get_rows("Tareas")
        headers = filas[0]
        ci_estado, ci_desc, ci_proy = headers.index("Estado"), headers.index("Descripcion"), headers.index("Proyecto")
        for n, f in enumerate(filas[1:], start=2):
            if len(f) > ci_desc and _coincide(desc, f[ci_desc]) and (not query or _coincide(query, f[ci_proy] if len(f) > ci_proy else "")):
                await sheets.set_cell("Tareas", n, ci_estado, "Completada")
                await sheets.set_cell("Tareas", n, headers.index("Completada"), "Sí")
                return f"Tarea completada: {f[ci_desc]}."
        return f"No encontré una tarea que coincida con '{desc}'."
    except Exception:
        logger.exception("tarea_completar falló")
        return "No pude completar la tarea ahora."


# ───────────────────────── Señal destilada ─────────────────────────

async def senal_proyectos() -> str:
    """Proyectos activos sin avance (0 tareas hechas) para el brief."""
    try:
        proys = await sheets.get_dicts("Proyectos")
        activos = [p for p in proys if str(p.get("Estado", "")).lower() in ACTIVOS]
        alertas = []
        for p in activos:
            h, tot = await _avance(p.get("ID", ""))
            if tot > 0 and h == 0 and str(p.get("Prioridad", "")).lower() == "alta":
                alertas.append(f"'{p.get('Proyecto')}' sin tareas hechas")
        return "Proyectos: " + "; ".join(alertas) + "." if alertas else ""
    except Exception:
        logger.exception("senal_proyectos falló")
        return ""


# ───────────────────────── Registro de tools ─────────────────────────

TOOLS = [
    {
        "name": "proy_listar",
        "description": "OBLIGATORIO cuando Nico pregunta por sus proyectos o cómo van. Lista los activos con su avance real (tareas hechas/total). No inventes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "proy_crear",
        "description": "OBLIGATORIO cuando Nico menciona un proyecto nuevo. Lo crea con un ID. Sin esta llamada no existe.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"}, "descripcion": {"type": "string"},
                "prioridad": {"type": "string", "enum": ["Alta", "Media", "Baja"]},
                "sem_estimadas": {"type": "number"},
            },
            "required": ["nombre"],
        },
    },
    {
        "name": "proy_actualizar",
        "description": "Actualiza estado, prioridad o notas de un proyecto existente (por nombre o ID).",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre o ID del proyecto"},
                "estado": {"type": "string"}, "prioridad": {"type": "string"}, "notas": {"type": "string"},
            },
            "required": ["nombre"],
        },
    },
    {
        "name": "proy_cerrar",
        "description": "Marca un proyecto como completado (por nombre o ID). Úsala cuando Nico dice que lo terminó.",
        "input_schema": {"type": "object", "properties": {"nombre": {"type": "string"}}, "required": ["nombre"]},
    },
    {
        "name": "tarea_listar",
        "description": "OBLIGATORIO cuando Nico pregunta por sus tareas (de un proyecto o en general). Lista las pendientes reales. No inventes.",
        "input_schema": {"type": "object", "properties": {"proyecto": {"type": "string", "description": "Opcional: filtrar por proyecto"}}},
    },
    {
        "name": "tarea_crear",
        "description": "OBLIGATORIO cuando Nico agrega una tarea a un proyecto. La registra como pendiente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "proyecto": {"type": "string", "description": "Nombre o ID del proyecto"},
                "descripcion": {"type": "string"}, "fase": {"type": "string"},
                "prioridad": {"type": "string", "enum": ["Alta", "Media", "Baja"]},
            },
            "required": ["proyecto", "descripcion"],
        },
    },
    {
        "name": "tarea_completar",
        "description": "OBLIGATORIO cuando Nico dice que terminó una tarea. La marca como completada.",
        "input_schema": {
            "type": "object",
            "properties": {
                "descripcion": {"type": "string", "description": "Parte de la descripción de la tarea"},
                "proyecto": {"type": "string", "description": "Opcional: para desambiguar"},
            },
            "required": ["descripcion"],
        },
    },
]

HANDLERS = {
    "proy_listar": _proy_listar,
    "proy_crear": _proy_crear,
    "proy_actualizar": _proy_actualizar,
    "proy_cerrar": _proy_cerrar,
    "tarea_listar": _tarea_listar,
    "tarea_crear": _tarea_crear,
    "tarea_completar": _tarea_completar,
}
