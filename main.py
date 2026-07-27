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
from core import brain, correo, espera, flows, frases, memory, voice
from core.scheduler import (
    DELAY_CORRELACION,
    es_domingo,
    job_correlacionar_una_vez,
    setup_scheduler,
    texto_brief_manual,
)
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


def _hoy_str() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


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


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """El brief de las 8:00 a demanda: para verlo si se te pasó y para verificar el heartbeat
    sin esperar a mañana. Solo lectura — no consume el brief programado (ver texto_brief_manual)."""
    if not _es_nico(update):
        return
    await update.message.reply_text(await texto_brief_manual())


async def cmd_cierre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispara el panel del cierre a mano (útil para probar)."""
    if not _es_nico(update):
        return
    await flows.enviar_panel_cierre(context.bot, update.effective_chat.id, "Cerremos el día.")
    await _preguntar_paso(update, context, "mits", "mits")   # arranca la misma cadena del job


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


async def cmd_lista(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """La lista del súper con toques para marcar comprado (módulo Compras)."""
    if not _es_nico(update):
        return
    await flows.enviar_lista_compras(context.bot, update.effective_chat.id)


# ───────────────────────── Esperas de un turno (Tanda 1) ─────────────────────────
# Punto único por el que pasa TODO mensaje (texto o voz ya transcrita) antes del cerebro: ¿hay
# algo que Donna esperaba (un monto, una categoría, un desglose, la corrección de una inferencia)
# y este mensaje lo resuelve? Antes cada espera vivía suelta y se tragaba lo que fuera; ahora se
# puede cancelar, expira sola, y si la respuesta no tiene pinta de tal se suelta y sigue normal
# hacia el cerebro — ver core/espera.py.

_CANCELAR_MSGS = {
    "correccion_tx": "Ok, dejo esa línea como estaba. Tócala de nuevo si quieres corregirla.",
    "correccion_item_cat": "Ok, no le cambio la categoría a ese ítem.",
    "correccion_item_nombre": "Ok, no le cambio el nombre a ese ítem.",
    "desglose_cargo": "Ok, lo dejamos para el cierre.",
    "foto_cargo": "Ok, sin foto. El cargo queda igual en el digest.",
    "correccion_inferencia": "Ok, no la corrijo. Sigue como estaba.",
}


async def _resolver_correccion_tx(update, context, payload: dict, texto: str, eco) -> bool:
    if not espera.parece_respuesta_corta(texto):
        return False
    await eco()  # el eco de voz sale SOLO tras validar que este mensaje sí resuelve la espera
    await update.message.reply_text(await flows.aplicar_correccion_tx(payload["buffer_id"], texto))
    # El digest vivo se re-dibuja EN SU LUGAR (no se apila otro digest en el chat).
    await flows.refrescar_digest(context.bot, update.effective_chat.id)
    return True


async def _resolver_correccion_item_cat(update, context, payload: dict, texto: str, eco) -> bool:
    if not espera.parece_respuesta_corta(texto):
        return False
    buf = context.user_data.get("items_buffer")
    idx = context.user_data.get("item_idx")
    it = await flows.corregir_categoria_item(buf, idx, texto) if buf is not None and idx is not None else None
    await eco()
    if it:
        await update.message.reply_text(f"«{it.get('item', '')}» → {it.get('categoria', '')}. Quedó.")
    else:
        await update.message.reply_text("No pude actualizar ese ítem.")
    await flows.refrescar_digest(context.bot, update.effective_chat.id)
    return True


async def _resolver_correccion_item_nombre(update, context, payload: dict, texto: str, eco) -> bool:
    if not espera.parece_respuesta_corta(texto):
        return False
    buf = context.user_data.get("items_buffer")
    idx = context.user_data.get("item_idx")
    it = await flows.corregir_nombre_item(buf, idx, texto) if buf is not None and idx is not None else None
    await eco()
    if it:
        await update.message.reply_text(f"«{it.get('item', '')}», anotado. Ya no te lo vuelvo a preguntar.")
    else:
        await update.message.reply_text("No pude actualizar ese ítem.")
    await flows.refrescar_digest(context.bot, update.effective_chat.id)
    return True


async def _resolver_desglose_cargo(update, context, payload: dict, texto: str, eco) -> bool:
    if not texto.strip() or texto.strip().endswith("?"):
        return False
    cargo_id = payload["buffer_id"]
    await eco()
    await update.message.reply_text(await finanzas.desglosar_cargo(cargo_id, texto))
    # El digest vuelve actualizado (la línea ya muestra sus ítems); si algún ítem quedó dudoso,
    # el botón 📋 lo trae con su grilla de excepciones.
    await flows.refrescar_digest(context.bot, update.effective_chat.id)
    return True


async def _resolver_correccion_inferencia(update, context, payload: dict, texto: str, eco) -> bool:
    if not texto.strip() or texto.strip().endswith("?"):
        return False
    inf_id = payload["inf_id"]
    inf = await memory.get_inferencia(inf_id)
    await memory.resolver_inferencia(inf_id, "corregida", correccion=texto)
    await aprendizaje.registrar_resultado((inf or {}).get("dominio", ""), acertada=False)
    await eco()
    await update.message.reply_text("Gracias. Actualizado. Eso es lo que importa.")
    return True


_MANEJADORES_ESPERA = {
    "correccion_tx": _resolver_correccion_tx,
    "correccion_item_cat": _resolver_correccion_item_cat,
    "correccion_item_nombre": _resolver_correccion_item_nombre,
    "desglose_cargo": _resolver_desglose_cargo,
    # Donna pidió la boleta, pero si Nico igual lo escribe ("pañales 12000, resto abarrotes") eso
    # vale como desglose del MISMO cargo: mismo payload, mismo resolvedor. Sin esto el tipo no
    # tenía manejador, la espera se descartaba y el texto se iba al cerebro — perdiendo el vínculo
    # con el cargo que el propio Nico acababa de establecer al tocar 📷.
    "foto_cargo": _resolver_desglose_cargo,
    "correccion_inferencia": _resolver_correccion_inferencia,
}


# ───────────────────────── Cadena del cierre (MITs → evento → peso) ─────────────────────────
# El cierre hace UNA pregunta abierta a la vez y la siguiente sale recién cuando la anterior se
# contesta. Antes las tres salían juntas y el flag de MITs se tragaba cualquier audio: contestar
# el peso por voz lo guardaba como MIT. Como esto vive en `_procesar_entrada`, texto y voz
# funcionan igual sin código duplicado.

def _parece_respuesta_abierta(texto: str) -> bool:
    """¿Tiene pinta de RESPUESTA y no de otra cosa? Una pregunta de Nico ('¿cómo va mi deuda?')
    en medio del cierre no es su MIT: se suelta y sigue al cerebro, y la cadena queda esperando."""
    t = (texto or "").strip()
    return bool(t) and not t.endswith("?")


async def _preguntar_paso(update, context, paso: str, frase_key: str) -> None:
    context.bot_data["cierre_cadena"] = {"paso": paso, "fecha": _hoy_str()}
    await update.message.reply_text(frases.frase(frase_key))


async def _resolver_cadena_cierre(update, context, texto: str, eco) -> bool:
    """True si este mensaje resolvió un paso de la cadena (no debe seguir al cerebro)."""
    cad = context.bot_data.get("cierre_cadena")
    if not cad or cad.get("fecha") != _hoy_str():
        return False
    paso = cad.get("paso")

    if paso == "mits":
        if not _parece_respuesta_abierta(texto):
            return False
        await eco()
        await update.message.reply_text(await _guardar_mits(texto))
        await _preguntar_paso(update, context, "evento", "evento_contextual")
        return True

    if paso == "evento":
        if not _parece_respuesta_abierta(texto):
            return False
        await eco()
        try:
            r = await salud.evento_contextual(texto)
        except Exception:
            logger.exception("No pude guardar el evento contextual")
            r = ""
        # `evento_contextual` devuelve '' cuando Nico dice que no pasó nada: no hay nada que
        # guardar, pero la cadena igual avanza (respondió).
        await update.message.reply_text(r or "Ok, nada que anotar entonces.")
        if es_domingo():
            await _preguntar_paso(update, context, "peso", "peso_semanal")
        else:
            context.bot_data.pop("cierre_cadena", None)
        return True

    if paso == "peso":
        if not salud.parece_peso(texto):
            return False        # no era el peso (una pregunta, un comentario) → sigue al cerebro
        await eco()
        await update.message.reply_text(await salud.registrar_peso(texto))
        context.bot_data.pop("cierre_cadena", None)
        return True

    context.bot_data.pop("cierre_cadena", None)
    return False


async def _procesar_entrada(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str, es_voz: bool = False) -> bool:
    """¿Este mensaje resuelve algo que Donna estaba esperando? True si quedó consumido acá (no
    debe seguir al cerebro). Cubre, en orden: el gasto sin monto legible (global de finanzas, sin
    contexto de Telegram) y las esperas de un turno (digest / ítems / desglose / inferencia).

    El eco de la transcripción ('🎙️ Escuché…') se emite SOLO cuando el mensaje efectivamente
    resuelve la espera: si cae al cerebro, el eco lo pone manejar_voz (uno solo, no dos)."""
    async def eco():
        if es_voz:
            await update.message.reply_text(f"🎙️ Escuché: «{texto}»")

    if finanzas.hay_gasto_incompleto():
        r = await finanzas.completar_gasto_incompleto(texto)
        if r:
            await eco()
            await update.message.reply_text(r)
            return True
        finanzas.limpiar_gasto_incompleto()  # no era el monto → sigue normal
        return False

    if await _resolver_cadena_cierre(update, context, texto, eco):
        return True

    esp = espera.activa(context.user_data)
    if esp is None:
        return False
    if espera.es_cancelacion(texto):
        espera.limpiar(context.user_data)
        await eco()
        await update.message.reply_text(_CANCELAR_MSGS.get(esp["tipo"], "Ok, lo dejamos."))
        if esp["tipo"] in ("correccion_tx", "correccion_item_cat", "correccion_item_nombre", "desglose_cargo", "foto_cargo"):
            # El ancla del digest quedó mutada en modo pregunta → restaurarla a la vista normal.
            await flows.refrescar_digest(context.bot, update.effective_chat.id)
        return True
    manejador = _MANEJADORES_ESPERA.get(esp["tipo"])
    if manejador is None:
        espera.limpiar(context.user_data)
        return False
    resuelto = await manejador(update, context, esp["payload"], texto, eco)
    if not resuelto:
        return False  # no calzó -> se deja caer al cerebro (manejar_voz pone su propio eco)
    espera.limpiar(context.user_data)
    return True


# ───────────────────────── Mensajes ─────────────────────────

async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_nico(update):
        return
    texto = update.message.text

    if await _procesar_entrada(update, context, texto):
        return

    off = texto.lower().startswith(OFF_RECORD)
    history = context.chat_data.get("history", [])
    respuesta, history, tools, _ = await brain.responder(texto, history, off_record=off, _return_tools=True)
    context.chat_data["history"] = history
    await update.message.reply_text(respuesta)
    # Si dictó una compra con detalle, agenda la correlación con el correo del banco a +30 min.
    if "fin_compra_detallada" in tools and context.job_queue:
        context.job_queue.run_once(job_correlacionar_una_vez, DELAY_CORRELACION)


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

    if await _procesar_entrada(update, context, texto, es_voz=True):
        return
    # Los MITs ya NO se capturan acá: la cadena del cierre los toma en _procesar_entrada, que
    # ven por igual el texto y la voz. Antes esto vivía solo en el handler de voz y por eso los
    # MITs eran voice-only (y se tragaban el audio del peso).

    history = context.chat_data.get("history", [])
    respuesta, history, tools, _ = await brain.responder(texto, history, _return_tools=True)
    context.chat_data["history"] = history
    await update.message.reply_text(f"_{texto}_\n\n{respuesta}", parse_mode="Markdown")
    if "fin_compra_detallada" in tools and context.job_queue:
        context.job_queue.run_once(job_correlacionar_una_vez, DELAY_CORRELACION)


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
    # ¿Donna pidió LA boleta de un cargo concreto? Entonces los ítems van a ese cargo, sin pasar
    # por la correlación (el vínculo ya lo puso Nico al tocar 📷). La espera expira sola a los
    # 15 min como todas: una foto que llega después es una boleta suelta, no la respuesta.
    esp = espera.activa(context.user_data)
    if esp and esp["tipo"] == "foto_cargo":
        espera.limpiar(context.user_data)
        msg = await finanzas.adjuntar_foto_a_cargo(esp["payload"]["buffer_id"], buf, "image/jpeg")
        await update.message.reply_text(msg)
        await flows.refrescar_digest(context.bot, update.effective_chat.id)
        return
    datos = await finanzas.procesar_foto(buf, "image/jpeg")
    if datos:
        n_items = len(datos.get("items") or [])
        detalle = f", {n_items} ítem(s)" if n_items else ""
        cruce = " Lo cruzo con el cargo de tu correo para no contarlo dos veces." if n_items else ""
        await update.message.reply_text(
            f"Leí la boleta: {finanzas.clp(datos['monto'])} → {datos.get('categoria', 'otros')}{detalle}.{cruce} "
            "Lo confirmas en el digest del cierre."
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
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("cierre", cmd_cierre))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("spam", cmd_spam))
    app.add_handler(CommandHandler("correos", cmd_correos))
    app.add_handler(CommandHandler("lista", cmd_lista))
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
