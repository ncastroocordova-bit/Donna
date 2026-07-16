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


def test_teclado_cierre_ya_no_tiene_agua_ni_proteina():
    # Agua/proteína se retiraron del panel del cierre (quedan como columnas legado sin capturar).
    cbs = _cbs(flows.teclado_cierre(fecha="2026-07-01"))
    assert not any(c.startswith("agua:") or c.startswith("prot:") for c in cbs)
    assert not any(c.startswith("hab:agua") or c.startswith("hab:proteina") for c in cbs)


def test_teclado_cierre_ultima_comida_cubre_18_a_01():
    """Reemplaza al test de 'una sola fila con 21+': el rango pasó a 18–01 en filas de 4, porque
    la hora real de Nico se salía del rango viejo (y el '21+' escondía cualquier hora posterior)."""
    kb = flows.teclado_cierre(fecha="2026-07-01").inline_keyboard
    filas_comida = [row for row in kb if any("🍽" in b.text for b in row)]
    assert len(filas_comida) == 2                                  # 8 horas en filas de 4
    textos = [b.text for row in filas_comida for b in row]
    assert not any("+" in t for t in textos)                       # ya no hay hora-cajón
    assert any(t.endswith(" 01") for t in textos)                  # llega hasta la 01:00


def test_teclado_cierre_primera_comida_cubre_6_a_12():
    kb = flows.teclado_cierre(fecha="2026-07-01").inline_keyboard
    filas = [row for row in kb if any("🍳" in b.text for b in row)]
    textos = [b.text for row in filas for b in row]
    assert len(textos) == 7 and textos[0].endswith(" 6") and textos[-1].endswith(" 12")


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


# ───────────────────────── Revisión semanal (domingo): mensaje + cruces editables ─────────────────────────

class _FakeBot:
    def __init__(self):
        self.mensajes = []

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self.mensajes.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})


def _cbs_markup(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_enviar_cruces_correlador_manda_botones_editables_por_cruce(monkeypatch):
    async def _fake_cruces(limite=10):
        return [
            {"id": "a1", "contenido": "Duermes mal → gastas más", "estado": "confirmada"},
            {"id": "b2", "contenido": "Duermes mal → ánimo baja", "estado": "pendiente"},
        ]

    monkeypatch.setattr(flows.memory, "get_inferencias_correlador", _fake_cruces)
    bot = _FakeBot()
    n = asyncio.run(flows.enviar_cruces_correlador(bot, 123))
    assert n == 2 and len(bot.mensajes) == 2
    cbs = [c for m in bot.mensajes for c in _cbs_markup(m["reply_markup"])]
    # cada cruce trae los 3 botones del mecanismo estrella (sí/no/corregir), también el confirmado.
    assert "inf:confirmada:a1" in cbs and "inf:descartada:a1" in cbs and "inf:corregir:a1" in cbs
    assert "inf:corregir:b2" in cbs


def test_enviar_cruces_correlador_sin_cruces_no_manda_nada(monkeypatch):
    async def _fake_cruces(limite=10):
        return []

    monkeypatch.setattr(flows.memory, "get_inferencias_correlador", _fake_cruces)
    bot = _FakeBot()
    n = asyncio.run(flows.enviar_cruces_correlador(bot, 123))
    assert n == 0 and bot.mensajes == []


def test_job_resumen_semanal_manda_mensaje_y_registra_el_job(monkeypatch):
    marcados = []

    async def _fake_generar():
        return {"semana": "2026-06-29", "score": {"score": 67, "cumplidos": 2, "total": 3},
                "ventanas": {}, "peso": "", "peso_actual": None, "peso_delta": None}

    async def _fake_texto(r):  # evita pegarle al LLM en el test
        return "Tu semana vino sólida."

    async def _fake_cruces(bot, chat_id):
        return 0

    async def _fake_marcar(job, fecha=None):
        marcados.append(job)

    monkeypatch.setattr(scheduler.salud, "generar_resumen_semanal", _fake_generar)
    monkeypatch.setattr(scheduler, "_texto_revision_semanal", _fake_texto)
    monkeypatch.setattr(scheduler.flows, "enviar_cruces_correlador", _fake_cruces)
    monkeypatch.setattr(scheduler.memory, "marcar_job", _fake_marcar)
    bot = _FakeBot()
    ctx = type("Ctx", (), {"bot": bot})()
    asyncio.run(scheduler.job_resumen_semanal(ctx))
    assert "resumen_semanal" in marcados            # ahora sí queda en jobs_log (resiliencia)
    assert any("Tu semana" in m["text"] for m in bot.mensajes)


def test_check_pendientes_recupera_revision_semanal_el_domingo(monkeypatch):
    import datetime as _dt
    llamado = []

    class _FakeDatetime:
        @staticmethod
        def now(tz=None):
            return _dt.datetime(2026, 7, 5, 22, 35)  # domingo 22:35 (weekday 6)

    monkeypatch.setattr(scheduler, "datetime", _FakeDatetime)

    async def _ya(job, fecha=None):
        return job != "resumen_semanal"  # brief/cierre/spam ya corrieron; la revisión no

    monkeypatch.setattr(scheduler.memory, "job_ya_corrio", _ya)

    async def _fake_job(context):
        llamado.append("resumen_semanal")

    monkeypatch.setattr(scheduler, "job_resumen_semanal", _fake_job)
    monkeypatch.setattr(scheduler.correo, "disponible", lambda: False)
    ctx = type("Ctx", (), {"bot": _FakeBot()})()
    asyncio.run(scheduler.check_pendientes(ctx))
    assert llamado == ["resumen_semanal"]
