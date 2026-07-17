"""El cerebro de Donna: agentic loop con carácter blindado.

Plan v7 §7: la constitución + anclas se sirven como prefijo estable con PROMPT
CACHING (cache_control), re-inyectadas completas en cada llamada pero baratas.
El contexto se arma con presupuesto: prefijo cacheado + datos del día + top-k
memorias relevantes (contextual retrieval, just-in-time). Historial largo → compactación.
"""
import logging
from pathlib import Path

from anthropic import AsyncAnthropic

from config import settings
from core import agenda, diagnostico, memory
from modules import archivista, aprendizaje, compras, estados_cuenta, finanzas, proyectos, recordatorios, salud, spam

logger = logging.getLogger(__name__)
_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
CONSTITUTION = (_PROMPTS / "constitution.md").read_text(encoding="utf-8")
ANCHORS = (_PROMPTS / "anchors.md").read_text(encoding="utf-8")
CAPACIDADES = (_PROMPTS / "capacidades.md").read_text(encoding="utf-8")

MAX_TURNS = 6  # tope de iteraciones del agentic loop (anti bucle de tools)


def _system_blocks(hint: str = "") -> list[dict]:
    """Prefijo cacheado + hint dinámico opcional como segundo bloque de sistema."""
    blocks = [{
        "type": "text",
        "text": CONSTITUTION + "\n\n# ANCLAS\n" + ANCHORS + "\n\n# CAPACIDADES\n" + CAPACIDADES,
        "cache_control": {"type": "ephemeral"},
    }]
    if hint:
        blocks.append({
            "type": "text",
            "text": f"# INSTRUCCION CRITICA PARA ESTA RESPUESTA\n{hint}",
        })
    return blocks


# ───────────────────────── Tools del núcleo ─────────────────────────

async def _t_buscar_memoria(inp: dict) -> str:
    memorias = await memory.buscar_memoria(inp["consulta"])
    if not memorias:
        return "Sin memorias relevantes."
    return "\n".join(f"- [{m.get('contexto', '')}] {m['texto']}" for m in memorias)


async def _t_guardar_memoria(inp: dict) -> str:
    await memory.guardar_memoria(inp["texto"], dominio=inp.get("dominio", "nota"), forzar=True)
    return "Guardado en memoria."


async def _t_actualizar_perfil(inp: dict) -> str:
    await memory.set_perfil(inp["clave"], inp["valor"], inp.get("categoria", ""))
    return f"Perfil actualizado: {inp['clave']} = {inp['valor']}."


async def _t_leer_agenda(inp: dict) -> str:
    eventos = await agenda.eventos_de_hoy()
    if not eventos:
        return "Hoy no hay eventos en la agenda."
    return "\n".join(f"- {e['hora']}: {e['titulo']}" for e in eventos)


async def _t_abrir_inferencia(inp: dict) -> str:
    await memory.crear_inferencia(inp["contenido"], dominio=inp.get("dominio", ""))
    return "Inferencia abierta (pendiente de validar con Nico en el cierre)."


async def _t_registrar_compromiso(inp: dict) -> str:
    await memory.crear_compromiso(inp["descripcion"], inp.get("fecha_limite"))
    return "Compromiso registrado."


async def _t_ver_compromisos(inp: dict) -> str:
    comp = await memory.get_compromisos_abiertos()
    if not comp:
        return "No hay compromisos abiertos."
    return "\n".join(f"- [{c['created_at'][:10]}] {c['descripcion']}" for c in comp)


CORE_TOOLS = [
    {
        "name": "buscar_memoria",
        "description": "Busca en la memoria de largo plazo de Nico por significado. Úsala cuando necesites recordar algo que él contó antes.",
        "input_schema": {"type": "object", "properties": {"consulta": {"type": "string"}}, "required": ["consulta"]},
    },
    {
        "name": "guardar_memoria",
        "description": "Guarda explícitamente un hecho importante sobre Nico en la memoria de largo plazo. Solo para cosas que valga la pena recordar.",
        "input_schema": {
            "type": "object",
            "properties": {"texto": {"type": "string"}, "dominio": {"type": "string"}},
            "required": ["texto"],
        },
    },
    {
        "name": "actualizar_perfil",
        "description": (
            "Guarda un HECHO ESTABLE de Nico en su perfil (clave-valor): cómo prefiere que le hablen, "
            "a qué se dedica, sus metas, situación de plata/deuda, gente clave, hábitos base. "
            "Úsala cuando aprendas algo durable sobre quién es (no un evento puntual — eso es guardar_memoria). "
            "Ejemplos de clave: 'nombre', 'trabajo', 'meta_actual', 'deuda', 'tono_preferido'. Sobrescribe si la clave ya existe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "clave": {"type": "string", "description": "Identificador corto del hecho, ej. 'meta_actual'"},
                "valor": {"type": "string", "description": "El hecho en sí"},
                "categoria": {"type": "string", "description": "Agrupador opcional: plata, trabajo, salud, personal"},
            },
            "required": ["clave", "valor"],
        },
    },
    {
        "name": "leer_agenda",
        "description": "Lee los eventos de hoy del calendario de Nico. Úsala para el brief o cuando pregunta por su día.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "abrir_inferencia",
        "description": "Abre una inferencia sobre Nico (algo que dedujiste pero NO confirmaste). Queda pendiente para validarla con él. Úsala en vez de afirmar algo inferido como si fuera un hecho. Indica el dominio (sueño, plata, salud, ánimo, trabajo, etc.) para que Donna aprenda dónde acierta.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contenido": {"type": "string"},
                "dominio": {"type": "string", "description": "Área de la inferencia: sueño, plata, salud, ánimo, trabajo, relaciones..."},
            },
            "required": ["contenido"],
        },
    },
    {
        "name": "registrar_compromiso",
        "description": "Registra algo que Nico dijo que iba a hacer. Úsala cuando se compromete a una acción ('voy a llamar a...', 'mañana hago...').",
        "input_schema": {
            "type": "object",
            "properties": {"descripcion": {"type": "string"}, "fecha_limite": {"type": "string"}},
            "required": ["descripcion"],
        },
    },
    {
        "name": "ver_compromisos",
        "description": "Lista los compromisos abiertos de Nico. Úsala para recordarle lo pendiente.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

_CORE_HANDLERS = {
    "buscar_memoria": _t_buscar_memoria,
    "guardar_memoria": _t_guardar_memoria,
    "actualizar_perfil": _t_actualizar_perfil,
    "leer_agenda": _t_leer_agenda,
    "abrir_inferencia": _t_abrir_inferencia,
    "registrar_compromiso": _t_registrar_compromiso,
    "ver_compromisos": _t_ver_compromisos,
}

# Herramientas que MUTAN estado externo (Supabase/Sheets/Calendar). En modo eval
# (dry_run) no se ejecutan: se devuelve un stub. La selección de tool igual se
# verifica porque el nombre se registra antes de ejecutar.
WRITE_TOOLS = {
    "guardar_memoria", "actualizar_perfil", "abrir_inferencia", "registrar_compromiso",
    "fin_registrar_gasto", "fin_aportar_meta", "fin_compra_detallada",
    "sal_marcar_habito", "sal_registrar_animo", "sal_registrar_sueno",
    "sal_set_hora", "sal_peso", "sal_evento_contextual",
    "rec_agregar",
    "proy_crear", "proy_actualizar", "proy_cerrar", "tarea_crear", "tarea_completar",
    "arc_guardar",
}

# Tools del núcleo + módulos (con prefijo, sin solapamiento).
ALL_TOOLS = (
    CORE_TOOLS + finanzas.TOOLS + salud.TOOLS + recordatorios.TOOLS
    + proyectos.TOOLS + spam.TOOLS + estados_cuenta.TOOLS + diagnostico.TOOLS + compras.TOOLS
    + archivista.TOOLS
)
_HANDLERS = {
    **_CORE_HANDLERS, **finanzas.HANDLERS, **salud.HANDLERS, **recordatorios.HANDLERS,
    **proyectos.HANDLERS, **spam.HANDLERS, **estados_cuenta.HANDLERS, **diagnostico.HANDLERS,
    **compras.HANDLERS, **archivista.HANDLERS,
}


async def _ejecutar_tool(name: str, inp: dict) -> str:
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"(herramienta desconocida: {name})"
    try:
        return await handler(inp)
    except Exception as e:
        logger.exception("Tool %s falló", name)
        # Autodiagnóstico: registra el incidente (dedup) y responde en carácter, sin stacktrace.
        try:
            inc = await diagnostico.registrar(name, "tool_excepcion",
                                              f"La tool {name} tiró una excepción",
                                              input_json=inp, error_texto=repr(e))
            return diagnostico.texto_para_nico(inc)
        except Exception:
            return f"(la herramienta {name} falló; sigo sin ella)"


# ───────────────────────── Presupuesto de contexto ─────────────────────────

def _hint_tool(mensaje: str) -> str:
    """Detecta el patrón del mensaje y devuelve una hint puntual con la tool obligatoria.
    Aparece en el contexto del usuario → más prominente que la tabla del system prompt."""
    msg = mensaje.lower()
    O = "[OBLIGATORIO ANTES DE RESPONDER] "
    # El freno: cualquier compra en cuotas pasa primero por el costo real de la deuda.
    if any(p in msg for p in ["en cuotas", "cuotas", "playstation", "lo compro en", "pagar en"]):
        return O + "llama fin_estado_deuda ANTES de opinar: es el freno. Muéstrale el costo real de su deuda antes de que se comprometa con cuotas."
    if any(p in msg for p in ["gasté", "gaste", "pagué", "pague", "compré", "compre", "recibí", "recibi", "me pagaron", "me llegó"]):
        return O + "llama fin_registrar_gasto para anotarlo en el buffer del día (se confirma en el cierre). Sin esta llamada no queda."
    if any(p in msg for p in ["cómo voy de plata", "cuánto gasté", "balance", "cuánto llevo gastado", "cómo va mi plata", "saldo"]):
        return O + "llama fin_saldo_mes para el saldo real del mes. No inventes cifras."
    if any(p in msg for p in ["presupuesto", "me estoy pasando", "cuánto llevo en", "cuánto gasté en"]):
        return O + "llama fin_presupuesto para comparar gasto vs presupuesto. No inventes."
    if any(p in msg for p in ["cómo va mi deuda", "progreso de la deuda", "ha bajado la deuda", "cuánto he bajado", "deuda mes a mes"]):
        return O + "llama fin_progreso_deuda para el historial mes a mes real. No inventes."
    if any(p in msg for p in ["tarjeta", "deuda", "cupo", "cuánto debo"]):
        return O + "llama fin_estado_deuda para la deuda/cupo real. No inventes montos."
    if any(p in msg for p in ["fui al gym", "hice ejercicio", "medité", "medite", "ayuné", "ayune", "comí a las", "última comida"]):
        return O + "llama sal_marcar_habito para anotar el hábito del día. Sin esta llamada no queda."
    if any(p in msg for p in ["dormí", "dormi", "me acosté", "me dormí", "horas dormí"]):
        return O + "llama sal_registrar_sueno para anotar el sueño. Sin esta llamada no queda."
    if any(p in msg for p in ["días llevo", "cuántos días", "cuál es mi racha", "llevo meditando", "llevo yendo"]):
        return O + "llama sal_racha para la racha real. No inventes el número."
    if any(p in msg for p in ["recuérdame", "recuerdame", "avísame", "avisame", "no me olvides", "acuérdame"]):
        return O + "llama rec_agregar para crear el recordatorio."
    if any(p in msg for p in ["qué recordatorios", "qué pagos tengo", "qué se viene", "próximos pagos"]):
        return O + "llama rec_proximos para los recordatorios reales. No inventes."
    if any(p in msg for p in ["cómo van mis proyectos", "qué proyectos tengo", "estado de mis proyectos"]):
        return O + "llama proy_listar para el estado real. No inventes."
    if any(p in msg for p in ["nuevo proyecto", "empecé un proyecto", "empece un proyecto", "quiero hacer un proyecto"]):
        return O + "llama proy_crear para registrar el proyecto."
    if any(p in msg for p in ["mis tareas", "qué tareas", "tareas pendientes", "qué me falta"]):
        return O + "llama tarea_listar para las tareas reales. No inventes."
    if any(p in msg for p in ["terminé la tarea", "completé", "complete", "hice la tarea", "marqué", "listo la tarea"]):
        return O + "llama tarea_completar para marcar la tarea hecha."
    if any(p in msg for p in ["mis metas", "meta de ahorro", "cómo voy con las metas", "cómo va mi meta"]):
        return O + "llama fin_metas para las metas financieras reales y su avance. No inventes."
    if any(p in msg for p in ["lista del súper", "lista del super", "qué comprar", "que comprar", "qué tengo que comprar", "que tengo que comprar", "qué hay que comprar"]):
        return O + "llama cmp_lista para la lista real del súper. No inventes."
    if any(p in msg for p in ["falta ", "faltan ", "se acabó", "se acabo", "queda poco", "para el súper", "para el super", "a la lista del súper", "anota para", "anótame"]):
        return O + "llama cmp_agregar para sumar el producto a la lista del súper."
    if any(p in msg for p in ["spam", "correo basura", "junk", "tengo correos basura", "tengo basura en el correo"]):
        return O + "llama spam_resumen para mirar el spam real. No inventes cuántos hay."
    return ""


async def _armar_contexto(mensaje: str) -> str:
    # Degrada elegante (contrato §4): si la memoria/Supabase/Voyage falla, Donna responde
    # IGUAL sin contexto, en vez de caerse en cada mensaje. Cada fuente se aísla.
    try:
        perfil = await memory.get_perfil()
    except Exception:
        logger.exception("_armar_contexto: perfil no disponible; sigo sin él")
        perfil = {}
    try:
        memorias = await memory.buscar_memoria(mensaje)
    except Exception:
        logger.exception("_armar_contexto: memorias no disponibles; sigo sin ellas")
        memorias = []
    try:
        aprendido = await aprendizaje.senal_aprendizaje()
    except Exception:
        logger.exception("_armar_contexto: aprendizaje no disponible; sigo sin él")
        aprendido = ""
    bloques = []
    if perfil:
        bloques.append("Perfil de Nico:\n" + "\n".join(f"- {k}: {v}" for k, v in perfil.items() if not k.startswith("_")))
    if memorias:
        bloques.append("Memorias relevantes:\n" + "\n".join(f"- [{m.get('contexto', '')}] {m['texto']}" for m in memorias))
    if aprendido:
        bloques.append(aprendido)
    if not bloques:
        bloques.append("(Sin contexto cargado — para cualquier dato de Nico usa las herramientas; no inventes cifras ni estados.)")
    return "\n\n".join(bloques)


def _estimar_tokens(history: list[dict]) -> int:
    chars = sum(len(str(m.get("content", ""))) for m in history)
    return chars // 4


async def _compactar_si_necesario(history: list[dict]) -> list[dict]:
    if _estimar_tokens(history) < settings.max_history_tokens:
        return history
    viejo, reciente = history[:-4], history[-4:]
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in viejo if isinstance(m.get("content"), str))
    try:
        r = await _client.messages.create(
            model=settings.model_cheap,
            max_tokens=400,
            system="Resume esta conversación conservando decisiones, correcciones y datos sobre la persona. Descarta lo redundante.",
            messages=[{"role": "user", "content": transcript}],
        )
        resumen = r.content[0].text
    except Exception:
        logger.exception("Compactación falló; trunco el historial.")
        return history[-8:]
    return [{"role": "user", "content": f"[Resumen de lo anterior: {resumen}]"},
            {"role": "assistant", "content": "Lo tengo."}] + reciente


def _texto_de(resp) -> str:
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ───────────────────────── Loop principal ─────────────────────────

def _acumular_uso(uso: dict, resp) -> None:
    """Suma el usage de una respuesta al acumulador (para medir costo)."""
    u = getattr(resp, "usage", None)
    if u is None:
        return
    uso["input_tokens"] += getattr(u, "input_tokens", 0) or 0
    uso["output_tokens"] += getattr(u, "output_tokens", 0) or 0
    uso["cache_creation_input_tokens"] += getattr(u, "cache_creation_input_tokens", 0) or 0
    uso["cache_read_input_tokens"] += getattr(u, "cache_read_input_tokens", 0) or 0


async def responder(
    mensaje: str,
    history: list[dict] | None = None,
    off_record: bool = False,
    model: str | None = None,
    dry_run: bool = False,
    _return_tools: bool = False,
) -> tuple:
    """Responde con voz, memoria y tools. Devuelve (respuesta, historial_actualizado).

    `model` permite forzar un modelo distinto al de config (para evals/comparación).
    `dry_run` (evals): las tools de escritura no se ejecutan — no tocan producción."""
    history = history or []
    modelo = model or settings.model_brain
    contexto = await _armar_contexto(mensaje)
    entrada = f"{contexto}\n\nNico: {mensaje}" if contexto else f"Nico: {mensaje}"

    hint = _hint_tool(mensaje)
    system = _system_blocks(hint)

    working = list(history) + [{"role": "user", "content": entrada}]
    resp = None
    tools_llamadas: list[str] = []
    uso = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    for _ in range(MAX_TURNS):
        resp = await _client.messages.create(
            model=modelo,
            max_tokens=1024,
            system=system,
            tools=ALL_TOOLS,
            messages=working,
        )
        _acumular_uso(uso, resp)
        working.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break
        resultados = []
        for block in resp.content:
            if block.type == "tool_use":
                tools_llamadas.append(block.name)
                if dry_run and block.name in WRITE_TOOLS:
                    salida = f"(modo eval: '{block.name}' no se ejecutó)"
                else:
                    salida = await _ejecutar_tool(block.name, block.input)
                resultados.append({"type": "tool_result", "tool_use_id": block.id, "content": salida})
        working.append({"role": "user", "content": resultados})

    texto = _texto_de(resp) if resp else "Me quedé pensando y se me fue. Repíteme."

    # Historial limpio para la próxima vuelta (sin el contexto inyectado ni los pasos de tools).
    history = history + [{"role": "user", "content": mensaje}, {"role": "assistant", "content": texto}]
    history = await _compactar_si_necesario(history)

    if not off_record:
        try:
            await memory.guardar_memoria(mensaje, dominio="conversacion")
        except Exception:
            logger.exception("No pude guardar el mensaje en memoria.")

    if _return_tools:
        return texto, history, tools_llamadas, uso
    return texto, history


async def generar(prompt_text: str, model: str | None = None) -> str:
    """Genera un mensaje proactivo (brief/cierre/proactividad) sin historial, con contexto fresco."""
    modelo = model or settings.model_brain
    contexto = await _armar_contexto(prompt_text)
    working = [{"role": "user", "content": f"{contexto}\n\n{prompt_text}"}]
    resp = await _client.messages.create(
        model=modelo, max_tokens=1024, system=_system_blocks(), tools=ALL_TOOLS, messages=working,
    )
    for _ in range(MAX_TURNS):
        working.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break
        resultados = [
            {"type": "tool_result", "tool_use_id": b.id, "content": await _ejecutar_tool(b.name, b.input)}
            for b in resp.content if b.type == "tool_use"
        ]
        working.append({"role": "user", "content": resultados})
        resp = await _client.messages.create(
            model=modelo, max_tokens=1024, system=_system_blocks(), tools=ALL_TOOLS, messages=working,
        )
    return _texto_de(resp)
