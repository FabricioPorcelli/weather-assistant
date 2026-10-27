"""Endpoint de consejos directos, sin LLM."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.advice.engine import build_advice
from app.advice.models import Advice, AdviceKind
from app.api.dependencies import LocationDep, WeatherClientDep

router = APIRouter(prefix="/v1", tags=["advice"])


@router.get("/advice/{kind}", response_model=Advice)
async def get_advice(
    kind: AdviceKind,
    location: LocationDep,
    weather_client: WeatherClientDep,
    target_date: Annotated[
        date | None,
        Query(
            alias="date",
            description=(
                "Fecha objetivo en formato YYYY-MM-DD. Solo para paraguas y ropa."
            ),
        ),
    ] = None,
) -> Advice:
    """Devuelve un consejo determinista para la ubicación y fecha pedidas."""
    return await build_advice(
        kind,
        location,
        weather_client,
        target_date=target_date,
    )
