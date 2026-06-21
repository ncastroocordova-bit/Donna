"""Flujos de botones de Telegram (Plan v7 §5: toque > texto, panel > conversación).

Tres piezas:
- Panel del cierre 22:00: hábitos + ánimo + "¿avanzaste un MIT?" en un solo mensaje.
- Digest financiero: lista del día pre-categorizada + "✅ Aceptar todo" / tap por línea.
- Validación de inferencias: el mecanismo estrella (botones sí/no/corregir).
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core import memory
from modules import aprendizaje, finanzas, salud
from modules import spam as spam_mod

logger = logging.getLogger(__name__)

CHIPS_COMIDA = ["19:00", "20:00", "21:00", "22:00"]


# ───────────────────────── Panel del cierre ─────────────────────────

def teclado_cierre(estado: dict | None = None) -> InlineKeyboardMarkup:
    """Panel del cierre. `estado` marca con ✅ lo ya elegido (se reconstruye en cada toque,
    sin cerrar el panel) — así Nico puede anotar varios hábitos, no solo uno."""
    e = estado or {}

    def mk(label: str, on: bool) -> str:
        return ("✅ " + label) if on else label

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(mk("🏃 Ejercicio", e.get("ejercicio")), callback_data="hab:ejercicio"),
         InlineKeyboardButton(mk("🧘 Meditación", e.get("meditacion")), callback_data="hab:meditacion")],
        [InlineKeyboardButton(mk(f"🍽️ {h}", e.get("comida") == h), callback_data=f"comida:{h}") for h in CHIPS_COMIDA[:2]],
        [InlineKeyboardButton(mk(f"🍽️ {h}", e.get("comida") == h), callback_data=f"comida:{h}") for h in CHIPS_COMIDA[2:]],
        [InlineKeyboardButton(mk(f"Ánimo {n}", e.get("animo") == n), callback_data=f"animo:{n}") for n in ("1", "2", "3", "4")],
        [InlineKeyboardButton(mk("Avancé un MIT", e.get("mit") == "si"), callback_data="mit:si"),
         InlineKeyboardButton(mk("Hoy no", e.get("mit") == "no"), callback_data="mit:no")],
    ])


def teclado_brief_sueno() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("😴 Dormí 7h+", callback_data="sueno:si"),
        InlineKeyboardButton("Menos de 7h", callback_data="sueno:no"),
    ]])


async def enviar_panel_cierre(bot, chat_id: int, intro: str) -> None:
    await bot.send_message(chat_id, intro, reply_markup=teclado_cierre())


# ───────────────────────── Digest financiero ─────────────────────────

def _teclado_digest(d: dict) -> InlineKeyboardMarkup:
    filas = [[InlineKeyboardButton("✅ Aceptar todo", callback_data="digest:aceptar")]]
    for m in d["movimientos"][:10]:
        etiqueta = ("⚠️ " if m["dudosa"] else "✏️ ") + (m["comercio"] or m["categoria"])[:25]
        filas.append([InlineKeyboardButton(etiqueta, callback_data=f"digest:fix:{m['id']}")])
    return InlineKeyboardMarkup(filas)


def _texto_digest(d: dict) -> str:
    if d["n"] == 0:
        return "Hoy no detecté movimientos. Tu plata quedó quieta."
    lineas = []
    for m in d["movimientos"]:
        marca = f"  ⚠️ {m['motivo_duda']}" if m["dudosa"] else ""
        lineas.append(f"• {m['comercio'] or m['categoria']}: {finanzas.clp(m['monto'])} → {m['categoria']}{marca}")
    cab = f"Tienes {d['n']} movimiento(s) por confirmar ({finanzas.clp(d['total'])})."
    if d["n_dudosas"]:
        cab += f" Hay {d['n_dudosas']} que quiero confirmar contigo."
    return cab + "\n\n" + "\n".join(lineas) + "\n\nToca «Aceptar todo» o la línea que esté mal."


async def enviar_digest(bot, chat_id: int) -> None:
    d = await finanzas.armar_digest()
    if d["n"] == 0:
        await bot.send_message(chat_id, _texto_digest(d))
        return
    await bot.send_message(chat_id, _texto_digest(d), reply_markup=_teclado_digest(d))


# ───────────────────────── Digest de spam ─────────────────────────

def _texto_spam(correos: list[dict]) -> str:
    if not correos:
        return "Tu spam está limpio. No hay nada que botar."
    lineas = [f"• {spam_mod._dominio(c['remitente'])} — {c['asunto'][:50]}" for c in correos]
    return (
        f"Spam de hoy: {len(correos)} correo(s).\n\n" + "\n".join(lineas)
        + "\n\nToca «Borrar todo» o «Conservar» el que sí quieras guardar."
    )


def _teclado_spam(correos: list[dict]) -> InlineKeyboardMarkup:
    filas = [[InlineKeyboardButton("🗑️ Borrar todo", callback_data="spam:borrar")]]
    for i, c in enumerate(correos[:10]):
        filas.append([InlineKeyboardButton(f"✋ Conservar {spam_mod._dominio(c['remitente'])[:22]}", callback_data=f"spam:keep:{i}")])
    return InlineKeyboardMarkup(filas)


async def enviar_digest_spam(bot, chat_id: int) -> None:
    d = await spam_mod.armar_digest_spam()
    if d["n"] == 0:
        await bot.send_message(chat_id, _texto_spam([]))
        return
    await bot.send_message(chat_id, _texto_spam(d["correos"]), reply_markup=_teclado_spam(d["correos"]))


# ───────────────────────── Inferencias ─────────────────────────

async def preguntar_inferencia_pendiente(bot, chat_id: int) -> None:
    """Si hay una inferencia pendiente, la manda con botones para validar (mecanismo estrella)."""
    pendientes = await memory.get_inferencias_pendientes()
    if not pendientes:
        return
    inf = pendientes[0]
    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Sí, me pasa", callback_data=f"inf:confirmada:{inf['id']}"),
            InlineKeyboardButton("No, coincidencia", callback_data=f"inf:descartada:{inf['id']}"),
        ],
        [InlineKeyboardButton("Es por otra razón...", callback_data=f"inf:corregir:{inf['id']}")],
    ])
    await bot.send_message(
        chat_id,
        f"Vengo notando algo y quiero validarlo antes de darlo por cierto:\n\n_{inf['contenido']}_\n\n¿Te pasa, o es coincidencia?",
        reply_markup=teclado,
        parse_mode="Markdown",
    )


# ───────────────────────── Router de callbacks ─────────────────────────

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data

    if data.split(":", 1)[0] in ("hab", "comida", "animo", "mit"):
        # Panel del cierre: cada toque actualiza SOLO el teclado (marca ✅), sin cerrar el panel,
        # para poder anotar varios hábitos. El estado vive por message_id (no se arrastra entre días).
        tipo, val = data.split(":", 1)
        estado = context.user_data.setdefault("cierre_estados", {}).setdefault(q.message.message_id, {})
        try:
            if tipo == "hab":
                estado[val] = True
                await salud.marcar_habito(val)
            elif tipo == "comida":
                estado["comida"] = val
                await salud.marcar_habito("ultima_comida", val)
            elif tipo == "animo":
                estado["animo"] = val
                await salud.registrar_animo(val)
            elif tipo == "mit":
                estado["mit"] = val
        except Exception:
            logger.exception("cierre: no pude anotar %s", data)
        try:
            await q.edit_message_reply_markup(reply_markup=teclado_cierre(estado))
        except Exception:
            pass  # "message is not modified" si se re-toca lo mismo
        return

    if data.startswith("sueno:"):
        valor = "Sí" if data.endswith("si") else "No"
        await salud.registrar_sueno(valor)
        cierre = "Bien ahí." if valor == "Sí" else "Lo veo. Hoy a las 23:00 a la cama, te conozco."
        await q.edit_message_text(f"Sueño anotado. {cierre}")
        return


    if data == "digest:aceptar":
        res = await finanzas.confirmar_digest({})
        cola = f" ({res['duplicadas']} ya estaban, no las dupliqué)" if res.get("duplicadas") else ""
        await q.edit_message_text(f"Listo. Anoté {res['escritas']} movimiento(s) en tu planilla{cola}. Cerrado el día.")
        return

    if data.startswith("digest:fix:"):
        buffer_id = data.split(":", 2)[2]
        context.user_data["corrigiendo_tx"] = buffer_id
        await q.edit_message_text(
            "Dime la categoría correcta para esa línea (o escribe «descartar» para botarla). "
            "Después toca el cierre de nuevo para aceptar el resto."
        )
        return

    if data == "spam:borrar":
        n = await spam_mod.borrar_todo()
        await q.edit_message_text(f"Listo. Mandé {n} correo(s) a la papelera (recuperables 30 días).")
        return

    if data.startswith("spam:keep:"):
        idx = int(data.split(":", 2)[2])
        dom = spam_mod.conservar_idx(idx)
        restantes = spam_mod.pendientes()
        if not restantes:
            await q.edit_message_text(f"Conservo {dom}. No queda nada más que botar.")
            return
        nota = f"Conservo {dom}. " if dom else ""
        await q.edit_message_text(nota + _texto_spam(restantes), reply_markup=_teclado_spam(restantes))
        return

    if data.startswith("inf:"):
        _, accion, inf_id = data.split(":", 2)
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


# ───────────────────────── Corrección de una línea del digest ─────────────────────────

async def aplicar_correccion_tx(buffer_id: str, texto: str) -> str:
    """Nico tipeó la categoría correcta (o 'descartar') para una línea del digest."""
    if texto.strip().lower() in ("descartar", "bórralo", "borralo", "no es mío", "no"):
        await memory.buffer_marcar(buffer_id, "descartada")
        return "Descartada. No la anoto."
    categoria = texto.strip()
    await memory.buffer_actualizar(buffer_id, {"categoria": categoria, "dudosa": False, "motivo_duda": ""})
    # Aprende: este comercio → esta categoría, para reconocerlo solo la próxima vez.
    aprendido = False
    try:
        linea = next((p for p in await memory.buffer_pendientes() if p["id"] == buffer_id), None)
        if linea and linea.get("comercio"):
            await memory.upsert_comercio(linea["comercio"], linea["comercio"], categoria)
            aprendido = True
    except Exception:
        logger.exception("No pude aprender la categoría del comercio")
    cola = " La próxima la reconozco sola." if aprendido else " Cuando toques «Aceptar todo» queda."
    return f"Corregida a «{categoria}».{cola}"
