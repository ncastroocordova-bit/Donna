"""Módulo Proactividad. Donna rompe el silencio sin que Nico hable primero.

Máx 1 mensaje espontáneo al día. Solo cuando hay una señal real que supera
el umbral: proyecto en riesgo, compromiso vencido, racha de sueño cortada
con agenda pesada al día siguiente. No satura.

El scheduler llama a detectar_senal() al mediodía. Si devuelve algo, genera
y manda. Si no, silencio. El control de "ya mandé hoy" vive en scheduler.py.
"""
import logging
from datetime import datetime, timedelta

from config import settings
from memory import _get_db, get_compromisos_abiertos

logger = logging.getLogger(__name__)

UMBRAL_PROYECTO_SIN_AVANCE_DIAS = 7
UMBRAL_DEADLINE_PROXIMO_DIAS = 14


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


async def _senal_proyecto_en_riesgo() -> str:
    try:
        db = await _get_db()
        r = await db.table("proyectos").select("*").eq("estado", "activo").execute()
        hoy = datetime.now(settings.tz).date()
        limite_alerta = (hoy + timedelta(days=UMBRAL_DEADLINE_PROXIMO_DIAS)).strftime("%Y-%m-%d")
        umbral_updated = (hoy - timedelta(days=UMBRAL_PROYECTO_SIN_AVANCE_DIAS)).isoformat()

        en_riesgo = []
        for p in r.data:
            tiene_deadline = p.get("fecha_limite") and p["fecha_limite"] <= limite_alerta
            sin_avance_reciente = p.get("updated_at", "")[:10] <= umbral_updated
            if tiene_deadline and sin_avance_reciente and p["progreso"] < 90:
                dias = (datetime.strptime(p["fecha_limite"], "%Y-%m-%d").date() - hoy).days
                en_riesgo.append(f"'{p['nombre']}' al {p['progreso']}% (faltan {dias}d)")

        if not en_riesgo:
            return ""
        return f"Proyectos en riesgo: {'; '.join(en_riesgo[:2])}."
    except Exception:
        logger.exception("_senal_proyecto_en_riesgo falló")
        return ""


async def detectar_senal() -> str:
    """Devuelve la señal más urgente, o '' si no hay nada que justifique interrumpir.

    Prioridad: compromisos vencidos > proyectos en riesgo.
    Si no hay señal concreta, silencio — Donna no inventa razones para escribir.
    """
    senal = await _senal_compromiso_vencido()
    if senal:
        return senal
    senal = await _senal_proyecto_en_riesgo()
    if senal:
        return senal
    return ""
