from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações carregadas de variáveis de ambiente / arquivo .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "IdeaAgenda"
    environment: str = "development"

    # Banco de dados
    database_url: str = "postgresql+asyncpg://ideaagenda:ideaagenda@localhost:5432/ideaagenda"
    database_echo: bool = False

    # Redis (logs, rate limit)
    redis_url: str = "redis://localhost:6379/0"
    log_stream_key: str = "ideaagenda:logs"
    log_max_entries: int = 20000
    log_level: str = "INFO"

    # Segurança
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    # E-mails (separados por vírgula) que são "donos"/administradores do sistema.
    # Se vazio, o primeiro usuário cadastrado vira administrador.
    admin_emails: str = ""
    allow_dev_login: bool = False

    # URLs
    frontend_url: str = "http://localhost:8080"
    cors_origins: str = "http://localhost:4200,http://localhost:8080"

    # Google OAuth / Calendar
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8080/api/auth/google/callback"
    google_calendar_id: str = "primary"
    default_timezone: str = "America/Sao_Paulo"

    # IA
    ai_provider: str = "openai"  # openai | gemini (padrão; o dono pode trocar pelo painel)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    ai_timeout_seconds: float = 60.0
    ai_rate_limit_per_hour: int = 30

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
