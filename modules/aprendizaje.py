"""Módulo Aprendizaje avanzado (Plan v5 §10, Fase 4).

Aprendizaje en 3 niveles:
  - Nivel 1 (hechos): memoria episódica — vive en memory.py.
  - Nivel 2 (patrones): una inferencia confirmada se consolida como patrón con
    un peso que decae si no se reconfirma.
  - Nivel 3 (calibración): tasa de acierto de inferencias por dominio. Donna usa
    esto para modular su confianza — abre menos inferencias donde suele errar.

Guardia anti-patrones-falsos:
  - Un patrón no se da por cierto con una sola confirmación: arranca con peso bajo
    y solo pesa cuando se repite.
  - El decay baja el peso de patrones viejos; bajo el umbral se silencian.
  - La calibración por dominio frena a Donna en áreas donde acierta poco.
"""
import logging
from datetime import datetime, timedelta

from config import settings
from memory import _get_db

logger = logging.getLogger(__name__)

# Guardia: bajo esta tasa de acierto, Donna debe contenerse en ese dominio.
UMBRAL_CONFIABLE = 0.6
# Mínimo de muestras antes de tomar la tasa en serio (evita juzgar con n=1).
MIN_MUESTRAS = 3
# Decay semanal del peso de un patrón; bajo PESO_MIN se silencia.
DECAY_SEMANAL = 0.85
PESO_MIN = 0.3


# ───────────────────────── Nivel 3: calibración ─────────────────────────

async def registrar_resultado(dominio: str, acertada: bool) -> None:
    """Tras validar una inferencia: suma a confirmadas o descartadas del dominio."""
    dominio = (dominio or "general").strip().lower()
    try:
        db = await _get_db()
        r = await db.table("calibracion").select("*").eq("dominio", dominio).limit(1).execute()
        ahora = datetime.now(settings.tz).isoformat()
        if r.data:
            fila = r.data[0]
            cambios = {
                "confirmadas": fila["confirmadas"] + (1 if acertada else 0),
                "descartadas": fila["descartadas"] + (0 if acertada else 1),
                "updated_at": ahora,
            }
            await db.table("calibracion").update(cambios).eq("dominio", dominio).execute()
        else:
            await db.table("calibracion").insert({
                "dominio": dominio,
                "confirmadas": 1 if acertada else 0,
                "descartadas": 0 if acertada else 1,
                "updated_at": ahora,
            }).execute()
    except Exception:
        logger.exception("registrar_resultado falló")


async def perfil_calibracion() -> str:
    """Resumen para inyectar en el contexto de Donna: dónde acierta y dónde no.

    Solo menciona dominios con suficientes muestras. Vacío si aún no hay datos.
    """
    try:
        db = await _get_db()
        r = await db.table("calibracion").select("*").execute()
        confiables, flojos = [], []
        for fila in r.data:
            total = fila["confirmadas"] + fila["descartadas"]
            if total < MIN_MUESTRAS:
                continue
            tasa = fila["confirmadas"] / total
            if tasa >= UMBRAL_CONFIABLE:
                confiables.append(f"{fila['dominio']} ({tasa:.0%})")
            else:
                flojos.append(f"{fila['dominio']} ({tasa:.0%})")
        if not confiables and not flojos:
            return ""
        partes = []
        if confiables:
            partes.append("Aciertas tus inferencias en: " + ", ".join(confiables) + " — ahí puedes ser más directa.")
        if flojos:
            partes.append("Sueles errar en: " + ", ".join(flojos) + " — ahí abre la inferencia con más cautela o cállala.")
        return "Calibración (autoconocimiento): " + " ".join(partes)
    except Exception:
        logger.exception("perfil_calibracion falló")
        return ""


# ───────────────────────── Nivel 2: patrones ─────────────────────────

async def consolidar_patron(descripcion: str, dominio: str = "") -> None:
    """Una inferencia confirmada se vuelve (o refuerza) un patrón.

    Si ya existe uno parecido (mismo dominio, texto contenido), suma confirmación
    y peso en vez de duplicar. Guardia: el peso arranca bajo y crece al repetirse.
    """
    descripcion = descripcion.strip()
    dominio = (dominio or "general").strip().lower()
    if not descripcion:
        return
    try:
        db = await _get_db()
        ahora = datetime.now(settings.tz).isoformat()
        r = await db.table("patrones").select("*").eq("dominio", dominio).ilike(
            "descripcion", f"%{descripcion[:30]}%"
        ).limit(1).execute()
        if r.data:
            p = r.data[0]
            await db.table("patrones").update({
                "confirmaciones": p["confirmaciones"] + 1,
                "peso": min(p["peso"] + 0.5, 3.0),
                "estado": "activo",
                "last_visto": ahora,
            }).eq("id", p["id"]).execute()
        else:
            await db.table("patrones").insert({
                "descripcion": descripcion,
                "dominio": dominio,
                "peso": 1.0,
                "confirmaciones": 1,
                "last_visto": ahora,
            }).execute()
    except Exception:
        logger.exception("consolidar_patron falló")


async def patrones_activos(limite: int = 5) -> str:
    """Patrones consolidados (peso alto) para que Donna los tenga presentes."""
    try:
        db = await _get_db()
        r = (
            await db.table("patrones")
            .select("descripcion, peso")
            .eq("estado", "activo")
            .order("peso", desc=True)
            .limit(limite)
            .execute()
        )
        if not r.data:
            return ""
        return "Patrones confirmados de Nico:\n" + "\n".join(f"- {p['descripcion']}" for p in r.data)
    except Exception:
        logger.exception("patrones_activos falló")
        return ""


# ───────────────────────── Decay (job semanal) ─────────────────────────

async def aplicar_decay() -> int:
    """Baja el peso de los patrones no reconfirmados hace >7 días. Silencia los
    que caen bajo PESO_MIN. Devuelve cuántos silenció. Lo llama el scheduler."""
    try:
        db = await _get_db()
        corte = (datetime.now(settings.tz) - timedelta(days=7)).isoformat()
        r = await db.table("patrones").select("*").eq("estado", "activo").lt("last_visto", corte).execute()
        silenciados = 0
        for p in r.data:
            nuevo_peso = p["peso"] * DECAY_SEMANAL
            if nuevo_peso < PESO_MIN:
                await db.table("patrones").update({"estado": "silenciado", "peso": nuevo_peso}).eq("id", p["id"]).execute()
                silenciados += 1
            else:
                await db.table("patrones").update({"peso": nuevo_peso}).eq("id", p["id"]).execute()
        return silenciados
    except Exception:
        logger.exception("aplicar_decay falló")
        return 0


# ───────────────────────── Señal para el contexto ─────────────────────────

async def senal_aprendizaje() -> str:
    """Bloque que el brain inyecta en el contexto: patrones + calibración.
    Le da a Donna autoconocimiento sin saturar — solo lo consolidado."""
    bloques = [b for b in [await patrones_activos(), await perfil_calibracion()] if b]
    return "\n\n".join(bloques)
