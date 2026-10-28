"""Cliente HTTP async de weather-api."""

import asyncio
from datetime import date, datetime, time
from types import TracebackType
from typing import Protocol, Self, TypeVar
from urllib.parse import quote

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

DEFAULT_FORECAST_DAYS = 5
MIN_FORECAST_DAYS = 1
MAX_FORECAST_DAYS = 15
RETRYABLE_STATUS_CODES = frozenset({502, 504})

ModelT = TypeVar("ModelT", bound=BaseModel)


class WeatherApiError(Exception):
    """Error base del cliente de weather-api."""


class LocationNotFound(WeatherApiError):
    """weather-api no reconoce la ciudad o las coordenadas solicitadas."""


class InvalidRequest(WeatherApiError):
    """weather-api rechazó los parámetros enviados (HTTP 422)."""


class RateLimited(WeatherApiError):
    """Se superó el límite de pedidos por minuto de weather-api (HTTP 429)."""


class UpstreamError(WeatherApiError):
    """weather-api falló, no está disponible o devolvió datos inesperados."""


class UpstreamTimeout(UpstreamError):
    """weather-api no respondió dentro del tiempo máximo configurado."""


class Location(BaseModel):
    """Ubicación consultada: ciudad o par de coordenadas, nunca ambas."""

    model_config = ConfigDict(frozen=True)

    city: str | None = Field(default=None, min_length=2, max_length=100)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    label: str | None = Field(default=None, max_length=200)

    @field_validator("city", mode="before")
    @classmethod
    def _normalize_city(cls, value):
        """Limpia espacios accidentales del nombre de la ciudad."""
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_label(cls, value):
        """Limpia espacios del texto que se muestra al usuario."""
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def _validate_location_mode(self) -> Self:
        """Exige una ciudad sola o un par completo de coordenadas."""
        has_city = self.city is not None
        has_any_coordinate = self.lat is not None or self.lon is not None
        has_both_coordinates = self.lat is not None and self.lon is not None

        if has_any_coordinate and not has_both_coordinates:
            raise ValueError("lat y lon deben enviarse juntos")
        if has_city and has_both_coordinates:
            raise ValueError("enviá una ciudad o coordenadas, no ambas")
        if not has_city and not has_both_coordinates:
            raise ValueError("se requiere una ciudad o un par de coordenadas")
        return self


class CurrentWeather(BaseModel):
    """Clima actual normalizado."""

    location: str
    temperature_c: float
    feels_like_c: float
    humidity: int = Field(ge=0, le=100)
    conditions: str
    wind_speed_kmh: float = Field(ge=0)
    precipitation_mm: float = Field(ge=0)
    updated_at: datetime


class DailyForecast(BaseModel):
    """Resumen de un día de pronóstico o de histórico."""

    date: date
    temp_max_c: float
    temp_min_c: float
    temp_c: float
    precipitation_mm: float = Field(ge=0)
    precipitation_probability: int | None = Field(default=None, ge=0, le=100)
    conditions: str
    wind_speed_kmh: float = Field(ge=0)
    sunrise: time
    sunset: time


class Forecast(BaseModel):
    """Pronóstico diario devuelto por weather-api."""

    location: str
    days: list[DailyForecast] = Field(min_length=1)


class History(BaseModel):
    """Histórico diario devuelto por weather-api."""

    location: str
    days: list[DailyForecast] = Field(min_length=1)


class WeatherApi(Protocol):
    """Operaciones que necesita el motor; permite sustituir el cliente."""

    async def get_current(self, location: Location) -> CurrentWeather: ...

    async def get_forecast(
        self, location: Location, days: int = DEFAULT_FORECAST_DAYS
    ) -> Forecast: ...

    async def get_history(
        self, location: Location, start: date, end: date
    ) -> History: ...


class WeatherApiClient:
    """Cliente async con timeouts y errores de dominio tipados."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        retries: int = 1,
        retry_delay: float = 0.5,
    ) -> None:
        base_url = base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("base_url no puede estar vacía")
        if timeout <= 0:
            raise ValueError("timeout debe ser mayor que cero")
        if not 0 <= retries <= 3:
            raise ValueError("retries debe estar entre 0 y 3")
        if retry_delay < 0:
            raise ValueError("retry_delay no puede ser negativo")

        self._retries = retries
        self._retry_delay = retry_delay
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def get_current(self, location: Location) -> CurrentWeather:
        """Obtiene el clima actual de una ubicación."""
        path = self._resource_path("weather", location)
        data = await self._get_json(path)
        return self._parse(CurrentWeather, data)

    async def get_forecast(
        self, location: Location, days: int = DEFAULT_FORECAST_DAYS
    ) -> Forecast:
        """Obtiene hasta 15 días de pronóstico diario."""
        if not MIN_FORECAST_DAYS <= days <= MAX_FORECAST_DAYS:
            raise ValueError(
                f"days debe estar entre {MIN_FORECAST_DAYS} y {MAX_FORECAST_DAYS}"
            )

        path = self._resource_path("forecast", location)
        data = await self._get_json(path, params={"days": days})
        return self._parse(Forecast, data)

    async def get_history(self, location: Location, start: date, end: date) -> History:
        """Obtiene el histórico diario de un rango inclusivo de fechas."""
        if start > end:
            raise ValueError("start no puede ser posterior a end")

        path = self._resource_path("history", location)
        data = await self._get_json(
            path,
            params={"start": start.isoformat(), "end": end.isoformat()},
        )
        return self._parse(History, data)

    async def aclose(self) -> None:
        """Cierra las conexiones HTTP abiertas por el cliente."""
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    def _resource_path(self, resource: str, location: Location) -> str:
        """Construye la ruta según la ubicación, sin aceptar URLs del usuario."""
        if location.city is not None:
            return f"/v1/{resource}/{quote(location.city, safe='')}"

        if location.lat is None or location.lon is None:
            raise ValueError("la ubicación no tiene coordenadas completas")

        # Dos decimales (~1 km) coinciden con la precisión de caché de weather-api.
        return f"/v1/{resource}/coords/{location.lat:.2f}/{location.lon:.2f}"

    async def _get_json(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> object:
        """Hace un GET, reintenta fallos transitorios y traduce errores."""
        response = None
        for attempt in range(self._retries + 1):
            try:
                response = await self._http.get(path, params=params)
            except httpx.TimeoutException as exc:
                if attempt < self._retries:
                    await asyncio.sleep(self._retry_delay)
                    continue
                raise UpstreamTimeout("weather-api no respondió a tiempo") from exc
            except httpx.RequestError as exc:
                raise UpstreamError("no se pudo conectar con weather-api") from exc

            if (
                response.status_code in RETRYABLE_STATUS_CODES
                and attempt < self._retries
            ):
                await asyncio.sleep(self._retry_delay)
                continue
            break

        if response is None:
            raise UpstreamError("weather-api no devolvió una respuesta")

        if response.status_code == 404:
            raise LocationNotFound("weather-api no encontró la ubicación")
        if response.status_code == 422:
            raise InvalidRequest("weather-api rechazó los parámetros enviados")
        if response.status_code == 429:
            raise RateLimited("se superó el límite de pedidos de weather-api")
        if response.status_code == 504:
            raise UpstreamTimeout("weather-api informó un timeout del proveedor")
        if response.status_code == 502:
            raise UpstreamError("el proveedor del clima no está disponible")
        if response.is_error:
            raise UpstreamError(
                f"weather-api respondió con estado {response.status_code}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError(
                "weather-api devolvió una respuesta que no es JSON"
            ) from exc

    @staticmethod
    def _parse(model: type[ModelT], data: object) -> ModelT:
        """Valida el JSON contra el modelo esperado."""
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise UpstreamError(
                "weather-api devolvió datos con un formato inesperado"
            ) from exc
