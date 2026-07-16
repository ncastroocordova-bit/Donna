"""Evals de la variedad de textos fijos (core/frases.py)."""
from core import frases


def test_frase_siempre_del_pool():
    for _ in range(20):
        assert frases.frase("sueno_dormi") in frases.POOLS["sueno_dormi"]


def test_frase_no_repite_la_ultima():
    # Con pools de ≥2 variantes, dos llamadas seguidas no dan la misma (evita la última usada).
    a = frases.frase("mits")
    b = frases.frase("mits")
    assert a != b


def test_los_mits_no_empujan_un_solo_canal():
    """Los MITs se contestan por texto O por voz: ninguna variante puede pedir solo audio."""
    for f in frases.POOLS["mits"]:
        assert "por voz:" not in f.lower()


def test_frase_key_desconocido_es_vacio():
    assert frases.frase("no_existe") == ""


def test_todos_los_pools_varian():
    for k, pool in frases.POOLS.items():
        assert len(pool) >= 2, f"'{k}' necesita ≥2 variantes para poder variar"
