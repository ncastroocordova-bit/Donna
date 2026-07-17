"""
cortex_core — la librería del segundo cerebro.
Donna y Noomi Bot la importan directo; el MCP y los loops la envuelven.

Uso típico desde un agente:
    from cortex_core import vault, search
    vault.escribir_nota("Decisión X", "...", carpeta="30-NCC-Automatizaciones",
                        tipo="decision", area="ncc", autor="donna")
    resultados = search.buscar("correlador")
"""
from . import config, vault, search, linter, health, crosslinker, gitsync  # noqa: F401

__version__ = "0.1.0"
