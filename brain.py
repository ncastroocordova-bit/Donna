"""El cerebro de Donna: agentic loop con carácter blindado.

Plan v5 §4.1: la constitución + anclas se sirven como prefijo estable con PROMPT
CACHING (cache_control), re-inyectadas completas en cada llamada pero baratas.
El contexto se arma con presupuesto: prefijo cacheado + datos del día + top-k
memorias relevantes (contextual retrieval, just-in-time). Historial largo → compactación.
"""
import logging
from pathlib import Path

from anthropic import AsyncAnthropic

import agenda
import memory
from config import settings
from modules import aprendizaje, finanzas, proyectos, salud

logger = logging.getLogger(__name__)
_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

_PROMPTS = Path(__file__).parent / "prompts"
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
# verifica porque el nombre se registra antes de ejecutar. Así los evals no
# contaminan la base de producción.
WRITE_TOOLS = {
    "guardar_memoria", "actualizar_perfil", "abrir_inferencia", "registrar_compromiso",
    "fin_registrar_gasto", "fin_registrar_ingreso",
    "salud_marcar_habito",
    "proy_crear", "proy_actualizar", "proy_cerrar", "proy_bloquear_tiempo",
}

# Tools del núcleo + módulos (con prefijo, sin solapamiento).
ALL_TOOLS = CORE_TOOLS + finanzas.TOOLS + salud.TOOLS + proyectos.TOOLS
_HANDLERS = {**_CORE_HANDLERS, **finanzas.HANDLERS, **salud.HANDLERS, **proyectos.HANDLERS}


async def _ejecutar_tool(name: str, inp: dict) -> str:
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"(herramienta desconocida: {name})"
    try:
        return await handler(inp)
    except Exception:
        logger.exception("Tool %s falló", name)
        return f"(la herramienta {name} falló; sigo sin ella)"


# ───────────────────────── Presupuesto de contexto ─────────────────────────

def _hint_tool(mensaje: str) -> str:
    """Detecta el patrón del mensaje y devuelve una hint puntual con la tool obligatoria.
    Aparece en el contexto del usuario → más prominente que la tabla del system prompt."""
    msg = mensaje.lower()
    if any(p in msg for p in ["cómo voy de plata", "cuánto gasté", "balance", "cuánto llevo gastado"]):
        return "[OBLIGATORIO ANTES DE RESPONDER] llama fin_get_balance para obtener el balance real del mes."
    if any(p in msg for p in ["qué tengo que pagar", "qué cuentas", "cuánto debo pagar", "pagos próximos", "qué cuentas tengo"]):
        return "[OBLIGATORIO ANTES DE RESPONDER] llama fin_get_pagos_proximos para obtener la lista real de pagos."
    if any(p in msg for p in ["fui al gym", "hice ejercicio", "medité", "meditación", "ayuné", "dormí bien", "hoy fui"]):
        return "[OBLIGATORIO ANTES DE RESPONDER] llama salud_marcar_habito para registrar el hábito. Sin esta llamada el registro no existe."
    if any(p in msg for p in ["días llevo", "cuántos días", "cuál es mi racha", "llevo meditando", "llevo haciendo"]):
        return "[OBLIGATORIO ANTES DE RESPONDER] llama salud_get_racha para obtener la racha real. No inventes el número."
    if any(p in msg for p in ["empecé a trabajar en", "nuevo proyecto", "empecé un proyecto", "quiero hacer un proyecto"]):
        return "[OBLIGATORIO ANTES DE RESPONDER] llama proy_crear para registrar el proyecto. Sin esta llamada no existe en el sistema."
    if any(p in msg for p in ["cómo van mis proyectos", "qué proyectos tengo", "estado de mis proyectos"]):
        return "[OBLIGATORIO ANTES DE RESPONDER] llama proy_listar para obtener el estado real. No inventes proyectos ni porcentajes."
    if any(p in msg for p in ["va al ", "avancé en", "proyecto va al", "actualiza el proyecto"]):
        return "[OBLIGATORIO ANTES DE RESPONDER] llama proy_actualizar para guardar el avance. Sin esta llamada el cambio no se guarda."
    return ""


async def _armar_contexto(mensaje: str) -> str:
    perfil = await memory.get_perfil()
    memorias = await memory.buscar_memoria(mensaje)
    aprendido = await aprendizaje.senal_aprendizaje()
    bloques = []
    if perfil:
        bloques.append("Perfil de Nico:\n" + "\n".join(f"- {k}: {v}" for k, v in perfil.items()))
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
    """Genera un mensaje proactivo (brief/cierre) sin historial, con contexto fresco."""
    modelo = model or settings.model_brain
    contexto = await _armar_contexto(prompt_text)
    resp = await _client.messages.create(
        model=modelo,
        max_tokens=1024,
        system=_system_blocks(),
        tools=ALL_TOOLS,
        messages=[{"role": "user", "content": f"{contexto}\n\n{prompt_text}"}],
    )
    # Una sola pasada con posible tool_use → resolver tools y cerrar.
    working = [{"role": "user", "content": f"{contexto}\n\n{prompt_text}"}]
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
