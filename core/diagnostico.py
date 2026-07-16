"""Autodiagnóstico lean (Ficha_Autodiagnostico_y_Variedad, Parte 1 — versión reducida).

Donna detecta cuando algo se rompe, lo registra deduplicado por firma en Supabase (tabla
`incidentes`) y avisa a Nico en su voz. NO se auto-arregla: los fixes van por Claude Code.

Versión lean: detección determinista, sin diagnóstico con Haiku. Tres tipos:
- `tool_excepcion`      — una tool tiró excepción (wrapper de core/brain._ejecutar_tool).
- `schema_sheets`       — una hoja no tiene la columna que el código espera (chequeo al boot).
- `verificacion_escritura` — se escribió una fila y al releerla no cuadra (append_row_verificado).

Contrato §4 (degrada elegante): si Supabase falla, jamás tumba la respuesta a Nico — loguea y
devuelve un dict mínimo.
"""
import hashlib
import logging
import re
from datetime import datetime

from config import settings
from core import memory

logger = logging.getLogger(__name__)

TIPOS = ("tool_excepcion", "schema_sheets", "verificacion_escritura")


def _ahora() -> str:
    return datetime.now(settings.tz).isoformat()


def _firma(tool: str, tipo: str, error_texto: str) -> str:
    """Hash corto de (tool, tipo, 1ª línea del error normalizada). Los números (filas/fechas/
    montos) → '#' para que el MISMO bug agrupe aunque cambien los detalles."""
    primera = (str(error_texto or "").strip().splitlines() or [""])[0]
    norm = re.sub(r"\d+", "#", primera)[:200]
    return hashlib.sha1(f"{tool}|{tipo}|{norm}".encode()).hexdigest()[:10]


def _safe_json(x) -> dict | None:
    """Input de la tool, recortado y sin objetos raros (no vuelca strings largos ni off-record)."""
    if not isinstance(x, dict):
        return None
    return {k: (v if isinstance(v, (int, float, bool)) else str(v)[:200]) for k, v in x.items()}


async def registrar(tool: str, tipo: str, resumen: str, *, input_json=None, error_texto: str = "") -> dict:
    """Upsert por firma (dedup). Si la firma ya está abierta → frecuencia += 1 y ultimo_visto.
    Devuelve la fila (con id y frecuencia). Degrada: si Supabase falla, devuelve un dict mínimo
    sin lanzar — el diagnóstico nunca puede tumbar la respuesta a Nico."""
    firma = _firma(tool, tipo, error_texto or resumen)
    base = {"id": None, "firma": firma, "tool": tool, "tipo": tipo, "resumen": resumen, "frecuencia": 1}
    try:
        db = await memory._get_db()
        prev = (await db.table("incidentes").select("id, frecuencia")
                .eq("firma", firma).eq("estado", "abierto").limit(1).execute()).data
        if prev:
            freq = (prev[0].get("frecuencia") or 1) + 1
            await (db.table("incidentes").update({"frecuencia": freq, "ultimo_visto": _ahora()})
                   .eq("id", prev[0]["id"]).execute())
            return {**base, "id": prev[0]["id"], "frecuencia": freq}
        nuevo = (await db.table("incidentes").insert({
            "firma": firma, "tool": tool, "tipo": tipo, "resumen": resumen,
            "error_texto": (error_texto or "")[:2000], "input_json": _safe_json(input_json),
        }).execute()).data
        return {**base, "id": (nuevo[0]["id"] if nuevo else None)}
    except Exception:
        logger.exception("diagnostico.registrar falló (Supabase); sigo sin registrar")
        return base


def texto_para_nico(inc: dict, contexto_accion: str = "hacer eso") -> str:
    """Respuesta EN CARÁCTER cuando algo se rompe. Determinista, sin LLM, JAMÁS un stacktrace."""
    n = inc.get("frecuencia", 1)
    cola_freq = f", va {n} veces" if n and n > 1 else ""
    ident = f" (#{inc['id']}{cola_freq})" if inc.get("id") else ""
    return (f"No pude {contexto_accion} — algo del código no me calzó{ident}. "
            "Ya lo dejé anotado para arreglarlo con Claude Code; sigo con el resto.")


async def pendientes() -> list[dict]:
    """Incidentes abiertos, los más frecuentes primero."""
    try:
        db = await memory._get_db()
        r = await (db.table("incidentes").select("id, tool, tipo, resumen, frecuencia")
                   .eq("estado", "abierto").order("frecuencia", desc=True).execute())
        return r.data or []
    except Exception:
        logger.exception("diagnostico.pendientes falló")
        return []


async def cerrar(incidente_id: int) -> bool:
    """Marca un incidente como cerrado (lo corre la sesión de Claude Code al terminar el fix)."""
    try:
        db = await memory._get_db()
        await (db.table("incidentes").update({"estado": "cerrado", "cerrado_en": _ahora()})
               .eq("id", incidente_id).execute())
        return True
    except Exception:
        logger.exception("diagnostico.cerrar falló")
        return False


# ───────────────────────── Heartbeat: el brief avisa solo (push) ─────────────────────────

async def senal_heartbeat() -> str:
    """Señal PUSH para el brief de las 8:00: si hay incidentes abiertos, Donna los saca sola,
    sin que Nico tenga que preguntar con `diag_estado`. **Silenciosa si todo está en orden** —
    no rellena el brief (contrato §2: señal destilada; canon: no afirmar por afirmar). Degrada
    elegante: `pendientes()` ya devuelve [] si Supabase se cae, así que aquí sale '' y el brief
    sigue sin el heartbeat."""
    incs = await pendientes()
    if not incs:
        return ""
    n = len(incs)
    top = incs[0]
    freq = f" (va {top['frecuencia']}x)" if top.get("frecuencia", 1) > 1 else ""
    plural = "incidente" if n == 1 else "incidentes"
    return (f"AVISO REAL para decirle a Nico en tu voz (breve, sin stacktrace): tengo {n} {plural} "
            f"abierto(s) que arreglar con Claude Code; el más repetido es «{top['resumen']}»{freq}.")


# ───────────────────────── Tool: ¿qué se ha roto? ─────────────────────────

async def _t_estado(inp: dict) -> str:
    incs = await pendientes()
    if not incs:
        return "Todo en orden — no tengo incidentes abiertos."
    lineas = [f"#{i['id']} {i['resumen']}" + (f" (va {i['frecuencia']}x)" if i.get("frecuencia", 1) > 1 else "")
              for i in incs[:8]]
    return "Esto es lo que detecté para arreglar con Claude Code:\n" + "\n".join(lineas)


TOOLS = [{
    "name": "diag_estado",
    "description": "OBLIGATORIO cuando Nico pregunta qué se ha roto, qué errores has tenido, o si estás funcionando bien. Lista los incidentes reales que detectaste. No inventes.",
    "input_schema": {"type": "object", "properties": {}},
}]
HANDLERS = {"diag_estado": _t_estado}
