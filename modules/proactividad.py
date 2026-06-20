"""Módulo Proactividad. Donna rompe el silencio sin que Nico hable primero.

Máx 1 mensaje espontáneo al día. Solo cuando hay una señal real que supera
el umbral: proyecto en riesgo, compromiso vencido, racha de sueño cortada
con agenda pesada al día siguiente. No satura.

El scheduler llama a detectar_senal() al mediodía. Si devuelve algo, genera
y manda. Si no, silencio. El control de "ya mandé hoy" vive en scheduler.py.
"""
import logging
from datetime import datetime

from config import settings
from core.memory import get_compromisos_abiertos
from modules import metas, proyectos

logger = logging.getLogger(__name__)


async def _senal_compromiso_vencido() -> str:
    try:
        compromisos = await get_compromisos_abiertos()
        hoy = datetime.now(settings.tz).strftime("%Y-%m-%d")
        vencidos = [c for c in compromisos if c.get("fecha_limite") and c["fecha_limite"] < hoy]
        if not vencidos:
            return ""
        nombres = ", ".join(f"'{c['descripcion'][:50]}'" for c in vencidos[:2])
        extra = f" (y {len(vencidos) - 2} más)" if len(vencidos) > 2 else ""
        return f"Compromisos vencidos sin cerrar: {nombres}{extra}."
    except Exception:
        logger.exception("_senal_compromiso_vencido falló")
        return ""


async def detectar_senal() -> str:
    """Devuelve la señal más urgente, o '' si no hay nada que justifique interrumpir.

    Prioridad: compromisos vencidos > proyectos en riesgo > metas atrasadas.
    Si no hay señal concreta, silencio — Donna no inventa razones para escribir.
    """
    for fn in (_senal_compromiso_vencido, proyectos.senal_proyectos, metas.senal_metas):
        senal = await fn()
        if senal:
            return senal
    return ""
