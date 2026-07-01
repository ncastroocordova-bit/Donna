"""Brief (8:00) y cierre (22:00) con resiliencia ante reinicios de Railway (Plan v7 §5).

Brief — SOLO LECTURA (~5s): agenda + saldo del mes corriendo + recordatorios próximos +
señal de salud, y un botón para el sueño (1 toque).

Cierre — PANEL ÚNICO (~45–50s): hábitos + ánimo + "¿avanzaste un MIT?" por toque, MITs de
mañana por voz, el DIGEST financiero, y la línea madre de las 23:00.

Resiliencia: al arrancar, Donna chequea en `jobs_log` si el brief/cierre de hoy ya salió;
si no, lo manda. Sin punto único de falla silencioso. Zona horaria: America/Santiago.
"""
import logging
from datetime import datetime, time, timedelta

from telegram.ext import Application, ContextTypes

from config import settings
from core import agenda, brain, correlador, correo, flows, memory
from modules import aprendizaje, finanzas, proactividad, proyectos, recordatorios, salud

logger = logging.getLogger(__name__)


# ───────────────────────── Brief 8:00 (read-only) ─────────────────────────

async def _texto_brief() -> str:
    eventos = await agenda.eventos_de_hoy()
    ag = "; ".join(f"{e['hora']} {e['titulo']}" for e in eventos) or "sin eventos"
    aviso_correo = ("AVISO REAL para decirle a Nico: perdí el acceso a tu correo financiero "
                    "(el token venció); no estoy registrando gastos por mail hasta que me re-autorices."
                    if correo.disponible() and correo.gmail_token_invalido() else "")
    señales = " ".join(s for s in [
        aviso_correo,
        await finanzas.senal_finanzas(),
        await salud.senal_salud(),
        await salud.senal_mits_brief(),
        await recordatorios.texto_proximos(7),
        await proyectos.senal_proyectos(),
    ] if s)
    prompt = (
        f"Es el brief de las 8:00 de Nico (solo lectura, breve). Agenda de hoy: {ag}. {señales} "
        "Dale su día en pocas líneas con tu voz. Si tienes un patrón o aviso real, dilo. Si no, no rellenes. "
        "No le pidas datos: el sueño se lo pregunto aparte con un botón."
    )
    return await brain.generar(prompt)


async def job_brief(context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = await _texto_brief()
    await context.bot.send_message(settings.nico_telegram_id, texto)
    await context.bot.send_message(
        settings.nico_telegram_id, "¿Cuánto dormiste?", reply_markup=flows.teclado_brief_sueno()
    )
    try:
        await salud.marcar_brief()
    except Exception:
        logger.exception("No pude marcar Brief ✓ en Diario")
    await memory.marcar_job("brief")
    logger.info("Brief enviado.")


# ───────────────────────── Cierre 22:00 (panel + digest) ─────────────────────────

async def _texto_cierre() -> str:
    señales = " ".join(s for s in [await salud.senal_salud(), await proyectos.senal_proyectos()] if s)
    prompt = (
        f"Es el cierre de las 22:00 de Nico. {señales} Cierra el día en una o dos líneas con tu voz. "
        f"Si el sueño viene flojo, deja caer la línea madre (a la cama a las {settings.meta_hora_dormir}, "
        "te conozco). Los toques de hábitos, ánimo y MIT salen aparte en un panel."
    )
    return await brain.generar(prompt)


async def job_cierre(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = settings.nico_telegram_id
    # 0) Sincroniza correos de gasto al buffer para que el digest de las 22:00 esté completo.
    await finanzas.ingerir_gastos_email()
    intro = await _texto_cierre()
    # 1) Panel único de toques (hábitos + ánimo + MIT).
    await flows.enviar_panel_cierre(context.bot, chat, intro)
    # 2) MITs de mañana por voz (la próxima nota de voz se interpreta como MITs).
    context.bot_data["esperando_mits"] = datetime.now(settings.tz).strftime("%Y-%m-%d")
    await context.bot.send_message(chat, "Y por voz: dime tus 1 a 3 prioridades de mañana. 🎙️")
    # 2.5) Evento contextual (E8): lo que Nico no controló hoy, para que el correlador no lo
    # confunda con un patrón. Conversacional — no bloquea el panel ni cuenta contra Proactividad.
    await context.bot.send_message(
        chat, "¿Hubo algo hoy fuera de tu control que te bajó el ánimo o no te dejó hacer lo planeado?"
    )
    # 2.6) Peso (E8): se pide solo los domingos, no diario.
    if datetime.now(settings.tz).weekday() == 6:
        await context.bot.send_message(chat, "Y como es domingo: ¿cuánto pesaste esta semana?")
    # 3) Digest financiero del día.
    await flows.enviar_digest(context.bot, chat)
    # 3.5) La espina aprende de la plata (perfil + inferencia de deuda con su dato).
    try:
        await finanzas.sembrar_espina()
    except Exception:
        logger.exception("No pude sembrar la espina de finanzas")
    # 3.6) El correlador cruza dominios (sueño↔ánimo↔gasto) si ya hay datos suficientes.
    try:
        await correlador.correr()
    except Exception:
        logger.exception("No pude correr el correlador")
    # 4) Inferencia pendiente, si hay (puede ser la que acaba de sembrar la espina).
    await flows.preguntar_inferencia_pendiente(context.bot, chat)
    try:
        await salud.marcar_cierre()
    except Exception:
        logger.exception("No pude marcar Cierre ✓ en Diario")
    await memory.marcar_job("cierre")
    logger.info("Cierre enviado.")


# ───────────────────────── Resumen semanal (domingo, E8) ─────────────────────────

async def job_resumen_semanal(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Domingo: Salud calcula score de hábitos + ventanas de ayuno/sueño + último peso y los
    deja en `Semanal` (lectura). No manda mensaje aparte — se lee bajo demanda o el domingo."""
    try:
        r = await salud.generar_resumen_semanal()
        logger.info("Resumen semanal escrito (%s): score=%s", r["semana"], r["score"].get("score"))
    except Exception:
        logger.exception("No pude generar el resumen semanal de Salud")


# ───────────────────────── Proactividad 12:00 ─────────────────────────

async def job_proactividad(context: ContextTypes.DEFAULT_TYPE) -> None:
    if await memory.job_ya_corrio("proactividad"):
        return
    senal = await proactividad.detectar_senal()
    if not senal:
        return
    prompt = (
        f"Nico no te habló hoy todavía. Tienes esta señal concreta: {senal} "
        "Rómpele el silencio con tu voz — una sola cosa, sin rollos."
    )
    texto = await brain.generar(prompt)
    await context.bot.send_message(settings.nico_telegram_id, texto)
    await memory.marcar_job("proactividad")
    logger.info("Proactividad enviada: %s", senal[:60])


async def job_decay(context: ContextTypes.DEFAULT_TYPE) -> None:
    silenciados = await aprendizaje.aplicar_decay()
    logger.info("Decay aplicado; %d patrón(es) silenciado(s).", silenciados)


# ───────────────────────── Correo: gastos (sync) + spam (digest) ─────────────────────────

async def job_sync_correos(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trae los correos de gasto al buffer cada pocas horas (solo Gmail; Outlook OFF)."""
    if not correo.disponible():
        return
    res = await finanzas.ingerir_gastos_email()
    if res["nuevos"]:
        logger.info("Sync de correos: %d gasto(s) nuevo(s) al buffer.", res["nuevos"])


# ───────────────────────── Compras: detalle (v3) ─────────────────────────

POLL_COMPRAS = timedelta(hours=5)        # cada cuánto Donna revisa cargos de compras sin detalle
DELAY_CORRELACION = timedelta(minutes=30)  # tras dictar una compra, espera el correo del banco
MAX_PREGUNTAS_COMPRA = 3                  # tope por corrida, para no inundar de mensajes


async def job_preguntar_compras(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Poll cada 5h: por cada cargo de un comercio 'de compras' sin detalle, Donna pregunta
    '¿qué compraste?'. Marca el cargo como preguntado para no insistir."""
    if not correo.disponible():
        return
    await finanzas.ingerir_gastos_email()  # trae cargos nuevos + correlaciona lo que ya tenga detalle
    cargos = await finanzas.cargos_sin_detalle()
    for c in cargos[:MAX_PREGUNTAS_COMPRA]:
        try:
            await context.bot.send_message(
                settings.nico_telegram_id,
                f"Vi {finanzas.clp(c.get('monto'))} en {c.get('comercio') or 'un comercio'} — ¿qué compraste?",
                reply_markup=flows.teclado_pregunta_compra(c["id"]),
            )
            await memory.buffer_marcar_preguntado(c["id"])
        except Exception:
            logger.exception("job_preguntar_compras: no pude preguntar por un cargo")
    if cargos:
        logger.info("Compras: pregunté por %d cargo(s) sin detalle.", min(len(cargos), MAX_PREGUNTAS_COMPRA))


async def job_correlacionar_una_vez(context: ContextTypes.DEFAULT_TYPE) -> None:
    """One-shot a +30 min de que Nico dicta una compra: ingiere el correo (ya debería haber
    llegado el cargo del banco) y lo cruza con el detalle dictado, sin doble conteo."""
    if not correo.disponible():
        return
    res = await finanzas.ingerir_gastos_email()
    if res.get("correlacionados"):
        await context.bot.send_message(
            settings.nico_telegram_id,
            "Listo, crucé tu compra con el cargo del banco — quedó como un solo gasto para el cierre.",
        )


async def job_spam(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Digest diario de spam (con borrado por confirmación)."""
    if not correo.disponible() or await memory.job_ya_corrio("spam"):
        return
    await flows.enviar_digest_spam(context.bot, settings.nico_telegram_id)
    await memory.marcar_job("spam")
    logger.info("Digest de spam enviado.")


# ───────────────────────── Resiliencia ─────────────────────────

async def check_pendientes(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Al arrancar: si ya pasó la hora del brief/cierre y no salió hoy, lo manda."""
    ahora = datetime.now(settings.tz)
    if ahora.hour >= 8 and not await memory.job_ya_corrio("brief"):
        logger.info("Brief de hoy pendiente tras reinicio; lo envío.")
        await job_brief(context)
    if ahora.hour >= 22 and not await memory.job_ya_corrio("cierre"):
        logger.info("Cierre de hoy pendiente tras reinicio; lo envío.")
        await job_cierre(context)
    if correo.disponible() and ahora.hour >= settings.spam_hora and not await memory.job_ya_corrio("spam"):
        logger.info("Digest de spam pendiente tras reinicio; lo envío.")
        await job_spam(context)


def setup_scheduler(app: Application) -> None:
    jq = app.job_queue
    if jq is None:
        raise RuntimeError("JobQueue no disponible. Instala python-telegram-bot[job-queue].")
    tz = settings.tz
    jq.run_daily(job_brief, time=time(8, 0, tzinfo=tz))
    jq.run_daily(job_proactividad, time=time(12, 0, tzinfo=tz))
    jq.run_daily(job_cierre, time=time(22, 0, tzinfo=tz))
    jq.run_daily(job_resumen_semanal, time=time(22, 30, tzinfo=tz), days=(0,))  # domingo (PTB: 0=domingo)
    jq.run_repeating(job_decay, interval=timedelta(days=7), first=timedelta(hours=1))
    if correo.disponible():
        jq.run_repeating(job_sync_correos, interval=timedelta(hours=3), first=timedelta(minutes=2))
        jq.run_repeating(job_preguntar_compras, interval=POLL_COMPRAS, first=timedelta(minutes=15))
        jq.run_daily(job_spam, time=time(settings.spam_hora, 0, tzinfo=tz))
        logger.info("Correo activo (%s): sync de gastos cada 3h + pregunta-compras cada 5h + digest de spam %d:00.",
                    ", ".join(correo.proveedores_activos()), settings.spam_hora)
    jq.run_once(check_pendientes, when=10)  # recupera el toque perdido tras un reinicio
    logger.info(
        "Scheduler listo (%s): brief 8:00, proactividad 12:00, cierre 22:00 (+digest), "
        "resumen semanal domingo 22:30, decay semanal, + resiliencia.",
        settings.timezone,
    )
