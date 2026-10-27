"""Tests de la configuración tipada."""

import pytest
from pydantic import ValidationError

from app.config import Settings

ENV_KEYS = (
    "WEATHER_API_BASE_URL",
    "WEATHER_API_TIMEOUT_SECONDS",
    "WEATHER_API_RETRIES",
    "WEATHER_API_RETRY_DELAY_SECONDS",
    "ASSISTANT_CORS_ORIGINS",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "MAX_TOOL_CALLS_PER_TURN",
    "DATABASE_URL",
    "REDIS_URL",
    "RATE_LIMIT",
    "MAX_MESSAGE_CHARS",
    "HISTORY_TURNS",
)


def _settings_without_env_file(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return Settings(_env_file=None)


def test_default_settings(monkeypatch):
    settings = _settings_without_env_file(monkeypatch)

    assert settings.weather_api_base_url == "http://localhost:8000"
    assert settings.weather_api_timeout_seconds == 10.0
    assert settings.weather_api_retries == 1
    assert settings.weather_api_retry_delay_seconds == 0.5
    assert settings.assistant_cors_origins == []
    assert settings.llm_base_url == ""
    assert settings.llm_api_key == ""
    assert settings.llm_model == ""
    assert settings.llm_timeout_seconds == 30.0
    assert settings.max_tool_calls_per_turn == 4
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url == "redis://localhost:6379/1"
    assert settings.rate_limit == "20/minute"
    assert settings.max_message_chars == 500
    assert settings.history_turns == 6


def test_cors_origins_are_split_by_comma(monkeypatch):
    monkeypatch.setenv(
        "ASSISTANT_CORS_ORIGINS",
        "http://localhost:5500, http://127.0.0.1:5500",
    )

    settings = Settings(_env_file=None)

    assert settings.assistant_cors_origins == [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ]


def test_base_url_loses_trailing_slash(monkeypatch):
    monkeypatch.setenv("WEATHER_API_BASE_URL", "http://weather-api:8000/")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1/")

    settings = Settings(_env_file=None)

    assert settings.weather_api_base_url == "http://weather-api:8000"
    assert settings.llm_base_url == "https://api.groq.com/openai/v1"


def test_llm_settings_are_loaded(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("MAX_TOOL_CALLS_PER_TURN", "3")

    settings = Settings(_env_file=None)

    assert settings.llm_api_key == "clave-de-prueba"
    assert settings.llm_model == "openai/gpt-oss-120b"
    assert settings.llm_timeout_seconds == 15.0
    assert settings.max_tool_calls_per_turn == 3


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("WEATHER_API_BASE_URL", "weather-api:8000"),
        ("WEATHER_API_TIMEOUT_SECONDS", "0"),
        ("WEATHER_API_TIMEOUT_SECONDS", "no-es-un-numero"),
        ("WEATHER_API_RETRIES", "4"),
        ("WEATHER_API_RETRY_DELAY_SECONDS", "-1"),
        ("LLM_BASE_URL", "api.groq.com/openai/v1"),
        ("LLM_TIMEOUT_SECONDS", "0"),
        ("MAX_TOOL_CALLS_PER_TURN", "0"),
        ("MAX_TOOL_CALLS_PER_TURN", "11"),
        ("DATABASE_URL", "mysql://localhost/db"),
        ("MAX_MESSAGE_CHARS", "0"),
        ("MAX_MESSAGE_CHARS", "5001"),
        ("HISTORY_TURNS", "-1"),
        ("HISTORY_TURNS", "51"),
        ("RATE_LIMIT", "   "),
    ],
)
def test_invalid_settings_are_rejected(monkeypatch, key, value):
    monkeypatch.setenv(key, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
