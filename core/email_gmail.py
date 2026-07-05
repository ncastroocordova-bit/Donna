"""Cliente de Gmail vía API oficial (OAuth2 con refresh token).

Scope: gmail.modify (leer + etiquetar). Invariante duro: JAMÁS borra ni manda a la
papelera — el spam se archiva con la etiqueta `Donna/Archivado` + se le quita `INBOX`,
recuperable de un clic desde esa etiqueta en Gmail (a diferencia de la papelera, no expira).
El refresh token se genera una vez con `python auth_email.py`. Degrada a vacío/seguro si
no hay credenciales.

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


LABEL_ARCHIVO = "Donna/Archivado"
_label_archivo_id: str | None = None


def _obtener_o_crear_label_archivo(svc) -> str:
    """Id de la etiqueta `Donna/Archivado`, creándola si no existe. Se cachea en memoria
    (el id de una etiqueta no cambia una vez creada)."""
    global _label_archivo_id
    if _label_archivo_id:
        return _label_archivo_id
    labels = svc.users().labels().list(userId="me").execute().get("labels", [])
    existente = next((l for l in labels if l["name"] == LABEL_ARCHIVO), None)
    if existente:
        _label_archivo_id = existente["id"]
    else:
        creada = svc.users().labels().create(userId="me", body={
            "name": LABEL_ARCHIVO, "labelListVisibility": "labelShow", "messageListVisibility": "show",
        }).execute()
        _label_archivo_id = creada["id"]
    return _label_archivo_id


async def archivar(ids: list[str]) -> int:
    """Invariante duro: JAMÁS borra. Etiqueta `Donna/Archivado` + quita `INBOX` — recuperable
    de un clic desde esa etiqueta, no expira como la papelera. Devuelve cuántos archivó."""
    if not disponible() or not ids:
        return 0

    def _call():
        svc = _svc()
        label_id = _obtener_o_crear_label_archivo(svc)
        n = 0
        for mid in ids:
            try:
                svc.users().messages().modify(
                    userId="me", id=mid, body={"removeLabelIds": ["INBOX"], "addLabelIds": [label_id]}
                ).execute()
                n += 1
            except Exception:
                logger.exception("Gmail archivar falló para %s", mid)
        return n

    return await asyncio.to_thread(_call)


# ───────────────────────── Adjuntos (estados de cuenta PDF, Finanzas v4) ─────────────────────────

def _adjuntos_pdf(payload: dict) -> list[dict]:
    """Recorre el árbol de partes y junta los adjuntos PDF: {filename, attachment_id, size}."""
    out = []
    fn = payload.get("filename", "")
    body = payload.get("body", {})
    mime = payload.get("mimeType", "")
    if fn and (fn.lower().endswith(".pdf") or mime == "application/pdf") and body.get("attachmentId"):
        out.append({"filename": fn, "attachment_id": body["attachmentId"], "size": body.get("size", 0)})
    for parte in payload.get("parts", []) or []:
        out += _adjuntos_pdf(parte)
    return out


async def buscar_estados(query: str, max_n: int = 30) -> list[dict]:
    """Correos con PDF adjunto (estados de cuenta). Devuelve {id, remitente, asunto, fecha,
    adjuntos:[{filename, attachment_id, size}]}. Solo metadata — los bytes se bajan aparte."""
    if not disponible():
        return []

    def _call():
        svc = _svc()
        res = svc.users().messages().list(
            userId="me", q=f"({query}) has:attachment filename:pdf", maxResults=max_n
        ).execute()
        out = []
        for ref in res.get("messages", []) or []:
            full = svc.users().messages().get(userId="me", id=ref["id"], format="full").execute()
            adj = _adjuntos_pdf(full.get("payload", {}))
            if not adj:
                continue
            hs = {h["name"].lower(): h["value"] for h in full.get("payload", {}).get("headers", [])}
            out.append({"id": full["id"], "remitente": hs.get("from", ""), "asunto": hs.get("subject", ""),
                        "fecha": hs.get("date", ""), "adjuntos": adj})
        return out

    try:
        return await asyncio.to_thread(_call)
    except Exception:
        logger.exception("Gmail buscar_estados falló")
        return []


async def descargar_adjunto(message_id: str, attachment_id: str) -> bytes | None:
    """Bytes de un adjunto. El scope gmail.modify ya permite leerlo. None si falla."""
    if not disponible():
        return None

    def _call():
        att = _svc().users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        return base64.urlsafe_b64decode(att["data"])

    try:
        return await asyncio.to_thread(_call)
    except Exception:
        logger.exception("Gmail descargar_adjunto falló")
        return None
