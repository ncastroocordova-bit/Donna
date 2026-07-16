"""Evals del motor unificado de esperas (Tanda 1: cancelable, valida antes de aceptar, expira
sola). Puros: sin red, sin Telegram real — `user_data` se simula con un dict cualquiera."""
import time

from core import espera


# ───────────────────────── Ciclo de vida básico ─────────────────────────

def test_iniciar_y_activa():
    ud = {}
    espera.iniciar(ud, "correccion_tx", {"buffer_id": "abc123"})
    esp = espera.activa(ud)
    assert esp is not None
    assert esp["tipo"] == "correccion_tx"
    assert esp["payload"] == {"buffer_id": "abc123"}


def test_activa_sin_espera_devuelve_none():
    assert espera.activa({}) is None


def test_limpiar_borra_la_espera():
    ud = {}
    espera.iniciar(ud, "desglose_cargo", {"buffer_id": "x"})
    espera.limpiar(ud)
    assert espera.activa(ud) is None


def test_iniciar_reemplaza_la_espera_anterior():
    ud = {}
    espera.iniciar(ud, "correccion_tx", {"buffer_id": "primera"})
    espera.iniciar(ud, "desglose_cargo", {"buffer_id": "segunda"})
    esp = espera.activa(ud)
    assert esp["tipo"] == "desglose_cargo"
    assert esp["payload"]["buffer_id"] == "segunda"


# ───────────────────────── Expiración (no insiste con algo viejo) ─────────────────────────

def test_espera_expira_sola():
    ud = {"espera": {"tipo": "correccion_tx", "payload": {}, "creado": time.time() - espera.TTL_SEGUNDOS - 1}}
    assert espera.activa(ud) is None
    assert "espera" not in ud  # se auto-limpió al detectar que expiró


def test_espera_reciente_no_expira():
    ud = {"espera": {"tipo": "correccion_tx", "payload": {}, "creado": time.time() - 60}}
    assert espera.activa(ud) is not None


# ───────────────────────── Cancelación ─────────────────────────

def test_es_cancelacion_reconoce_frases_comunes():
    for frase in ("cancelar", "Olvídalo", "  DÉJALO  ", "nada", "no importa", "mejor no", "ya no"):
        assert espera.es_cancelacion(frase), frase


def test_es_cancelacion_no_confunde_descartar_con_cancelar():
    # "descartar" / "no es mío" son respuestas VÁLIDAS del flujo de corrección del digest (botar
    # la línea), no una cancelación de la espera — no deben ir en la lista de cancelación.
    assert not espera.es_cancelacion("descartar")
    assert not espera.es_cancelacion("no es mío")
    assert not espera.es_cancelacion("no")


def test_es_cancelacion_no_confunde_una_categoria():
    assert not espera.es_cancelacion("Alimentación")


# ───────────────────────── Validador genérico de "respuesta corta" ─────────────────────────

def test_parece_respuesta_corta_acepta_categorias():
    assert espera.parece_respuesta_corta("Alimentación")
    assert espera.parece_respuesta_corta("descartar")
    assert espera.parece_respuesta_corta("Tecnología y Suscripciones")  # 3 palabras, al límite


def test_parece_respuesta_corta_rechaza_vacio_y_preguntas():
    assert not espera.parece_respuesta_corta("")
    assert not espera.parece_respuesta_corta("   ")
    assert not espera.parece_respuesta_corta("¿cuánto llevo gastado este mes?")


def test_parece_respuesta_corta_rechaza_frases_largas():
    # El caso del audit: un mensaje despistado no relacionado con la corrección.
    assert not espera.parece_respuesta_corta("oye cuánto llevo gastado este mes en total")
