"""Donna — punto de entrada. Monolito simple, un proceso (Plan v7)."""
import logging
import os
import tempfile
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import settings
from core import brain, correo, flows, memory, voice
from core.scheduler import setup_scheduler
from modules import aprendizaje, finanzas, salud

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

OFF_RECORD = ("off the record", "off record", "fuera de registro")

ONBOARDING_PROMPT = (
    "[Sistema: es la primera conversación con Nico y tu perfil de él está vacío — no sabes nada todavía. "
    "Preséntate como Donna en una o dos líneas y arranca un onboarding corto y natural para conocerlo. "
    "Pregúntale lo esencial, de a una o dos cosas por mensaje, sin abrumar: cómo quiere que le hables, "
    "a qué se dedica, su meta principal ahora, su situación de plata/deudas, y qué hábitos quiere que le siga. "
    "A medida que te vaya contando, guarda cada hecho estable con actualizar_perfil. Con tu voz, no como formulario.]"
)


def _es_nico(update: Update) -> bool:
    return bool(update.effective_user) and update.effective_user.id == settings.nico_telegram_id


async def _perfil_real() -> dict:
    perfil = await memory.get_perfil()
    return {k: v for k, v in perfil.items() if not k.startswith("_")}


async def _correr_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    history = context.chat_data.get("history", [])
    respuesta, history = await brain.responder(ONBOARDING_PROMPT, history, off_record=True)
    context.chat_data["history"] = history
    await update.message.reply_text(respuesta)


# ───────────────────────── Comandos ─────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_nico(update):
        return
    if await _perfil_real():
        await update.message.reply_text("Soy Donna. Ya era hora.")
    else:
        await _correr_onboarding(update, context)


async def cmd_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_nico(update):
        return
    await _correr_onboarding(update, context)


async def cmd_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vista 'lo que sé de ti' (espina): perfil estable + inferencias top, cada una con su
    dato. Crece con cada módulo; en el Módulo 1 ya muestra lo de plata."""
    if not _es_nico(update):
        return
    perfil = await _perfil_real()
    try:
        inferencias = await memory.get_inferencias_top(5)
    except Exception:
        logger.exception("cmd_perfil: no pude leer inferencias")
        inferencias = []
    if not perfil and not inferencias:
        await update.message.reply_text("Todavía no sé nada de ti. Manda /onboarding y arrancamos.")
        return
    partes = []
    if perfil:
        partes.append("Esto es lo que sé de ti:\n" + "\n".join(f"• {k}: {v}" for k, v in perfil.items()))
    if inferencias:
        marca = {"confirmada": "✓", "pendiente": "·"}
        lineas = "\n".join(f"{marca.get(i.get('estado'), '·')} {i['contenido']}" for i in inferencias)
        partes.append("Y algunos patrones que vengo notando (✓ confirmado, · por validar):\n" + lineas)
    await update.message.reply_text("\n\n".join(partes))


async def cmd_cierre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispara el panel del cierre a mano (útil para probar)."""
    if not _es_nico(update):
        return
    await flows.enviar_panel_cierre(context.bot, update.effective_chat.id, "Cerremos el día.")
    context.bot_data["esperando_mits"] = datetime.now(settings.tz).strftime("%Y-%m-%d")
    await update.message.reply_text("Y por voz: tus 1 a 3 MITs de mañana. 🎙️")


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_nico(update):
        return
    await flows.enviar_digest(context.bot, update.effective_chat.id)


async def cmd_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_nico(update):
        return
    if not correo.disponible():
        await update.message.reply_text("Aún no tengo tu correo conectado. Configura Gmail/Outlook y lo reviso.")
        return
    await flows.enviar_digest_spam(context.bot, update.effective_chat.id)


async def cmd_correos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fuerza una sincronización de correos de gasto al buffer del día."""
    if not _es_nico(update):
        return
    if not correo.disponible():
        await update.message.reply_text("Aún no tengo tu correo conectado.")
        return
    res = await finanzas.ingerir_gastos_email()
    await update.message.reply_text(
        f"Revisé {res['revisados']} correo(s); {res['nuevos']} gasto(s) nuevo(s) al digest de hoy."
    )


# ───────────────────────── Mensajes ─────────────────────────

async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_nico(update):
        return
    texto = update.message.text

    # ¿Está corrigiendo una línea del digest? (categoría o "descartar")
    tx_id = context.user_data.pop("corrigiendo_tx", None)
    if tx_id:
        await update.message.reply_text(await flows.aplicar_correccion_tx(tx_id, texto))
        await flows.enviar_digest(context.bot, update.effective_chat.id)  # re-muestra con "Aceptar todo"
        return

    # ¿Está corrigiendo una inferencia? (la deducción original falló → cuenta como descarte)
    inf_id = context.user_data.pop("corrigiendo_inferencia", None)
    if inf_id:
        inf = await memory.get_inferencia(inf_id)
        await memory.resolver_inferencia(inf_id, "corregida", correccion=texto)
        await aprendizaje.registrar_resultado((inf or {}).get("dominio", ""), acertada=False)
        await update.message.reply_text("Gracias. Actualizado. Eso es lo que importa.")
        return

    off = texto.lower().startswith(OFF_RECORD)
    history = context.chat_data.get("history", [])
    respuesta, history = await brain.responder(texto, history, off_record=off)
    context.chat_data["history"] = history
    await update.message.reply_text(respuesta)


async def manejar_voz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_nico(update):
        return
    f = await update.message.voice.get_file()
    fd, path = tempfile.mkstemp(suffix=".oga")
    os.close(fd)
    try:
        await f.download_to_drive(path)
        texto = await voice.transcribir(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    # Si el cierre está esperando los MITs de mañana, esta voz son los MITs.
    hoy = datetime.now(settings.tz).strftime("%Y-%m-%d")
    if context.bot_data.get("esperando_mits") == hoy:
        context.bot_data.pop("esperando_mits", None)
        await update.message.reply_text(f"_{texto}_\n\n" + await _guardar_mits(texto), parse_mode="Markdown")
        return

    history = context.chat_data.get("history", [])
    respuesta, history = await brain.responder(texto, history)
    context.chat_data["history"] = history
    await update.message.reply_text(f"_{texto}_\n\n{respuesta}", parse_mode="Markdown")


async def _guardar_mits(texto: str) -> str:
    try:
        await salud.registrar_mits(texto)
        return "Anotados tus MITs de mañana. Mañana te los recuerdo en el brief."
    except Exception:
        logger.exception("No pude guardar los MITs")
        return "No pude anotarlos en la planilla, pero los tengo. Reintenta si quieres que queden."


async def manejar_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_nico(update):
        return
    f = await update.message.photo[-1].get_file()
    buf = bytes(await f.download_as_bytearray())
    datos = await finanzas.procesar_foto(buf, "image/jpeg")
    if datos:
        marca = f" (¿{datos['motivo_duda']})" if datos.get("dudosa") and datos.get("motivo_duda") else ""
        await update.message.reply_text(
            f"Leí la boleta: ${datos['monto']:,.0f} → {datos.get('categoria', 'otros')}{marca}. "
            "Lo tienes en el digest del cierre para confirmar."
        )
    else:
        await update.message.reply_text("No pude leer bien la boleta. Pásame el monto y lo dejo listo para el cierre.")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Error procesando un update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Se me trabó algo por dentro. Dame un segundo y reintenta.")


def main() -> None:
    logger.info("Iniciando Donna...")
    app = Application.builder().token(settings.telegram_token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("onboarding", cmd_onboarding))
    app.add_handler(CommandHandler("perfil", cmd_perfil))
    app.add_handler(CommandHandler("cierre", cmd_cierre))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("spam", cmd_spam))
    app.add_handler(CommandHandler("correos", cmd_correos))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))
    app.add_handler(MessageHandler(filters.VOICE, manejar_voz))
    app.add_handler(MessageHandler(filters.PHOTO, manejar_foto))
    app.add_handler(CallbackQueryHandler(flows.on_callback))
    app.add_error_handler(on_error)

    setup_scheduler(app)

    logger.info("Donna lista. Escuchando en Telegram.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
