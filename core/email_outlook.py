"""Cliente de Outlook personal (outlook.com/hotmail/live) vía Microsoft Graph.

OAuth2 con refresh token (cuentas personales → authority 'consumers'). Permiso delegado
Mail.ReadWrite + offline_access. El refresh token se genera una vez con `python auth_email.py`.
Degrada a vacío/seguro si no hay credenciales. Mensajes normalizados igual que Gmail.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from config import settings

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["Mail.ReadWrite"]


def disponible() -> bool:
    return settings.outlook_activo


def _token() -> str | None:
    import msal
    app = msal.PublicClientApplication(settings.outlook_client_id, authority=AUTHORITY)
    res = app.acquire_token_by_refresh_token(settings.outlook_refresh_token, scopes=SCOPES)
    if "access_token" not in res:
        logger.error("Outlook: no pude refrescar el token: %s", res.get("error_description", res))
        return None
    return res["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _normalizar(m: dict) -> dict:
    cuerpo = (m.get("body") or {}).get("content", "") or m.get("bodyPreview", "")
    if (m.get("body") or {}).get("contentType", "").lower() == "html":
        cuerpo = re.sub(r"<[^>]+>", " ", cuerpo)
    return {
        "proveedor": "outlook",
        "id": m.get("id", ""),
        "remitente": ((m.get("from") or {}).get("emailAddress") or {}).get("address", ""),
        "asunto": m.get("subject", ""),
        "fecha": m.get("receivedDateTime", ""),
        "texto": re.sub(r"\s+", " ", cuerpo).strip()[:4000],
    }


def _get(token: str, url: str, params: dict) -> list[dict]:
    import requests
    r = requests.get(url, headers=_headers(token), params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("value", [])


async def _mensajes_carpeta(carpeta: str, top: int) -> list[dict]:
    if not disponible():
        return []

    def _call():
        token = _token()
        if not token:
            return []
        params = {
            "$top": top,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,body",
        }
        return [_normalizar(m) for m in _get(token, f"{GRAPH}/me/mailFolders/{carpeta}/messages", params)]

    try:
        return await asyncio.to_thread(_call)
    except Exception:
        logger.exception("Outlook lectura de %s falló", carpeta)
        return []


async def obtener_gastos(dominios: list[str], max_n: int = 25) -> list[dict]:
    """Inbox reciente filtrado por dominio del remitente y ventana de días (Graph no
    permite 'contains' en from; se filtra en código)."""
    msgs = await _mensajes_carpeta("Inbox", max(max_n * 2, 50))
    corte = datetime.now(timezone.utc) - timedelta(days=settings.correo_dias + 1)
    out = []
    for m in msgs:
        rem = m["remitente"].lower()
        if not any(d in rem for d in dominios):
            continue
        try:
            recibido = datetime.fromisoformat(m["fecha"].replace("Z", "+00:00"))
            if recibido < corte:
                continue
        except (ValueError, TypeError):
            pass
        out.append(m)
    return out[:max_n]


async def obtener_spam(max_n: int | None = None) -> list[dict]:
    return await _mensajes_carpeta("JunkEmail", max_n or settings.spam_max)


async def borrar(ids: list[str]) -> int:
    """DELETE de Graph → mueve a Elementos eliminados. Devuelve cuántos borró."""
    if not disponible() or not ids:
        return 0

    def _call():
        import requests
        token = _token()
        if not token:
            return 0
        n = 0
        for mid in ids:
            try:
                r = requests.delete(f"{GRAPH}/me/messages/{mid}", headers=_headers(token), timeout=30)
                if r.status_code in (200, 204):
                    n += 1
            except Exception:
                logger.exception("Outlook delete falló para %s", mid)
        return n

    return await asyncio.to_thread(_call)
