"""La memoria de Donna: Supabase (pgvector) + contextual retrieval + política de guardado.

Diseño clave (Plan v5 §4.2): cada nota se guarda VERBATIM (`texto`) junto a una
etiqueta de CONTEXTO (`contexto`: fecha/dominio/situación). Lo que se embebe es la
versión contextualizada (contexto + texto), así `buscar_memoria` recupera la memoria
*correcta*, no solo la parecida. Embeddings con Voyage AI.

4 tablas: perfil, memoria, inferencias, compromisos.
"""
import asyncio
import logging
from datetime import datetime

import voyageai
from anthropic import AsyncAnthropic
from supabase import AsyncClient, create_async_client

from config import settings

logger = logging.getLogger(__name__)

_voyage = voyageai.Client(api_key=settings.voyage_api_key)  # cliente sync → se usa con to_thread
_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
_db: AsyncClient | None = None


async def _get_db() -> AsyncClient:
    global _db
    if _db is None:
        _db = await create_async_client(settings.supabase_url, settings.supabase_key)
    return _db


async def _embed(texto: str, input_type: str) -> list[float] | None:
    """input_type: 'document' al guardar, 'query' al buscar (mejora la recuperación).
    Devuelve None si el rate limit de Voyage está activo — el llamador degrada graciosamente."""
    def _call():
        r = _voyage.embed([texto], model=settings.voyage_model, input_type=input_type)
        return r.embeddings[0]

    try:
        return await asyncio.to_thread(_call)
    except voyageai.error.RateLimitError:
        logger.warning("Voyage AI rate limit — embed omitido (agrega tarjeta en dashboard.voyageai.com).")
        return None


def _etiqueta_contexto(dominio: str | None, situacion: str | None) -> str:
    fecha = datetime.now(settings.tz).strftime("%Y-%m-%d %A")
    partes = [fecha]
    if dominio:
        partes.append(dominio)
    if situacion:
        partes.append(situacion)
    return " | ".join(partes)


# ───────────────────────── Política de guardado ─────────────────────────

async def es_relevante(texto: str) -> bool:
    """Barra de relevancia (Plan v5 §4.3): descarta lo trivial. Usa el modelo barato.
    Ante cualquier duda o error, devuelve True (mejor guardar de más que perder algo)."""
    try:
        r = await _anthropic.messages.create(
            model=settings.model_cheap,
            max_tokens=5,
            system=(
                "Decides si vale la pena recordar un mensaje en la memoria de largo plazo de un "
                "asistente personal. Vale la pena si dice algo sobre la persona: sus hábitos, "
                "emociones, decisiones, compromisos, gente, plata, salud, planes. NO vale la pena "
                "el chitchat trivial ('hola', 'gracias', 'ok'). Responde solo SI o NO."
            ),
            messages=[{"role": "user", "content": texto}],
        )
        return r.content[0].text.strip().upper().startswith("SI")
    except Exception:
        logger.exception("Falló la barra de relevancia; guardo por las dudas.")
        return True


# ───────────────────────── Memoria episódica ─────────────────────────

async def guardar_memoria(
    texto: str,
    dominio: str | None = None,
    situacion: str | None = None,
    off_record: bool = False,
    forzar: bool = False,
) -> bool:
    """Guarda una nota con contextual retrieval. Devuelve True si se guardó."""
    if off_record:
        return False
    if not forzar and not await es_relevante(texto):
        return False

    contexto = _etiqueta_contexto(dominio, situacion)
    combinado = f"[{contexto}] {texto}"
    try:
        embedding = await _embed(combinado, "document")
    except Exception:
        logger.exception("Falló el embedding; guardo la nota sin vector.")
        embedding = None

    db = await _get_db()
    await db.table("memoria").insert({
        "texto": texto,
        "contexto": contexto,
        "dominio": dominio or "",
        "embedding": embedding,
        "off_record": False,
    }).execute()
    return True


async def buscar_memoria(consulta: str, k: int | None = None) -> list[dict]:
    """Top-k memorias por similitud sobre la versión contextualizada.
    Devuelve [] si el embedding falla (rate limit u otro error)."""
    k = k or settings.top_k_memorias
    embedding = await _embed(consulta, "query")
    if embedding is None:
        return []
    db = await _get_db()
    r = await db.rpc("buscar_memoria", {"query_embedding": embedding, "match_count": k}).execute()
    return r.data


async def olvidar(fragmento: str) -> int:
    db = await _get_db()
    r = await db.table("memoria").select("id").ilike("texto", f"%{fragmento}%").execute()
    ids = [row["id"] for row in r.data]
    if ids:
        await db.table("memoria").delete().in_("id", ids).execute()
    return len(ids)


# ───────────────────────── Perfil (hechos estables) ─────────────────────────

async def get_perfil() -> dict[str, str]:
    db = await _get_db()
    r = await db.table("perfil").select("clave, valor").execute()
    return {row["clave"]: row["valor"] for row in r.data}


async def set_perfil(clave: str, valor: str, categoria: str = "") -> None:
    db = await _get_db()
    await db.table("perfil").upsert(
        {"clave": clave, "valor": valor, "categoria": categoria}, on_conflict="clave"
    ).execute()


# ───────────────────────── Inferencias (validadas) ─────────────────────────

async def crear_inferencia(contenido: str, dominio: str = "") -> str:
    db = await _get_db()
    r = await db.table("inferencias").insert(
        {"contenido": contenido, "dominio": dominio, "estado": "pendiente"}
    ).execute()
    return r.data[0]["id"]


async def get_inferencias_pendientes() -> list[dict]:
    db = await _get_db()
    r = await db.table("inferencias").select("*").eq("estado", "pendiente").order("created_at").execute()
    return r.data


async def get_inferencia(inferencia_id: str) -> dict | None:
    db = await _get_db()
    r = await db.table("inferencias").select("*").eq("id", inferencia_id).limit(1).execute()
    return r.data[0] if r.data else None


async def resolver_inferencia(inferencia_id: str, estado: str, correccion: str = "") -> None:
    db = await _get_db()
    payload: dict = {"estado": estado}
    if correccion:
        payload["correccion"] = correccion
    await db.table("inferencias").update(payload).eq("id", inferencia_id).execute()


# ───────────────────────── Compromisos ─────────────────────────

async def crear_compromiso(descripcion: str, fecha_limite: str | None = None) -> None:
    db = await _get_db()
    payload = {"descripcion": descripcion, "estado": "abierto"}
    if fecha_limite:
        payload["fecha_limite"] = fecha_limite
    await db.table("compromisos").insert(payload).execute()


async def get_compromisos_abiertos() -> list[dict]:
    db = await _get_db()
    r = await db.table("compromisos").select("*").eq("estado", "abierto").order("created_at").execute()
    return r.data


async def cerrar_compromiso(compromiso_id: str, estado: str = "cumplido") -> None:
    db = await _get_db()
    await db.table("compromisos").update({"estado": estado}).eq("id", compromiso_id).execute()
