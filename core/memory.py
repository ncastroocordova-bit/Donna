"""La memoria de Donna: Supabase (pgvector) + contextual retrieval + política de guardado.

Diseño clave (Plan v7 §7): cada nota se guarda VERBATIM (`texto`) junto a una
etiqueta de CONTEXTO (`contexto`: fecha/dominio/situación). Lo que se embebe es la
versión contextualizada (contexto + texto), así `buscar_memoria` recupera la memoria
*correcta*, no solo la parecida. Embeddings con Voyage AI.

Tablas: perfil, memoria, inferencias, compromisos (núcleo) + buffer_transacciones
(alimenta el digest nocturno) + jobs_log (resiliencia del scheduler).
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


def _hoy() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d")


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
    """Barra de relevancia (Plan v7 §7): descarta lo trivial. Usa el modelo barato.
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


async def inferencia_existe(contenido: str) -> bool:
    """¿Ya registré esta inferencia (en cualquier estado)? Evita re-proponer lo mismo
    cada noche y no insiste con lo que Nico ya descartó (mismo contenido)."""
    if not contenido:
        return False
    db = await _get_db()
    r = await db.table("inferencias").select("id").eq("contenido", contenido).limit(1).execute()
    return bool(r.data)


async def crear_inferencia_si_nueva(contenido: str, dominio: str = "") -> str | None:
    """Idempotente: crea la inferencia solo si su contenido es nuevo. Devuelve el id
    creado, o None si ya existía. La espina la usa para sembrar sin spamear."""
    if await inferencia_existe(contenido):
        return None
    return await crear_inferencia(contenido, dominio)


async def get_inferencias_pendientes() -> list[dict]:
    db = await _get_db()
    r = await db.table("inferencias").select("*").eq("estado", "pendiente").order("created_at").execute()
    return r.data


async def get_inferencias_top(limite: int = 5) -> list[dict]:
    """Para la vista /perfil: las inferencias que importan, confirmadas primero, luego
    las pendientes; descartadas afuera. Cada una trae su contenido (con su dato)."""
    db = await _get_db()
    r = (
        await db.table("inferencias")
        .select("contenido, dominio, estado, created_at")
        .in_("estado", ["confirmada", "pendiente"])
        .order("created_at", desc=True)
        .limit(limite)
        .execute()
    )
    orden = {"confirmada": 0, "pendiente": 1}
    return sorted(r.data, key=lambda x: orden.get(x.get("estado"), 2))


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


# ───────────────────────── Buffer del digest financiero ─────────────────────────
# El digest no escribe a Sheets durante el día: acumula acá y confirma de noche.

async def buffer_existe(id_unico: str) -> bool:
    """¿Ya tengo esta transacción en el buffer? (anti-duplicado por ID_Único)."""
    if not id_unico:
        return False
    db = await _get_db()
    r = await db.table("buffer_transacciones").select("id").eq("id_unico", id_unico).limit(1).execute()
    return bool(r.data)


async def buffer_agregar(tx: dict) -> bool:
    """Agrega una transacción detectada (de correo o foto) al buffer del día.
    Devuelve False si ya estaba (duplicado). `tx` trae fecha/tipo/categoria/comercio/monto/medio/fuente
    + opcional dudosa/motivo_duda/id_unico."""
    id_unico = tx.get("id_unico", "")
    if await buffer_existe(id_unico):
        return False
    db = await _get_db()
    payload = {
        "fecha": tx.get("fecha") or _hoy(),
        "tipo": tx.get("tipo", "Gasto"),
        "categoria": tx.get("categoria", ""),
        "subcategoria": tx.get("subcategoria", ""),
        "comercio": tx.get("comercio", ""),
        "monto": tx.get("monto", 0),
        "medio": tx.get("medio", ""),
        "fuente": tx.get("fuente", ""),
        "id_unico": id_unico or None,
        "dudosa": bool(tx.get("dudosa", False)),
        "motivo_duda": tx.get("motivo_duda", ""),
        "estado": "pendiente",
    }
    await db.table("buffer_transacciones").insert(payload).execute()
    return True


async def buffer_pendientes(fecha: str | None = None) -> list[dict]:
    """Las transacciones del día aún sin confirmar (para armar el digest)."""
    db = await _get_db()
    q = db.table("buffer_transacciones").select("*").eq("estado", "pendiente")
    if fecha:
        q = q.eq("fecha", fecha)
    r = await q.order("created_at").execute()
    return r.data


async def buffer_actualizar(buffer_id: str, campos: dict) -> None:
    db = await _get_db()
    await db.table("buffer_transacciones").update(campos).eq("id", buffer_id).execute()


async def buffer_marcar(buffer_id: str, estado: str) -> None:
    await buffer_actualizar(buffer_id, {"estado": estado})


# ───────────────────────── jobs_log: resiliencia del scheduler ─────────────────────────

async def job_ya_corrio(job: str, fecha: str | None = None) -> bool:
    fecha = fecha or _hoy()
    db = await _get_db()
    r = await db.table("jobs_log").select("job").eq("job", job).eq("fecha", fecha).limit(1).execute()
    return bool(r.data)


async def marcar_job(job: str, fecha: str | None = None) -> None:
    fecha = fecha or _hoy()
    db = await _get_db()
    await db.table("jobs_log").upsert({"job": job, "fecha": fecha}, on_conflict="job,fecha").execute()


# ───────────────────────── Correos ya procesados (anti-reproceso) ─────────────────────────

async def correo_visto(proveedor: str, msg_id: str) -> bool:
    db = await _get_db()
    r = (await db.table("correos_vistos").select("msg_id")
         .eq("proveedor", proveedor).eq("msg_id", msg_id).limit(1).execute())
    return bool(r.data)


async def marcar_correo_visto(proveedor: str, msg_id: str, tipo: str = "gasto") -> None:
    db = await _get_db()
    await db.table("correos_vistos").upsert(
        {"proveedor": proveedor, "msg_id": msg_id, "tipo": tipo}, on_conflict="proveedor,msg_id"
    ).execute()
