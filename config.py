"""Configuración central de Donna. Todo el stack en un solo lugar."""
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Telegram ---
    telegram_token: str
    nico_telegram_id: int

    # --- Claude (Anthropic) ---
    anthropic_api_key: str
    model_brain: str = "claude-sonnet-4-6"     # cerebro: conversación e inferencia
    model_cheap: str = "claude-haiku-4-5"       # ops baratas: relevancia, compactación, evals

    # --- Supabase (memoria) ---
    supabase_url: str
    supabase_key: str                            # service_role (secreta) — con RLS solo esta accede

    # --- Voyage AI (embeddings + contextual retrieval) ---
    voyage_api_key: str
    voyage_model: str = "voyage-3"
    embed_dim: int = 1024                         # debe coincidir con VECTOR(n) en la migración

    # --- Whisper (voz) ---
    openai_api_key: str = ""

    # --- Google (Sheets + Calendar) ---
    google_credentials_json: str = "credentials.json"   # ruta al JSON del service account
    google_sheet_id: str = ""
    google_calendar_id: str = "primary"                  # calendario compartido con el service account

    # --- Operación ---
    timezone: str = "America/Santiago"
    top_k_memorias: int = 5                       # presupuesto de contexto: memorias relevantes
    max_history_tokens: int = 8000                # umbral para compactar el historial

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


settings = Settings()
