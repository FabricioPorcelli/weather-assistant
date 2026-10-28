"""Tests del ajuste de comodidad."""

import pytest

from app.advice.personalization import (
    MAX_COMFORT_OFFSET_C,
    ComfortFeedback,
    update_comfort_offset,
)


@pytest.mark.parametrize(
    ("current", "feedback", "expected"),
    [
        (0.0, ComfortFeedback.COLD, -0.5),
        (0.0, ComfortFeedback.HOT, 0.5),
        (1.5, ComfortFeedback.JUST_RIGHT, 1.5),
        (-1.0, ComfortFeedback.COLD, -1.5),
    ],
)
def test_update_comfort_offset(current, feedback, expected):
    assert update_comfort_offset(current, feedback) == expected


def test_offset_is_clamped():
    assert (
        update_comfort_offset(
            MAX_COMFORT_OFFSET_C,
            ComfortFeedback.HOT,
        )
        == MAX_COMFORT_OFFSET_C
    )
    assert (
        update_comfort_offset(
            -MAX_COMFORT_OFFSET_C,
            ComfortFeedback.COLD,
        )
        == -MAX_COMFORT_OFFSET_C
    )


def test_synthetic_user_converges():
    target_offset = -3.0
    current_offset = 0.0

    for _ in range(30):
        if current_offset > target_offset + 0.25:
            feedback = ComfortFeedback.COLD
        elif current_offset < target_offset - 0.25:
            feedback = ComfortFeedback.HOT
        else:
            feedback = ComfortFeedback.JUST_RIGHT
        current_offset = update_comfort_offset(current_offset, feedback)

    assert abs(current_offset - target_offset) <= 0.5
