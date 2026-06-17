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


def _col_letter(idx0: int) -> str:
    """Índice de columna 0-based → letra(s) de Sheets (0→A, 26→AA)."""
    s = ""
    idx0 += 1
    while idx0:
        idx0, r = divmod(idx0 - 1, 26)
        s = chr(65 + r) + s
    return s


async def set_cell(hoja: str, fila: int, col_idx0: int, valor) -> None:
    """Escribe una celda (fila 1-based, columna 0-based)."""
    rango = f"{hoja}!{_col_letter(col_idx0)}{fila}"

    def _call():
        _svc().spreadsheets().values().update(
            spreadsheetId=settings.google_sheet_id,
            range=rango,
            valueInputOption="USER_ENTERED",
            body={"values": [[valor]]},
        ).execute()

    await asyncio.to_thread(_call)


async def upsert_por_clave(hoja: str, clave_col: str, clave_val: str, set_col: str, valor) -> str:
    """Busca la fila donde `clave_col` == `clave_val` y setea `set_col`=valor.
    Si no existe la fila, la crea con la clave + el valor. Devuelve un estado."""
    filas = await get_rows(hoja)
    if not filas:
        return "hoja vacía (sin headers)"
    headers = filas[0]
    if clave_col not in headers or set_col not in headers:
        return f"columna desconocida ({clave_col}/{set_col})"
    ci, si = headers.index(clave_col), headers.index(set_col)
    for n, fila in enumerate(filas[1:], start=2):  # fila 1 = header
        if len(fila) > ci and str(fila[ci]) == str(clave_val):
            await set_cell(hoja, n, si, valor)
            return "actualizado"
    # No existe → crear fila nueva con clave + valor en sus columnas
    nueva = [""] * len(headers)
    nueva[ci] = clave_val
    nueva[si] = valor
    await append_row(hoja, nueva)
    return "creado"
