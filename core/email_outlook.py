"""Cliente de Outlook personal (outlook.com/hotmail/live) vía Microsoft Graph.

OAuth2 con refresh token (cuentas personales → authority 'consumers'). Permiso delegado
Mail.ReadWrite + offline_access. El refresh token se genera una vez con `python auth_email.py`.
Degrada a vacío/seguro si no hay credenciales. Mensajes normalizados igual que Gmail.

Invariante duro: JAMÁS borra. El equivalente de la etiqueta `Donna/Archivado` de Gmail acá
es una carpeta propia (`FOLDER_ARCHIVO`) — el spam se MUEVE ahí, nunca se manda a Elementos
eliminados. Outlook está OFF por canon (no se usa hoy); igual queda alineado con el invariante.
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


FOLDER_ARCHIVO = "Donna Archivado"
_folder_archivo_id: str | None = None


def _obtener_o_crear_folder_archivo(token: str) -> str | None:
    """Id de la carpeta `Donna Archivado`, creándola si no existe. Se cachea en memoria."""
    import requests
    global _folder_archivo_id
    if _folder_archivo_id:
        return _folder_archivo_id
    r = requests.get(
        f"{GRAPH}/me/mailFolders", headers=_headers(token),
        params={"$filter": f"displayName eq '{FOLDER_ARCHIVO}'"}, timeout=30,
    )
    r.raise_for_status()
    existentes = r.json().get("value", [])
    if existentes:
        _folder_archivo_id = existentes[0]["id"]
        return _folder_archivo_id
    r = requests.post(
        f"{GRAPH}/me/mailFolders", headers=_headers(token),
        json={"displayName": FOLDER_ARCHIVO}, timeout=30,
    )
    r.raise_for_status()
    _folder_archivo_id = r.json()["id"]
    return _folder_archivo_id


async def archivar(ids: list[str]) -> int:
    """Invariante duro: JAMÁS borra. Mueve a la carpeta `Donna Archivado` (nunca a Elementos
    eliminados). Devuelve cuántos archivó."""
    if not disponible() or not ids:
        return 0

    def _call():
        import requests
        token = _token()
        if not token:
            return 0
        folder_id = _obtener_o_crear_folder_archivo(token)
        if not folder_id:
            return 0
        n = 0
        for mid in ids:
            try:
                r = requests.post(
                    f"{GRAPH}/me/messages/{mid}/move", headers=_headers(token),
                    json={"destinationId": folder_id}, timeout=30,
                )
                if r.status_code in (200, 201):
                    n += 1
            except Exception:
                logger.exception("Outlook archivar falló para %s", mid)
        return n

    return await asyncio.to_thread(_call)
