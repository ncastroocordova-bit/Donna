"""Módulo Proyectos + Tareas. Tools `proy_*` y `tarea_*`.

Opera por NOMBRE sobre el schema real de la planilla (sin IDs fantasma). Schemas reales:

    Proyectos: Proyecto · Estado · Foco actual · Próxima acción · % Avance · Última act. · Notas
    Tareas:    Creada · Descripción · Proyecto · Tipo · Fecha objetivo · Estado · Completada · Notas

El % de avance se computa desde Tareas (hechas/total de ESE proyecto, por nombre), excluyendo
los MITs de Salud (Tipo=MIT) que viven en la misma hoja. Degradación elegante.
"""
import logging
from datetime import datetime

from config import settings
from core import sheets

logger = logging.getLogger(__name__)

HOJA_PROY = "Proyectos"
HOJA_TAREAS = "Tareas"
TIPO_MIT = "MIT"  # los MITs de Salud viven en Tareas; se excluyen del avance de proyectos

ACTIVOS = ("en curso", "planificación", "planificacion", "activo", "en progreso")
HECHO = ("completada", "completado", "hecha", "hecho", "sí", "si", "x", "true")

COLS_PROY = {
    "proyecto": "Proyecto", "estado": "Estado", "foco": "Foco actual",
    "proxima": "Próxima acción", "avance": "% Avance", "ultima": "Última act.", "notas": "Notas",
}
# = salud.COLS_TAREAS, mismo canon. Se duplica el literal a propósito (contrato de módulo:
# sin acoplar Proyectos con Salud); ambos escritores de `Tareas` usan estos nombres exactos.
COLS_TAREAS = {
    "creada": "Creada", "descripcion": "Descripción", "proyecto": "Proyecto", "tipo": "Tipo",
    "fecha_objetivo": "Fecha objetivo", "estado": "Estado", "completada": "Completada", "notas": "Notas",
}


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


def _coincide(query: str, nombre: str) -> bool:
    return query.lower().strip() in str(nombre).lower()


def _completada(t: dict) -> bool:
    return (str(t.get(COLS_TAREAS["estado"], "")).strip().lower() in HECHO
            or str(t.get(COLS_TAREAS["completada"], "")).strip().lower() in HECHO)


async def _buscar_proyecto(query: str) -> dict | None:
    if not query:
        return None
    for p in await sheets.get_dicts(HOJA_PROY):
        if _coincide(query, p.get(COLS_PROY["proyecto"], "")):
            return p
    return None


async def _avance(nombre_proy: str) -> tuple[int, int]:
    """Tareas hechas / total de un proyecto, por NOMBRE (case-insensitive). Excluye los MITs
    de Salud (Tipo=MIT) para no contaminar el conteo con tareas de otro dominio."""
    tareas = await sheets.get_dicts(HOJA_TAREAS)
    nombre = str(nombre_proy).strip().lower()
    de_proy = [
        t for t in tareas
        if str(t.get(COLS_TAREAS["proyecto"], "")).strip().lower() == nombre
        and str(t.get(COLS_TAREAS["tipo"], "")).strip() != TIPO_MIT
    ]
    hechas = sum(1 for t in de_proy if _completada(t))
    return hechas, len(de_proy)


# ───────────────────────── Proyectos ─────────────────────────

async def _proy_listar(inp: dict) -> str:
    try:
        proys = await sheets.get_dicts(HOJA_PROY)
        activos = [p for p in proys if str(p.get(COLS_PROY["estado"], "")).lower() in ACTIVOS]
        if not activos:
            return "No hay proyectos activos."
        lineas = []
        for p in activos:
            nombre = p.get(COLS_PROY["proyecto"], "")
            h, tot = await _avance(nombre)
            pct = f"{h}/{tot} tareas ({h * 100 // tot}%)" if tot else "sin tareas"
            foco = str(p.get(COLS_PROY["foco"], "")).strip()
            cola = f" · foco: {foco}" if foco else ""
            lineas.append(f"[{p.get(COLS_PROY['estado'])}] {nombre} — {pct}{cola}")
        return "\n".join(lineas)
    except Exception:
        logger.exception("proy_listar falló")
        return "No pude listar los proyectos ahora."


async def _proy_crear(inp: dict) -> str:
    nombre = str(inp.get("nombre", "")).strip()
    if not nombre:
        return "Necesito un nombre para el proyecto."
    try:
        # Orden real: Proyecto · Estado · Foco actual · Próxima acción · % Avance · Última act. · Notas
        await sheets.append_row(HOJA_PROY, [
            nombre, "Activo", inp.get("descripcion", ""),
            inp.get("proxima_accion", "(define tu próxima acción)"),
            "0%", _hoy(), inp.get("notas", ""),
        ])
        return f"Proyecto '{nombre}' creado."
    except Exception:
        logger.exception("proy_crear falló")
        return "No pude crear el proyecto ahora."


async def _proy_actualizar(inp: dict) -> str:
    query = str(inp.get("nombre", "")).strip()
    p = await _buscar_proyecto(query)
    if not p:
        return f"No encontré un proyecto que coincida con '{query}'."
    nombre = p[COLS_PROY["proyecto"]]
    try:
        campos = (("estado", COLS_PROY["estado"]), ("foco", COLS_PROY["foco"]),
                  ("proxima_accion", COLS_PROY["proxima"]), ("notas", COLS_PROY["notas"]))
        cambios = 0
        for campo, col in campos:
            if inp.get(campo):
                await sheets.upsert_por_clave(HOJA_PROY, COLS_PROY["proyecto"], nombre, col, inp[campo])
                cambios += 1
        if cambios:
            await sheets.upsert_por_clave(HOJA_PROY, COLS_PROY["proyecto"], nombre, COLS_PROY["ultima"], _hoy())
        return f"Proyecto '{nombre}' actualizado."
    except Exception:
        logger.exception("proy_actualizar falló")
        return "No pude actualizar el proyecto ahora."


async def _proy_cerrar(inp: dict) -> str:
    query = str(inp.get("nombre", "")).strip()
    p = await _buscar_proyecto(query)
    if not p:
        return f"No encontré un proyecto que coincida con '{query}'."
    nombre = p[COLS_PROY["proyecto"]]
    try:
        await sheets.upsert_por_clave(HOJA_PROY, COLS_PROY["proyecto"], nombre, COLS_PROY["estado"], "Completado")
        await sheets.upsert_por_clave(HOJA_PROY, COLS_PROY["proyecto"], nombre, COLS_PROY["ultima"], _hoy())
        return f"Proyecto '{nombre}' marcado como completado."
    except Exception:
        logger.exception("proy_cerrar falló")
        return "No pude cerrar el proyecto ahora."


# ───────────────────────── Tareas ─────────────────────────

async def _tarea_listar(inp: dict) -> str:
    try:
        tareas = await sheets.get_dicts(HOJA_TAREAS)
        query = str(inp.get("proyecto", "")).strip()
        if query:
            tareas = [t for t in tareas if _coincide(query, t.get(COLS_TAREAS["proyecto"], ""))]
        pendientes = [t for t in tareas
                      if not _completada(t) and str(t.get(COLS_TAREAS["descripcion"], "")).strip()]
        if not pendientes:
            return "No hay tareas pendientes." + ("" if query else " (especifica un proyecto si buscas alguno puntual)")
        lineas = []
        for t in pendientes[:12]:
            proy = str(t.get(COLS_TAREAS["proyecto"], "")).strip()
            desc = str(t.get(COLS_TAREAS["descripcion"], "")).strip()
            fobj = str(t.get(COLS_TAREAS["fecha_objetivo"], "")).strip()
            es_mit = str(t.get(COLS_TAREAS["tipo"], "")).strip() == TIPO_MIT
            etiqueta = "[MIT]" if es_mit else f"[{str(t.get(COLS_TAREAS['estado'], '')).strip() or 'Pendiente'}]"
            cola = f" (para {fobj})" if fobj else ""
            lineas.append(f"{etiqueta} {proy} · {desc}{cola}")
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
    nombre_proy = p[COLS_PROY["proyecto"]] if p else (query or "—")
    try:
        # Orden real (idéntico a como salud.py crea un MIT): Creada · Descripción · Proyecto ·
        # Tipo · Fecha objetivo · Estado · Completada · Notas.
        await sheets.append_row(HOJA_TAREAS, [
            _hoy(), desc, nombre_proy, inp.get("tipo", "Tarea"),
            inp.get("fecha_objetivo", ""), "Pendiente", "", inp.get("notas", ""),
        ])
        return f"Tarea agregada a '{nombre_proy}': {desc}."
    except Exception:
        logger.exception("tarea_crear falló")
        return "No pude crear la tarea ahora."


async def _tarea_completar(inp: dict) -> str:
    query = str(inp.get("proyecto", "")).strip()
    desc = str(inp.get("descripcion", "")).strip()
    if not desc:
        return "¿Qué tarea terminaste?"
    try:
        filas = await sheets.get_rows(HOJA_TAREAS)
        h_idx, headers = sheets._fila_headers(filas)
        if h_idx < 0:
            return "No pude leer las tareas ahora."
        idx = {c: headers.index(v) for c, v in COLS_TAREAS.items() if v in headers}
        if not all(k in idx for k in ("descripcion", "estado", "completada")):
            return "No pude leer las tareas ahora."

        def _get(fila, col):
            i = idx[col]
            return str(fila[i]).strip() if len(fila) > i else ""

        for n, fila in enumerate(filas[h_idx + 1:], start=h_idx + 2):
            if not _coincide(desc, _get(fila, "descripcion")):
                continue
            if query and "proyecto" in idx and not _coincide(query, _get(fila, "proyecto")):
                continue
            await sheets.set_cell(HOJA_TAREAS, n, idx["estado"], "Completada")
            await sheets.set_cell(HOJA_TAREAS, n, idx["completada"], "Sí")
            return f"Tarea completada: {_get(fila, 'descripcion')}."
        return f"No encontré una tarea que coincida con '{desc}'."
    except Exception:
        logger.exception("tarea_completar falló")
        return "No pude completar la tarea ahora."


# ───────────────────────── Señal destilada ─────────────────────────

async def senal_proyectos() -> str:
    """Proyectos activos con tareas pero sin ninguna hecha (0 avance) para el brief."""
    try:
        proys = await sheets.get_dicts(HOJA_PROY)
        activos = [p for p in proys if str(p.get(COLS_PROY["estado"], "")).lower() in ACTIVOS]
        alertas = []
        for p in activos:
            nombre = p.get(COLS_PROY["proyecto"], "")
            h, tot = await _avance(nombre)
            if tot > 0 and h == 0:
                alertas.append(f"'{nombre}' sin tareas hechas")
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
        "description": "OBLIGATORIO cuando Nico menciona un proyecto nuevo. Lo crea (la clave es el nombre). Sin esta llamada no existe.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "descripcion": {"type": "string", "description": "Foco actual del proyecto (opcional)"},
                "proxima_accion": {"type": "string", "description": "La próxima acción concreta (opcional)"},
                "notas": {"type": "string"},
            },
            "required": ["nombre"],
        },
    },
    {
        "name": "proy_actualizar",
        "description": "Actualiza estado, foco, próxima acción o notas de un proyecto existente (por nombre).",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre del proyecto"},
                "estado": {"type": "string"}, "foco": {"type": "string"},
                "proxima_accion": {"type": "string"}, "notas": {"type": "string"},
            },
            "required": ["nombre"],
        },
    },
    {
        "name": "proy_cerrar",
        "description": "Marca un proyecto como completado (por nombre). Úsala cuando Nico dice que lo terminó.",
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
                "proyecto": {"type": "string", "description": "Nombre del proyecto (opcional)"},
                "descripcion": {"type": "string"},
                "fecha_objetivo": {"type": "string", "description": "Fecha objetivo YYYY-MM-DD (opcional)"},
            },
            "required": ["descripcion"],
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
