"""Evals del digest vivo (rediseño 2026-07-16). Puros: sin Telegram, sin Supabase, sin Sheets.

Cubren las reglas del paquete: un solo mensaje que se edita (ancla + refresco), chips de
categoría top-3 que excluyen la actual, ítems como excepciones (no re-revisar todo), toggles
de un toque, y el tope de 64 bytes de callback_data que Telegram corta en silencio.
"""
import asyncio

from core import flows
from modules import finanzas

UUID = "a" * 36  # largo real de un id del buffer (uuid4)

CATS = {"alimentacion": "Alimentación", "chancheria": "Chanchería", "transporte": "Transporte",
        "tecnologia": "Tecnología", "hogar": "Hogar", "otro gasto": "Otro Gasto"}


def _con_catalogo(monkeypatch):
    monkeypatch.setattr(finanzas, "_cache_categorias", dict(CATS))


# ───────────────────────── sugerencias de categoría (top-3) ─────────────────────────

def test_sugerencias_aprendidas_primero_y_excluye_la_actual(monkeypatch):
    """Lo aprendido del comercio va primero, y la categoría ACTUAL no aparece: si Nico está
    corrigiendo, la actual es justo la equivocada."""
    _con_catalogo(monkeypatch)

    async def _comercios():
        return [{"patron": "jumbo", "nombre": "Jumbo", "categoria": "Hogar"}]
    monkeypatch.setattr(finanzas.memory, "get_comercios", _comercios)

    s = asyncio.run(finanzas.sugerencias_categoria("JUMBO LOS ANGELES", actual="Alimentación"))
    assert s[0] == "Hogar"                      # la regla aprendida manda
    assert "Alimentación" not in s              # la actual queda fuera
    assert len(s) == 3


def test_sugerencias_degrada_sin_supabase(monkeypatch):
    _con_catalogo(monkeypatch)

    async def _boom():
        raise RuntimeError("supabase down")
    monkeypatch.setattr(finanzas.memory, "get_comercios", _boom)

    s = asyncio.run(finanzas.sugerencias_categoria("copec", actual=""))
    assert s and s[0] == "Transporte"           # keywords siguen funcionando sin lo aprendido


# ───────────────────────── ítems: excepciones, no re-revisión ─────────────────────────

ITEMS = [
    {"item": "arroz", "precio": 1290, "categoria": "Alimentación", "intencion": "Necesario", "predecible": True},
    {"item": "leche", "precio": 990, "categoria": "Alimentación", "intencion": "Necesario", "predecible": False},
    {"item": "", "precio": 2000, "categoria": "Alimentación", "intencion": "Necesario", "predecible": False},   # sin nombre
    {"item": "no sé qué", "precio": 0, "categoria": "", "intencion": "", "predecible": False},                  # ilegible
]


def test_item_dudoso_criterio():
    assert not flows._item_dudoso(ITEMS[0])
    assert flows._item_dudoso(ITEMS[2])         # sin nombre
    assert flows._item_dudoso(ITEMS[3])         # sin categoría y precio 0


def test_grilla_muestra_solo_las_excepciones():
    kb = flows._teclado_items(UUID, ITEMS, ver_todos=False).inline_keyboard
    filas_item = [f for f in kb if f[0].callback_data.startswith("dgi:c:")]
    assert len(filas_item) == 2                 # solo los 2 dudosos, no los 4
    assert any("Ver los 4" in b.text for f in kb for b in f)
    assert any(b.callback_data == f"dgi:ok:{UUID}" for f in kb for b in f)


def test_grilla_ver_todos_trae_los_4():
    kb = flows._teclado_items(UUID, ITEMS, ver_todos=True).inline_keyboard
    filas_item = [f for f in kb if f[0].callback_data.startswith("dgi:c:")]
    assert len(filas_item) == 4


def test_toggle_deseo_cicla():
    assert flows._sig_deseo("Necesario") == "Inversion"
    assert flows._sig_deseo("Deseo") == "Necesario"
    assert flows._sig_deseo("") == "Necesario"


def test_callback_data_cabe_en_64_bytes():
    """Telegram corta callback_data en 64 bytes SIN error: un id de buffer real (uuid de 36)
    con índice de dos dígitos tiene que caber en el peor caso de cada familia."""
    peores = [f"dgi:c:{UUID}:11:a", f"dic:{UUID}:11:999", f"dgc:{UUID}:desc", f"digest:items:{UUID}"]
    for cb in peores:
        assert len(cb.encode("utf-8")) <= 64, cb


# ───────────────────────── el digest vivo: texto y refresco ─────────────────────────

D = {"movimientos": [
        {"id": "m1", "tipo": "Gasto", "categoria": "Alimentación", "comercio": "Jumbo", "monto": 32000,
         "intencion": "Necesario", "items": ITEMS, "n_items": 4, "dudosa": False, "motivo_duda": ""},
        {"id": "m2", "tipo": "Gasto", "categoria": "Transporte", "comercio": "Uber", "monto": 3300,
         "intencion": "", "items": [], "n_items": 0, "dudosa": True, "motivo_duda": "monto raro"},
     ], "total": 35300, "n": 2, "n_dudosas": 1}


def test_texto_digest_marca_estados_sin_instrucciones():
    flows._revisados.clear()
    t = flows._texto_digest(D)
    assert "2 por revisar" in t                  # ítems dudosos visibles por línea
    assert "⚠️ monto raro" in t
    assert "Toca «Aceptar todo»" not in t        # las instrucciones son botones, no párrafos
    flows._revisados.add("m1")
    assert "ítems ✓" in flows._texto_digest(D)
    flows._revisados.clear()


def test_vista_correccion_linea_es_de_chips(monkeypatch):
    _con_catalogo(monkeypatch)

    async def _comercios():
        return []
    monkeypatch.setattr(finanzas.memory, "get_comercios", _comercios)

    m = dict(D["movimientos"][1], id=UUID)
    texto, kb = asyncio.run(flows._vista_correccion_linea(m, todo_el_catalogo=False))
    cbs = [b.callback_data for f in kb.inline_keyboard for b in f]
    assert "Elige la categoría:" in texto
    assert any(c.startswith(f"dgc:{UUID}:") and c.split(":")[-1].isdigit() for c in cbs)  # chips
    assert f"dgc:{UUID}:mas" in cbs and f"dgc:{UUID}:desc" in cbs and "digest:volver" in cbs
    assert f"dgc:{UUID}:esc" not in cbs          # escribir solo aparece en el catálogo completo

    _, kb_full = asyncio.run(flows._vista_correccion_linea(m, todo_el_catalogo=True))
    cbs_full = [b.callback_data for f in kb_full.inline_keyboard for b in f]
    assert f"dgc:{UUID}:esc" in cbs_full


class _BotDigest:
    def __init__(self, falla_edit=False):
        self.falla_edit = falla_edit
        self.ediciones, self.enviados = [], []

    async def edit_message_text(self, texto, chat_id=None, message_id=None, reply_markup=None):
        if self.falla_edit:
            raise RuntimeError("message to edit not found")
        self.ediciones.append((chat_id, message_id))

    async def send_message(self, chat_id, texto, reply_markup=None):
        self.enviados.append(chat_id)
        return type("M", (), {"message_id": 999})()


def _mock_armar(monkeypatch):
    async def _d():
        return D
    monkeypatch.setattr(flows.finanzas, "armar_digest", _d)


def test_refrescar_edita_el_ancla_no_apila(monkeypatch):
    _mock_armar(monkeypatch)
    flows._digest_msg[123] = 55
    bot = _BotDigest()
    asyncio.run(flows.refrescar_digest(bot, 123))
    assert bot.ediciones == [(123, 55)] and bot.enviados == []   # editó; NO mandó otro digest


def test_refrescar_sin_ancla_manda_y_reancla(monkeypatch):
    _mock_armar(monkeypatch)
    flows._digest_msg.pop(124, None)
    bot = _BotDigest()
    asyncio.run(flows.refrescar_digest(bot, 124))
    assert bot.enviados == [124] and flows._digest_msg[124] == 999


def test_refrescar_con_ancla_muerta_degrada_a_mensaje_nuevo(monkeypatch):
    _mock_armar(monkeypatch)
    flows._digest_msg[125] = 55
    bot = _BotDigest(falla_edit=True)
    asyncio.run(flows.refrescar_digest(bot, 125))
    assert bot.enviados == [125] and flows._digest_msg[125] == 999
