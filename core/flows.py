"""Flujos de botones de Telegram (Plan v7 §5: toque > texto, panel > conversación).

Tres piezas:
- Panel del cierre 22:00: hábitos + ánimo + "¿avanzaste un MIT?" en un solo mensaje.
- Digest financiero: lista del día pre-categorizada + "✅ Aceptar todo" / tap por línea.
- Validación de inferencias: el mecanismo estrella (botones sí/no/corregir).
"""
import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import settings
from core import memory, sheets
from modules import aprendizaje, finanzas, recordatorios, salud
from modules import spam as spam_mod

logger = logging.getLogger(__name__)

# Chips del cierre. Para las horas: (etiqueta, valor); el valor "HH:00" alimenta las ventanas.
CHIPS_PRIMERA_COMIDA = [("9", "09:00"), ("10", "10:00"), ("11", "11:00"), ("12", "12:00")]   # primera comida
CHIPS_COMIDA = [("18", "18:00"), ("19", "19:00"), ("20", "20:00"), ("21+", "21:00")]          # última comida
CHIPS_AGUA = ["1", "2", "3"]           # litros de agua
CHIPS_PROTEINA = ["80", "90", "100"]   # gramos de proteína
CHIPS_HORA_DORMI = ["22:30", "23:00", "00:00", "01:00", "02:00"]
CHIPS_HORA_DESPERTAR = ["06:30", "07:00", "07:30", "08:00", "09:00"]
HOJA_CONFIG = "⚙️ Config"


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


async def _edit_ok(q, texto, reply_markup=None) -> None:
    """edit_message_text que traga el 'message is not modified' de Telegram (que salta al
    re-tocar el mismo valor). Sin esto, el editor de ítems se trababa al re-seleccionar el
    mismo deseo/categoría: la excepción no capturada dejaba el toque sin efecto."""
    try:
        await q.edit_message_text(texto, reply_markup=reply_markup)
    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.exception("edit_message_text falló")


# ───────────────────────── Panel del cierre ─────────────────────────

def teclado_cierre(estado: dict | None = None, mits: list[str] | None = None, fecha: str = "") -> InlineKeyboardMarkup:
    """Panel del cierre. `estado` marca con ✅ lo ya elegido (se reconstruye en cada toque,
    sin cerrar el panel) — así Nico puede anotar varios hábitos, no solo uno. `mits` son TODOS
    los MITs pendientes (de hoy + acumulados de antes, sin tope) — cada uno es su propio toque
    marcable. Lo que no se marca hoy sigue apareciendo mañana (no desaparece solo).

    `fecha` (la del ENVÍO del panel) se ancla en cada callback_data con sufijo `|YYYY-MM-DD`:
    si Nico responde el panel pasada la medianoche, el toque igual cae en la fila del día
    correcto y no en la del día siguiente (fix C6). Sin fecha → los toques usan el día del tap."""
    e = estado or {}
    suf = f"|{fecha}" if fecha else ""

    def mk(label: str, on: bool) -> str:
        return ("✅ " + label) if on else label

    filas = [
        [InlineKeyboardButton(mk("🏃 Hice ejercicio", e.get("ejercicio") == "si"), callback_data=f"hab:ejercicio:si{suf}"),
         InlineKeyboardButton(mk("🏃 Hoy no", e.get("ejercicio") == "no"), callback_data=f"hab:ejercicio:no{suf}")],
        [InlineKeyboardButton(mk("🧘 Medité", e.get("meditacion") == "si"), callback_data=f"hab:meditacion:si{suf}"),
         InlineKeyboardButton(mk("🧘 Hoy no", e.get("meditacion") == "no"), callback_data=f"hab:meditacion:no{suf}")],
        # 💧 agua por litros (1/2/3 L) y 🥩 proteína por gramos (80/90/100 g) — cuánto, no sí/no.
        [InlineKeyboardButton(mk(f"💧 {litros}L", e.get("agua") == litros), callback_data=f"agua:{litros}{suf}") for litros in CHIPS_AGUA],
        [InlineKeyboardButton(mk(f"🥩 {gr}g", e.get("proteina") == gr), callback_data=f"prot:{gr}{suf}") for gr in CHIPS_PROTEINA],
        # 🍳 primera comida (9–12) y 🍽️ última comida (18–21+), cada una en UNA fila horizontal.
        [InlineKeyboardButton(mk(f"🍳 {lbl}", e.get("primera_comida") == val), callback_data=f"pcom:{val}{suf}") for lbl, val in CHIPS_PRIMERA_COMIDA],
        [InlineKeyboardButton(mk(f"🍽️ {lbl}", e.get("comida") == val), callback_data=f"comida:{val}{suf}") for lbl, val in CHIPS_COMIDA],
        [InlineKeyboardButton(mk(f"Ánimo {n}", e.get("animo") == n), callback_data=f"animo:{n}{suf}") for n in ("1", "2", "3", "4")],
    ]
    for i, texto in enumerate(mits or []):
        etiqueta = (texto[:32] + "…") if len(texto) > 32 else texto
        marca = "✅ " if e.get(f"mit_{i}") == "si" else "☐ "
        filas.append([InlineKeyboardButton(marca + etiqueta, callback_data=f"mit:{i}{suf}")])
    return InlineKeyboardMarkup(filas)


def teclado_brief_sueno() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("😴 Dormí 7h+", callback_data="sueno:si"),
        InlineKeyboardButton("Menos de 7h", callback_data="sueno:no"),
    ]])


def teclado_hora_dormi() -> InlineKeyboardMarkup:
    """Chips de hora dormí (C3), encadenados tras el botón de sueño en el brief."""
    return InlineKeyboardMarkup([[InlineKeyboardButton(h, callback_data=f"sh:d:{h}") for h in CHIPS_HORA_DORMI]])


def teclado_hora_despertar() -> InlineKeyboardMarkup:
    """Chips de hora desperté (C3), encadenados tras elegir la hora dormí."""
    return InlineKeyboardMarkup([[InlineKeyboardButton(h, callback_data=f"sh:w:{h}") for h in CHIPS_HORA_DESPERTAR]])


def teclado_mes_activo(mes: int) -> InlineKeyboardMarkup:
    """Toque del día 1 para actualizar el Mes activo del Dashboard (C2)."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Sí, actualiza", callback_data=f"cfg:mes:{mes}"),
        InlineKeyboardButton("Después", callback_data="cfg:no"),
    ]])


def teclado_vencidos(vencidos: list[dict]) -> InlineKeyboardMarkup:
    """Un botón ✅ Hecho por recordatorio vencido (C4). Salta los nombres tan largos que no
    caben en el tope de 64 bytes de callback_data de Telegram (igual salen en el texto)."""
    filas = []
    for v in vencidos[:8]:
        nombre = v.get("nombre", "")
        cb = f"rec:hecho:{nombre}"
        if len(cb.encode("utf-8")) <= 64:
            filas.append([InlineKeyboardButton(f"✅ Hecho: {nombre[:30]}", callback_data=cb)])
    return InlineKeyboardMarkup(filas)


def texto_vencidos(vencidos: list[dict]) -> str:
    lineas = []
    for v in vencidos:
        n = abs(v.get("falta", 0))
        lineas.append(f"• {v.get('nombre', '')} — venció hace {n} día{'s' if n != 1 else ''}")
    return "Tienes recordatorios vencidos. Márcalos cuando los hagas:\n\n" + "\n".join(lineas)


async def enviar_panel_cierre(bot, chat_id: int, intro: str) -> None:
    # Fetch directo (sin user_data): este envío puede venir de un job del scheduler, que no
    # tiene un user_id asociado y por lo tanto no tiene context.user_data (ver on_callback,
    # que sí puede cachear ahí porque corre siempre en respuesta a un toque real de Nico).
    # La fecha del envío se ancla en los callbacks (C6): un toque post-medianoche cae en el día
    # correcto, no en el siguiente.
    mits = await salud.mits_pendientes()
    await bot.send_message(chat_id, intro, reply_markup=teclado_cierre(mits=mits, fecha=_hoy()))


# ───────────────────────── Digest financiero ─────────────────────────

def _teclado_digest(d: dict) -> InlineKeyboardMarkup:
    filas = [[InlineKeyboardButton("✅ Aceptar todo", callback_data="digest:aceptar")]]
    for m in d["movimientos"][:10]:
        etiqueta = ("⚠️ " if m["dudosa"] else "✏️ ") + (m["comercio"] or m["categoria"])[:20]
        fila = [InlineKeyboardButton(etiqueta, callback_data=f"digest:fix:{m['id']}")]
        if m.get("tipo", "Gasto") == "Gasto":
            if m.get("n_items"):  # ya detallado → revisar/corregir ítems
                fila.append(InlineKeyboardButton(f"📋 {m['n_items']} ítems", callback_data=f"digest:items:{m['id']}"))
            else:                 # sin detalle → ofrecer detallar (foto o dictado)
                fila.append(InlineKeyboardButton("📝 Detallar", callback_data=f"digest:detallar:{m['id']}"))
        filas.append(fila)
    return InlineKeyboardMarkup(filas)


# ───────────────────────── Editor de ítems (v3, mini-panel) ─────────────────────────

_DESEOS = ["Necesario", "Inversion", "Deseo"]


def _texto_panel_items(comercio: str, items: list[dict]) -> str:
    lineas = []
    for i, it in enumerate(items, 1):
        pred = "📦 despensa" if it.get("predecible") else "🥖 perecible"
        lineas.append(f"{i}) {it.get('item', '') or '—'} · {finanzas.clp(it.get('precio', 0))} · "
                      f"{it.get('categoria', '')} · {it.get('intencion', '')} · {pred}")
    return (f"Detalle de {comercio or 'la compra'} — {len(items)} ítem(s). "
            f"Toca uno para corregir su deseo, categoría o si es de despensa:\n\n" + "\n".join(lineas))


def _teclado_panel_items(items: list[dict]) -> InlineKeyboardMarkup:
    filas = [[InlineKeyboardButton(f"✏️ {i + 1}. {(it.get('item') or '—')[:24]}", callback_data=f"it:p:{i}")]
             for i, it in enumerate(items[:12])]
    filas.append([InlineKeyboardButton("✅ Listo", callback_data="it:ok")])
    return InlineKeyboardMarkup(filas)


def _teclado_item_editor(it: dict) -> InlineKeyboardMarkup:
    d, p = it.get("intencion", ""), it.get("predecible")

    def mk(label, on):
        return ("✅ " + label) if on else label

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(mk(x, d == x), callback_data=f"it:d:{x}") for x in _DESEOS],
        [InlineKeyboardButton(mk("📦 Despensa", p is True), callback_data="it:pr:1"),
         InlineKeyboardButton(mk("🥖 Perecible", p is False), callback_data="it:pr:0")],
        [InlineKeyboardButton("🏷️ Categoría", callback_data="it:cat"),
         InlineKeyboardButton("⬅️ Volver", callback_data="it:back")],
    ])


def _texto_item(it: dict) -> str:
    return (f"«{it.get('item', '') or '—'}» · {finanzas.clp(it.get('precio', 0))}\n"
            f"Categoría: {it.get('categoria', '')} · Deseo: {it.get('intencion', '')} · "
            f"{'despensa' if it.get('predecible') else 'perecible'}")


async def enviar_panel_items(bot, chat_id: int, buffer_id: str) -> bool:
    """Muestra el detalle ítem-a-ítem de un cargo para revisar/corregir. Devuelve si lo abrió."""
    b = await memory.get_buffer(buffer_id)
    items = (b or {}).get("items") or []
    if not items:
        return False
    await bot.send_message(chat_id, _texto_panel_items((b or {}).get("comercio", ""), items),
                           reply_markup=_teclado_panel_items(items))
    return True


async def corregir_categoria_item(buffer_id: str, idx: int, categoria: str) -> dict | None:
    """Aplica la categoría dictada a un ítem y devuelve el ítem actualizado (o None)."""
    b = await memory.get_buffer(buffer_id)
    items = (b or {}).get("items") or []
    if not (0 <= idx < len(items)):
        return None
    items[idx]["categoria"] = categoria.strip()
    await memory.buffer_actualizar(buffer_id, {"items": items})
    return items[idx]


def teclado_pregunta_compra(buffer_id: str) -> InlineKeyboardMarkup:
    """Botones de la pregunta '¿qué compraste?' (v3): foto, desglosar por texto, o después."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📷 Mandar foto", callback_data=f"compra:foto:{buffer_id}"),
         InlineKeyboardButton("✍️ Desglosar", callback_data=f"compra:desglosar:{buffer_id}")],
        [InlineKeyboardButton("⏭️ Después", callback_data=f"compra:despues:{buffer_id}")],
    ])


def _texto_digest(d: dict) -> str:
    if d["n"] == 0:
        return "Hoy no detecté movimientos. Tu plata quedó quieta."
    lineas = []
    for m in d["movimientos"]:
        marca = f"  ⚠️ {m['motivo_duda']}" if m["dudosa"] else ""
        intencion = f" · {m['intencion']}" if m.get("intencion") else ""
        detalle = f" · {m['n_items']} ítems" if m.get("n_items") else ""
        lineas.append(f"• {m['comercio'] or m['categoria']}: {finanzas.clp(m['monto'])} → {m['categoria']}{intencion}{detalle}{marca}")
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
        + "\n\nToca «Archivar todo» o «Conservar» el que sí quieras guardar."
    )


def _teclado_spam(correos: list[dict]) -> InlineKeyboardMarkup:
    filas = [[InlineKeyboardButton("🗄️ Archivar todo", callback_data="spam:archivar")]]
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

    if data.split(":", 1)[0] in ("hab", "comida", "pcom", "agua", "prot", "animo", "mit"):
        # Panel del cierre: cada toque actualiza SOLO el teclado (marca ✅), sin cerrar el panel,
        # para poder anotar varios hábitos. El estado vive por message_id (no se arrastra entre días).
        # La fecha va anclada al final del callback (|YYYY-MM-DD, fix C6): así el toque cae en la
        # fila del día del ENVÍO del panel aunque Nico responda pasada la medianoche.
        base, _, fecha = data.partition("|")
        fecha = fecha or None
        partes = base.split(":")
        tipo = partes[0]
        estado = context.user_data.setdefault("cierre_estados", {}).setdefault(q.message.message_id, {})
        try:
            if tipo == "hab":  # hab:ejercicio:si | hab:meditacion:no → anota "Sí"/"No" explícito
                campo, signo = partes[1], partes[2]
                estado[campo] = signo
                await salud.marcar_habito(campo, "Sí" if signo == "si" else "No", fecha=fecha)
            elif tipo == "comida":
                hora = base.split(":", 1)[1]  # "20:00" lleva ':' → tomo todo lo que sigue al primer ':'
                estado["comida"] = hora
                await salud.marcar_habito("ultima_comida", hora, fecha=fecha)
            elif tipo == "pcom":  # primera comida (ventanas E8, C3)
                hora = base.split(":", 1)[1]
                estado["primera_comida"] = hora
                await salud.registrar_hora("primera_comida", hora, fecha=fecha)
            elif tipo == "agua":  # litros de agua (1/2/3)
                estado["agua"] = partes[1]
                await salud.marcar_habito("agua", partes[1], fecha=fecha)
            elif tipo == "prot":  # gramos de proteína (80/90/100)
                estado["proteina"] = partes[1]
                await salud.marcar_habito("proteina", partes[1], fecha=fecha)
            elif tipo == "animo":
                estado["animo"] = partes[1]
                await salud.registrar_animo(partes[1], fecha=fecha)
            # Los MITs se cachean por message_id (igual que cierre_estados) la primera vez que
            # se necesitan: on_callback siempre corre en respuesta a un toque real de Nico, así
            # que a diferencia del job del scheduler, acá context.user_data sí existe — pero un
            # cache plano (sin message_id) mostraría los de otro panel si se toca uno distinto
            # en la misma sesión. La lista es TODOS los pendientes (hoy + acumulados).
            mits_cache = context.user_data.setdefault("cierre_mits_cache", {})
            if q.message.message_id not in mits_cache:
                mits_cache[q.message.message_id] = await salud.mits_pendientes()
            mits = mits_cache[q.message.message_id]
            if tipo == "mit":  # mit:<idx> → toggle (tocar de nuevo lo desmarca)
                campo = f"mit_{partes[1]}"
                idx_mit = int(partes[1])
                hecho = estado.get(campo) != "si"
                estado[campo] = "si" if hecho else "no"
                if 0 <= idx_mit < len(mits):
                    await salud.marcar_mit(mits[idx_mit], hecho)
        except Exception:
            logger.exception("cierre: no pude anotar %s", data)
        try:
            mits = context.user_data.get("cierre_mits_cache", {}).get(q.message.message_id, [])
            await q.edit_message_reply_markup(reply_markup=teclado_cierre(estado, mits, fecha=fecha or ""))
        except Exception:
            pass  # "message is not modified" si se re-toca lo mismo
        return

    if data.startswith("sueno:"):
        valor = "Sí" if data.endswith("si") else "No"
        await salud.registrar_sueno(valor)
        cierre = "Bien ahí." if valor == "Sí" else "Lo veo. Hoy a las 23:00 a la cama, te conozco."
        await q.edit_message_text(f"Sueño anotado. {cierre}")
        # C3: encadena la hora exacta (chips) para llenar la ventana de sueño (el eje #1).
        await context.bot.send_message(q.message.chat_id, "¿A qué hora te dormiste?",
                                       reply_markup=teclado_hora_dormi())
        return

    if data.startswith("sh:"):  # sueño por chips de hora (d = dormí, w = desperté)
        partes = data.split(":", 2)  # ["sh", "d"|"w", "HH:MM"]
        cual, hora = partes[1], partes[2]
        if cual == "d":
            await salud.registrar_hora_dormi(hora)
            await q.edit_message_text(f"Te dormiste {hora}, anotado.")
            await context.bot.send_message(q.message.chat_id, "¿Y a qué hora despertaste?",
                                           reply_markup=teclado_hora_despertar())
        else:  # w = desperté → deriva el '7h+' de la ventana (sin preguntar el binario inútil)
            await salud.registrar_hora("hora_despertar", hora)
            val = await salud.derivar_sueno_de_ventana()
            if val == "Sí":
                cola = "Dormiste tus 7+, bien ahí."
            elif val == "No":
                cola = "Menos de 7. Hoy a la cama a las 23:00, te conozco."
            else:
                cola = ""
            await q.edit_message_text(f"Despertaste {hora}. Ventana de sueño anotada. {cola}".strip())
        return

    if data.startswith("cfg:"):  # C2: actualizar el Mes activo del Dashboard (toque del día 1)
        partes = data.split(":")
        if partes[1] == "mes":
            mes = partes[2]
            try:
                await sheets.upsert_por_clave(HOJA_CONFIG, "Parámetro", "Mes activo", "Valor", int(mes))
                await q.edit_message_text(f"Dashboard apuntando al mes {mes}. Ya lo resolví.")
            except Exception:
                logger.exception("cfg:mes falló")
                await q.edit_message_text("No pude actualizar el Mes activo ahora. Reintenta luego.")
        else:  # cfg:no
            await q.edit_message_text("Ok, lo dejamos. Avísame cuando quieras.")
        return

    if data.startswith("rec:hecho:"):  # C4: marcar un recordatorio vencido como hecho
        nombre = data.split(":", 2)[2]
        await recordatorios.marcar_hecho(nombre)
        await q.edit_message_text(f"Listo, marqué «{nombre}» como hecho. Ya no te insisto.")
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

    if data.startswith("digest:detallar:"):
        buffer_id = data.split(":", 2)[2]
        await q.edit_message_text(
            "¿Qué compraste en esta compra? Mándame la 📷 foto de la boleta o ✍️ desglósalo por texto "
            "(«arroz 1290, leche 990»). Le pongo categoría y deseo a cada ítem.",
            reply_markup=teclado_pregunta_compra(buffer_id),
        )
        return

    if data.startswith("digest:items:"):  # revisar el detalle de un gasto ya detallado
        buffer_id = data.split(":", 2)[2]
        context.user_data["items_buffer"] = buffer_id
        if not await enviar_panel_items(context.bot, q.message.chat_id, buffer_id):
            await q.answer("Ese gasto no tiene ítems detallados.")
        return

    if data.startswith("it:"):  # editor de ítems (mini-panel v3)
        buffer_id = context.user_data.get("items_buffer")
        b = await memory.get_buffer(buffer_id) if buffer_id else None
        items = (b or {}).get("items") or []
        if not items:
            await q.answer("Esa lista ya no está activa.")
            return
        partes = data.split(":")
        accion = partes[1]
        if accion == "ok":
            context.user_data.pop("items_buffer", None)
            context.user_data.pop("item_idx", None)
            await _edit_ok(q, f"Listo, {len(items)} ítem(s) guardados. Quedan en el digest para aceptar.")
            return
        if accion == "back":
            await _edit_ok(q, _texto_panel_items(b.get("comercio", ""), items), reply_markup=_teclado_panel_items(items))
            return
        if accion == "p":  # elegir ítem → abre su editor
            idx = int(partes[2])
            context.user_data["item_idx"] = idx
            await _edit_ok(q, _texto_item(items[idx]), reply_markup=_teclado_item_editor(items[idx]))
            return
        idx = context.user_data.get("item_idx")
        if idx is None or idx >= len(items):
            await q.answer("Elegí el ítem de nuevo.")
            return
        if accion == "cat":
            context.user_data["corrigiendo_item_cat"] = True
            await _edit_ok(q, f"¿Qué categoría para «{items[idx].get('item', '')}»? Escríbela.")
            return
        if accion == "d":
            items[idx]["intencion"] = partes[2]
        elif accion == "pr":
            items[idx]["predecible"] = (partes[2] == "1")
        await memory.buffer_actualizar(buffer_id, {"items": items})
        await _edit_ok(q, _texto_item(items[idx]), reply_markup=_teclado_item_editor(items[idx]))
        return

    if data.startswith("compra:"):
        _, accion, buffer_id = data.split(":", 2)
        if accion == "desglosar":
            context.user_data["desglosando_cargo"] = buffer_id
            await q.edit_message_text(
                "Dale: ¿qué compraste? Dímelo como «arroz 1290, leche 990» o «2000 chanchería, resto pan»."
            )
        elif accion == "foto":
            await q.edit_message_text("Mándame la foto de la boleta y la cruzo con este cargo. 📷")
        else:  # despues
            await q.edit_message_text("Ok, lo dejamos para el cierre.")
        return

    if data == "spam:archivar":
        n = await spam_mod.archivar_todo()
        await q.edit_message_text(
            f"Listo. Archivé {n} correo(s) — quedan con la etiqueta Donna/Archivado, recuperables cuando quieras."
        )
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
    # Al corregir la categoría, la intención se re-deriva de ella (la guardada quedó obsoleta).
    await memory.buffer_actualizar(buffer_id, {
        "categoria": categoria, "intencion": finanzas._intencion_de(categoria),
        "dudosa": False, "motivo_duda": "",
    })
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
