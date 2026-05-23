from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # App
    ENV: str = "development"
    DEBUG: bool = True

    # Security
    INTERNAL_SECRET_KEY: str
    INTERNAL_API_KEY: str = "bdh-internal-key-2024"

    # LLM Configuration - Groq
    LLM_PROVIDER: str = "openai"
    OPENAI_BASE_URL: str = "https://api.groq.com/openai/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "llama-3.1-8b-instant"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    MAX_TOKENS_PER_REQUEST: int = 2000

    # Database - PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/ai_services"

    # Redis
    REDIS_URL: Optional[str] = None

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_PER_MINUTE: int = 60

    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


def get_settings() -> "Settings":
    return Settings.model_validate({})


settings = get_settings()
