"""Evals del scheduler. Puros: sin Telegram, sin Sheets, sin LLM.

Cubren el contrato del `/brief` a demanda (texto_brief_manual): mismo texto que el brief de
las 8:00, y **sin efectos de lado** — el riesgo real es que marcar el job desde el comando
haga que el brief programado no salga.
"""
import asyncio

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
