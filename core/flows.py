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
from core import espera, memory, sheets
from modules import aprendizaje, compras, finanzas, recordatorios, salud
from modules import spam as spam_mod

logger = logging.getLogger(__name__)

# Chips del cierre. Para las horas: (etiqueta, valor); el valor "HH:00" alimenta las ventanas.
# Horas completas (sin minutos, por canon). Rango elegido por Nico: primera 6-12, última 18-01.
# La última cruza medianoche a propósito (00/01 = comió pasada la medianoche, típico de una noche
# de producción): `salud._ventana_minutos` ya suma 24h cuando el fin es menor que el inicio, así
# que "primera 09:00 → última 01:00" da 16h, no un negativo.
CHIPS_PRIMERA_COMIDA = [(str(h), f"{h:02d}:00") for h in range(6, 13)]                        # 6..12
CHIPS_COMIDA = [(f"{h % 24:02d}", f"{h % 24:02d}:00") for h in range(18, 26)]                 # 18..23, 00, 01
CHIPS_POR_FILA = 4
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

    def chips(emoji: str, campo: str, opciones: list[tuple[str, str]], prefijo: str) -> list[list]:
        """Las horas de una comida, repartidas en filas de CHIPS_POR_FILA. El rango completo va
        a la vista (no hay 'otra hora'): siempre 1 toque, nunca un paso extra."""
        botones = [InlineKeyboardButton(mk(f"{emoji} {lbl}", e.get(campo) == val), callback_data=f"{prefijo}:{val}{suf}")
                   for lbl, val in opciones]
        return [botones[i:i + CHIPS_POR_FILA] for i in range(0, len(botones), CHIPS_POR_FILA)]

    filas = [
        [InlineKeyboardButton(mk("🏃 Hice ejercicio", e.get("ejercicio") == "si"), callback_data=f"hab:ejercicio:si{suf}"),
         InlineKeyboardButton(mk("🏃 Hoy no", e.get("ejercicio") == "no"), callback_data=f"hab:ejercicio:no{suf}")],
        [InlineKeyboardButton(mk("🧘 Medité", e.get("meditacion") == "si"), callback_data=f"hab:meditacion:si{suf}"),
         InlineKeyboardButton(mk("🧘 Hoy no", e.get("meditacion") == "no"), callback_data=f"hab:meditacion:no{suf}")],
        *chips("🍳", "primera_comida", CHIPS_PRIMERA_COMIDA, "pcom"),
        *chips("🍽️", "comida", CHIPS_COMIDA, "comida"),
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


# ───────────────────────── Digest financiero — el digest vivo ─────────────────────────
# UN solo mensaje que muta en su lugar (el mismo patrón del panel del cierre): vista principal
# ⇄ corregir una línea (chips de categoría) ⇄ ítems (solo excepciones). Regla de commit único:
# NADA se escribe a la planilla hasta el único «Aceptar todo» — los cambios intermedios viven
# en el buffer. Regla de microcopy: si un texto dice qué tocar, debía ser un botón.

_digest_msg: dict[int, int] = {}   # chat_id → message_id del digest anclado (memoria del proceso)
_revisados: set[str] = set()       # buffers cuyos ítems Nico ya revisó (marca ✓; muere al aceptar)


def _item_dudoso(it: dict) -> bool:
    """¿Este ítem necesita el ojo de Nico? Sin nombre, sin categoría, o precio ilegible. El
    resto ya viene clasificado por el parseo: el flujo corrige EXCEPCIONES, no re-revisa todo
    (de ~32 toques por boleta a 2-4)."""
    nombre = str(it.get("item") or "").strip()
    try:
        precio = float(it.get("precio") or 0)
    except (TypeError, ValueError):
        precio = 0
    return not nombre or nombre == "—" or precio <= 0 or not str(it.get("categoria") or "").strip()


def _teclado_digest(d: dict) -> InlineKeyboardMarkup:
    filas = [[InlineKeyboardButton("✅ Aceptar todo", callback_data="digest:aceptar")]]
    for m in d["movimientos"][:10]:
        etiqueta = ("⚠️ " if m["dudosa"] else "✏️ ") + (m["comercio"] or m["categoria"])[:20]
        fila = [InlineKeyboardButton(etiqueta, callback_data=f"digest:fix:{m['id']}")]
        if m.get("tipo", "Gasto") == "Gasto":
            if m.get("n_items"):  # ya detallado → revisar/corregir ítems
                marca = "✓" if m["id"] in _revisados else str(m["n_items"])
                fila.append(InlineKeyboardButton(f"📋 {marca} ítems", callback_data=f"digest:items:{m['id']}"))
            else:                 # sin detalle → ofrecer detallar (foto o dictado)
                fila.append(InlineKeyboardButton("📝 Detallar", callback_data=f"digest:detallar:{m['id']}"))
        filas.append(fila)
    return InlineKeyboardMarkup(filas)


# ───────────────────────── Ítems: grilla de excepciones (digest vivo) ─────────────────────────
# Reemplaza al mini-panel entrar→editar→volver. El texto muestra TODOS los ítems con su marca
# (✓ claro / ⚠️ por revisar); la grilla de botones trae SOLO los dudosos — cada fila es el ítem
# con toggles que ciclan al toque (deseo, despensa/perecible) y su nombre abre chips de
# categoría. «Ver todos» expande la grilla completa para auditar.

_DESEOS = ["Necesario", "Inversion", "Deseo"]


def _sig_deseo(actual: str) -> str:
    """El deseo que sigue en el ciclo Necesario→Inversion→Deseo→Necesario (toggle de 1 toque)."""
    try:
        return _DESEOS[(_DESEOS.index(str(actual).strip()) + 1) % len(_DESEOS)]
    except ValueError:
        return _DESEOS[0]


def _texto_items(m: dict, items: list[dict]) -> str:
    dudosos = sum(1 for it in items if _item_dudoso(it))
    lineas = []
    for it in items:
        marca = "⚠️" if _item_dudoso(it) else "✓"
        pred = "📦" if it.get("predecible") else "🥖"
        lineas.append(f"{marca} {it.get('item') or '—'} · {finanzas.clp(it.get('precio', 0))} · "
                      f"{it.get('categoria') or '¿?'} · {it.get('intencion') or '¿?'} {pred}")
    cab = (f"«{m.get('comercio') or m.get('categoria', '')}» — {len(items)} ítem(s): "
           f"{len(items) - dudosos} claros, {dudosos} por revisar.")
    return cab + "\n\n" + "\n".join(lineas)


def _teclado_items(mid: str, items: list[dict], ver_todos: bool) -> InlineKeyboardMarkup:
    v = "a" if ver_todos else "e"
    idxs = [i for i, it in enumerate(items) if ver_todos or _item_dudoso(it)][:10]
    filas = []
    for i in idxs:
        it = items[i]
        filas.append([
            InlineKeyboardButton(f"✏️ {(str(it.get('item') or '—'))[:14]}", callback_data=f"dgi:c:{mid}:{i}:{v}"),
            InlineKeyboardButton(f"{(it.get('intencion') or '¿?')[:9]}▸", callback_data=f"dgi:d:{mid}:{i}:{v}"),
            InlineKeyboardButton("📦" if it.get("predecible") else "🥖", callback_data=f"dgi:p:{mid}:{i}:{v}"),
        ])
    if not ver_todos and len(idxs) < len(items):
        filas.append([InlineKeyboardButton(f"👀 Ver los {len(items)}", callback_data=f"dgi:all:{mid}")])
    filas.append([InlineKeyboardButton("✅ Listo", callback_data=f"dgi:ok:{mid}")])
    return InlineKeyboardMarkup(filas)


async def _vista_items(buffer_id: str, ver_todos: bool):
    """(texto, teclado) de la vista de ítems, o None si el buffer ya no tiene detalle."""
    b = await memory.get_buffer(buffer_id)
    items = (b or {}).get("items") or []
    if not items:
        return None
    return _texto_items(b or {}, items), _teclado_items(buffer_id, items, ver_todos)


async def corregir_categoria_item(buffer_id: str, idx: int, categoria: str) -> dict | None:
    """Aplica la categoría dictada a un ítem y devuelve el ítem actualizado (o None)."""
    b = await memory.get_buffer(buffer_id)
    items = (b or {}).get("items") or []
    if not (0 <= idx < len(items)):
        return None
    items[idx]["categoria"] = categoria.strip()
    await memory.buffer_actualizar(buffer_id, {"items": items})
    return items[idx]


def teclado_pregunta_compra(buffer_id: str, foto_primero: bool = False) -> InlineKeyboardMarkup:
    """Botones de la pregunta '¿qué compraste?' (v3): foto, desglosar por texto, o después.

    `foto_primero` (paso 3 del plan de Predecible) es para las compras grandes: la foto pasa a
    ocupar su propia fila arriba y el desglose por texto baja a secundario. En una vuelta al súper
    el texto no sirve —nadie dicta 15 productos— y la despensa que alimenta al predictor está
    justamente ahí."""
    if foto_primero:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📷 Mandar la boleta", callback_data=f"compra:foto:{buffer_id}")],
            [InlineKeyboardButton("✍️ Prefiero escribirlo", callback_data=f"compra:desglosar:{buffer_id}"),
             InlineKeyboardButton("⏭️ Después", callback_data=f"compra:despues:{buffer_id}")],
        ])
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
        detalle = ""
        if m.get("n_items"):
            dudosos = sum(1 for it in (m.get("items") or []) if _item_dudoso(it))
            estado = " ✓" if m["id"] in _revisados else (f" ({dudosos} por revisar)" if dudosos else "")
            detalle = f" · {m['n_items']} ítems{estado}"
        lineas.append(f"• {m['comercio'] or m['categoria']}: {finanzas.clp(m['monto'])} → {m['categoria']}{intencion}{detalle}{marca}")
    cab = f"🧾 {d['n']} movimiento(s) por confirmar · {finanzas.clp(d['total'])}."
    if d["n_dudosas"]:
        cab += f" Los ⚠️ esperan lo tuyo."
    # Sin párrafo de instrucciones: los botones son la instrucción (si un texto dice qué tocar,
    # debía ser un botón).
    return cab + "\n\n" + "\n".join(lineas)


async def _vista_digest():
    d = await finanzas.armar_digest()
    return _texto_digest(d), (_teclado_digest(d) if d["n"] else None)


async def enviar_digest(bot, chat_id: int) -> None:
    """Manda el digest y lo deja ANCLADO: de aquí en adelante todo (corregir, ítems, detallar)
    edita ESTE mensaje en su lugar — un solo digest en el chat, siempre el vigente."""
    texto, teclado = await _vista_digest()
    msg = await bot.send_message(chat_id, texto, reply_markup=teclado)
    if teclado is not None:
        _digest_msg[chat_id] = msg.message_id


async def refrescar_digest(bot, chat_id: int) -> None:
    """Re-dibuja el digest EN SU LUGAR tras una corrección que llegó por texto/voz/foto (las
    esperas de main). Si el ancla ya no existe (deploy de por medio, chat limpiado), manda uno
    nuevo y re-ancla — el camino normal es editar, no apilar copias."""
    mid = _digest_msg.get(chat_id)
    texto, teclado = await _vista_digest()
    if mid:
        try:
            await bot.edit_message_text(texto, chat_id=chat_id, message_id=mid, reply_markup=teclado)
            return
        except Exception as e:
            if "not modified" in str(e).lower():
                return
            logger.info("refrescar_digest: el ancla no se pudo editar; mando un digest nuevo")
    if teclado is None:
        return  # nada pendiente y sin ancla: no hay que mostrar nada
    msg = await bot.send_message(chat_id, texto, reply_markup=teclado)
    _digest_msg[chat_id] = msg.message_id


async def _volver_al_digest(q) -> None:
    texto, teclado = await _vista_digest()
    await _edit_ok(q, texto, reply_markup=teclado)
    _digest_msg[q.message.chat_id] = q.message.message_id


# ───────────────────────── Corrección de una línea: chips, no teclado ─────────────────────────

def _chips_categorias(prefijo: str, cats: list[str], todas: list[str]) -> list[list[InlineKeyboardButton]]:
    """Chips de categoría en filas de 3. El callback lleva el ÍNDICE en el catálogo, no el
    nombre: callback_data tope 64 bytes, y un nombre con tilde junto al uuid no cabe."""
    botones = []
    for c in cats:
        try:
            i = todas.index(c)
        except ValueError:
            continue
        botones.append(InlineKeyboardButton(c[:18], callback_data=f"{prefijo}{i}"))
    return [botones[i:i + 3] for i in range(0, len(botones), 3)]


async def _mov_digest(buffer_id: str) -> dict | None:
    d = await finanzas.armar_digest()
    return next((m for m in d["movimientos"] if str(m["id"]) == str(buffer_id)), None)


async def _vista_correccion_linea(m: dict, todo_el_catalogo: bool):
    """(texto, teclado) del modo corrección de una línea: top-3 aprendido primero; «Más
    categorías» abre el catálogo completo; «Escribirla» queda como último recurso."""
    todas = await finanzas.categorias_lista()
    cats = todas if todo_el_catalogo else await finanzas.sugerencias_categoria(
        m.get("comercio", ""), m.get("categoria", ""))
    filas = _chips_categorias(f"dgc:{m['id']}:", cats, todas)
    if not todo_el_catalogo:
        filas.append([InlineKeyboardButton("📚 Más categorías", callback_data=f"dgc:{m['id']}:mas")])
    else:
        filas.append([InlineKeyboardButton("⌨️ Escribirla", callback_data=f"dgc:{m['id']}:esc")])
    filas.append([InlineKeyboardButton("🗑 Descartar", callback_data=f"dgc:{m['id']}:desc"),
                  InlineKeyboardButton("⬅️ Volver", callback_data="digest:volver")])
    duda = f"\n⚠️ {m['motivo_duda']}" if m.get("dudosa") and m.get("motivo_duda") else ""
    texto = (f"«{m.get('comercio') or m.get('categoria', '')}» · {finanzas.clp(m.get('monto', 0))} "
             f"→ {m.get('categoria', '')}{duda}\n\nElige la categoría:")
    return texto, InlineKeyboardMarkup(filas)


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


# ───────────────────────── Lista del súper (Compras, tocable) ─────────────────────────

def teclado_compras(items: list[str]) -> InlineKeyboardMarkup:
    """Un botón ✅ por producto pendiente — tocarlo lo marca comprado. Salta los nombres tan
    largos que no caben en el tope de 64 bytes de callback_data (igual salen en el texto)."""
    filas = []
    for it in items[:14]:
        cb = f"cmp:ok:{it}"
        if len(cb.encode("utf-8")) <= 64:
            filas.append([InlineKeyboardButton(f"✅ {it[:40]}", callback_data=cb)])
    return InlineKeyboardMarkup(filas)


async def enviar_lista_compras(bot, chat_id: int) -> None:
    pend = await compras.pendientes()
    if not pend:
        await bot.send_message(chat_id, "Tu lista del súper está vacía. Dime «falta X» y la armo.")
        return
    await bot.send_message(chat_id, f"Lista del súper ({len(pend)}) — toca lo que ya compraste:",
                           reply_markup=teclado_compras(pend))


# ───────────────────────── Inferencias ─────────────────────────

def _teclado_inferencia(inf_id: str) -> InlineKeyboardMarkup:
    """Botones del mecanismo estrella: validar (sí/no) o corregir una inferencia/cruce."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Sí, me pasa", callback_data=f"inf:confirmada:{inf_id}"),
            InlineKeyboardButton("No, coincidencia", callback_data=f"inf:descartada:{inf_id}"),
        ],
        [InlineKeyboardButton("Es por otra razón...", callback_data=f"inf:corregir:{inf_id}")],
    ])


async def preguntar_inferencia_pendiente(bot, chat_id: int) -> None:
    """Si hay una inferencia pendiente, la manda con botones para validar (mecanismo estrella)."""
    pendientes = await memory.get_inferencias_pendientes()
    if not pendientes:
        return
    inf = pendientes[0]
    await bot.send_message(
        chat_id,
        f"Vengo notando algo y quiero validarlo antes de darlo por cierto:\n\n_{inf['contenido']}_\n\n¿Te pasa, o es coincidencia?",
        reply_markup=_teclado_inferencia(inf["id"]),
        parse_mode="Markdown",
    )


async def enviar_cruces_correlador(bot, chat_id: int) -> int:
    """Revisión dominical: manda cada cruce del correlador vigente (pendiente o confirmado) con
    los botones de validar/corregir, para que Nico reedite si algo se ve raro — el mecanismo
    estrella, ahora también sobre los ya confirmados (el flujo diario solo mostraba pendientes).
    Devuelve cuántos mandó."""
    cruces = await memory.get_inferencias_correlador()
    for inf in cruces:
        marca = "lo tengo confirmado" if inf.get("estado") == "confirmada" else "aún por validar"
        await bot.send_message(
            chat_id,
            f"Cruce de la semana ({marca}):\n\n_{inf['contenido']}_\n\nSi algo se ve raro, dímelo y lo corrijo.",
            reply_markup=_teclado_inferencia(inf["id"]),
            parse_mode="Markdown",
        )
    return len(cruces)


# ───────────────────────── Router de callbacks ─────────────────────────

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data

    if data.split(":", 1)[0] in ("hab", "comida", "pcom", "animo", "mit"):
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

    if data.startswith("cmp:ok:"):  # Compras: marcar un producto como comprado por toque
        item = data.split(":", 2)[2]
        await compras.marcar_comprado(item)
        pend = await compras.pendientes()
        if pend:
            await _edit_ok(q, f"Lista del súper ({len(pend)}) — toca lo que ya compraste:",
                           reply_markup=teclado_compras(pend))
        else:
            await _edit_ok(q, "Listo, compraste todo. Lista limpia. 🛒")
        return

    if data == "digest:aceptar":
        res = await finanzas.confirmar_digest({})
        cola = f" ({res['duplicadas']} ya estaban, no las dupliqué)" if res.get("duplicadas") else ""
        await q.edit_message_text(f"Listo. Anoté {res['escritas']} movimiento(s) en tu planilla{cola}. Cerrado el día.")
        _digest_msg.pop(q.message.chat_id, None)   # el ancla murió: el digest quedó confirmado
        _revisados.clear()
        return

    if data == "digest:volver":
        await _volver_al_digest(q)
        return

    if data.startswith("digest:fix:"):
        # El digest NO se destruye: este mismo mensaje muta a modo corrección (chips top-3
        # aprendidas) y vuelve a ser el digest al elegir. El teclado quedó como último recurso.
        m = await _mov_digest(data.split(":", 2)[2])
        if m is None:
            await _volver_al_digest(q)
            return
        texto, teclado = await _vista_correccion_linea(m, todo_el_catalogo=False)
        await _edit_ok(q, texto, reply_markup=teclado)
        return

    if data.startswith("dgc:"):  # corrección de línea: chip elegido / más / escribir / descartar
        _, buffer_id, arg = data.split(":", 2)
        if arg == "mas":
            m = await _mov_digest(buffer_id)
            if m is None:
                await _volver_al_digest(q)
                return
            texto, teclado = await _vista_correccion_linea(m, todo_el_catalogo=True)
            await _edit_ok(q, texto, reply_markup=teclado)
            return
        if arg == "esc":
            espera.iniciar(context.user_data, "correccion_tx", {"buffer_id": buffer_id})
            await _edit_ok(q, "Escríbeme la categoría (o «cancelar» y lo dejamos como estaba).")
            return
        if arg == "desc":
            await memory.buffer_marcar(buffer_id, "descartada")
            await q.answer("Descartada. No la anoto.")
            await _volver_al_digest(q)
            return
        todas = await finanzas.categorias_lista()
        try:
            categoria = todas[int(arg)]
        except (ValueError, IndexError):
            await _volver_al_digest(q)
            return
        r = await aplicar_correccion_tx(buffer_id, categoria)
        await q.answer(r[:190])                     # toast corto; el digest vuelve actualizado
        await _volver_al_digest(q)
        return

    if data.startswith("digest:detallar:"):
        buffer_id = data.split(":", 2)[2]
        filas = list(teclado_pregunta_compra(buffer_id).inline_keyboard)
        filas.append([InlineKeyboardButton("⬅️ Volver", callback_data="digest:volver")])
        await _edit_ok(
            q,
            "¿Qué compraste? 📷 foto de la boleta, o ✍️ desglose por texto («arroz 1290, leche 990»).",
            reply_markup=InlineKeyboardMarkup(filas),
        )
        return

    if data.startswith("digest:items:"):  # ítems: grilla de excepciones, en el MISMO mensaje
        buffer_id = data.split(":", 2)[2]
        v = await _vista_items(buffer_id, ver_todos=False)
        if v is None:
            await q.answer("Ese gasto no tiene ítems detallados.")
            return
        await _edit_ok(q, v[0], reply_markup=v[1])
        return

    if data.startswith("dgi:"):  # grilla de ítems: toggles de 1 toque
        partes = data.split(":")
        accion, mid = partes[1], partes[2]
        if accion == "all":
            v = await _vista_items(mid, ver_todos=True)
            if v:
                await _edit_ok(q, v[0], reply_markup=v[1])
            return
        if accion == "ok":
            _revisados.add(mid)
            await _volver_al_digest(q)
            return
        b = await memory.get_buffer(mid)
        items = (b or {}).get("items") or []
        i = int(partes[3])
        ver_todos = len(partes) > 4 and partes[4] == "a"
        if i >= len(items):
            await q.answer("Ese ítem ya no está.")
            return
        if accion == "c":   # el nombre abre chips de categoría para ese ítem
            todas = await finanzas.categorias_lista()
            sugeridas = await finanzas.sugerencias_categoria(items[i].get("item", ""), items[i].get("categoria", ""))
            cats = sugeridas + [c for c in todas if c not in sugeridas]
            filas = _chips_categorias(f"dic:{mid}:{i}:", cats[:9], todas)
            filas.append([InlineKeyboardButton("⌨️ Escribirla", callback_data=f"dic:{mid}:{i}:esc"),
                          InlineKeyboardButton("⬅️ Volver", callback_data=f"digest:items:{mid}")])
            await _edit_ok(q, f"«{items[i].get('item') or '—'}» · {finanzas.clp(items[i].get('precio', 0))}\n\n"
                              "Elige su categoría:", reply_markup=InlineKeyboardMarkup(filas))
            return
        if accion == "d":
            items[i]["intencion"] = _sig_deseo(items[i].get("intencion", ""))
        elif accion == "p":
            items[i]["predecible"] = not items[i].get("predecible")
            # El toque no se queda en este digest: se aprende. Sin esto Nico marcaba "pañales"
            # como reposición cada semana y Donna lo volvía a inferir mal la siguiente — el chip
            # existía desde v3 pero no alimentaba nada (canon de la espina: el aprendizaje se
            # persiste en Supabase). Degrada elegante: si falla, el digest sigue igual.
            try:
                await finanzas.aprender_predecible(items[i].get("item", ""), items[i]["predecible"])
            except Exception:
                logger.exception("digest: no pude aprender el predecible del ítem")
        await memory.buffer_actualizar(mid, {"items": items})
        await _edit_ok(q, _texto_items(b or {}, items), reply_markup=_teclado_items(mid, items, ver_todos))
        return

    if data.startswith("dic:"):  # categoría elegida para un ítem
        _, mid, i_raw, arg = data.split(":", 3)
        i = int(i_raw)
        b = await memory.get_buffer(mid)
        items = (b or {}).get("items") or []
        if i >= len(items):
            await q.answer("Ese ítem ya no está.")
            return
        if arg == "esc":
            context.user_data["items_buffer"] = mid
            context.user_data["item_idx"] = i
            espera.iniciar(context.user_data, "correccion_item_cat")
            await _edit_ok(q, f"Escríbeme la categoría para «{items[i].get('item', '')}» (o «cancelar»).")
            return
        todas = await finanzas.categorias_lista()
        try:
            items[i]["categoria"] = todas[int(arg)]
        except (ValueError, IndexError):
            pass
        await memory.buffer_actualizar(mid, {"items": items})
        await _edit_ok(q, _texto_items(b or {}, items), reply_markup=_teclado_items(mid, items, ver_todos=False))
        return

    if data.startswith("compra:"):
        _, accion, buffer_id = data.split(":", 2)
        if accion == "desglosar":
            espera.iniciar(context.user_data, "desglose_cargo", {"buffer_id": buffer_id})
            await q.edit_message_text(
                "Dale: ¿qué compraste? Dímelo como «arroz 1290, leche 990» o «2000 chanchería, resto pan» "
                "(o «cancelar» si mejor no)."
            )
        elif accion == "foto":
            # La espera ATA la próxima foto a ESTE cargo. Antes solo se pedía la foto y se confiaba
            # en que la correlación monto+fecha+comercio la juntara con el cargo — y esa es la que
            # falla cuando la boleta dice 'ALMACEN SAN VALENTIN' y el banco 'MERCADOPAGO*SANVA'.
            espera.iniciar(context.user_data, "foto_cargo", {"buffer_id": buffer_id})
            await q.edit_message_text("Dale, mándame la foto de la boleta y la pego a este cargo. 📷")
        else:  # despues
            if q.message.message_id == _digest_msg.get(q.message.chat_id):
                await _volver_al_digest(q)   # venía del digest anclado → el digest vuelve, no un texto suelto
            else:
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
            espera.iniciar(context.user_data, "correccion_inferencia", {"inf_id": inf_id})
            await q.edit_message_text("Cuéntame — ¿por qué pasa de verdad? (o «cancelar»)")


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
