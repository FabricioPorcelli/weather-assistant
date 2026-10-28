"""Modelos de salida del motor de consejos."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class AdviceKind(StrEnum):
    """Tipos de consejo disponibles en el MVP."""

    UMBRELLA = "umbrella"
    CLOTHING = "clothing"
    WATERING = "watering"


class ActivityId(StrEnum):
    """Actividades que el motor sabe evaluar."""

    OUTDOOR_EVENT = "outdoor_event"
    OUTDOOR_EXERCISE = "outdoor_exercise"
    EXTERIOR_PAINTING = "exterior_painting"
    DRYING_LAUNDRY = "drying_laundry"


class ActivityVerdict(StrEnum):
    """Resultado de evaluar un día para una actividad."""

    IDEAL = "ideal"
    ACCEPTABLE = "acceptable"
    NOT_RECOMMENDED = "not_recommended"


class Confidence(StrEnum):
    """Confianza según cuán lejos está el día dentro del pronóstico."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Reason(BaseModel):
    """Cifra concreta que justifica una decisión."""

    metric: str = Field(min_length=1)
    value: float | int | str
    unit: str | None = None


class Advice(BaseModel):
    """Resultado común de los consejos."""

    kind: AdviceKind
    verdict: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    reasons: list[Reason]
    target_date: date
    location_label: str
    data_sources: list[str]
    caveats: list[str]


class DayEvaluation(BaseModel):
    """Evaluación de un día para una actividad concreta."""

    date: date
    score: int = Field(ge=0, le=100)
    verdict: ActivityVerdict
    reasons: list[Reason]
    blockers: list[str]
    confidence: Confidence


class DateRange(BaseModel):
    """Rango inclusivo de fechas."""

    start: date
    end: date


class BestDayResult(BaseModel):
    """Ranking de días para una actividad dentro de un rango."""

    activity: ActivityId
    location_label: str
    range: DateRange
    ranking: list[DayEvaluation]
    has_acceptable_day: bool
    caveats: list[str]
