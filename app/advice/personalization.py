"""Ajuste incremental del offset de comodidad."""

from enum import StrEnum

COMFORT_STEP_C = 0.5
MAX_COMFORT_OFFSET_C = 10.0


class ComfortFeedback(StrEnum):
    """Feedback disponible para el consejo de ropa."""

    COLD = "cold"
    JUST_RIGHT = "just_right"
    HOT = "hot"


def update_comfort_offset(
    current_offset_c: float,
    feedback: ComfortFeedback,
) -> float:
    """Frío baja la referencia y pide más abrigo; calor la sube."""
    if feedback == ComfortFeedback.COLD:
        current_offset_c -= COMFORT_STEP_C
    elif feedback == ComfortFeedback.HOT:
        current_offset_c += COMFORT_STEP_C

    return round(
        max(-MAX_COMFORT_OFFSET_C, min(MAX_COMFORT_OFFSET_C, current_offset_c)),
        2,
    )
