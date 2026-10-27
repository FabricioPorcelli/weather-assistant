"""Dobles de prueba para el agente, sin red."""

from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from app.agent.llm import (
    LLMError,
    LLMResponse,
    StreamCompleted,
    TextDelta,
)
from app.clients.weather_api import (
    DEFAULT_FORECAST_DAYS,
    CurrentWeather,
    Forecast,
    History,
    Location,
)
from tests.helpers import (
    DEFAULT_DAY,
    make_current,
    make_day,
    make_forecast,
    make_forecast_range,
    make_history,
)


class FakeLLMClient:
    """Devuelve respuestas guionadas y registra cada llamada."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": deepcopy(messages),
                "tools": deepcopy(tools),
            }
        )
        if not self.responses:
            raise AssertionError("FakeLLMClient se quedó sin respuestas")
        return self.responses.pop(0)

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ):
        self.calls.append(
            {
                "messages": deepcopy(messages),
                "tools": deepcopy(tools),
            }
        )
        if not self.responses:
            raise AssertionError("FakeLLMClient se quedó sin respuestas")
        response = self.responses.pop(0)

        if response.content:
            for start in range(0, len(response.content), 12):
                yield TextDelta(response.content[start : start + 12])

        yield StreamCompleted(response)

    async def aclose(self) -> None:
        """No hay recursos que cerrar."""


class FailingLLMClient:
    """Simula un proveedor del LLM caído."""

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        raise LLMError("proveedor caído")

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ):
        raise LLMError("proveedor caído")
        yield  # pragma: no cover

    async def aclose(self) -> None:
        """No hay recursos que cerrar."""


class FakeWeatherApi:
    """Cliente de clima con datos guardados en memoria."""

    def __init__(
        self,
        *,
        current: CurrentWeather | None = None,
        forecasts: dict[str, Forecast] | None = None,
        histories: list[History] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.current = current or make_current()
        self.forecasts = forecasts or {}
        self.histories = histories or [
            make_history([make_day(day=DEFAULT_DAY - timedelta(days=1))])
        ]
        self.error = error
        self.calls: list[tuple[Any, ...]] = []

    def _key(self, location: Location) -> str:
        return location.city or location.label or "default"

    async def get_current(self, location: Location) -> CurrentWeather:
        self.calls.append(("current", self._key(location)))
        if self.error is not None:
            raise self.error
        return self.current

    async def get_forecast(
        self,
        location: Location,
        days: int = DEFAULT_FORECAST_DAYS,
    ) -> Forecast:
        key = self._key(location)
        self.calls.append(("forecast", key, days))
        if self.error is not None:
            raise self.error
        if key in self.forecasts:
            return self.forecasts[key]
        return make_forecast(
            make_forecast_range(),
            location=location.city or "Ubicación de prueba",
        )

    async def get_history(
        self,
        location: Location,
        start: date,
        end: date,
    ) -> History:
        self.calls.append(("history", self._key(location), start, end))
        if self.error is not None:
            raise self.error
        return self.histories[0]
