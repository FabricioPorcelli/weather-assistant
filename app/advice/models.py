"""Modelos de salida del motor de consejos."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class AdviceKind(StrEnum):
    """Tipos de consejo disponibles en el MVP."""

    UMBRELLA = "umbrella"
    CLOTHING = "clothing"
    WATERING = "watering"


class Reason(BaseModel):
    """Cifra concreta que justifica una decisión."""

    metric: str = Field(min_length=1)
    value: float | int | str
    unit: str | None = None


class Advice(BaseModel):
    """Resultado común de todos los consejos.

    `summary` es una frase neutra: el LLM la usará como base para redactar,
    pero no decide el veredicto.
    """

    kind: AdviceKind
    verdict: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    reasons: list[Reason]
    target_date: date
    location_label: str
    data_sources: list[str]
    caveats: list[str]
