"""Evals del módulo Estados de cuenta (Finanzas v4). Puros: sin red, sin PDF real, sin LLM.
Se prueban las piezas deterministas (clasificación, mapeo al faro, historial, reconciliación,
reporte); la extracción con LLM y la descarga de Gmail se validan a mano contra los PDFs reales."""
import asyncio

from modules import estados_cuenta as ec


# ───────────────────────── Clasificación banco/producto ─────────────────────────

def test_banco_por_remitente():
    assert ec._banco("Banco de Chile <enviodigital@bancochile.cl>", "Estado de Cuenta") == "bch"
    assert ec._banco("MACHBANK <contacto@mail.machbank.cl>", "Estado de cuenta") == "mach"
    assert ec._banco("alguien@gmail.com", "hola") == "otro"


def test_producto_por_asunto_y_filename():
    assert ec._producto("Estado de Cuenta Tarjeta de Crédito", "EECCTarjetaVisa.pdf") == "tarjeta_credito"
    assert ec._producto("Cartola Línea de Crédito Mensual", "Linea_de_credito_mensual.pdf") == "linea_credito"
    assert ec._producto("Cartola de Liquidación de Intereses", "LiqIntLDCPersona.pdf") == "linea_interes"
    assert ec._producto("Cartola de Liquidación de Intereses", "LiqIntSobregiroNoPactado.pdf") == "sobregiro"


# ───────────────────────── Mapeo al faro (celdas-input) ─────────────────────────

def test_celdas_faro_tarjeta_bch():
    celdas = dict(ec._celdas_faro("bch", "tarjeta_credito", {"deuda_total": 1030608, "cupo": 1000000}))
    assert celdas[29] == 1030608 and celdas[28] == 1000000   # B29 deuda, B28 cupo


def test_celdas_faro_mach_linea_interes():
    assert dict(ec._celdas_faro("mach", "tarjeta_credito", {"deuda_total": 298327}))[40] == 298327
    assert dict(ec._celdas_faro("bch", "linea_credito", {"deuda_total": 969031}))[44] == 969031
    assert dict(ec._celdas_faro("bch", "linea_interes", {"interes_mes": 34210}))[45] == 34210


# ───────────────────────── Historial: suma por mes (excluye interés) ─────────────────────────

def test_deuda_por_mes_excluye_filas_de_interes():
    filas = [
        {"Mes": "2026-06", "Deuda": 1030608}, {"Mes": "2026-06", "Deuda": 969031},
        {"Mes": "2026-07", "Deuda": ""},   # doc de interés (deuda vacía) → no cuenta ni crea mes
    ]
    pm = ec._deuda_por_mes(filas)
    assert pm == {"2026-06": 1030608 + 969031}
    assert "2026-07" not in pm


# ───────────────────────── Reconciliación ─────────────────────────

def _mock_get_dicts(monkeypatch, filas):
    async def _fake(hoja, sheet_id=None, value_render="FORMATTED_VALUE"):
        return filas
    monkeypatch.setattr(ec.sheets, "get_dicts", _fake)


def test_reconciliar_marca_faltantes_y_filtra_ruido(monkeypatch):
    _mock_get_dicts(monkeypatch, [{"Fecha": "2026-06-11", "Monto": 5770}])  # UNIMARC ya está
    txs = [
        {"fecha": "2026-06-11", "comercio": "UNIMARC", "monto": 5770},            # calza → no falta
        {"fecha": "2026-06-05", "comercio": "SHELL", "monto": 10000},             # falta de verdad
        {"fecha": "2026-06-13", "comercio": "AVANCE EN CUOTAS", "monto": 40000},  # ruido → fuera
        {"fecha": "2026-06-01", "comercio": "PAGO PESOS TEF", "monto": 45049},    # pago → fuera
    ]
    faltan = asyncio.run(ec._reconciliar(txs, dias_recientes=10 ** 6))
    assert [f["comercio"] for f in faltan] == ["SHELL"]


# ───────────────────────── Reporte + progreso ─────────────────────────

def test_texto_reporte_completo():
    r = {"nuevos": 2, "bancos": {"bch", "mach"}, "deuda_actual": 2297966, "delta": -50000,
         "registros": [{"banco": "bch", "producto": "tarjeta_credito", "deuda_total": 1030608},
                       {"banco": "bch", "producto": "linea_interes", "deuda_total": None, "interes_mes": 34210}],
         "faltantes": [{"fecha": "2026-06-05", "comercio": "SHELL", "monto": 10000}]}
    t = ec.texto_reporte(r)
    assert "Llegaron estados" in t and "$2.297.966" in t
    assert "Bajó" in t and "$50.000" in t
    assert "interés línea $34.210" in t          # el doc de interés muestra el interés, no una deuda fantasma
    assert "no tengo registrados" in t and "SHELL" in t


def test_texto_reporte_sin_novedades_vacio():
    assert ec.texto_reporte({"nuevos": 0}) == ""


def test_progreso_deuda_lee_historial(monkeypatch):
    _mock_get_dicts(monkeypatch, [{"Mes": "2026-05", "Deuda": 2000000}, {"Mes": "2026-06", "Deuda": 2297966}])
    t = asyncio.run(ec._t_progreso({}))
    assert "2026-05" in t and "2026-06" in t
    assert "subió" in t.lower()


def test_progreso_sin_historial(monkeypatch):
    _mock_get_dicts(monkeypatch, [])
    t = asyncio.run(ec._t_progreso({}))
    assert "todavía no" in t.lower()
