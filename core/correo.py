"""Facade unificado de correo: Gmail + Outlook bajo una sola interfaz.

Cada mensaje viene normalizado: {proveedor, id, remitente, asunto, fecha, texto}.
La lógica de QUÉ es un gasto y de QUÉ categoría vive en modules/finanzas.py; acá solo
está la conectividad. Degrada por proveedor: si uno no está configurado, se omite.
"""
import logging

from core import email_gmail as gmail
from core import email_outlook as outlook

logger = logging.getLogger(__name__)


def disponible() -> bool:
    return gmail.disponible() or outlook.disponible()


def gmail_token_invalido() -> bool:
    """True si el refresh token de Gmail murió (hay que re-autorizar)."""
    return gmail.token_invalido()


def proveedores_activos() -> list[str]:
    activos = []
    if gmail.disponible():
        activos.append("gmail")
    if outlook.disponible():
        activos.append("outlook")
    return activos


async def obtener_gastos(gmail_query: str, max_n: int = 25) -> list[dict]:
    """Gastos SOLO por Gmail. Canon v7.2: Outlook OFF (descartado); el ingreso por
    correo del Modulo 1 (Finanzas) es Gmail-only. El correo dedicado financiero y el
    triage de 3 buckets aterrizan en el Modulo 4."""
    if not gmail.disponible():
        return []
    return await gmail.obtener_gastos(gmail_query, max_n)


async def obtener_spam(max_n: int | None = None) -> list[dict]:
    msgs: list[dict] = []
    if gmail.disponible():
        msgs += await gmail.obtener_spam(max_n)
    if outlook.disponible():
        msgs += await outlook.obtener_spam(max_n)
    return msgs


async def archivar(msgs: list[dict]) -> int:
    """Invariante duro: JAMÁS borra. Archiva (etiqueta/carpeta según proveedor) una lista de
    mensajes normalizados, agrupando por proveedor."""
    ids_gmail = [m["id"] for m in msgs if m.get("proveedor") == "gmail"]
    ids_outlook = [m["id"] for m in msgs if m.get("proveedor") == "outlook"]
    n = 0
    if ids_gmail:
        n += await gmail.archivar(ids_gmail)
    if ids_outlook:
        n += await outlook.archivar(ids_outlook)
    return n
