"""Configuración tipada de la aplicación, cargada desde variables de entorno.

Los valores tienen defaults seguros para desarrollo local. El archivo .env es
opcional y nunca se versiona: solo se versiona .env.example con placeholders.
"""

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
    # NoDecode evita que pydantic-settings intente interpretar el string como
    # JSON antes de que corra el validador que separa por comas.
    assistant_cors_origins: Annotated[list[str], NoDecode] = []

    @field_validator("weather_api_base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        """Quita espacios y barras finales para no duplicar separadores."""
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("weather_api_base_url debe empezar con http:// o https://")
        return value

    @field_validator("weather_api_timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        """Un timeout de cero o negativo dejaría llamadas sin límite útil."""
        if value <= 0:
            raise ValueError("weather_api_timeout_seconds debe ser mayor que cero")
        return value

    @field_validator("assistant_cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value):
        """Acepta un string separado por comas, cómodo para el archivo .env."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración una sola vez por proceso.

    Al quedar cacheada, cambiar el .env requiere reiniciar el servicio.
    """
    return Settings()
