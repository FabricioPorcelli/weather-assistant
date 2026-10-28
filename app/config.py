"""Configuración cargada desde variables de entorno."""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Valores de configuración del asistente."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    weather_api_base_url: str = "http://localhost:8000"
    weather_api_timeout_seconds: float = 10.0
    weather_api_retries: int = 1
    weather_api_retry_delay_seconds: float = 0.5

    database_url: str = (
        "postgresql+asyncpg://assistant:assistant@localhost:5432/assistant"
    )
    redis_url: str = "redis://localhost:6379/1"
    rate_limit: str = "20/minute"
    max_message_chars: int = 500
    history_turns: int = 6

    # NoDecode permite separar por comas antes de que Pydantic parsee el valor.
    assistant_cors_origins: Annotated[list[str], NoDecode] = []

    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 30.0
    max_tool_calls_per_turn: int = 4

    @field_validator("weather_api_base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        """Quita espacios y barras finales para no duplicar separadores."""
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("weather_api_base_url debe empezar con http:// o https://")
        return value

    @field_validator("weather_api_timeout_seconds", "llm_timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        """Un timeout de cero o negativo dejaría llamadas sin límite útil."""
        if value <= 0:
            raise ValueError("los timeouts deben ser mayores que cero")
        return value

    @field_validator("max_tool_calls_per_turn")
    @classmethod
    def _validate_max_tool_calls(cls, value: int) -> int:
        """Evita límites absurdos que dejen al agente sin herramientas."""
        if not 1 <= value <= 10:
            raise ValueError("max_tool_calls_per_turn debe estar entre 1 y 10")
        return value

    @field_validator("weather_api_retries")
    @classmethod
    def _validate_retries(cls, value: int) -> int:
        """Limita los reintentos para no multiplicar llamadas sin control."""
        if not 0 <= value <= 3:
            raise ValueError("weather_api_retries debe estar entre 0 y 3")
        return value

    @field_validator("weather_api_retry_delay_seconds")
    @classmethod
    def _validate_retry_delay(cls, value: float) -> float:
        """Permite desactivar la espera en tests, pero no usar valores negativos."""
        if value < 0:
            raise ValueError("weather_api_retry_delay_seconds no puede ser negativo")
        return value

    @field_validator("llm_base_url")
    @classmethod
    def _normalize_llm_base_url(cls, value: str) -> str:
        """Permite dejar el LLM sin configurar, pero valida la URL si existe."""
        value = value.strip().rstrip("/")
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("llm_base_url debe empezar con http:// o https://")
        return value

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        """Acepta PostgreSQL en producción y SQLite solo para tests."""
        if not value.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://")):
            raise ValueError(
                "database_url debe usar postgresql+asyncpg:// o sqlite+aiosqlite://"
            )
        return value

    @field_validator("max_message_chars")
    @classmethod
    def _validate_max_message_chars(cls, value: int) -> int:
        """Limita el tamaño para evitar pedidos desmesurados al LLM."""
        if not 1 <= value <= 5000:
            raise ValueError("max_message_chars debe estar entre 1 y 5000")
        return value

    @field_validator("history_turns")
    @classmethod
    def _validate_history_turns(cls, value: int) -> int:
        """Permite desactivar el historial, pero con un tope razonable."""
        if not 0 <= value <= 50:
            raise ValueError("history_turns debe estar entre 0 y 50")
        return value

    @field_validator("rate_limit")
    @classmethod
    def _validate_rate_limit(cls, value: str) -> str:
        """Evita una configuración vacía que desactive el límite sin querer."""
        if not value.strip():
            raise ValueError("rate_limit no puede estar vacío")
        return value.strip()

    @field_validator("assistant_cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value):
        """Acepta un string separado por comas, cómodo para el archivo .env."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración cacheada por proceso."""
    return Settings()
