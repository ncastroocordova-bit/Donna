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
from core import agenda, brain, correlador, correo, diagnostico, flows, frases, memory, sheets
from modules import aprendizaje, estados_cuenta, finanzas, proactividad, proyectos, recordatorios, salud

logger = logging.getLogger(__name__)

HOJA_CONFIG = "⚙️ Config"


async def _mes_config() -> int | None:
    """Lee 'Mes activo' del ⚙️ Config (int) o None si no está / no se puede leer (C2)."""
    try:
        filas = await sheets.get_dicts(HOJA_CONFIG)
    except Exception:
        logger.exception("_mes_config: no pude leer Config")
        return None
    fila = next((f for f in filas if str(f.get("Parámetro", "")).strip().lower() == "mes activo"), None)
    if fila is None:
        return None
    try:
        return int(float(str(fila.get("Valor", "")).strip()))
    except (ValueError, TypeError):
        return None


# ───────────────────────── Brief 8:00 (read-only) ─────────────────────────

async def _texto_brief() -> str:
    eventos = await agenda.eventos_de_hoy()
    ag = "; ".join(f"{e['hora']} {e['titulo']}" for e in eventos) or "sin eventos"
    aviso_correo = ("AVISO REAL para decirle a Nico: perdí el acceso a tu correo financiero "
                    "(el token venció); no estoy registrando gastos por mail hasta que me re-autorices."
                    if correo.disponible() and correo.gmail_token_invalido() else "")
    señales = " ".join(s for s in [
        aviso_correo,
        await diagnostico.senal_heartbeat(),   # heartbeat: Donna avisa sola si algo se rompió
        await finanzas.senal_finanzas(),
        await finanzas.senal_pendientes_digest(),
        await salud.senal_salud(),
        await salud.senal_mits_brief(),
        await recordatorios.texto_proximos(7),
        await proyectos.senal_proyectos(),
    ] if s)
    prompt = (
        f"Es el brief de las 8:00 de Nico (solo lectura, breve). Agenda de hoy: {ag}. {señales} "
        "Dale su día en pocas líneas con tu voz. Si tienes un patrón o aviso real, dilo. Si no, no rellenes. "
        "No le pidas datos: el sueño se lo pregunto aparte con un botón. "
        "Varía tu apertura, el ángulo y el remate respecto a otros días: no repitas la misma fórmula."
    )
    return await brain.generar(prompt)


async def job_brief(context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = await _texto_brief()
    await context.bot.send_message(settings.nico_telegram_id, texto)
    # Sueño: se pide la HORA directa (chips), no el binario +7h/-7h — el '7h+' se deriva de la
    # ventana dormí→desperté (ver flows sh:*). El texto de la pregunta varía día a día.
    await context.bot.send_message(
        settings.nico_telegram_id, frases.frase("sueno_dormi"), reply_markup=flows.teclado_hora_dormi()
    )
    # C2: el día 1, si el Dashboard sigue mirando el mes pasado, ofrece actualizarlo con un toque.
    ahora = datetime.now(settings.tz)
    if ahora.day == 1:
        try:
            mes_cfg = await _mes_config()
            if mes_cfg is not None and mes_cfg != ahora.month:
                await context.bot.send_message(
                    settings.nico_telegram_id,
                    f"Ojo: el Dashboard sigue en el mes {mes_cfg}. ¿Lo paso a {ahora.month}?",
                    reply_markup=flows.teclado_mes_activo(ahora.month),
                )
        except Exception:
            logger.exception("No pude chequear el Mes activo del Dashboard")
    # C4: recordatorios vencidos → push con botón ✅ Hecho (insisten a diario hasta marcarse).
    try:
        vencidos = await recordatorios.vencidos()
        if vencidos:
            await context.bot.send_message(
                settings.nico_telegram_id, flows.texto_vencidos(vencidos),
                reply_markup=flows.teclado_vencidos(vencidos),
            )
    except Exception:
        logger.exception("No pude enviar los recordatorios vencidos")
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
        "te conozco). Los toques de hábitos, ánimo y MIT salen aparte en un panel. "
        "Varía el arranque y el remate respecto a otros cierres: no repitas la misma fórmula."
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
    await context.bot.send_message(chat, frases.frase("mits_voz"))
    # 2.5) Evento contextual (E8): lo que Nico no controló hoy, para que el correlador no lo
    # confunda con un patrón. Conversacional — no bloquea el panel ni cuenta contra Proactividad.
    await context.bot.send_message(chat, frases.frase("evento_contextual"))
    # 2.6) Peso (E8): se pregunta en cada cierre.
    await context.bot.send_message(chat, frases.frase("peso_cierre"))
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

async def _texto_revision_semanal(r: dict) -> str:
    """Envuelve los datos EXACTOS de la semana en la voz de Donna (sin tocar números). Si el
    LLM falla, degrada a los datos crudos — nunca se queda muda con datos en mano."""
    datos = salud.texto_revision_semanal(r)
    if not datos:
        return ""
    prompt = (
        "Es la revisión dominical de Nico (cierre de semana). Estos son los datos EXACTOS de su "
        f"semana — NO cambies ni inventes ningún número, solo entrégaselos en tu voz, cálida y "
        f"breve:\n\n{datos}\n\nDale una lectura corta de cómo vino la semana. Si el sueño o los "
        "hábitos vinieron flojos, dilo sin regañar. Cierra suave: después le muestro los cruces aparte."
    )
    try:
        return await brain.generar(prompt)
    except Exception:
        logger.exception("revisión semanal: brain falló, mando los datos crudos")
        return "Tu semana:\n\n" + datos


async def job_resumen_semanal(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Domingo 22:30: Salud calcula score + ventanas + peso y los deja en `Semanal` (lectura),
    y ADEMÁS le manda a Nico la revisión de la semana en su voz + los cruces del correlador con
    botones para reeditarlos. Registra el job en `jobs_log` para resiliencia (lo recupera
    `check_pendientes` si Railway estaba caído a las 22:30)."""
    chat = settings.nico_telegram_id
    try:
        r = await salud.generar_resumen_semanal()
        logger.info("Resumen semanal escrito (%s): score=%s", r["semana"], r["score"].get("score"))
    except Exception:
        logger.exception("No pude generar el resumen semanal de Salud")
        return
    try:
        texto = await _texto_revision_semanal(r)
        if texto:
            await context.bot.send_message(chat, texto)
        n = await flows.enviar_cruces_correlador(context.bot, chat)
        logger.info("Revisión semanal enviada a Nico (%d cruce(s) del correlador).", n)
    except Exception:
        logger.exception("No pude enviar la revisión semanal a Nico")
    await memory.marcar_job("resumen_semanal")


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


async def job_estados_cuenta(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Diario: si llegaron estados de cuenta nuevos, actualiza la deuda del faro + historial,
    reconcilia contra la planilla y avisa a Nico. La dedup interna hace que solo actúe cuando hay
    un estado nuevo (≈ mensual), así que correrlo a diario es barato y no repite."""
    if not correo.disponible():
        return
    try:
        await estados_cuenta.procesar_y_reportar(context.bot, settings.nico_telegram_id)
    except Exception:
        logger.exception("job_estados_cuenta falló")


# ───────────────────────── Autodiagnóstico: guardián de schema al boot ─────────────────────────

# Hojas cuyas columnas el código lee/escribe posicionalmente — un mismatch corrompe datos.
HOJAS_CRITICAS = ("Diario", "Tareas", "Proyectos", "Recordatorios", "Reconciliacion", "Semanal",
                  "Transacciones", "Categorias", "Metas", "Compras_Detalle", "Deuda_Mensual")


async def job_verificar_schema(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Al boot: chequea que las hojas críticas tengan las columnas que el código espera. Cada
    mismatch → incidente `schema_sheets` (habría atrapado los bugs de Recordatorios/Proyectos el
    día uno, en vez de descubrirlos corrompiendo datos)."""
    try:
        from setup_sheets import TABS, TABS_LOUIS
        fin_hojas = set(TABS_LOUIS)
        esp_vida = {h: TABS[h] for h in HOJAS_CRITICAS if h in TABS and h not in fin_hojas}
        esp_louis = {h: TABS[h] for h in HOJAS_CRITICAS if h in fin_hojas}
        # Vida contra la planilla Donna (default); finanzas contra Louis. fin_id() cae a la
        # planilla Donna si Louis no existe, así que esto funciona igual en single-workbook.
        problemas = await sheets.verificar_headers(esp_vida)
        problemas += await sheets.verificar_headers(esp_louis, sheet_id=sheets.fin_id())
    except Exception:
        logger.exception("job_verificar_schema falló")
        return
    for p in problemas:
        hoja = p.split(":", 1)[0]
        await diagnostico.registrar(f"sheet:{hoja}", "schema_sheets", p, error_texto=p)
    if problemas:
        logger.warning("Schema: %d hoja(s) con columnas faltantes: %s", len(problemas), problemas)
    else:
        logger.info("Schema OK: las hojas críticas tienen sus columnas.")


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
    # Revisión semanal: solo el domingo (weekday 6, stdlib) tras las 22:30. Sin esto quedaba
    # silenciosamente perdida si Railway se reiniciaba en esa ventana (no la cubría nadie).
    es_domingo_tarde = ahora.weekday() == 6 and (ahora.hour, ahora.minute) >= (22, 30)
    if es_domingo_tarde and not await memory.job_ya_corrio("resumen_semanal"):
        logger.info("Revisión semanal del domingo pendiente tras reinicio; la envío.")
        await job_resumen_semanal(context)
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
        jq.run_daily(job_estados_cuenta, time=time(9, 30, tzinfo=tz))  # deuda mes a mes desde los estados
        logger.info("Correo activo (%s): sync de gastos cada 3h + pregunta-compras cada 5h + digest de spam %d:00 + estados de cuenta 9:30.",
                    ", ".join(correo.proveedores_activos()), settings.spam_hora)
    jq.run_once(check_pendientes, when=10)  # recupera el toque perdido tras un reinicio
    jq.run_once(job_verificar_schema, when=15)  # guardián de schema (autodiagnóstico)
    logger.info(
        "Scheduler listo (%s): brief 8:00, proactividad 12:00, cierre 22:00 (+digest), "
        "resumen semanal domingo 22:30, decay semanal, guardián de schema + resiliencia.",
        settings.timezone,
    )
