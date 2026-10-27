"""Recorte de rangos y ranking para la búsqueda del mejor día."""

from datetime import date

from app.advice.errors import InvalidAdviceRequest, OutOfRangeError
from app.advice.models import ActivityVerdict, DayEvaluation
from app.clients.weather_api import MAX_FORECAST_DAYS, Forecast


def clip_range(
    forecast: Forecast,
    start: date,
    end: date,
) -> tuple[date, date, bool]:
    """Recorta el rango pedido al horizonte disponible del pronóstico."""
    if start > end:
        raise InvalidAdviceRequest("start no puede ser posterior a end")

    first_available = forecast.days[0].date
    last_available = forecast.days[-1].date
    effective_start = max(start, first_available)
    effective_end = min(end, last_available)

    if effective_start > effective_end:
        raise OutOfRangeError(
            "No hay días del rango solicitado dentro del pronóstico disponible"
        )

    was_clipped = effective_start != start or effective_end != end
    return effective_start, effective_end, was_clipped


def rank_evaluations(
    evaluations: list[DayEvaluation],
    top_n: int,
) -> tuple[list[DayEvaluation], bool]:
    """Ordena por puntaje, desempata por fecha y calcula si hay días aceptables."""
    if top_n < 1:
        raise InvalidAdviceRequest("top_n debe ser al menos 1")

    ranking = sorted(
        evaluations,
        key=lambda evaluation: (-evaluation.score, evaluation.date),
    )[:top_n]
    has_acceptable_day = any(
        evaluation.verdict != ActivityVerdict.NOT_RECOMMENDED
        for evaluation in evaluations
    )
    return ranking, has_acceptable_day


def range_caveat(
    requested_start: date,
    requested_end: date,
    effective_start: date,
    effective_end: date,
) -> str:
    """Explica al usuario que el rango pedido se recortó."""
    return (
        f"El rango solicitado ({requested_start.isoformat()} a "
        f"{requested_end.isoformat()}) se recortó a "
        f"{effective_start.isoformat()} a {effective_end.isoformat()} "
        f"por el horizonte máximo de {MAX_FORECAST_DAYS} días."
    )
