"""Endpoints de actividades y búsqueda del mejor día, sin LLM."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.advice.engine import evaluate_activity, find_best_day
from app.advice.models import ActivityId, BestDayResult, DayEvaluation
from app.api.dependencies import LocationDep, WeatherClientDep
from app.clients.weather_api import MAX_FORECAST_DAYS

router = APIRouter(prefix="/v1", tags=["activities"])


@router.get(
    "/activities/{activity}/evaluate",
    response_model=DayEvaluation,
)
async def get_activity_evaluation(
    activity: ActivityId,
    location: LocationDep,
    weather_client: WeatherClientDep,
    target_date: Annotated[
        date,
        Query(alias="date", description="Fecha a evaluar en formato YYYY-MM-DD"),
    ],
) -> DayEvaluation:
    """Evalúa una actividad para un día concreto."""
    return await evaluate_activity(
        activity,
        location,
        weather_client,
        target_date,
    )


@router.get(
    "/activities/{activity}/best-day",
    response_model=BestDayResult,
)
async def get_best_day(
    activity: ActivityId,
    location: LocationDep,
    weather_client: WeatherClientDep,
    start: Annotated[date, Query(description="Inicio del rango, YYYY-MM-DD")],
    end: Annotated[date, Query(description="Fin del rango, YYYY-MM-DD")],
    top: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_FORECAST_DAYS,
            description="Cantidad de días en el ranking",
        ),
    ] = 3,
) -> BestDayResult:
    """Devuelve el ranking de días para una actividad dentro de un rango."""
    return await find_best_day(
        activity,
        location,
        weather_client,
        start,
        end,
        top_n=top,
    )
