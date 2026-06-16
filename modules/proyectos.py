"""Módulo Proyectos. Contrato de módulo (Plan v5 §8). Tools con prefijo `proy_`.

Datos en Supabase (tabla `proyectos`). Permite crear, actualizar y cerrar
proyectos de Nico. Búsqueda por nombre (ilike) para no depender de UUIDs.
"""
import logging
from datetime import datetime, timedelta

import agenda
from config import settings
from memory import _get_db

logger = logging.getLogger(__name__)


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


# ───────────────────────── Helpers ─────────────────────────

async def _buscar_por_nombre(nombre: str) -> dict | None:
    db = await _get_db()
    r = await db.table("proyectos").select("*").ilike("nombre", f"%{nombre}%").neq("estado", "completado").limit(1).execute()
    return r.data[0] if r.data else None


# ───────────────────────── Handlers de tools ─────────────────────────

async def _crear(inp: dict) -> str:
    nombre = inp.get("nombre", "").strip()
    if not nombre:
        return "Necesito un nombre para el proyecto."
    try:
        db = await _get_db()
        payload = {
            "nombre": nombre,
            "descripcion": inp.get("descripcion", ""),
            "fecha_inicio": _hoy(),
        }
        if inp.get("fecha_limite"):
            payload["fecha_limite"] = inp["fecha_limite"]
        await db.table("proyectos").insert(payload).execute()
        return f"Proyecto '{nombre}' creado."
    except Exception:
        logger.exception("proy_crear falló")
        return "No pude crear el proyecto ahora."


async def _listar(inp: dict) -> str:
    try:
        db = await _get_db()
        r = await db.table("proyectos").select("*").in_("estado", ["activo", "pausado"]).order("created_at").execute()
        if not r.data:
            return "No hay proyectos activos."
        lineas = []
        for p in r.data:
            limite = f" | límite: {p['fecha_limite']}" if p.get("fecha_limite") else ""
            notas = f" — {p['notas']}" if p.get("notas") else ""
            lineas.append(f"[{p['estado']}] {p['nombre']} ({p['progreso']}%){limite}{notas}")
        return "\n".join(lineas)
    except Exception:
        logger.exception("proy_listar falló")
        return "No pude listar los proyectos ahora."


async def _actualizar(inp: dict) -> str:
    nombre = inp.get("nombre", "").strip()
    if not nombre:
        return "Necesito el nombre del proyecto a actualizar."
    try:
        proyecto = await _buscar_por_nombre(nombre)
        if not proyecto:
            return f"No encontré un proyecto activo que coincida con '{nombre}'."
        cambios: dict = {"updated_at": datetime.now(settings.tz).isoformat()}
        if inp.get("progreso") is not None:
            cambios["progreso"] = int(inp["progreso"])
        if inp.get("notas"):
            cambios["notas"] = inp["notas"]
        if inp.get("estado"):
            cambios["estado"] = inp["estado"]
        db = await _get_db()
        await db.table("proyectos").update(cambios).eq("id", proyecto["id"]).execute()
        progreso = cambios.get("progreso", proyecto["progreso"])
        return f"Proyecto '{proyecto['nombre']}' actualizado — {progreso}% completado."
    except Exception:
        logger.exception("proy_actualizar falló")
        return "No pude actualizar el proyecto ahora."


async def _bloquear_tiempo(inp: dict) -> str:
    nombre = inp.get("nombre", "").strip()
    if not nombre:
        return "Necesito el nombre del proyecto para bloquear tiempo."
    try:
        duracion = float(inp.get("duracion_horas", 1.0))
        ahora = datetime.now(settings.tz)
        fecha_str = inp.get("fecha", (ahora + timedelta(days=1)).strftime("%Y-%m-%d"))
        hora_str = inp.get("hora_inicio", "09:00")
        hora, minuto = map(int, hora_str.split(":"))
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").replace(
            hour=hora, minute=minuto, tzinfo=settings.tz
        )
        fin = fecha + timedelta(hours=duracion)
        titulo = f"[Proyecto] {nombre}"
        link = await agenda.crear_evento(titulo, fecha, fin)
        if link:
            return f"Bloqueadas {duracion}h para '{nombre}' el {fecha_str} a las {hora_str}."
        return f"No pude crear el evento en el calendario, pero el proyecto está registrado."
    except Exception:
        logger.exception("proy_bloquear_tiempo falló")
        return "No pude bloquear el tiempo en el calendario ahora."


async def _cerrar(inp: dict) -> str:
    nombre = inp.get("nombre", "").strip()
    if not nombre:
        return "Necesito el nombre del proyecto a cerrar."
    try:
        proyecto = await _buscar_por_nombre(nombre)
        if not proyecto:
            return f"No encontré un proyecto activo que coincida con '{nombre}'."
        db = await _get_db()
        await db.table("proyectos").update({
            "estado": "completado",
            "progreso": 100,
            "updated_at": datetime.now(settings.tz).isoformat(),
        }).eq("id", proyecto["id"]).execute()
        return f"Proyecto '{proyecto['nombre']}' marcado como completado."
    except Exception:
        logger.exception("proy_cerrar falló")
        return "No pude cerrar el proyecto ahora."


# ───────────────────────── Señal destilada ─────────────────────────

async def senal_proyectos() -> str:
    """Proyectos activos con progreso bajo o fecha límite próxima. Para el brief."""
    try:
        db = await _get_db()
        r = await db.table("proyectos").select("*").eq("estado", "activo").order("fecha_limite", nullsfirst=False).execute()
        if not r.data:
            return ""
        hoy = _hoy()
        alertas = []
        for p in r.data:
            if p.get("fecha_limite") and p["fecha_limite"] <= hoy:
                alertas.append(f"'{p['nombre']}' venció (límite {p['fecha_limite']}, {p['progreso']}%)")
            elif p["progreso"] < 20 and p.get("fecha_limite"):
                alertas.append(f"'{p['nombre']}' al {p['progreso']}% con límite {p['fecha_limite']}")
        if not alertas and r.data:
            activos = [f"'{p['nombre']}' ({p['progreso']}%)" for p in r.data[:3]]
            return "Proyectos: " + ", ".join(activos) + "."
        return "Proyectos: " + "; ".join(alertas) + "." if alertas else ""
    except Exception:
        logger.exception("senal_proyectos falló")
        return ""


# ───────────────────────── Registro de tools ─────────────────────────

TOOLS = [
    {
        "name": "proy_crear",
        "description": "Crea un nuevo proyecto de Nico. Úsala cuando mencione que está empezando algo ('nuevo proyecto', 'quiero hacer X', 'empecé a trabajar en Y').",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre corto del proyecto"},
                "descripcion": {"type": "string", "description": "Descripción opcional"},
                "fecha_limite": {"type": "string", "description": "Fecha límite en formato YYYY-MM-DD"},
            },
            "required": ["nombre"],
        },
    },
    {
        "name": "proy_listar",
        "description": "Lista los proyectos activos o pausados de Nico con su progreso. SIEMPRE úsala cuando pregunta por sus proyectos — nunca inventes el estado.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "proy_actualizar",
        "description": "Actualiza el progreso, notas o estado de un proyecto existente. Úsala cuando Nico da un update ('el proyecto X va al 60%', 'avancé en Y').",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre o parte del nombre del proyecto"},
                "progreso": {"type": "integer", "description": "Porcentaje completado (0-100)"},
                "notas": {"type": "string", "description": "Nota de actualización"},
                "estado": {"type": "string", "enum": ["activo", "pausado"], "description": "Nuevo estado"},
            },
            "required": ["nombre"],
        },
    },
    {
        "name": "proy_bloquear_tiempo",
        "description": "Bloquea tiempo en el calendario de Nico para trabajar en un proyecto. Úsala cuando dice 'bloquea X horas para Y' o 'necesito tiempo para el proyecto Z mañana'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre o parte del nombre del proyecto"},
                "duracion_horas": {"type": "number", "description": "Duración en horas (default 1.0)"},
                "fecha": {"type": "string", "description": "Fecha YYYY-MM-DD (default mañana)"},
                "hora_inicio": {"type": "string", "description": "Hora de inicio HH:MM (default 09:00)"},
            },
            "required": ["nombre"],
        },
    },
    {
        "name": "proy_cerrar",
        "description": "Marca un proyecto como completado. Úsala cuando Nico dice que terminó un proyecto ('cerré X', 'terminé Y', 'entregué Z').",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre o parte del nombre del proyecto"},
            },
            "required": ["nombre"],
        },
    },
]

HANDLERS = {
    "proy_crear": _crear,
    "proy_listar": _listar,
    "proy_actualizar": _actualizar,
    "proy_bloquear_tiempo": _bloquear_tiempo,
    "proy_cerrar": _cerrar,
}
