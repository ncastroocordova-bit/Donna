"""Capa de Google Sheets (datos de los módulos). Auth por service account.

v7 usa DOS planillas: Vida_v6 (vida) y Finanzas_vigente (plata). Cada helper toma
un `sheet_id` opcional; por defecto apunta a Vida. Finanzas pasa `sheets.fin_id()`.

Los helpers son async: el cliente de Google es bloqueante, así que el trabajo real
corre en un hilo (asyncio.to_thread) para no tapar el event loop del bot.
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


def vida_id() -> str:
    return settings.sheet_vida


def fin_id() -> str:
    return settings.sheet_finanzas


def _sid(sheet_id: str | None) -> str:
    return sheet_id or vida_id()


def _rng(hoja: str, a1: str) -> str:
    """A1 con el nombre de hoja siempre entre comillas simples (Sheets lo exige cuando
    el título lleva espacios o tildes, ej. 'Tarjetas de Crédito'!B85). Comillas internas → dobladas."""
    return f"'{hoja.replace(chr(39), chr(39) * 2)}'!{a1}"


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


async def append_row(hoja: str, valores: list, sheet_id: str | None = None) -> None:
    def _call():
        _svc().spreadsheets().values().append(
            spreadsheetId=_sid(sheet_id),
            range=_rng(hoja, "A:Z"),
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [valores]},
        ).execute()

    await asyncio.to_thread(_call)


async def get_rows(
    hoja: str, rango: str = "A:Z", sheet_id: str | None = None, value_render: str = "FORMATTED_VALUE"
) -> list[list]:
    """Lee un rango. `value_render='UNFORMATTED_VALUE'` devuelve números crudos (sin
    separadores de miles ni símbolo de moneda) — úsalo para leer cifras que vas a parsear,
    así el locale del Sheet (coma vs punto) no rompe el cálculo."""
    def _call():
        r = (
            _svc()
            .spreadsheets()
            .values()
            .get(spreadsheetId=_sid(sheet_id), range=_rng(hoja, rango), valueRenderOption=value_render)
            .execute()
        )
        return r.get("values", [])

    return await asyncio.to_thread(_call)


def _fila_headers(filas: list[list], clave: str | None = None) -> tuple[int, list]:
    """Localiza la fila de encabezados saltando un posible banner de título (las hojas canónicas
    traen p.ej. '🌙 DIARIO — …' en la fila 1, con 1 sola celda). Si se pasa `clave`, busca la
    fila que la contenga; si no, la primera con ≥2 celdas no vacías. Devuelve (idx_0based, headers)."""
    for i, fila in enumerate(filas):
        if clave is not None:
            if clave in fila:
                return i, fila
        elif len([c for c in fila if str(c).strip()]) >= 2:
            return i, fila
    return -1, []


async def get_dicts(hoja: str, sheet_id: str | None = None) -> list[dict]:
    """Lee una hoja y devuelve lista de dicts. Encuentra la fila de headers (salta el banner)."""
    filas = await get_rows(hoja, sheet_id=sheet_id)
    h_idx, headers = _fila_headers(filas)
    if h_idx < 0:
        return []
    return [dict(zip(headers, fila)) for fila in filas[h_idx + 1:]]


async def get_celda(hoja: str, celda: str, sheet_id: str | None = None) -> str:
    """Lee UNA celda por referencia A1 (ej. 'B85'). Devuelve '' si está vacía.

    Lo usa el faro de deuda (Plan_Construccion_v7 Paso 1.5C): la planilla
    Finanzas_vigente trae las métricas ya calculadas en celdas fijas."""
    def _call():
        r = (
            _svc()
            .spreadsheets()
            .values()
            .get(spreadsheetId=_sid(sheet_id), range=_rng(hoja, celda))
            .execute()
        )
        vals = r.get("values", [])
        return str(vals[0][0]) if vals and vals[0] else ""

    return await asyncio.to_thread(_call)


def _col_letter(idx0: int) -> str:
    """Índice de columna 0-based → letra(s) de Sheets (0→A, 26→AA)."""
    s = ""
    idx0 += 1
    while idx0:
        idx0, r = divmod(idx0 - 1, 26)
        s = chr(65 + r) + s
    return s


async def set_cell(hoja: str, fila: int, col_idx0: int, valor, sheet_id: str | None = None) -> None:
    """Escribe una celda (fila 1-based, columna 0-based)."""
    rango = _rng(hoja, f"{_col_letter(col_idx0)}{fila}")

    def _call():
        _svc().spreadsheets().values().update(
            spreadsheetId=_sid(sheet_id),
            range=rango,
            valueInputOption="USER_ENTERED",
            body={"values": [[valor]]},
        ).execute()

    await asyncio.to_thread(_call)


async def upsert_por_clave(
    hoja: str, clave_col: str, clave_val: str, set_col: str, valor, sheet_id: str | None = None
) -> str:
    """Busca la fila donde `clave_col` == `clave_val` y setea `set_col`=valor.
    Si no existe la fila, la crea con la clave + el valor. Devuelve un estado."""
    filas = await get_rows(hoja, sheet_id=sheet_id)
    h_idx, headers = _fila_headers(filas, clave_col)
    if h_idx < 0:
        return "hoja vacía (sin headers)"
    if clave_col not in headers or set_col not in headers:
        return f"columna desconocida ({clave_col}/{set_col})"
    ci, si = headers.index(clave_col), headers.index(set_col)
    # Datos = filas tras el header. start = nº de fila 1-based de la primera fila de datos.
    for n, fila in enumerate(filas[h_idx + 1:], start=h_idx + 2):
        if len(fila) > ci and str(fila[ci]) == str(clave_val):
            await set_cell(hoja, n, si, valor, sheet_id=sheet_id)
            return "actualizado"
    # No existe → crear fila nueva con clave + valor en sus columnas
    nueva = [""] * len(headers)
    nueva[ci] = clave_val
    nueva[si] = valor
    await append_row(hoja, nueva, sheet_id=sheet_id)
    return "creado"
