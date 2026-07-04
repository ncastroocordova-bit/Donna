"""Guardias del registro de tools del brain (fix/tools-legacy).

Los módulos `metas` (hoja MetasSemanales inexistente, colisiona con fin_metas) y `tiempo`
(hoja Tiempo inexistente, log OFF por canon) NO deben volver a registrarse en el brain:
sus tools reventaban contra hojas que no existen. Este test lo bloquea.
"""
from core import brain


def _nombres_tools():
    return {t["name"] for t in brain.ALL_TOOLS}


def test_no_hay_tools_legacy_registrados():
    nombres = _nombres_tools()
    for legacy in ("metas_get_semana", "metas_actualizar", "tiempo_registrar", "tiempo_resumen"):
        assert legacy not in nombres, f"{legacy} no debe estar registrado (módulo legacy/dormido)"


def test_write_tools_no_referencian_legacy():
    assert "tiempo_registrar" not in brain.WRITE_TOOLS
    assert "metas_actualizar" not in brain.WRITE_TOOLS


def test_tools_y_handlers_consistentes():
    # Todo tool declarado tiene su handler, y todo handler tiene su tool: sin huérfanos.
    nombres = _nombres_tools()
    handlers = set(brain._HANDLERS)
    assert nombres == handlers, f"desajuste tools/handlers: {nombres ^ handlers}"


def test_fin_metas_sigue_disponible():
    # El reemplazo vigente de las metas legacy debe seguir registrado.
    assert "fin_metas" in _nombres_tools()
