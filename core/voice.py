"""Transcripción de notas de voz con Whisper (voz_a_texto). Lo usa el cierre 22:00
para capturar los MITs de mañana sin teclado."""
import logging

from config import settings

logger = logging.getLogger(__name__)
_client = None


def _svc():
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY no configurada; voz no disponible.")
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def transcribir(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        r = await _svc().audio.transcriptions.create(model="whisper-1", file=f, language="es")
    return r.text


# Alias con el nombre del runbook v7 (Paso 1.7).
voz_a_texto = transcribir
