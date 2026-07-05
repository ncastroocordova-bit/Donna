"""Evals del Módulo 3 (Compras, Fase 1 — lista manual). Puros: sin red, sin Sheets.
Cubren el eval del roadmap: 'falta X' agrega sin duplicar · 'dame la lista' devuelve lo
pendiente · marcar comprado lo saca y registra la fecha."""
import asyncio

from core import flows
from modules import compras


# ───────────────────────── Parser determinista ─────────────────────────

def test_parsear_items_varias_frases():
    assert compras._parsear_items("Donna falta toalla nova y se acabó el atún") == ["Toalla Nova", "Atún"]
    assert compras._parsear_items("queda poco arroz, anótalo") == ["Arroz"]
    assert compras._parsear_items("necesito comprar pan y leche") == ["Pan", "Leche"]
    assert compras._parsear_items("papel de baño") == ["Papel De Baño"]     # multi-palabra intacto
    assert compras._parsear_items("") == []


def test_parsear_no_duplica_en_la_misma_frase():
    assert compras._parsear_items("arroz, arroz y arroz") == ["Arroz"]


# ───────────────────────── Lista / agregar / comprado ─────────────────────────

def _fila(item, estado="pendiente"):
    return {compras.COLS["item"]: item, compras.COLS["estado"]: estado}


def _mock_dicts(monkeypatch, filas):
    async def _fake(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return filas
    monkeypatch.setattr(compras.sheets, "get_dicts", _fake)


def test_pendientes_filtra_comprados(monkeypatch):
    _mock_dicts(monkeypatch, [_fila("Arroz"), _fila("Atún", "comprado"), _fila("Pan")])
    assert asyncio.run(compras.pendientes()) == ["Arroz", "Pan"]


def test_agregar_no_duplica(monkeypatch):
    _mock_dicts(monkeypatch, [_fila("Arroz")])   # arroz ya pendiente
    capt = []

    async def _fake_append(hoja, valores, sheet_id=None):
        capt.append(valores)

    monkeypatch.setattr(compras.sheets, "append_row", _fake_append)
    agregados = asyncio.run(compras.agregar(["arroz", "Atún"]))
    assert agregados == ["Atún"]                          # arroz se salta (ya estaba)
    assert len(capt) == 1
    assert capt[0][0] == "Atún" and capt[0][1] == "pendiente"


def test_marcar_comprado_setea_estado_y_fecha(monkeypatch):
    headers = ["Item", "Estado", "Fecha_Agregado", "Fecha_Comprado", "Categoria"]
    filas = [["🛒 banner"], headers,
             ["Arroz", "pendiente", "2026-07-01", "", ""],
             ["Atún", "pendiente", "2026-07-01", "", ""]]

    async def _fake_rows(hoja, rango="A:Z", sheet_id=None, value_render="FORMATTED_VALUE"):
        return filas

    sets = []

    async def _fake_set(hoja, fila, col, valor, sheet_id=None):
        sets.append((fila, col, valor))

    monkeypatch.setattr(compras.sheets, "get_rows", _fake_rows)
    monkeypatch.setattr(compras.sheets, "set_cell", _fake_set)
    ok = asyncio.run(compras.marcar_comprado("arroz"))     # match por substring, case-insensitive
    assert ok is True
    # banner(1) + headers(2) + arroz(3): Estado col 1 = 'comprado', Fecha_Comprado col 3 seteada
    assert (3, 1, "comprado") in sets
    assert any(s[0] == 3 and s[1] == 3 for s in sets)


def test_marcar_comprado_no_encuentra(monkeypatch):
    async def _fake_rows(hoja, rango="A:Z", sheet_id=None, value_render="FORMATTED_VALUE"):
        return [["Item", "Estado", "Fecha_Agregado", "Fecha_Comprado", "Categoria"]]
    monkeypatch.setattr(compras.sheets, "get_rows", _fake_rows)
    assert asyncio.run(compras.marcar_comprado("chocolate")) is False


# ───────────────────────── Teclado tocable ─────────────────────────

def test_teclado_compras_un_boton_por_item():
    kb = flows.teclado_compras(["Arroz", "Atún"])
    cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert cbs == ["cmp:ok:Arroz", "cmp:ok:Atún"]
