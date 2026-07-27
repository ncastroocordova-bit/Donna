"""Fase 4: el hint-router debía tener con qué responder a 'muéstrame mis cargos' — antes no
había ninguna tool para movimientos individuales (solo totales como fin_saldo_mes), así que el
cerebro no tenía ninguna instrucción obligatoria que seguir para esa pregunta.
"""
from core import brain


def test_hint_movimientos_recientes_dispara_con_mis_cargos():
    assert "fin_movimientos_recientes" in brain._hint_tool("muéstrame mis cargos")


def test_hint_movimientos_recientes_dispara_con_que_he_gastado():
    assert "fin_movimientos_recientes" in brain._hint_tool("qué he gastado esta semana")


def test_hint_movimientos_recientes_no_pisa_el_registro_de_un_gasto_nuevo():
    """'compré'/'gasté' siguen siendo del registro de un gasto NUEVO — no deben terminar
    disparando la lectura de movimientos por accidente de orden."""
    assert "fin_registrar_gasto" in brain._hint_tool("gasté 5000 en el almacén")


def test_hint_saldo_mes_sigue_intacto():
    assert "fin_saldo_mes" in brain._hint_tool("cómo voy de plata")
