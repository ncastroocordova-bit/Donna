"""Módulo Compras (`cmp_`). Fase 1 = lista manual del súper.

- `cmp_agregar` ("Donna falta toalla nova" / "queda poco arroz, anótalo") → agrega a la lista,
  sin duplicar lo que ya está pendiente.
- `cmp_lista` ("dame la lista del súper") → devuelve exactamente lo pendiente. La versión con
  toques (marcar comprado tocando) vive en core/flows.py (`/lista`).
- `cmp_comprado` ("ya lo compré", "tacha el arroz") → lo marca comprado (sale de la lista).

Hoja `Compras`: Item · Estado (pendiente|comprado) · Fecha_Agregado · Fecha_Comprado · Categoria.

Fase 2 (predictor de reposición: "puede que toque comprar arroz") DIFERIDA por canon — no acá.
Parser determinista, cero LLM (contrato de costos).
"""
import logging
import re
from datetime import datetime

from config import settings
from core import sheets

logger = logging.getLogger(__name__)

HOJA = "Compras"
COLS = {"item": "Item", "estado": "Estado", "agregado": "Fecha_Agregado",
        "comprado": "Fecha_Comprado", "categoria": "Categoria"}

# Ruido a quitar antes de extraer el/los producto(s): disparadores + relleno.
_RUIDO = re.compile(
    r"\b(donna|por ?favor|porfa|me falta|falta[n]?|queda[n]? poco|se me acab[óo]|se acab[óo]|"
    r"necesito|hay que|tengo que|comprar|compra|an[óo]ta(?:me|lo)?|ap[uú]nta(?:me|lo)?|"
    r"agr[ée]ga(?:r|me|lo)?|tacha(?:r|me|lo)?|s[aá]ca(?:r|lo)?|borra(?:r|lo)?|"
    r"para el s[uú]per|del s[uú]per|a la lista|en la lista|de la lista)\b", re.I)
_ART = re.compile(r"^(el|la|los|las|un|una|unos|unas)\s+", re.I)


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


def _norm(s: str) -> str:
    return " ".join(str(s or "").lower().split()).strip()


def _parsear_items(texto: str) -> list[str]:
    """Extrae los productos de una frase, sin LLM. Quita disparadores/relleno, separa por comas
    o ' y ', y saca el artículo inicial. 'Donna falta toalla nova y se acabó el atún' →
    ['Toalla Nova', 'Atún']."""
    t = _RUIDO.sub(" ", texto or "")
    items, vistos = [], set()
    for p in re.split(r"[,;\n]|\sy\s", t, flags=re.I):
        p = _ART.sub("", " ".join(p.split()).strip(" .:"))
        if len(p) >= 2 and _norm(p) not in vistos:
            vistos.add(_norm(p))
            items.append(p.title())
    return items[:10]


def _es_comprado(fila: dict) -> bool:
    return str(fila.get(COLS["estado"], "")).strip().lower().startswith("comprad")


async def pendientes() -> list[str]:
    """Items de la lista que siguen pendientes (no comprados), en orden de agregado."""
    try:
        filas = await sheets.get_dicts(HOJA)
    except Exception:
        logger.exception("compras.pendientes: no pude leer la hoja")
        return []
    return [str(f.get(COLS["item"], "")).strip() for f in filas
            if str(f.get(COLS["item"], "")).strip() and not _es_comprado(f)]


async def agregar(items: list[str]) -> list[str]:
    """Agrega los items que no estén ya pendientes (dedup por nombre normalizado). Devuelve los
    realmente agregados. Orden real de la hoja: Item · Estado · Fecha_Agregado · Fecha_Comprado ·
    Categoria."""
    ya = {_norm(p) for p in await pendientes()}
    agregados = []
    for it in items:
        if _norm(it) in ya:
            continue
        ya.add(_norm(it))
        try:
            await sheets.append_row(HOJA, [it, "pendiente", _hoy(), "", ""])
            agregados.append(it)
        except Exception:
            logger.exception("compras.agregar: no pude anotar %s", it)
    return agregados


async def marcar_comprado(item: str) -> bool:
    """Marca un item pendiente como comprado (match por substring, case-insensitive) → setea
    Estado=comprado + Fecha_Comprado. Devuelve si encontró la fila."""
    q = _norm(item)
    if not q:
        return False
    try:
        filas = await sheets.get_rows(HOJA)
    except Exception:
        logger.exception("compras.marcar_comprado: no pude leer la hoja")
        return False
    h_idx, headers = sheets._fila_headers(filas)
    if h_idx < 0:
        return False
    idx = {c: headers.index(v) for c, v in COLS.items() if v in headers}
    if "item" not in idx or "estado" not in idx:
        return False

    def _get(fila, col):
        i = idx.get(col, -1)
        return str(fila[i]).strip() if 0 <= i < len(fila) else ""

    for n, fila in enumerate(filas[h_idx + 1:], start=h_idx + 2):
        item_fila = _get(fila, "item")
        if not item_fila or _get(fila, "estado").lower().startswith("comprad"):
            continue
        if q in _norm(item_fila) or _norm(item_fila) in q:
            await sheets.set_cell(HOJA, n, idx["estado"], "comprado")
            if "comprado" in idx:
                await sheets.set_cell(HOJA, n, idx["comprado"], _hoy())
            return True
    return False


# ───────────────────────── Handlers de tools ─────────────────────────

async def _t_agregar(inp: dict) -> str:
    items = _parsear_items(inp.get("texto", ""))
    if not items:
        return "¿Qué anoto para el súper?"
    agregados = await agregar(items)
    if not agregados:
        return "Eso ya estaba en tu lista del súper."
    return f"Anotado para el súper: {', '.join(agregados)}. Yo llevo la cuenta."


async def _t_lista(inp: dict) -> str:
    pend = await pendientes()
    if not pend:
        return "Tu lista del súper está vacía."
    return f"Lista del súper ({len(pend)}):\n" + "\n".join(f"• {p}" for p in pend)


async def _t_comprado(inp: dict) -> str:
    items = _parsear_items(inp.get("texto", ""))
    marcados = [it for it in items if await marcar_comprado(it)]
    if not marcados:
        return "No encontré eso en tu lista del súper."
    return f"Listo, lo saqué de la lista: {', '.join(marcados)}."


TOOLS = [
    {
        "name": "cmp_agregar",
        "description": "OBLIGATORIO cuando Nico dice que falta algo para el súper o que le anotes un producto ('falta arroz', 'queda poco atún, anótalo', 'agrega toalla nova'). Lo suma a la lista del súper.",
        "input_schema": {"type": "object", "properties": {"texto": {"type": "string", "description": "La frase tal cual la dijo Nico"}}, "required": ["texto"]},
    },
    {
        "name": "cmp_lista",
        "description": "OBLIGATORIO cuando Nico pide su lista del súper / qué tiene que comprar. Devuelve solo lo pendiente. No inventes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cmp_comprado",
        "description": "Cuando Nico dice que ya compró o que taches algo de la lista del súper ('ya compré el arroz', 'tacha el atún'). Lo marca comprado. NO es para registrar un gasto de plata.",
        "input_schema": {"type": "object", "properties": {"texto": {"type": "string", "description": "La frase tal cual la dijo Nico"}}, "required": ["texto"]},
    },
]

HANDLERS = {
    "cmp_agregar": _t_agregar,
    "cmp_lista": _t_lista,
    "cmp_comprado": _t_comprado,
}
