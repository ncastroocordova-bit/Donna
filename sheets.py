"""Capa de Google Sheets (datos de los módulos). Auth por service account.

Los helpers son async: el cliente de Google es bloqueante, así que el trabajo
real corre en un hilo (asyncio.to_thread) para no tapar el event loop del bot.
"""
import asyncio
import json
import logging

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
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
        _service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return _service


async def append_row(hoja: str, valores: list) -> None:
    def _call():
        _svc().spreadsheets().values().append(
            spreadsheetId=settings.google_sheet_id,
            range=f"{hoja}!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [valores]},
        ).execute()

    await asyncio.to_thread(_call)


async def get_rows(hoja: str, rango: str = "A:Z") -> list[list]:
    def _call():
        r = (
            _svc()
            .spreadsheets()
            .values()
            .get(spreadsheetId=settings.google_sheet_id, range=f"{hoja}!{rango}")
            .execute()
        )
        return r.get("values", [])

    return await asyncio.to_thread(_call)


async def get_dicts(hoja: str) -> list[dict]:
    """Lee una hoja con encabezados en la fila 1 y devuelve lista de dicts."""
    filas = await get_rows(hoja)
    if not filas:
        return []
    headers = filas[0]
    return [dict(zip(headers, fila)) for fila in filas[1:]]
