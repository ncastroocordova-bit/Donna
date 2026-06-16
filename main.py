"""Donna — punto de entrada. Monolito simple, un proceso (Plan v5)."""
import logging
import os
import tempfile

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import brain
import memory
import voice
from config import settings
from flows import on_callback, teclado_habitos
from modules import aprendizaje, finanzas
from scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

OFF_RECORD = ("off the record", "off record", "fuera de registro")

# Instrucción interna para que Donna lidere el onboarding (no se le muestra a Nico
# literal; lo que se muestra es la respuesta de Donna). off_record: no se guarda como memoria.
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
    """Perfil sin las claves de sistema (las que empiezan con '_')."""
    perfil = await memory.get_perfil()
    return {k: v for k, v in perfil.items() if not k.startswith("_")}


async def _correr_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    history = context.chat_data.get("history", [])
    respuesta, history = await brain.responder(ONBOARDING_PROMPT, history, off_record=True)
    context.chat_data["history"] = history
    await update.message.reply_text(respuesta)


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
    if not _es_nico(update):
        return
    perfil = await _perfil_real()
    if not perfil:
        await update.message.reply_text("Todavía no sé nada de ti. Manda /onboarding y arrancamos.")
        return
    lineas = "\n".join(f"• {k}: {v}" for k, v in perfil.items())
    await update.message.reply_text(f"Esto es lo que sé de ti:\n{lineas}")


async def cmd_habitos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_nico(update):
        return
    await update.message.reply_text("¿Qué cumpliste hoy?", reply_markup=teclado_habitos())


async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_nico(update):
        return

    # ¿Está corrigiendo una inferencia? (la deducción original falló → cuenta como descarte)
    inf_id = context.user_data.pop("corrigiendo_inferencia", None)
    if inf_id:
        inf = await memory.get_inferencia(inf_id)
        await memory.resolver_inferencia(inf_id, "corregida", correccion=update.message.text)
        await aprendizaje.registrar_resultado((inf or {}).get("dominio", ""), acertada=False)
        await update.message.reply_text("Gracias. Actualizado. Eso es lo que importa.")
        return

    texto = update.message.text
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
    history = context.chat_data.get("history", [])
    respuesta, history = await brain.responder(texto, history)
    context.chat_data["history"] = history
    await update.message.reply_text(f"_{texto}_\n\n{respuesta}", parse_mode="Markdown")


async def manejar_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_nico(update):
        return
    f = await update.message.photo[-1].get_file()
    buf = bytes(await f.download_as_bytearray())
    datos = await finanzas.procesar_imagen(buf, "image/jpeg")
    if datos:
        await update.message.reply_text(
            f"Boleta lista: ${datos.get('monto')} en {datos.get('categoria', 'otros')}. Ya lo anoté."
        )
    else:
        await update.message.reply_text("No pude leer bien la boleta. Pásame el monto y lo anoto.")


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
    app.add_handler(CommandHandler("habitos", cmd_habitos))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))
    app.add_handler(MessageHandler(filters.VOICE, manejar_voz))
    app.add_handler(MessageHandler(filters.PHOTO, manejar_foto))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_error_handler(on_error)

    setup_scheduler(app)

    logger.info("Donna lista. Escuchando en Telegram.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
