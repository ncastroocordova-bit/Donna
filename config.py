"""Configuración central de Donna. Todo el stack en un solo lugar (Plan v7)."""
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
    model_cheap: str = "claude-haiku-4-5"       # ops baratas: relevancia, compactación, vision de boletas

    # --- Supabase (memoria) ---
    supabase_url: str
    supabase_key: str                            # service_role (secreta) — con RLS solo esta accede

    # --- Voyage AI (embeddings + contextual retrieval) ---
    voyage_api_key: str
    voyage_model: str = "voyage-3"
    embed_dim: int = 1024                         # debe coincidir con VECTOR(n) en la migración

    # --- Whisper (voz) ---
    openai_api_key: str = ""

    # --- Correo: Gmail (API OAuth) + Outlook personal (Microsoft Graph OAuth) ---
    # Los tokens se generan una vez con `python auth_email.py` y se pegan acá / en Railway.
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    outlook_client_id: str = ""
    outlook_refresh_token: str = ""
    correo_dias: int = 2            # ventana de antigüedad para correos de gasto
    spam_hora: int = 9             # hora del digest de spam diario
    spam_max: int = 25             # tope de correos de spam a listar por digest

    # --- Estados de cuenta: PDF con clave (Finanzas v4) ---
    # La clave abre el DOCUMENTO (no es la del banco). Nunca al repo/Sheet/chat; solo en .env/Railway.
    banco_pdf_password_bch: str = ""    # clave del PDF de estado de cuenta de Banco de Chile
    banco_pdf_password_mach: str = ""   # clave del PDF de estado de cuenta de Mach

    # --- Google (Sheets + Calendar) ---
    # Canon v7.2: UN solo workbook "Donna" (vida + finanzas en la misma planilla).
    # GOOGLE_SHEET_ID es el id único. Los dos de abajo quedan como legacy: solo se
    # usan si el único está vacío (compatibilidad con la etapa de dos planillas).
    google_credentials_json: str = "credentials.json"   # ruta al JSON del service account
    google_sheet_id: str = ""                            # workbook único "Donna" (canon)
    google_sheet_id_vida: str = ""                       # legacy: planilla Vida_v6
    google_sheet_id_finanzas: str = ""                   # legacy: planilla Finanzas_vigente
    google_calendar_id: str = "primary"                  # calendario compartido con el service account

    # --- Operación ---
    timezone: str = "America/Santiago"
    top_k_memorias: int = 5                       # presupuesto de contexto: memorias relevantes
    max_history_tokens: int = 8000                # umbral para compactar el historial
    meta_hora_dormir: str = "23:00"               # la línea madre del cierre (editable en Config)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def sheet_vida(self) -> str:
        # Workbook único primero; cae al split legacy solo si el único está vacío.
        return self.google_sheet_id or self.google_sheet_id_vida

    @property
    def sheet_finanzas(self) -> str:
        return self.google_sheet_id or self.google_sheet_id_finanzas

    @property
    def gmail_activo(self) -> bool:
        return bool(self.gmail_client_id and self.gmail_client_secret and self.gmail_refresh_token)

    @property
    def outlook_activo(self) -> bool:
        return bool(self.outlook_client_id and self.outlook_refresh_token)


settings = Settings()
