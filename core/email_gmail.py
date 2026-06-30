"""Cliente de Gmail vía API oficial (OAuth2 con refresh token).

Scope: gmail.modify (leer + mover a papelera + etiquetas). El refresh token se genera
una vez con `python auth_email.py`. Degrada a vacío/seguro si no hay credenciales.

Devuelve mensajes normalizados: {proveedor, id, remitente, asunto, fecha, texto}.
"""
import asyncio
import base64
import html as _htmllib
import logging
import re

from config import settings

logger = logging.getLogger(__name__)


def _html_a_texto(html: str) -> str:
    """HTML → texto limpio: quita bloques <style>/<script>/<head> (no solo sus etiquetas),
    decodifica entidades (&nbsp; &aacute; &ordm;…) y colapsa espacios. Menos basura = menos
    tokens cuando el correo cae al LLM, y regex más confiable."""
    if not html:
        return ""
    html = re.sub(r"(?is)<(style|script|head|title)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    return " ".join(_htmllib.unescape(html).split())

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
_service = None
_token_invalido = False  # se prende si el refresh token murió (invalid_grant) → Donna avisa


def disponible() -> bool:
    return settings.gmail_activo


def token_invalido() -> bool:
    """True si la última llamada falló porque el refresh token expiró/se revocó (hay que
    re-autorizar). Las apps OAuth en modo 'Testing' expiran el token a los 7 días."""
    return _token_invalido


def _svc():
    global _service
    if _service is None:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials(
            token=None,
            refresh_token=settings.gmail_refresh_token,
            client_id=settings.gmail_client_id,
            client_secret=settings.gmail_client_secret,
            token_uri=TOKEN_URI,
            scopes=SCOPES,
        )
        _service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return _service


def _texto_de_payload(payload: dict) -> str:
    """Extrae el cuerpo en texto plano (o HTML degradado) de un mensaje de Gmail."""
    def _decode(data: str) -> str:
        return base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", "ignore")

    if not payload:
        return ""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})
    if mime == "text/plain" and body.get("data"):
        return _decode(body["data"])
    html = ""
    for parte in payload.get("parts", []) or []:
        t = _texto_de_payload(parte)
        if parte.get("mimeType") == "text/plain" and t:
            return t
        if parte.get("mimeType") == "text/html" and not html:
            html = t
    if not html and mime == "text/html" and body.get("data"):
        html = _decode(body["data"])
    return _html_a_texto(html)  # HTML → texto chabacano pero suficiente para parsear


def _normalizar(msg: dict) -> dict:
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "proveedor": "gmail",
        "id": msg["id"],
        "remitente": headers.get("from", ""),
        "asunto": headers.get("subject", ""),
        "fecha": headers.get("date", ""),
        # Colapsa saltos de línea y espacios múltiples: el texto/plain de los bancos parte
        # campos en varias líneas (ej. "Fecha\ny hora"), lo que rompía regex y gastaba tokens.
        "texto": " ".join((_texto_de_payload(msg.get("payload", {})) or msg.get("snippet", "")).split())[:4000],
    }


async def buscar(query: str, max_n: int = 25, label_ids: list[str] | None = None) -> list[dict]:
    if not disponible():
        return []

    def _call():
        svc = _svc()
        kwargs = {"userId": "me", "maxResults": max_n}
        if query:
            kwargs["q"] = query
        if label_ids:
            kwargs["labelIds"] = label_ids
        res = svc.users().messages().list(**kwargs).execute()
        out = []
        for ref in res.get("messages", []) or []:
            full = svc.users().messages().get(userId="me", id=ref["id"], format="full").execute()
            out.append(_normalizar(full))
        return out

    global _token_invalido
    try:
        out = await asyncio.to_thread(_call)
        _token_invalido = False  # una llamada OK limpia el flag
        return out
    except Exception as e:
        from google.auth.exceptions import RefreshError
        if isinstance(e, RefreshError) or "invalid_grant" in str(e):
            _token_invalido = True
            logger.error("Gmail: TOKEN INVÁLIDO (invalid_grant). Re-autoriza con `python auth_email.py gmail` "
                         "y publica la app OAuth a Producción para que no expire cada 7 días.")
        else:
            logger.exception("Gmail buscar falló")
        return []


async def obtener_gastos(remitentes_query: str, max_n: int = 25) -> list[dict]:
    q = f"({remitentes_query}) newer_than:{settings.correo_dias}d"
    return await buscar(q, max_n)


async def obtener_spam(max_n: int | None = None) -> list[dict]:
    return await buscar("", max_n or settings.spam_max, label_ids=["SPAM"])


async def borrar(ids: list[str]) -> int:
    """Mueve a la papelera (recuperable 30 días). Devuelve cuántos borró."""
    if not disponible() or not ids:
        return 0

    def _call():
        svc = _svc()
        n = 0
        for mid in ids:
            try:
                svc.users().messages().trash(userId="me", id=mid).execute()
                n += 1
            except Exception:
                logger.exception("Gmail trash falló para %s", mid)
        return n

    return await asyncio.to_thread(_call)
