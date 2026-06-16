"""Lectura de Google Calendar para el brief. Auth por service account.

El service account lee el calendario que Nico le comparta (GOOGLE_CALENDAR_ID).
"""
import asyncio
import json
import logging
from datetime import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
_service = None


def _get_creds(scopes):
    val = settings.google_credentials_json.strip()
    if val.startswith("{"):
        return Credentials.from_service_account_info(json.loads(val), scopes=scopes)
    return Credentials.from_service_account_file(val, scopes=scopes)


def _svc():
    global _service
    if _service is None:
        creds = _get_creds(SCOPES)
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _service


async def eventos_de_hoy() -> list[dict]:
    """Eventos de hoy en la zona de Nico. Degrada a [] si algo falla."""
    def _call():
        ahora = datetime.now(settings.tz)
        inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        fin = ahora.replace(hour=23, minute=59, second=59, microsecond=0)
        r = (
            _svc()
            .events()
            .list(
                calendarId=settings.google_calendar_id,
                timeMin=inicio.isoformat(),
                timeMax=fin.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return [
            {
                "titulo": e.get("summary", "Sin título"),
                "hora": e["start"].get("dateTime", e["start"].get("date", "")),
            }
            for e in r.get("items", [])
        ]

    try:
        return await asyncio.to_thread(_call)
    except Exception:
        logger.exception("No pude leer el calendario; sigo sin agenda.")
        return []
