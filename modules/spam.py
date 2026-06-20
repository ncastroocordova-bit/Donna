"""Módulo Spam. Tools `spam_*`. Digest diario de correo basura con borrado por confirmación.

Filosofía de Donna: nunca borra sin tu visto bueno. Cada día lista el spam (Gmail + Outlook)
y tú borras con un toque ("🗑️ Borrar todo") o rescatas líneas ("✋ Conservar"). El borrado
manda a la papelera (recuperable), no es permanente.

Cache de una sola sesión (bot de un usuario): la lista mostrada se guarda en memoria para
que los botones sepan qué borrar. Se opera por ÍNDICE (los ids de Outlook no caben en el
callback_data de Telegram). Si el proceso reinicia, simplemente se re-lista.
"""
import logging

from core import correo

logger = logging.getLogger(__name__)

# Lista mostrada en el último digest: lo que se borrará al confirmar (orden estable).
_PENDIENTE: list[dict] = []


def _dominio(remitente: str) -> str:
    return remitente.split("@")[-1].rstrip(">") if "@" in remitente else (remitente or "desconocido")


async def armar_digest_spam(max_n: int | None = None) -> dict:
    """Lee el spam de los proveedores activos y cachea la lista. Devuelve {correos, n}."""
    global _PENDIENTE
    _PENDIENTE = await correo.obtener_spam(max_n)
    return {"correos": _PENDIENTE, "n": len(_PENDIENTE)}


def pendientes() -> list[dict]:
    return _PENDIENTE


def conservar_idx(i: int) -> str:
    """Rescata por índice un correo del set a borrar. Devuelve su dominio (o '' si fuera de rango)."""
    if 0 <= i < len(_PENDIENTE):
        return _dominio(_PENDIENTE.pop(i)["remitente"])
    return ""


async def borrar_todo() -> int:
    """Manda a la papelera todo lo que quedó en el set pendiente. Devuelve cuántos borró."""
    global _PENDIENTE
    if not _PENDIENTE:
        return 0
    n = await correo.borrar(_PENDIENTE)
    _PENDIENTE = []
    return n


# ───────────────────────── Tool conversacional (read-only) ─────────────────────────

async def _t_resumen(inp: dict) -> str:
    if not correo.disponible():
        return "No tengo tu correo conectado todavía, así que no veo tu spam."
    try:
        d = await armar_digest_spam()
    except Exception:
        logger.exception("spam_resumen falló")
        return "No pude revisar tu spam ahora."
    if d["n"] == 0:
        return "Tu bandeja de spam está limpia. Nada que botar."
    muestra = "; ".join(f"{_dominio(c['remitente'])}: {c['asunto'][:40]}" for c in d["correos"][:5])
    cola = "" if d["n"] <= 5 else f" (y {d['n'] - 5} más)"
    return f"Tienes {d['n']} correo(s) en spam. Por ejemplo: {muestra}{cola}. ¿Te los muestro para borrarlos?"


TOOLS = [
    {
        "name": "spam_resumen",
        "description": "OBLIGATORIO cuando Nico pregunta por su spam o correo basura. Cuenta cuántos hay y da una muestra. No inventa.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "spam_resumen": _t_resumen,
}
