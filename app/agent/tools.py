"""Herramientas del agente, sus esquemas y su ejecución validada."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.advice.engine import (
    build_advice,
    evaluate_activity,
    find_best_day,
)
from app.advice.errors import AdviceError
from app.advice.models import ActivityId, AdviceKind
from app.agent.prompts import MONTHS_ES, WEEKDAYS_ES
from app.clients.weather_api import (
    MAX_FORECAST_DAYS,
    Location,
    WeatherApi,
    WeatherApiError,
)

LOCATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "Ubicación: una ciudad o un par completo de coordenadas, nunca ambas."
    ),
    "properties": {
        "city": {
            "type": "string",
            "description": "Nombre de la ciudad, por ejemplo Madrid.",
        },
        "lat": {
            "type": "number",
            "description": "Latitud en grados decimales.",
        },
        "lon": {
            "type": "number",
            "description": "Longitud en grados decimales.",
        },
        "label": {
            "type": "string",
            "description": "Texto opcional para mostrar la ubicación.",
        },
    },
    "additionalProperties": False,
}


class CurrentWeatherArgs(BaseModel):
    """Argumentos de get_current_weather."""

    model_config = ConfigDict(extra="forbid")

    location: Location


class ForecastArgs(BaseModel):
    """Argumentos de get_forecast."""

    model_config = ConfigDict(extra="forbid")

    location: Location
    days: int = Field(default=5, ge=1, le=MAX_FORECAST_DAYS)


class AdviceArgs(BaseModel):
    """Argumentos de las herramientas de consejos."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    location: Location
    target_date: date | None = Field(default=None, alias="date")


class WateringArgs(BaseModel):
    """Argumentos de get_watering_advice, que no acepta fecha."""

    model_config = ConfigDict(extra="forbid")

    location: Location


class ActivityArgs(BaseModel):
    """Argumentos de get_activity_advice."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    location: Location
    activity: ActivityId
    target_date: date = Field(alias="date")


class BestDayArgs(BaseModel):
    """Argumentos de find_best_day."""

    model_config = ConfigDict(extra="forbid")

    location: Location
    activity: ActivityId
    start_date: date
    end_date: date
    top_n: int = Field(default=3, ge=1, le=MAX_FORECAST_DAYS)


def _format_date_label(value: str) -> str:
    """Convierte una fecha ISO en un texto con día de la semana en español."""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    return (
        f"{WEEKDAYS_ES[parsed.weekday()]} {parsed.day} de "
        f"{MONTHS_ES[parsed.month - 1]} de {parsed.year}"
    )


def _add_date_labels(value: Any) -> None:
    """Agrega date_label a cada fecha para que el modelo no calcule el día."""
    if isinstance(value, list):
        for item in value:
            _add_date_labels(item)
        return

    if not isinstance(value, dict):
        return

    for key, item in list(value.items()):
        if key in {"date", "target_date", "start", "end"} and isinstance(item, str):
            value[f"{key}_label"] = _format_date_label(item)
        elif isinstance(item, (dict, list)):
            _add_date_labels(item)


def _function(
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Envuelve un esquema en el formato de herramientas de OpenAI."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


_DATE_SCHEMA = {
    "type": "string",
    "format": "date",
    "description": "Fecha en formato YYYY-MM-DD.",
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    _function(
        "get_current_weather",
        "Devuelve el clima actual normalizado de una ubicación.",
        {
            "type": "object",
            "properties": {"location": LOCATION_SCHEMA},
            "required": ["location"],
            "additionalProperties": False,
        },
    ),
    _function(
        "get_forecast",
        "Devuelve el pronóstico diario de una ubicación.",
        {
            "type": "object",
            "properties": {
                "location": LOCATION_SCHEMA,
                "days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_FORECAST_DAYS,
                    "description": "Cantidad de días de pronóstico.",
                },
            },
            "required": ["location"],
            "additionalProperties": False,
        },
    ),
    _function(
        "get_umbrella_advice",
        "Devuelve el consejo determinista de paraguas para una fecha.",
        {
            "type": "object",
            "properties": {
                "location": LOCATION_SCHEMA,
                "date": _DATE_SCHEMA,
            },
            "required": ["location"],
            "additionalProperties": False,
        },
    ),
    _function(
        "get_clothing_advice",
        "Devuelve el consejo determinista de ropa y abrigo para una fecha.",
        {
            "type": "object",
            "properties": {
                "location": LOCATION_SCHEMA,
                "date": _DATE_SCHEMA,
            },
            "required": ["location"],
            "additionalProperties": False,
        },
    ),
    _function(
        "get_watering_advice",
        "Devuelve el consejo determinista de riego para hoy.",
        {
            "type": "object",
            "properties": {"location": LOCATION_SCHEMA},
            "required": ["location"],
            "additionalProperties": False,
        },
    ),
    _function(
        "get_activity_advice",
        "Evalúa una actividad concreta en una fecha.",
        {
            "type": "object",
            "properties": {
                "location": LOCATION_SCHEMA,
                "activity": {
                    "type": "string",
                    "enum": [activity.value for activity in ActivityId],
                    "description": "Actividad a evaluar.",
                },
                "date": _DATE_SCHEMA,
            },
            "required": ["location", "activity", "date"],
            "additionalProperties": False,
        },
    ),
    _function(
        "find_best_day",
        "Devuelve el ranking de mejores días para una actividad en un rango.",
        {
            "type": "object",
            "properties": {
                "location": LOCATION_SCHEMA,
                "activity": {
                    "type": "string",
                    "enum": [activity.value for activity in ActivityId],
                    "description": "Actividad a evaluar.",
                },
                "start_date": _DATE_SCHEMA,
                "end_date": _DATE_SCHEMA,
                "top_n": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_FORECAST_DAYS,
                    "description": "Cantidad de días en el ranking.",
                },
            },
            "required": ["location", "activity", "start_date", "end_date"],
            "additionalProperties": False,
        },
    ),
]

TOOL_ARG_MODELS: dict[str, type[BaseModel]] = {
    "get_current_weather": CurrentWeatherArgs,
    "get_forecast": ForecastArgs,
    "get_umbrella_advice": AdviceArgs,
    "get_clothing_advice": AdviceArgs,
    "get_watering_advice": WateringArgs,
    "get_activity_advice": ActivityArgs,
    "find_best_day": BestDayArgs,
}


async def execute_tool(
    name: str,
    arguments_json: str,
    client: WeatherApi,
) -> dict[str, Any]:
    """Valida los argumentos, ejecuta la herramienta y devuelve JSON."""
    arg_model = TOOL_ARG_MODELS.get(name)
    if arg_model is None:
        return {"error": f"Herramienta desconocida: {name}"}

    try:
        args = arg_model.model_validate_json(arguments_json)
    except ValidationError:
        return {"error": f"Argumentos inválidos para {name}"}

    try:
        if name == "get_current_weather":
            result = await client.get_current(args.location)
        elif name == "get_forecast":
            result = await client.get_forecast(args.location, days=args.days)
        elif name == "get_umbrella_advice":
            result = await build_advice(
                AdviceKind.UMBRELLA,
                args.location,
                client,
                target_date=args.target_date,
            )
        elif name == "get_clothing_advice":
            result = await build_advice(
                AdviceKind.CLOTHING,
                args.location,
                client,
                target_date=args.target_date,
            )
        elif name == "get_watering_advice":
            result = await build_advice(
                AdviceKind.WATERING,
                args.location,
                client,
            )
        elif name == "get_activity_advice":
            result = await evaluate_activity(
                args.activity,
                args.location,
                client,
                args.target_date,
            )
        elif name == "find_best_day":
            result = await find_best_day(
                args.activity,
                args.location,
                client,
                args.start_date,
                args.end_date,
                top_n=args.top_n,
            )
        else:
            return {"error": f"Herramienta desconocida: {name}"}
    except (AdviceError, WeatherApiError, ValueError) as exc:
        return {"error": str(exc)}

    data = result.model_dump(mode="json")
    _add_date_labels(data)
    return data
