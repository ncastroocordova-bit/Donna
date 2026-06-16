"""Flujos de botones de Telegram: hábitos de un toque e inferencias para validar."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import memory
from modules import aprendizaje, salud

logger = logging.getLogger(__name__)


def teclado_habitos() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(h.capitalize(), callback_data=f"hab_{h}")] for h in salud.HABITOS])


async def preguntar_inferencia_pendiente(bot, chat_id: int) -> None:
    """Si hay una inferencia pendiente, la manda con botones para validar (mecanismo estrella)."""
    pendientes = await memory.get_inferencias_pendientes()
    if not pendientes:
        return
    inf = pendientes[0]
    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Sí, me pasa", callback_data=f"inf_confirmada_{inf['id']}"),
            InlineKeyboardButton("No, coincidencia", callback_data=f"inf_descartada_{inf['id']}"),
        ],
        [InlineKeyboardButton("Es por otra razón...", callback_data=f"inf_corregir_{inf['id']}")],
    ])
    await bot.send_message(
        chat_id,
        f"Vengo notando algo y quiero validarlo antes de darlo por cierto:\n\n_{inf['contenido']}_\n\n¿Te pasa, o es coincidencia?",
        reply_markup=teclado,
        parse_mode="Markdown",
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data

    if data.startswith("hab_"):
        habito = data.split("_", 1)[1]
        msg = await salud._marcar_habito({"habito": habito})
        await q.edit_message_text(msg)
        return

    if data.startswith("inf_"):
        _, accion, inf_id = data.split("_", 2)
        inf = await memory.get_inferencia(inf_id)
        dominio = (inf or {}).get("dominio", "")
        if accion == "confirmada":
            await memory.resolver_inferencia(inf_id, "confirmada")
            await aprendizaje.registrar_resultado(dominio, acertada=True)
            if inf:
                await aprendizaje.consolidar_patron(inf["contenido"], dominio)
            await q.edit_message_text("Anotado. Lo tengo como patrón confirmado. Te conozco.")
        elif accion == "descartada":
            await memory.resolver_inferencia(inf_id, "descartada")
            await aprendizaje.registrar_resultado(dominio, acertada=False)
            await q.edit_message_text("Entendido. Lo archivo. No insisto.")
        elif accion == "corregir":
            context.user_data["corrigiendo_inferencia"] = inf_id
            await q.edit_message_text("Cuéntame — ¿por qué pasa de verdad?")
