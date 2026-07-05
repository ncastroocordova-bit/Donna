"""Evals de la Fase 0 · bloque UX (C2 Mes activo · C3 captura de sueño/ventanas ·
C4 vencido-insiste · C6 ancla de fecha del panel de cierre).

Cubre las piezas DETERMINISTAS (teclados + funciones de escritura con fecha); el ruteo real de
Telegram (on_callback) se ejerce por Telegram en el smoke manual. Sin red, sin Sheets: se
monkeypatchea la capa de escritura.
"""
import asyncio
from datetime import date

from core import flows, scheduler
from modules import recordatorios, salud


def _cbs(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row]


def _mock_set(monkeypatch):
    calls = []

    async def _fake(campo, valor, fecha=None):
        calls.append((campo, valor, fecha))
        return "actualizado"

    monkeypatch.setattr(salud, "_set", _fake)
    return calls


# ───────────────────────── C6 · ancla de fecha del panel ─────────────────────────

def test_teclado_cierre_ancla_la_fecha_en_cada_callback():
    cbs = _cbs(flows.teclado_cierre(fecha="2026-07-01"))
    assert cbs, "el panel no debería salir vacío"
    assert all(c.endswith("|2026-07-01") for c in cbs)


def test_teclado_cierre_sin_fecha_no_ancla():
    cbs = _cbs(flows.teclado_cierre(fecha=""))
    assert all("|" not in c for c in cbs)


def test_marcar_habito_pasa_la_fecha(monkeypatch):
    calls = _mock_set(monkeypatch)

    async def _fake_racha(campo):
        return 3

    monkeypatch.setattr(salud, "calcular_racha", _fake_racha)
    asyncio.run(salud.marcar_habito("ejercicio", "Sí", fecha="2026-07-01"))
    assert calls[-1] == ("ejercicio", "Sí", "2026-07-01")


def test_registrar_animo_pasa_la_fecha(monkeypatch):
    calls = _mock_set(monkeypatch)
    asyncio.run(salud.registrar_animo("3", fecha="2026-07-01"))
    assert calls[-1] == ("animo", "3", "2026-07-01")


# ───────────────────────── C3 · captura de sueño/ventanas ─────────────────────────

def test_teclado_cierre_tiene_fila_de_primera_comida():
    cbs = _cbs(flows.teclado_cierre(fecha="2026-07-01"))
    assert any(c.startswith("pcom:") for c in cbs)


def test_teclado_cierre_agua_y_proteina_por_cantidad():
    cbs = _cbs(flows.teclado_cierre(fecha="2026-07-01"))
    assert any(c.startswith("agua:") for c in cbs)     # agua por litros (1/2/3)
    assert any(c.startswith("prot:") for c in cbs)     # proteína por gramos (80/90/100)
    # ya no es el binario sí/no
    assert not any(c.startswith("hab:agua") or c.startswith("hab:proteina") for c in cbs)


def test_teclado_cierre_ultima_comida_en_una_sola_fila():
    kb = flows.teclado_cierre(fecha="2026-07-01").inline_keyboard
    filas_comida = [row for row in kb if any("🍽" in b.text for b in row)]
    assert len(filas_comida) == 1 and len(filas_comida[0]) == 4   # línea horizontal de 4
    textos = [b.text for b in filas_comida[0]]
    assert any("21+" in t for t in textos)                        # última opción es 21+


def test_chips_de_hora_dormi_y_despertar():
    assert all(c.startswith("sh:d:") for c in _cbs(flows.teclado_hora_dormi()))
    assert all(c.startswith("sh:w:") for c in _cbs(flows.teclado_hora_despertar()))


def test_registrar_hora_dormi_valida_escribe(monkeypatch):
    calls = _mock_set(monkeypatch)
    asyncio.run(salud.registrar_hora_dormi("23:30", fecha="2026-07-01"))
    assert calls[-1] == ("hora_dormi", "23:30", "2026-07-01")


def test_registrar_hora_dormi_invalida_no_escribe(monkeypatch):
    calls = _mock_set(monkeypatch)
    r = asyncio.run(salud.registrar_hora_dormi("mañana temprano"))
    assert calls == []
    assert "HH:MM" in r


def test_registrar_hora_primera_comida_pasa_la_fecha(monkeypatch):
    calls = _mock_set(monkeypatch)
    asyncio.run(salud.registrar_hora("primera_comida", "08:00", fecha="2026-07-01"))
    assert calls[-1] == ("primera_comida", "08:00", "2026-07-01")


# ───────────────────────── C2 · Mes activo ─────────────────────────

def test_mes_config_lee_el_valor(monkeypatch):
    async def _fake(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return [{"Parámetro": "Mes activo", "Valor": "6", "Nota": ""}]
    monkeypatch.setattr(scheduler.sheets, "get_dicts", _fake)
    assert asyncio.run(scheduler._mes_config()) == 6


def test_mes_config_ausente_da_none(monkeypatch):
    async def _fake(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return [{"Parámetro": "hora_brief", "Valor": "08:00"}]
    monkeypatch.setattr(scheduler.sheets, "get_dicts", _fake)
    assert asyncio.run(scheduler._mes_config()) is None


def test_teclado_mes_activo_callback():
    assert "cfg:mes:7" in _cbs(flows.teclado_mes_activo(7))


# ───────────────────────── C4 · vencido-insiste ─────────────────────────

def _rec(nombre, tipo, dia_fecha, estado="Pendiente", activo="Sí"):
    return {
        recordatorios.COLS["recordatorio"]: nombre, recordatorios.COLS["tipo"]: tipo,
        recordatorios.COLS["dia_fecha"]: dia_fecha, recordatorios.COLS["monto"]: "",
        recordatorios.COLS["estado"]: estado, recordatorios.COLS["posposiciones"]: 0,
        recordatorios.COLS["ultima_accion"]: "", recordatorios.COLS["activo"]: activo,
    }


def test_vencidos_solo_devuelve_los_vencidos(monkeypatch):
    monkeypatch.setattr(recordatorios, "_hoy", lambda: date(2026, 7, 1))

    async def _fake(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return [
            _rec("Camioneta", "Única", "2026-06-30"),  # vencido (-1)
            _rec("Pago IVA", "Mensual", "1"),           # hoy (0), NO vencido
        ]

    monkeypatch.setattr(recordatorios.sheets, "get_dicts", _fake)
    v = asyncio.run(recordatorios.vencidos())
    assert len(v) == 1
    assert v[0]["nombre"] == "Camioneta" and v[0]["falta"] == -1


def test_marcar_hecho_upserta_estado_y_ultima_accion(monkeypatch):
    monkeypatch.setattr(recordatorios, "_hoy", lambda: date(2026, 7, 1))
    calls = []

    async def _fake_upsert(hoja, clave_col, clave_val, set_col, valor, sheet_id=None):
        calls.append((set_col, valor))
        return "actualizado"

    monkeypatch.setattr(recordatorios.sheets, "upsert_por_clave", _fake_upsert)
    asyncio.run(recordatorios.marcar_hecho("Camioneta"))
    assert (recordatorios.COLS["estado"], "Hecho") in calls
    assert any(c == recordatorios.COLS["ultima_accion"] for c, _ in calls)


def test_teclado_vencidos_arma_botones_y_salta_nombres_muy_largos():
    v = [{"nombre": "Camioneta", "falta": -1}, {"nombre": "Z" * 80, "falta": -2}]
    cbs = _cbs(flows.teclado_vencidos(v))
    assert "rec:hecho:Camioneta" in cbs
    assert all("Z" * 80 not in c for c in cbs)  # excede 64 bytes → sin botón (igual sale en texto)
