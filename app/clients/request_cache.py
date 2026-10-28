"""Caché en memoria durante un solo request."""

from datetime import date

from app.clients.weather_api import (
    DEFAULT_FORECAST_DAYS,
    CurrentWeather,
    Forecast,
    History,
    Location,
    WeatherApi,
)

ForecastKey = tuple[str, int]
HistoryKey = tuple[str, date, date]


class RequestWeatherClient:
    """Cliente con memoria temporal para un único pedido."""

    def __init__(self, client: WeatherApi) -> None:
        self._client = client
        self._current: dict[str, CurrentWeather] = {}
        self._forecasts: dict[ForecastKey, Forecast] = {}
        self._histories: dict[HistoryKey, History] = {}

    async def get_current(self, location: Location) -> CurrentWeather:
        """Reutiliza el clima actual si ya se pidió en este pedido."""
        key = self._location_key(location)
        if key not in self._current:
            self._current[key] = await self._client.get_current(location)
        return self._current[key]

    async def get_forecast(
        self,
        location: Location,
        days: int = DEFAULT_FORECAST_DAYS,
    ) -> Forecast:
        """Reutiliza el pronóstico de la misma ubicación y cantidad de días."""
        key = (self._location_key(location), days)
        if key not in self._forecasts:
            self._forecasts[key] = await self._client.get_forecast(location, days)
        return self._forecasts[key]

    async def get_history(
        self,
        location: Location,
        start: date,
        end: date,
    ) -> History:
        """Reutiliza el histórico de la misma ubicación y rango."""
        key = (self._location_key(location), start, end)
        if key not in self._histories:
            self._histories[key] = await self._client.get_history(
                location,
                start,
                end,
            )
        return self._histories[key]

    @staticmethod
    def _location_key(location: Location) -> str:
        """Normaliza la ubicación para compartir caché entre variantes iguales."""
        if location.city is not None:
            return f"city:{location.city.casefold()}"

        if location.lat is None or location.lon is None:
            raise ValueError("la ubicación no tiene coordenadas completas")

        return f"coords:{location.lat:.2f},{location.lon:.2f}"
