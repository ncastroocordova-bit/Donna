"""Brief (8:00) y cierre (22:00) con resiliencia ante reinicios de Railway.

Resiliencia (Plan v5 §9): al arrancar, Donna chequea si el toque de hoy ya salió
(guardado en `perfil` con categoría `_sistema`); si no, lo manda. Sin punto único
de falla silencioso. Zona horaria: America/Santiago.
"""
import logging
from datetime import datetime, time

from telegram.ext import Application, ContextTypes

import agenda
import brain
import memory
from config import settings
from flows import preguntar_inferencia_pendiente
from modules import finanzas, salud

logger = logging.getLogger(__name__)


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


async def _ya_se_envio(clave: str) -> bool:
    perfil = await memory.get_perfil()
    return perfil.get(clave) == _hoy()


async def _marcar_enviado(clave: str) -> None:
    await memory.set_perfil(clave, _hoy(), categoria="_sistema")


async def _texto_brief() -> str:
    eventos = await agenda.eventos_de_hoy()
    ag = "; ".join(f"{e['hora']} {e['titulo']}" for e in eventos) or "sin eventos"
    señales = " ".join(s for s in [await finanzas.senal_finanzas(), await salud.senal_salud()] if s)
    prompt = (
        f"Es el brief de las 8:00 de Nico. Agenda de hoy: {ag}. {señales} "
        "Dale su día en pocas líneas y, si tienes algo real que aportar (un patrón, un aviso), "
        "dilo con tu voz. Si no tienes nada concreto, no rellenes."
    )
    return await brain.generar(prompt)


async def _texto_cierre() -> str:
    señal = await salud.senal_salud()
    prompt = (
        f"Es el cierre de las 22:00 de Nico. {señal} Cierra el día breve, con tu voz. "
        "Si corresponde, deja el pie para validar una inferencia (la pregunta sale aparte con botones)."
    )
    return await brain.generar(prompt)


async def job_brief(context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = await _texto_brief()
    await context.bot.send_message(settings.nico_telegram_id, texto)
    await _marcar_enviado("_ultimo_brief")
    logger.info("Brief enviado.")


async def job_cierre(context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = await _texto_cierre()
    await context.bot.send_message(settings.nico_telegram_id, texto)
    await _marcar_enviado("_ultimo_cierre")
    await preguntar_inferencia_pendiente(context.bot, settings.nico_telegram_id)
    logger.info("Cierre enviado.")


async def check_pendientes(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Al arrancar: si ya pasó la hora del brief/cierre y no salió hoy, lo manda."""
    ahora = datetime.now(settings.tz)
    if ahora.hour >= 8 and not await _ya_se_envio("_ultimo_brief"):
        logger.info("Brief de hoy pendiente tras reinicio; lo envío.")
        await job_brief(context)
    if ahora.hour >= 22 and not await _ya_se_envio("_ultimo_cierre"):
        logger.info("Cierre de hoy pendiente tras reinicio; lo envío.")
        await job_cierre(context)


def setup_scheduler(app: Application) -> None:
    jq = app.job_queue
    if jq is None:
        raise RuntimeError("JobQueue no disponible. Instala python-telegram-bot[job-queue].")
    tz = settings.tz
    jq.run_daily(job_brief, time=time(8, 0, tzinfo=tz))
    jq.run_daily(job_cierre, time=time(22, 0, tzinfo=tz))
    jq.run_once(check_pendientes, when=10)  # recupera el toque perdido tras un reinicio
    logger.info("Scheduler listo (%s): brief 8:00, cierre 22:00, + chequeo de resiliencia.", settings.timezone)
