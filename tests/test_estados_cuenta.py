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

def _celdas(banco, producto, d):
    """(fila, col) → valor. La firma devuelve tríos desde la Ola 1 (col B inputs, col C interés)."""
    return {(f, c): v for f, c, v in ec._celdas_faro(banco, producto, d)}


def test_celdas_faro_tarjeta_bch():
    celdas = _celdas("bch", "tarjeta_credito", {"deuda_total": 1030608, "cupo": 1000000})
    assert celdas[(29, 1)] == 1030608 and celdas[(28, 1)] == 1000000   # B29 deuda, B28 cupo


def test_celdas_faro_mach_linea_interes():
    assert _celdas("mach", "tarjeta_credito", {"deuda_total": 298327})[(40, 1)] == 298327
    assert _celdas("bch", "linea_credito", {"deuda_total": 969031})[(44, 1)] == 969031
    assert _celdas("bch", "linea_interes", {"interes_mes": 34210})[(45, 1)] == 34210


# ── Ola 1 · F1.1: el interés del ESTADO manda sobre el cálculo tasa×rotativa ──
# Regresión del bug encontrado el 2026-07-23: Mach declaraba $5.310 de interés y el faro
# calculaba $0 (su tasa-input es 0), subreportando los intereses muertos en $6.652/mes.

def test_interes_del_estado_va_a_la_columna_c():
    mach = _celdas("mach", "tarjeta_credito", {"deuda_total": 300000, "cupo": 300000, "interes_mes": 5310})
    assert mach[(37, 2)] == 5310          # C37 = interés reportado por Mach
    assert mach[(40, 1)] == 300000        # B40 = deuda, sigue en la columna de siempre
    bch = _celdas("bch", "tarjeta_credito", {"deuda_total": 1030608, "interes_mes": 24388})
    assert bch[(25, 2)] == 24388          # C25 = interés reportado por BCh


def test_sin_interes_en_el_estado_no_escribe_la_celda():
    """Si el PDF no trae interés, no se pisa la celda: B25/B37 caen solos al cálculo de respaldo."""
    celdas = _celdas("bch", "tarjeta_credito", {"deuda_total": 1030608, "cupo": 1000000})
    assert not [k for k in celdas if k[1] == 2]


# ── Ola 1 · F1.2: de qué mes es cada cifra del faro ──

def _hist():
    return [
        {"Mes": "2026-06", "Banco": "bch", "Producto": "tarjeta_credito", "Deuda": 1030608},
        {"Mes": "2026-06", "Banco": "bch", "Producto": "linea_credito", "Deuda": 969031},
        {"Mes": "2026-07", "Banco": "bch", "Producto": "linea_interes", "Interés mes": 34210},
        {"Mes": "2026-06", "Banco": "mach", "Producto": "tarjeta_credito", "Deuda": 298327},
        {"Mes": "2026-07", "Banco": "mach", "Producto": "tarjeta_credito", "Deuda": 300000},
    ]


def test_procedencia_toma_el_mes_mas_reciente_por_producto(monkeypatch):
    monkeypatch.setattr(ec, "_hoy", lambda: "2026-07-23")
    por = {(p["banco"], p["producto"]): p for p in ec.procedencia(_hist())}
    assert por[("mach", "tarjeta_credito")]["mes"] == "2026-07"   # gana julio sobre junio
    assert por[("mach", "tarjeta_credito")]["atrasado"] is False
    assert por[("bch", "tarjeta_credito")]["mes"] == "2026-06"
    assert por[("bch", "tarjeta_credito")]["atrasado"] is True    # el de julio aún no llega


def test_texto_procedencia_nombra_lo_que_falta(monkeypatch):
    monkeypatch.setattr(ec, "_hoy", lambda: "2026-07-23")
    t = ec.texto_procedencia(ec.procedencia(_hist()))
    assert "BCh tarjeta de junio" in t and "Mach tarjeta de julio" in t
    assert "Aún no llega" in t and "BCh tarjeta" in t.split("Aún no llega")[1]


def test_texto_procedencia_calla_si_todo_al_dia(monkeypatch):
    monkeypatch.setattr(ec, "_hoy", lambda: "2026-06-15")
    t = ec.texto_procedencia(ec.procedencia(_hist()[:1]))
    assert "Aún no llega" not in t


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
