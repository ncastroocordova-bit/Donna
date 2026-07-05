"""Evals del autodiagnóstico lean (core/diagnostico.py + los helpers de sheets). Puros: sin
Supabase real, sin Sheets. Se prueban la firma/dedup, la respuesta en carácter, la degradación
ante Supabase caído, el guardián de schema y la verificación de escritura."""
import asyncio

from core import diagnostico, sheets


# ───────────────────────── firma / texto / safe_json ─────────────────────────

def test_firma_agrupa_el_mismo_bug_ignorando_numeros():
    a = diagnostico._firma("rec_agregar", "tool_excepcion", "ValueError en fila 5")
    b = diagnostico._firma("rec_agregar", "tool_excepcion", "ValueError en fila 9")
    assert a == b                       # los números → '#', misma firma (dedup)
    assert diagnostico._firma("rec_agregar", "tool_excepcion", "KeyError otro") != a


def test_texto_para_nico_en_caracter_sin_stacktrace():
    t = diagnostico.texto_para_nico({"id": 12, "frecuencia": 3}, "anotar el recordatorio")
    assert "Traceback" not in t
    assert "#12" in t and "3 veces" in t
    assert "anotar el recordatorio" in t and "Claude Code" in t


def test_safe_json_recorta_strings_conserva_numeros():
    d = diagnostico._safe_json({"texto": "x" * 500, "monto": 1000, "flag": True})
    assert len(d["texto"]) == 200 and d["monto"] == 1000 and d["flag"] is True
    assert diagnostico._safe_json("no es dict") is None


def test_registrar_con_supabase_caido_no_lanza(monkeypatch):
    async def _boom():
        raise RuntimeError("supabase down")
    monkeypatch.setattr(diagnostico.memory, "_get_db", _boom)
    inc = asyncio.run(diagnostico.registrar("rec_agregar", "tool_excepcion", "algo", error_texto="err"))
    assert inc["id"] is None and inc["tool"] == "rec_agregar"   # dict mínimo, sin excepción


# ───────────────────────── verificar_headers (guardián de schema) ─────────────────────────

def test_verificar_headers_detecta_columna_faltante(monkeypatch):
    async def _rows(hoja, rango="A:Z", sheet_id=None, value_render="FORMATTED_VALUE"):
        return [["🔔 banner de la hoja"], ["Recordatorio", "Tipo", "Día / Fecha"]]   # sin 'Activo'
    monkeypatch.setattr(sheets, "get_rows", _rows)
    problemas = asyncio.run(sheets.verificar_headers({"Recordatorios": ["Recordatorio", "Activo"]}))
    assert len(problemas) == 1 and "Activo" in problemas[0]


def test_verificar_headers_ok_no_reporta(monkeypatch):
    async def _rows(hoja, rango="A:Z", sheet_id=None, value_render="FORMATTED_VALUE"):
        return [["Recordatorio", "Tipo", "Activo"]]
    monkeypatch.setattr(sheets, "get_rows", _rows)
    assert asyncio.run(sheets.verificar_headers({"Recordatorios": ["Recordatorio", "Activo"]})) == []


# ───────────────────────── append_row_verificado ─────────────────────────

def _mock_append_y_relee(monkeypatch, ultima_fila):
    async def _append(hoja, valores, sheet_id=None):
        pass
    async def _rows(hoja, rango="A:Z", sheet_id=None, value_render="FORMATTED_VALUE"):
        return [["hdr"], ultima_fila]
    monkeypatch.setattr(sheets, "append_row", _append)
    monkeypatch.setattr(sheets, "get_rows", _rows)


def test_append_verificado_detecta_columna_corrida(monkeypatch):
    # La fila releída tiene el Estado (col 4) vacío → escritura corrida.
    _mock_append_y_relee(monkeypatch, ["Pago X", "Mensual", "1", "", "", 0, "", "Sí"])
    reg = {}
    async def _fake_reg(tool, tipo, resumen, *, input_json=None, error_texto=""):
        reg.update({"tool": tool, "tipo": tipo})
        return {"id": 1}
    monkeypatch.setattr(diagnostico, "registrar", _fake_reg)
    ok = asyncio.run(sheets.append_row_verificado(
        "Recordatorios", ["Pago X", "Mensual", "1", "", "Pendiente", 0, "", "Sí"],
        verificar_cols=[4], tool="rec_agregar"))
    assert ok is False and reg["tipo"] == "verificacion_escritura"


def test_append_verificado_ok_no_registra(monkeypatch):
    _mock_append_y_relee(monkeypatch, ["Pago X", "Mensual", "1", "", "Pendiente", 0, "", "Sí"])
    ok = asyncio.run(sheets.append_row_verificado(
        "Recordatorios", ["Pago X", "Mensual", "1", "", "Pendiente", 0, "", "Sí"],
        verificar_cols=[0, 4, 7], tool="rec_agregar"))
    assert ok is True


# ───────────────────────── tool diag_estado ─────────────────────────

def test_diag_estado_lista_pendientes(monkeypatch):
    async def _pend():
        return [{"id": 7, "resumen": "rec_agregar tiró excepción", "frecuencia": 3}]
    monkeypatch.setattr(diagnostico, "pendientes", _pend)
    t = asyncio.run(diagnostico._t_estado({}))
    assert "#7" in t and "3x" in t


def test_diag_estado_sin_incidentes(monkeypatch):
    async def _pend():
        return []
    monkeypatch.setattr(diagnostico, "pendientes", _pend)
    assert "orden" in asyncio.run(diagnostico._t_estado({})).lower()
