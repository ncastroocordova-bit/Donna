"""Evals del correlador de la espina (puros, sin red). Verifican que CRUZA cuando el dato
lo sostiene y que CALLA cuando no (N chico, sin señal) — la guardia anti-patrones-falsos."""
from core import correlador as c


def _dias(spec):
    """spec: lista de (sueno_ok, animo, gasto)."""
    return [{"fecha": f"2026-06-{i+1:02d}", "sueno_ok": s, "animo": a, "gasto": g}
            for i, (s, a, g) in enumerate(spec)]


# ───────────────────────── sueño ↔ ánimo ─────────────────────────

def test_sueno_animo_detecta_patron_real():
    # 6 noches malas con ánimo ~2, 6 buenas con ánimo ~4 → cruce con su dato.
    dias = _dias([(False, 2, None)] * 6 + [(True, 4, None)] * 6)
    inf = c._analizar_sueno_animo(dias)
    assert inf and "ánimo cae" in inf and "2.0/4" in inf and "4.0/4" in inf


def test_sueno_animo_calla_sin_diferencia():
    # mismo ánimo durmiendo bien o mal → no hay señal.
    dias = _dias([(False, 3, None)] * 6 + [(True, 3, None)] * 6)
    assert c._analizar_sueno_animo(dias) is None


def test_sueno_animo_calla_con_n_chico():
    # solo 2 noches malas → por debajo de MIN_GRUPO, no afirma aunque haya diferencia.
    dias = _dias([(False, 1, None)] * 2 + [(True, 4, None)] * 6)
    assert c._analizar_sueno_animo(dias) is None


# ───────────────────────── sueño ↔ gasto ─────────────────────────

def test_sueno_gasto_detecta_patron_real():
    # noches malas: gasto mediano 30k; buenas: 10k → +200% → cruce.
    dias = _dias([(False, None, 30000)] * 5 + [(True, None, 10000)] * 5)
    inf = c._analizar_sueno_gasto(dias)
    assert inf is not None
    assert "gastas más" in inf and "$30.000" in inf and "$10.000" in inf


def test_sueno_gasto_calla_si_gasto_similar():
    dias = _dias([(False, None, 10500)] * 5 + [(True, None, 10000)] * 5)  # +5% < umbral 25%
    assert c._analizar_sueno_gasto(dias) is None


def test_sueno_gasto_calla_con_n_chico():
    dias = _dias([(False, None, 50000)] * 3 + [(True, None, 10000)] * 5)  # 3 < MIN_GRUPO
    assert c._analizar_sueno_gasto(dias) is None


# ───────────────────────── normalización ─────────────────────────

def test_dias_con_dato_mapea_sueno_animo_gasto(monkeypatch):
    from modules import salud
    diario = [
        {"Fecha": "2026-06-01", salud.COLS["sueno_7h"]: "No", salud.COLS["animo"]: "2"},
        {"Fecha": "2026-06-02", salud.COLS["sueno_7h"]: "Sí", salud.COLS["animo"]: "4"},
        {"Fecha": "2026-06-03", salud.COLS["sueno_7h"]: "", salud.COLS["animo"]: ""},  # sin dato
    ]
    dias = c._dias_con_dato(diario, {"2026-06-01": 25000})
    assert dias[0]["sueno_ok"] is False and dias[0]["animo"] == 2 and dias[0]["gasto"] == 25000
    assert dias[1]["sueno_ok"] is True and dias[1]["animo"] == 4 and dias[1]["gasto"] is None
    assert dias[2]["sueno_ok"] is None  # celda vacía → sin dato, no se cruza


def test_dias_con_dato_evento_externo_excluye_el_animo(monkeypatch):
    # E8: un día con evento_externo se trata como CONTEXTO, no como patrón — su ánimo no
    # debe ensuciar el cruce sueño↔ánimo aunque haya durmido mal ese día.
    from modules import salud
    diario = [
        {"Fecha": "2026-06-01", salud.COLS["sueno_7h"]: "No", salud.COLS["animo"]: "1"},
        {"Fecha": "2026-06-02", salud.COLS["sueno_7h"]: "No", salud.COLS["animo"]: "2"},
    ]
    dias = c._dias_con_dato(diario, {}, dias_contexto={"2026-06-01"})
    assert dias[0]["sueno_ok"] is False and dias[0]["animo"] is None  # contexto: se excluye
    assert dias[1]["sueno_ok"] is False and dias[1]["animo"] == 2     # día normal: se conserva
