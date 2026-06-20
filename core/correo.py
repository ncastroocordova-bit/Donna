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


def proveedores_activos() -> list[str]:
    activos = []
    if gmail.disponible():
        activos.append("gmail")
    if outlook.disponible():
        activos.append("outlook")
    return activos


async def obtener_gastos(gmail_query: str, outlook_dominios: list[str], max_n: int = 25) -> list[dict]:
    msgs: list[dict] = []
    if gmail.disponible():
        msgs += await gmail.obtener_gastos(gmail_query, max_n)
    if outlook.disponible():
        msgs += await outlook.obtener_gastos(outlook_dominios, max_n)
    return msgs


async def obtener_spam(max_n: int | None = None) -> list[dict]:
    msgs: list[dict] = []
    if gmail.disponible():
        msgs += await gmail.obtener_spam(max_n)
    if outlook.disponible():
        msgs += await outlook.obtener_spam(max_n)
    return msgs


async def borrar(msgs: list[dict]) -> int:
    """Borra (papelera) una lista de mensajes normalizados, agrupando por proveedor."""
    ids_gmail = [m["id"] for m in msgs if m.get("proveedor") == "gmail"]
    ids_outlook = [m["id"] for m in msgs if m.get("proveedor") == "outlook"]
    n = 0
    if ids_gmail:
        n += await gmail.borrar(ids_gmail)
    if ids_outlook:
        n += await outlook.borrar(ids_outlook)
    return n
