"""Tests de la configuración tipada."""

import pytest
from pydantic import ValidationError

from app.config import Settings

ENV_KEYS = (
    "WEATHER_API_BASE_URL",
    "WEATHER_API_TIMEOUT_SECONDS",
    "ASSISTANT_CORS_ORIGINS",
)


def _settings_without_env_file(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return Settings(_env_file=None)


def test_default_settings(monkeypatch):
    settings = _settings_without_env_file(monkeypatch)

    assert settings.weather_api_base_url == "http://localhost:8000"
    assert settings.weather_api_timeout_seconds == 10.0
    assert settings.assistant_cors_origins == []


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

    settings = Settings(_env_file=None)

    assert settings.weather_api_base_url == "http://weather-api:8000"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("WEATHER_API_BASE_URL", "weather-api:8000"),
        ("WEATHER_API_TIMEOUT_SECONDS", "0"),
        ("WEATHER_API_TIMEOUT_SECONDS", "no-es-un-numero"),
    ],
)
def test_invalid_settings_are_rejected(monkeypatch, key, value):
    monkeypatch.setenv(key, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
