"""Evals no-destructivos del Módulo 1 (Finanzas). Puros: sin red, sin Supabase, sin
Sheets — corren en milisegundos y no tocan datos de producción.

Cubren los criterios del roadmap (ficha Finanzas):
  · faro da $2.028.091 y $48.236  → formato chileno + lectura del faro.
  · "aceptar todo" escribe sin duplicar → planificador anti-duplicado del digest.

El caso foto→categoría y el freno-antes-de-cuota viven en los evals conversacionales
(tests/casos.yaml) y en la semana de prueba real.
"""
from pathlib import Path

import pytest

from modules import finanzas


# ───────────────────────── Formato de pesos chilenos ─────────────────────────

def test_clp_formato_chileno():
    assert finanzas.clp(2028091) == "$2.028.091"
    assert finanzas.clp(48236) == "$48.236"
    assert finanzas.clp(0) == "$0"
    assert finanzas.clp("15000") == "$15.000"      # acepta string
    assert finanzas.clp(999) == "$999"             # sin separador bajo mil


# ───────────────────────── Faro de deuda (las cifras del canon) ─────────────────────────

def test_faro_muestra_las_cifras_del_canon():
    d = {
        "deuda_total_real": 2028091,
        "intereses_muertos": 48236,
        "utilizacion": 79,
        "semaforo": "🔴",
        "total_a_pagar": 350000,
    }
    texto = finanzas.formatear_deuda(d)
    assert "$2.028.091" in texto       # deuda real (incluye la línea)
    assert "$48.236" in texto          # intereses muertos del mes
    assert "79%" in texto


def test_constantes_del_faro_apuntan_al_canon():
    """Ancla las celdas que lee el código al layout real de Donna_Canonico.xlsx, y verifica
    que los insumos dan las cifras del canon — la deuda real INCLUYE la línea de crédito.
    Este es el eval del roadmap: 'faro da $2.028.091 y $48.236'."""
    openpyxl = pytest.importorskip("openpyxl")
    ruta = Path(__file__).resolve().parent.parent / "docs" / "Donna_Canonico.xlsx"
    if not ruta.exists():
        pytest.skip("falta docs/Donna_Canonico.xlsx")
    wb = openpyxl.load_workbook(ruta, data_only=False)
    assert finanzas.HOJA_TARJETAS in wb.sheetnames           # 'Tarjetas y Deuda'
    ws = wb[finanzas.HOJA_TARJETAS]
    fila_deuda = finanzas.CELDA_DEUDA_REAL[1:]               # 'B4' -> '4'
    fila_int = finanzas.CELDA_INTERESES_MUERTOS[1:]
    assert "DEUDA TOTAL REAL" in str(ws[f"A{fila_deuda}"].value).upper()
    assert "INTERESES MUERTOS" in str(ws[f"A{fila_int}"].value).upper()
    # Insumos → cifras del canon (B4 = BCh + Mach + línea; B5 = interés rotativo + línea).
    deuda = ws["B29"].value + ws["B40"].value + ws["B44"].value
    intereses = round(ws["B20"].value * ws["B21"].value) + 0 + ws["B45"].value
    assert round(deuda) == 2028091
    assert round(intereses) == 48236


# ───────────────────────── Anti-duplicado del digest ("aceptar todo" sin duplicar) ─────────────────────────

def _pend(buffer_id, id_unico, **extra):
    base = {"id": buffer_id, "id_unico": id_unico, "categoria": "Otros", "monto": 1000}
    base.update(extra)
    return base


def test_aceptar_todo_escribe_los_nuevos():
    pendientes = [_pend("b1", "2026-06-20_1000_Jumbo"), _pend("b2", "2026-06-20_500_Uber")]
    plan = finanzas._planificar_digest(pendientes, {}, set())
    assert len(plan["a_escribir"]) == 2
    assert plan["duplicadas"] == []
    assert plan["a_descartar"] == []


def test_no_duplica_lo_que_ya_esta_en_la_planilla():
    pendientes = [_pend("b1", "2026-06-20_1000_Jumbo"), _pend("b2", "2026-06-20_500_Uber")]
    ya = {"2026-06-20_1000_Jumbo"}                  # Jumbo ya escrito antes
    plan = finanzas._planificar_digest(pendientes, {}, ya)
    escritos = [i["p"]["id"] for i in plan["a_escribir"]]
    duplicados = [p["id"] for p in plan["duplicadas"]]
    assert escritos == ["b2"]
    assert duplicados == ["b1"]


def test_no_duplica_dos_lineas_iguales_en_el_mismo_digest():
    pendientes = [_pend("b1", "2026-06-20_1000_Jumbo"), _pend("b2", "2026-06-20_1000_Jumbo")]
    plan = finanzas._planificar_digest(pendientes, {}, set())
    assert len(plan["a_escribir"]) == 1            # se escribe una sola vez
    assert len(plan["duplicadas"]) == 1


def test_descartar_no_escribe():
    pendientes = [_pend("b1", "2026-06-20_1000_Jumbo")]
    plan = finanzas._planificar_digest(pendientes, {"b1": {"descartar": True}}, set())
    assert plan["a_escribir"] == []
    assert [p["id"] for p in plan["a_descartar"]] == ["b1"]


def test_correccion_de_categoria_se_respeta():
    pendientes = [_pend("b1", "2026-06-20_1000_Jumbo", categoria="Otros")]
    plan = finanzas._planificar_digest(pendientes, {"b1": {"categoria": "Supermercado"}}, set())
    assert plan["a_escribir"][0]["categoria"] == "Supermercado"


# ───────────────────────── Utilidades base ─────────────────────────

def test_num_parsea_formato_chileno():
    assert finanzas._num("$2.028.091") == 2028091
    assert finanzas._num("1.500,50") == 1500.50
    assert finanzas._num("") == 0.0


def test_id_unico_estable():
    a = finanzas._id_unico("2026-06-20", 15000, "Jumbo Maipú")
    b = finanzas._id_unico("2026-06-20", 15000, "Jumbo Maipú")
    assert a == b                                   # mismo gasto → mismo id (anti-duplicado)
