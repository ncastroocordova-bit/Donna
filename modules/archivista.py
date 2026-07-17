"""Módulo Archivista. Tools `arc_`.

F3-lite del Roadmap-Holding (adelantado 2026-07-16, fuera de orden: solo esta
rebanada, sin migrar el cron ni la síntesis al brief — eso sigue siendo F3
completo, semana 4). Escribe directo en Córtex (el segundo cerebro de Nico)
importando `cortex_core` — la misma librería que usan el MCP y el loop
nocturno, vendorizada en `cortex_core/` (copia, no submódulo; ver
`cortex/README.md` §4 para el patrón).

Política de captura (decisión 2026-07-16, en `cortex/CLAUDE.md`): Nico no
escribe en el vault. Donna captura todo lo que detecte que solo vive en su
cabeza — ante la duda, captura. El jardinero nocturno limpia después.
"""
import logging

logger = logging.getLogger(__name__)

try:
    from cortex_core import config as cortex_config
    from cortex_core import vault as cortex_vault
    DISPONIBLE = True
except Exception:  # paquete no vendorizado o vault no configurado: no debe tumbar a Donna
    logger.exception("cortex_core no disponible; arc_guardar degradará")
    DISPONIBLE = False


async def _t_guardar(inp: dict) -> str:
    if not DISPONIBLE:
        return "Todavía no tengo el cerebro (Córtex) conectado. Se lo cuento a Nico igual, no se pierde."

    titulo = str(inp.get("titulo", "")).strip()
    contenido = str(inp.get("contenido", "")).strip()
    if not titulo or not contenido:
        return "Me faltó título o contenido para guardar la nota."

    area = inp.get("area") or "personal"
    tipo = inp.get("tipo") or "concepto"
    if area not in cortex_config.AREAS_VALIDAS:
        area = "personal"
    if tipo not in cortex_config.TIPOS_VALIDOS:
        tipo = "concepto"
    tags = inp.get("tags") or []

    try:
        nota = cortex_vault.escribir_nota(
            titulo, contenido, carpeta="00-Inbox", tipo=tipo, area=area, tags=tags, autor="donna",
        )
        return f"Guardado en el cerebro: «{nota.titulo}»."
    except Exception:
        logger.exception("arc_guardar falló")
        return "No pude escribirlo en el cerebro ahora, pero lo tengo en la conversación. Reintenta en un rato."


TOOLS = [
    {
        "name": "arc_guardar",
        "description": (
            "Guarda una nota en Córtex, el segundo cerebro de Nico: una decisión y su porqué, "
            "un dato del mundo real (un cliente, un proveedor, un negocio), un juicio que solo "
            "vive en su cabeza — cualquier cosa que valga la pena recordar más allá de esta "
            "conversación y que no sea un hecho estable de perfil (usa actualizar_perfil para eso) "
            "ni un episodio personal (usa guardar_memoria para eso). CAPTURA TODO lo que detectes "
            "que aplique; ante la duda, captura — el jardinero nocturno limpia después. "
            "Ejemplos: 'Nube pidió entregar dos veces por semana, pendiente de decidir', "
            "'Álvaro de ICA sigue sin confirmar el pago', 'decidí posponer el quiz de perfumes'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título corto de la nota"},
                "contenido": {"type": "string", "description": "El contenido en sí, con contexto suficiente para entenderlo después"},
                "area": {
                    "type": "string",
                    "description": "holding | personal | noomi | ncc | universidad | casa | recursos | meta",
                },
                "tipo": {
                    "type": "string",
                    "description": "concepto | proyecto | persona | decision | recurso | diario | reunion | meta",
                },
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["titulo", "contenido"],
        },
    },
]

HANDLERS = {
    "arc_guardar": _t_guardar,
}
