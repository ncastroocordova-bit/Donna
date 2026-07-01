"""Evals no-destructivos del Módulo 2 (Salud v2 / E8). Puros: sin red, sin Supabase, sin
Sheets — corren en milisegundos. Donde el flujo real escribe a Sheets/Supabase (registrar_hora,
registrar_peso, evento_contextual), se monkeypatchea esa llamada: se prueba la lógica
determinista de Donna, no la API externa.

Cubren los criterios del roadmap (ficha Salud, E8):
  · toques de agua/proteína/comidas escriben en Diario (vía el mismo _set que ya prueba
    marcar_habito; aquí se prueba el enrutamiento agua/proteina/horas específico de v2).
  · sal_resumen_ventanas da medianas coherentes (semana vs fin de semana), sin inventar
    con días incompletos.
  · Score_Habitos cuadra con los toques.
  · un evento contextual no se guarda si Nico dice que no pasó nada.
"""
import asyncio

from modules import salud


# ───────────────────────── Horas: parseo y ventanas ─────────────────────────

def test_parse_hora_valida():
    assert salud._parse_hora("08:15") == 8 * 60 + 15
    assert salud._parse_hora("23:59") == 23 * 60 + 59
    assert salud._parse_hora("00:00") == 0


def test_parse_hora_invalida_no_inventa():
    assert salud._parse_hora("") is None
    assert salud._parse_hora("mañana temprano") is None
    assert salud._parse_hora("25:00") is None
    assert salud._parse_hora("08:70") is None


def test_ventana_minutos_mismo_dia():
    # primera comida 08:00 -> última comida 20:00 = 12h de ventana de comida.
    assert salud._ventana_minutos("08:00", "20:00") == 12 * 60


def test_ventana_minutos_cruza_medianoche():
    # dormí 23:30 -> desperté 07:00 = 7h30, no un número negativo.
    assert salud._ventana_minutos("23:30", "07:00") == 7 * 60 + 30
    # dormí ya pasada la medianoche (01:15) -> desperté 07:00 = 5h45, sin restar 24h de más.
    assert salud._ventana_minutos("01:15", "07:00") == 5 * 60 + 45


def test_ventana_minutos_sin_dato_no_inventa():
    assert salud._ventana_minutos("", "07:00") is None
    assert salud._ventana_minutos("23:30", "") is None


def test_fmt_minutos():
    assert salud._fmt_minutos(7 * 60 + 30) == "7h30"
    assert salud._fmt_minutos(12 * 60) == "12h"
    assert salud._fmt_minutos(None) == "—"


# ───────────────────────── Resumen de ventanas (semana vs finde) ─────────────────────────

def _fila(fecha, primera="", ultima="", dormi="", despierta=""):
    return {
        "Fecha": fecha,
        salud.COLS["primera_comida"]: primera,
        salud.COLS["ultima_comida"]: ultima,
        salud.COLS["hora_dormi"]: dormi,
        salud.COLS["hora_despertar"]: despierta,
    }


def test_calcular_ventanas_separa_semana_de_finde():
    filas = [
        _fila("2026-06-15", "08:00", "20:00", "23:30", "07:00"),  # lunes
        _fila("2026-06-16", "08:30", "20:30", "23:45", "07:15"),  # martes
        _fila("2026-06-20", "10:00", "22:00", "01:00", "09:00"),  # sábado
        _fila("2026-06-21", "10:30", "22:30", "01:30", "09:30"),  # domingo
    ]
    v = salud._calcular_ventanas(filas)
    assert v["comida_semana_n"] == 2 and v["comida_finde_n"] == 2
    assert v["comida_semana_txt"] == "12h" and v["comida_finde_txt"] == "12h"
    assert v["sueno_semana_n"] == 2 and v["sueno_finde_n"] == 2
    assert v["sueno_semana_txt"] == "7h30"  # ambas noches dan 7h30 exacto (23:30->07:00, 23:45->07:15)
    assert v["sueno_finde_txt"] == "8h"     # ambas noches dan 8h exacto (01:00->09:00, 01:30->09:30)


def test_calcular_ventanas_dia_incompleto_no_entra():
    filas = [
        _fila("2026-06-15", "08:00", "20:00", "23:30", ""),   # sin hora de despertar
        _fila("2026-06-16", "", "20:30", "23:45", "07:15"),   # sin primera comida
    ]
    v = salud._calcular_ventanas(filas)
    assert v["comida_semana_n"] == 1     # solo el 15 tiene ambas horas de comida
    assert v["sueno_semana_n"] == 1      # solo el 16 tiene ambas horas de sueño


def test_calcular_ventanas_sin_datos_no_falla():
    v = salud._calcular_ventanas([])
    assert v["comida_semana"] is None and v["comida_semana_txt"] == "—"


# ───────────────────────── Score semanal de hábitos ─────────────────────────

def _fila_habitos(fecha, ejercicio="No", meditacion="No", sueno="No", agua="No", proteina="No"):
    return {
        "Fecha": fecha,
        salud.COLS["ejercicio"]: ejercicio,
        salud.COLS["meditacion"]: meditacion,
        salud.COLS["sueno_7h"]: sueno,
        salud.COLS["agua"]: agua,
        salud.COLS["proteina"]: proteina,
    }


def test_calcular_score_cuadra_con_los_toques():
    # 1 día, 5 hábitos, 3 cumplidos -> 60%.
    filas = [_fila_habitos("2026-06-15", ejercicio="Sí", meditacion="Sí", sueno="Sí")]
    s = salud._calcular_score(filas)
    assert s == {"score": 60, "cumplidos": 3, "total": 5}


def test_calcular_score_semana_completa():
    # 7 días, todo "Sí" -> 100%.
    filas = [_fila_habitos(f"2026-06-{15+i}", "Sí", "Sí", "Sí", "Sí", "Sí") for i in range(7)]
    s = salud._calcular_score(filas)
    assert s == {"score": 100, "cumplidos": 35, "total": 35}


def test_calcular_score_sin_filas_no_falla():
    assert salud._calcular_score([]) == {"score": None, "cumplidos": 0, "total": 0}


# ───────────────────────── Evento contextual: no guarda "no pasó nada" ─────────────────────────

def _mock_memoria(monkeypatch):
    llamadas = []

    async def _fake_guardar(texto, dominio=None, situacion=None, off_record=False, forzar=False):
        llamadas.append({"texto": texto, "dominio": dominio, "forzar": forzar})
        return True

    monkeypatch.setattr(salud.memory, "guardar_memoria", _fake_guardar)
    return llamadas


def test_evento_contextual_no_pasa_nada_no_guarda(monkeypatch):
    llamadas = _mock_memoria(monkeypatch)
    for texto in ("no", "Nada", "no pasó nada.", "todo normal", ""):
        r = asyncio.run(salud.evento_contextual(texto))
        assert r == ""
    assert llamadas == []


def test_evento_contextual_real_se_guarda_como_contexto(monkeypatch):
    llamadas = _mock_memoria(monkeypatch)
    r = asyncio.run(salud.evento_contextual("Se enfermó Emilio y tuve que llevarlo a urgencias"))
    assert "contexto" in r.lower()
    assert len(llamadas) == 1
    assert llamadas[0]["dominio"] == "evento_externo"
    assert llamadas[0]["forzar"] is True
    assert "Emilio" in llamadas[0]["texto"]


# ───────────────────────── Hora / peso: enrutan al campo correcto ─────────────────────────

def _mock_sheets(monkeypatch):
    llamadas = []

    async def _fake_upsert(hoja, clave_col, clave_val, set_col, valor, sheet_id=None):
        llamadas.append({"hoja": hoja, "set_col": set_col, "valor": valor})
        return "actualizado"

    monkeypatch.setattr(salud.sheets, "upsert_por_clave", _fake_upsert)
    return llamadas


def test_registrar_hora_campo_valido(monkeypatch):
    llamadas = _mock_sheets(monkeypatch)
    r = asyncio.run(salud.registrar_hora("primera_comida", "08:15"))
    assert "08:15" in r
    assert llamadas[0]["set_col"] == salud.COLS["primera_comida"]
    assert llamadas[0]["valor"] == "08:15"


def test_registrar_hora_campo_desconocido_no_escribe(monkeypatch):
    llamadas = _mock_sheets(monkeypatch)
    r = asyncio.run(salud.registrar_hora("hora_dormi", "23:00"))  # ese campo tiene su propio tool
    assert llamadas == []
    assert "No anoto" in r


def test_registrar_peso_valido(monkeypatch):
    llamadas = _mock_sheets(monkeypatch)
    r = asyncio.run(salud.registrar_peso("77.5"))
    assert "77.5" in r
    assert llamadas[0]["set_col"] == salud.COLS["peso"]
    assert llamadas[0]["valor"] == 77.5


def test_registrar_peso_invalido_no_escribe(monkeypatch):
    llamadas = _mock_sheets(monkeypatch)
    r = asyncio.run(salud.registrar_peso("no sé"))
    assert llamadas == []
    assert "kilos" in r.lower()


# ───────────────────────── Hábitos v2: agua/proteína entran al mismo patrón ─────────────────────────

def test_agua_proteina_son_toque_y_binario():
    assert "agua" in salud.HABITOS_TOQUE and "proteina" in salud.HABITOS_TOQUE
    assert "agua" in salud.BINARIOS and "proteina" in salud.BINARIOS


def test_marcar_habito_agua_default_si(monkeypatch):
    llamadas = _mock_sheets(monkeypatch)

    async def _fake_racha(campo):
        return 1

    monkeypatch.setattr(salud, "calcular_racha", _fake_racha)
    r = asyncio.run(salud.marcar_habito("agua"))  # sin valor explícito -> default "Sí" (BINARIOS)
    assert llamadas[0]["valor"] == "Sí"
    assert "Racha" in r
