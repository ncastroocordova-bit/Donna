"""Evals del Módulo 4 (Recordatorios) contra el schema REAL de la planilla:
Recordatorio · Tipo · Día / Fecha · Monto aprox · Estado · Posposiciones · Última acción · Activo.

Regresión del bug de la auditoría 2026-07-01: el módulo leía Dia_Fecha/Aviso_Dias/Ultimo_Aviso
(columnas que NO existen) → rec_proximos siempre daba vacío (el brief nunca avisaba un pago) y
rec_agregar escribía 7 valores corriendo las columnas Estado/Posposiciones.

Puros: sin red, sin Sheets. Donde el flujo escribe (rec_agregar) o lee (proximos) se monkeypatchea
la llamada a Sheets/Anthropic; se prueba la lógica determinista, no la API externa.
"""
import asyncio
import types
from datetime import date

from modules import recordatorios


def _fila(recordatorio, tipo, dia_fecha, monto="", estado="Pendiente", activo="Sí"):
    return {
        recordatorios.COLS["recordatorio"]: recordatorio,
        recordatorios.COLS["tipo"]: tipo,
        recordatorios.COLS["dia_fecha"]: dia_fecha,
        recordatorios.COLS["monto"]: monto,
        recordatorios.COLS["estado"]: estado,
        recordatorios.COLS["posposiciones"]: 0,
        recordatorios.COLS["ultima_accion"]: "",
        recordatorios.COLS["activo"]: activo,
    }


def _fijar_hoy(monkeypatch, y, m, d):
    monkeypatch.setattr(recordatorios, "_hoy", lambda: date(y, m, d))


def _mock_get_dicts(monkeypatch, filas):
    async def _fake(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return filas
    monkeypatch.setattr(recordatorios.sheets, "get_dicts", _fake)


# ───────────────────────── _dias_hasta (parseo por tipo) ─────────────────────────

def test_mensual_dia_1_cae_hoy(monkeypatch):
    _fijar_hoy(monkeypatch, 2026, 7, 1)
    assert recordatorios._dias_hasta(_fila("Pago contadora", "Mensual", "1")) == 0


def test_anual_rollover_al_proximo_anio(monkeypatch):
    _fijar_hoy(monkeypatch, 2026, 7, 1)
    # 26 de mayo ya pasó este año → cuenta hasta el 2027.
    r = _fila("Cumple pareja", "Anual", "2026-05-26")
    assert recordatorios._dias_hasta(r) == (date(2027, 5, 26) - date(2026, 7, 1)).days


def test_unica_vencida_da_negativo(monkeypatch):
    _fijar_hoy(monkeypatch, 2026, 7, 1)
    # La camioneta venció el 30-jun; sin rollover, falta = -1.
    r = _fila("Revisión técnica camioneta", "Única", "2026-06-30")
    assert recordatorios._dias_hasta(r) == -1


def test_dia_fecha_vacio_no_revienta(monkeypatch):
    _fijar_hoy(monkeypatch, 2026, 7, 1)
    assert recordatorios._dias_hasta(_fila("placeholder", "", "")) is None


# ───────────────────────── proximos / texto_proximos ─────────────────────────

def test_proximos_incluye_vencido_y_texto_dice_vencio(monkeypatch):
    _fijar_hoy(monkeypatch, 2026, 7, 1)
    _mock_get_dicts(monkeypatch, [_fila("Revisión técnica camioneta", "Única", "2026-06-30")])
    txt = asyncio.run(recordatorios.texto_proximos(7))
    assert "venció" in txt and "camioneta" in txt.lower()


def test_estado_hecho_se_excluye(monkeypatch):
    _fijar_hoy(monkeypatch, 2026, 7, 1)
    _mock_get_dicts(monkeypatch, [_fila("Pago IVA", "Mensual", "1", estado="Hecho")])
    assert asyncio.run(recordatorios.proximos(7)) == []


def test_inactivo_se_excluye(monkeypatch):
    _fijar_hoy(monkeypatch, 2026, 7, 1)
    _mock_get_dicts(monkeypatch, [_fila("Pago viejo", "Mensual", "1", activo="No")])
    assert asyncio.run(recordatorios.proximos(7)) == []


def test_futuro_fuera_de_ventana_no_aparece(monkeypatch):
    _fijar_hoy(monkeypatch, 2026, 7, 1)
    _mock_get_dicts(monkeypatch, [_fila("Cumple pareja", "Anual", "2026-08-15")])
    assert asyncio.run(recordatorios.proximos(7)) == []


# ───────────────────────── rec_agregar (append con schema real) ─────────────────────────

def test_agregar_appendea_8_valores_schema_real(monkeypatch):
    capturado = {}

    # rec_agregar usa la escritura VERIFICADA (autodiagnóstico); se mockea esa, no append_row.
    async def _fake_append_v(hoja, valores, verificar_cols, *, tool="-", sheet_id=None):
        capturado["valores"] = valores
        return True

    monkeypatch.setattr(recordatorios.sheets, "append_row_verificado", _fake_append_v)

    async def _fake_create(**kwargs):
        payload = '{"recordatorio": "Pago patente", "tipo": "anual", "dia_fecha": "01-03", "monto_aprox": 80000}'
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=payload)])

    monkeypatch.setattr(recordatorios._anthropic.messages, "create", _fake_create)
    r = asyncio.run(recordatorios._t_agregar({"texto": "recuérdame la patente el 1 de marzo, 80 lucas"}))

    v = capturado["valores"]
    assert len(v) == 8            # 8 columnas reales, no 7
    assert v[4] == "Pendiente"    # Estado (no un aviso_dias corrido)
    assert v[5] == 0              # Posposiciones
    assert v[7] == "Sí"           # Activo
    assert "Pago patente" in r
