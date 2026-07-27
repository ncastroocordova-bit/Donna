"""La fecha real llega a TODO lo que genera el cerebro (chat, brief, cierre, proactividad).

Antes, el único lugar con la fecha determinista era el encabezado del brief
(`scheduler._encabezado_fecha`), antepuesto AL texto del LLM. En cualquier otro momento —el
cierre, un chat normal— el modelo no tenía de dónde sacar el día real, y podía inventar uno que
no calzara (se vio en producción: "Domingo 26/07" en el encabezado del brief, pero "Nico. Jueves"
en el cierre de esa misma fecha). `_fecha_hoy` se calcula en código, igual que el encabezado del
brief, y `_armar_contexto` la inyecta siempre — el LLM nunca tiene que adivinarla.
"""
import asyncio
from datetime import datetime

from core import brain


def test_fecha_hoy_dice_el_dia_correcto():
    # 2026-07-26 es domingo (mismo ancla que usa test_scheduler para el encabezado del brief).
    assert brain._fecha_hoy(datetime(2026, 7, 26)) == "Hoy es domingo 26/07/2026."


def test_fecha_hoy_cubre_los_7_dias_sin_desfase():
    esperado = ["lunes 13/07/2026", "martes 14/07/2026", "miércoles 15/07/2026",
                "jueves 16/07/2026", "viernes 17/07/2026", "sábado 18/07/2026", "domingo 19/07/2026"]
    real = [brain._fecha_hoy(datetime(2026, 7, 13 + i)).removeprefix("Hoy es ").removesuffix(".")
            for i in range(7)]
    assert real == esperado


def test_armar_contexto_siempre_trae_la_fecha(monkeypatch):
    async def _sin_perfil():
        return {}
    async def _sin_memorias(_):
        return []
    async def _sin_aprendizaje():
        return ""
    monkeypatch.setattr(brain.memory, "get_perfil", _sin_perfil)
    monkeypatch.setattr(brain.memory, "buscar_memoria", _sin_memorias)
    monkeypatch.setattr(brain.aprendizaje, "senal_aprendizaje", _sin_aprendizaje)

    contexto = asyncio.run(brain._armar_contexto("hola"))
    assert contexto.startswith("Hoy es ")
    # Sin perfil/memoria/aprendizaje, sigue avisando que no hay más contexto (no inventar datos).
    assert "no inventes cifras ni estados" in contexto


def test_armar_contexto_trae_fecha_y_perfil_juntos(monkeypatch):
    async def _con_perfil():
        return {"nombre": "Nico"}
    async def _sin_memorias(_):
        return []
    async def _sin_aprendizaje():
        return ""
    monkeypatch.setattr(brain.memory, "get_perfil", _con_perfil)
    monkeypatch.setattr(brain.memory, "buscar_memoria", _sin_memorias)
    monkeypatch.setattr(brain.aprendizaje, "senal_aprendizaje", _sin_aprendizaje)

    contexto = asyncio.run(brain._armar_contexto("hola"))
    assert contexto.startswith("Hoy es ")
    assert "Perfil de Nico" in contexto
