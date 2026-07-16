"""Evals del scheduler. Puros: sin Telegram, sin Sheets, sin LLM.

Cubren el contrato del `/brief` a demanda (texto_brief_manual): mismo texto que el brief de
las 8:00, y **sin efectos de lado** — el riesgo real es que marcar el job desde el comando
haga que el brief programado no salga.
"""
import asyncio
from datetime import datetime

from core import scheduler


def test_brief_manual_devuelve_el_mismo_texto_del_brief(monkeypatch):
    async def _texto():
        return "el brief de hoy"
    monkeypatch.setattr(scheduler, "_texto_brief", _texto)
    assert asyncio.run(scheduler.texto_brief_manual()) == "el brief de hoy"


def test_brief_manual_no_consume_el_brief_programado(monkeypatch):
    """Si /brief marcara el job o el Brief ✓, el chequeo de resiliencia creería que el brief
    del día ya salió y el de las 8:00 se saltaría. Pedirlo a mano no puede costar el real."""
    llamadas = []

    async def _texto():
        return "brief"
    async def _marcar_job(nombre):
        llamadas.append(("marcar_job", nombre))
    async def _marcar_brief():
        llamadas.append(("marcar_brief", None))

    monkeypatch.setattr(scheduler, "_texto_brief", _texto)
    monkeypatch.setattr(scheduler.memory, "marcar_job", _marcar_job)
    monkeypatch.setattr(scheduler.salud, "marcar_brief", _marcar_brief)

    asyncio.run(scheduler.texto_brief_manual())
    assert llamadas == []          # ni marcar_job ni marcar_brief: cero efectos de lado


# ───────────────────────── encabezado día + fecha ─────────────────────────

def test_encabezado_dia_y_fecha_en_espanol():
    # lunes 13/07/2026 — el día lo pone la tabla propia, no el locale del sistema.
    assert scheduler._encabezado_fecha(datetime(2026, 7, 13)) == "📅 Lunes 13/07"


def test_encabezado_cubre_los_7_dias_sin_desfase():
    """El desfase de días es justo lo que Nico quiere poder auditar: 2026-07-13 es lunes y
    2026-07-19 domingo. Si algún día saliera corrido, el encabezado dejaría de servir."""
    esperado = ["Lunes 13/07", "Martes 14/07", "Miércoles 15/07", "Jueves 16/07",
                "Viernes 17/07", "Sábado 18/07", "Domingo 19/07"]
    real = [scheduler._encabezado_fecha(datetime(2026, 7, 13 + i)).removeprefix("📅 ") for i in range(7)]
    assert real == esperado


def test_brief_arranca_con_el_encabezado(monkeypatch):
    async def _generar(prompt):
        return "tu día viene tranquilo"
    monkeypatch.setattr(scheduler.brain, "generar", _generar)
    for mod, fn in [(scheduler.agenda, "eventos_de_hoy")]:
        monkeypatch.setattr(mod, fn, lambda: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(scheduler.correo, "disponible", lambda: False)
    for mod, fns in [(scheduler.diagnostico, ["senal_heartbeat"]),
                     (scheduler.finanzas, ["senal_finanzas", "senal_pendientes_digest"]),
                     (scheduler.salud, ["senal_salud", "senal_mits_brief"]),
                     (scheduler.proyectos, ["senal_proyectos"])]:
        for fn in fns:
            monkeypatch.setattr(mod, fn, lambda: asyncio.sleep(0, result=""))
    monkeypatch.setattr(scheduler.recordatorios, "texto_proximos", lambda d: asyncio.sleep(0, result=""))

    texto = asyncio.run(scheduler._texto_brief())
    assert texto.startswith("📅 ")          # el día/fecha siempre primero, venga lo que venga del LLM
    assert "tu día viene tranquilo" in texto


# ───────────────────────── revisión dominical: nunca falla en silencio ─────────────────────────

class _BotFake:
    def __init__(self):
        self.enviados = []
    async def send_message(self, chat, texto, **kw):
        self.enviados.append(texto)


class _CtxFake:
    def __init__(self):
        self.bot = _BotFake()


def test_revision_dominical_si_salud_falla_registra_incidente(monkeypatch):
    """Antes era un `return` mudo: el domingo no llegaba nada y Nico nunca sabía por qué.
    Ahora queda como incidente → el heartbeat lo saca en el brief del lunes."""
    registrados = []

    async def _boom():
        raise RuntimeError("Semanal no se pudo escribir")
    async def _registrar(tool, tipo, resumen, *, input_json=None, error_texto=""):
        registrados.append((tool, tipo, resumen))
        return {"id": 1}

    monkeypatch.setattr(scheduler.salud, "generar_resumen_semanal", _boom)
    monkeypatch.setattr(scheduler.diagnostico, "registrar", _registrar)
    asyncio.run(scheduler.job_resumen_semanal(_CtxFake()))

    assert len(registrados) == 1
    assert registrados[0][0] == "job_resumen_semanal" and registrados[0][1] == "tool_excepcion"


# ───────────────────────── cierre: cadena de una pregunta a la vez ─────────────────────────

def _mock_cierre(monkeypatch):
    """Silencia todo lo que el cierre toca salvo lo que se está probando."""
    async def _nada(*a, **k):
        return None
    async def _ingerir():
        return {"revisados": 0, "nuevos": 0}
    async def _intro():
        return "cerremos"
    monkeypatch.setattr(scheduler.finanzas, "ingerir_gastos_email", _ingerir)
    monkeypatch.setattr(scheduler, "_texto_cierre", _intro)
    monkeypatch.setattr(scheduler.flows, "enviar_panel_cierre", _nada)
    monkeypatch.setattr(scheduler.flows, "enviar_digest", _nada)
    monkeypatch.setattr(scheduler.flows, "preguntar_inferencia_pendiente", _nada)
    monkeypatch.setattr(scheduler.finanzas, "sembrar_espina", _nada)
    monkeypatch.setattr(scheduler.correlador, "correr", _nada)
    monkeypatch.setattr(scheduler.salud, "marcar_cierre", _nada)
    monkeypatch.setattr(scheduler.memory, "marcar_job", _nada)


class _CtxCierre(_CtxFake):
    def __init__(self):
        super().__init__()
        self.bot_data = {}


def test_cierre_pregunta_solo_los_mits_y_arma_la_cadena(monkeypatch):
    """El cierre ya no dispara MITs + evento + peso de corrido: abre UNA pregunta y deja la
    cadena armada. Con tres abiertas, un audio caía en la equivocada."""
    _mock_cierre(monkeypatch)
    ctx = _CtxCierre()
    asyncio.run(scheduler.job_cierre(ctx))

    assert ctx.bot_data["cierre_cadena"]["paso"] == "mits"
    assert len(ctx.bot.enviados) == 1          # una sola pregunta abierta


def test_cierre_ya_no_pregunta_el_peso(monkeypatch):
    """El peso pasó a ser semanal (domingo). No puede volver a aparecer cada noche."""
    _mock_cierre(monkeypatch)
    ctx = _CtxCierre()
    asyncio.run(scheduler.job_cierre(ctx))
    assert not any("pesa" in t.lower() or "peso" in t.lower() for t in ctx.bot.enviados)


def test_es_domingo_usa_la_convencion_stdlib():
    assert scheduler.es_domingo(datetime(2026, 7, 19)) is True    # domingo
    assert scheduler.es_domingo(datetime(2026, 7, 13)) is False   # lunes
