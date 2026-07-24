"""Evals de core/sheets.py. Puros: sin red, sin credenciales."""
from core import sheets


# ── fecha_iso (Ola 5, F5.2) ──
# Bug real de la auditoría del 2026-07-23: una columna DATE leída con UNFORMATTED_VALUE devuelve
# el número de serie de Sheets, no un string "YYYY-MM-DD" — a diferencia de Monto, que sí llega
# usable. Rompió en silencio tres lugares que comparaban Fecha como si ya fuera texto.

def test_fecha_iso_convierte_el_serial_de_sheets():
    # Verificado contra la API real: Transacciones!A3 = serial 46163, Sheets lo formatea como
    # "2026-05-21" — fecha_iso() debe dar exactamente lo mismo, no un valor a ojo.
    assert sheets.fecha_iso(46163) == "2026-05-21"
    assert sheets.fecha_iso(46163.0) == "2026-05-21"
    assert sheets.fecha_iso(46178) == "2026-06-05"


def test_fecha_iso_es_idempotente_con_texto():
    """Si ya viene como string (FORMATTED_VALUE, o una columna sin formato DATE real), se
    devuelve tal cual — recortado a 10 chars por si trae hora."""
    assert sheets.fecha_iso("2026-06-11") == "2026-06-11"
    assert sheets.fecha_iso("2026-06-11T00:00:00") == "2026-06-11"


def test_fecha_iso_vacio_no_truena():
    assert sheets.fecha_iso("") == ""
    assert sheets.fecha_iso(None) == ""
