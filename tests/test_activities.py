"""Tests de perfiles, vetos y puntaje de actividades."""

import pytest

from app.advice.activities import (
    confidence_for_offset,
    evaluate_activity_day,
)
from app.advice.errors import InvalidAdviceRequest
from app.advice.models import ActivityId, ActivityVerdict, Confidence
from tests.helpers import make_day


def _evaluate(
    activity: ActivityId,
    *,
    previous_rain_mm: float = 0.0,
    next_day_probability: int | None = None,
    **day_kwargs,
):
    return evaluate_activity_day(
        activity,
        make_day(**day_kwargs),
        confidence=Confidence.HIGH,
        previous_day_precipitation_mm=previous_rain_mm,
        next_day_precipitation_probability=next_day_probability,
    )


@pytest.mark.parametrize(
    ("activity", "day_kwargs", "blocker_fragment"),
    [
        (ActivityId.OUTDOOR_EVENT, {"probability": 40}, "Probabilidad"),
        (ActivityId.OUTDOOR_EVENT, {"precipitation_mm": 1.0}, "Lluvia"),
        (ActivityId.OUTDOOR_EVENT, {"wind_speed_kmh": 35.0}, "Viento"),
        (ActivityId.OUTDOOR_EXERCISE, {"probability": 60}, "Probabilidad"),
        (ActivityId.OUTDOOR_EXERCISE, {"precipitation_mm": 5.0}, "Lluvia"),
        (ActivityId.OUTDOOR_EXERCISE, {"wind_speed_kmh": 40.0}, "Viento"),
        (ActivityId.OUTDOOR_EXERCISE, {"temp_max_c": 33.0}, "Temperatura máxima"),
        (ActivityId.EXTERIOR_PAINTING, {"probability": 30}, "Probabilidad"),
        (ActivityId.EXTERIOR_PAINTING, {"precipitation_mm": 0.2}, "Lluvia"),
        (ActivityId.EXTERIOR_PAINTING, {"wind_speed_kmh": 25.0}, "Viento"),
        (ActivityId.DRYING_LAUNDRY, {"probability": 40}, "Probabilidad"),
        (ActivityId.DRYING_LAUNDRY, {"precipitation_mm": 1.0}, "Lluvia"),
    ],
)
def test_activity_vetoes(activity, day_kwargs, blocker_fragment):
    evaluation = _evaluate(activity, **day_kwargs)

    assert evaluation.score == 0
    assert evaluation.verdict == ActivityVerdict.NOT_RECOMMENDED
    assert any(
        blocker_fragment.lower() in blocker.lower() for blocker in evaluation.blockers
    )


def test_previous_rain_vetoes_painting():
    evaluation = _evaluate(
        ActivityId.EXTERIOR_PAINTING,
        previous_rain_mm=1.0,
    )

    assert evaluation.score == 0
    assert evaluation.verdict == ActivityVerdict.NOT_RECOMMENDED
    assert any("día anterior" in blocker for blocker in evaluation.blockers)


@pytest.mark.parametrize(
    ("activity", "day_kwargs"),
    [
        (
            ActivityId.OUTDOOR_EVENT,
            {"temp_max_c": 25.0, "temp_min_c": 21.0},
        ),
        (
            ActivityId.OUTDOOR_EXERCISE,
            {"temp_max_c": 18.0, "temp_min_c": 14.0},
        ),
        (
            ActivityId.EXTERIOR_PAINTING,
            {"temp_max_c": 22.0, "temp_min_c": 18.0},
        ),
        (
            ActivityId.DRYING_LAUNDRY,
            {"temp_max_c": 26.0, "temp_min_c": 10.0, "wind_speed_kmh": 20.0},
        ),
    ],
)
def test_ideal_days_score_100(activity, day_kwargs):
    evaluation = _evaluate(activity, **day_kwargs)

    assert evaluation.score == 100
    assert evaluation.verdict == ActivityVerdict.IDEAL
    assert evaluation.blockers == []


@pytest.mark.parametrize(
    ("average_temperature_c", "expected_score", "expected_verdict"),
    [
        (32.0, 80, ActivityVerdict.IDEAL),
        (33.0, 75, ActivityVerdict.ACCEPTABLE),
        (38.0, 50, ActivityVerdict.ACCEPTABLE),
        (39.0, 45, ActivityVerdict.NOT_RECOMMENDED),
    ],
)
def test_temperature_score_boundaries(
    average_temperature_c,
    expected_score,
    expected_verdict,
):
    evaluation = _evaluate(
        ActivityId.OUTDOOR_EVENT,
        temp_max_c=average_temperature_c + 2,
        temp_min_c=average_temperature_c - 2,
    )

    assert evaluation.score == expected_score
    assert evaluation.verdict == expected_verdict


def test_probability_penalty_can_reach_ideal_boundary():
    evaluation = _evaluate(ActivityId.OUTDOOR_EVENT, probability=25)

    assert evaluation.score == 80
    assert evaluation.verdict == ActivityVerdict.IDEAL


def test_wind_penalty_can_reach_ideal_boundary():
    evaluation = _evaluate(ActivityId.OUTDOOR_EVENT, wind_speed_kmh=25.0)

    assert evaluation.score == 80
    assert evaluation.verdict == ActivityVerdict.IDEAL


def test_event_penalties_accumulate():
    evaluation = _evaluate(
        ActivityId.OUTDOOR_EVENT,
        probability=25,
        wind_speed_kmh=25.0,
    )

    assert evaluation.score == 60
    assert evaluation.verdict == ActivityVerdict.ACCEPTABLE


@pytest.mark.parametrize(
    ("next_day_probability", "expected_score"),
    [
        (39, 100),
        (40, 80),
    ],
)
def test_painting_next_day_probability_penalty(
    next_day_probability,
    expected_score,
):
    evaluation = _evaluate(
        ActivityId.EXTERIOR_PAINTING,
        next_day_probability=next_day_probability,
    )

    assert evaluation.score == expected_score


@pytest.mark.parametrize(
    ("day_kwargs", "expected_score"),
    [
        ({"temp_max_c": 35.0}, 85),
        ({"wind_speed_kmh": 5.0}, 85),
        ({"wind_speed_kmh": 35.0}, 85),
        ({"temp_max_c": 39.0}, 65),
    ],
)
def test_drying_laundry_penalties(day_kwargs, expected_score):
    evaluation = _evaluate(ActivityId.DRYING_LAUNDRY, **day_kwargs)

    assert evaluation.score == expected_score


def test_reasons_include_profile_metrics():
    evaluation = _evaluate(ActivityId.OUTDOOR_EVENT)

    metrics = {reason.metric for reason in evaluation.reasons}
    assert metrics == {
        "average_temperature_c",
        "precipitation_probability",
        "precipitation_mm",
        "wind_speed_kmh",
    }


def test_painting_adds_previous_and_next_day_reasons():
    evaluation = _evaluate(
        ActivityId.EXTERIOR_PAINTING,
        previous_rain_mm=0.5,
        next_day_probability=20,
    )

    metrics = {reason.metric for reason in evaluation.reasons}
    assert "previous_day_precipitation_mm" in metrics
    assert "next_day_precipitation_probability" in metrics


def test_drying_uses_max_temperature_reason():
    evaluation = _evaluate(ActivityId.DRYING_LAUNDRY)

    assert any(reason.metric == "temp_max_c" for reason in evaluation.reasons)


@pytest.mark.parametrize(
    ("offset_days", "expected"),
    [
        (0, Confidence.HIGH),
        (2, Confidence.HIGH),
        (3, Confidence.MEDIUM),
        (6, Confidence.MEDIUM),
        (7, Confidence.LOW),
        (14, Confidence.LOW),
    ],
)
def test_confidence_by_offset(offset_days, expected):
    assert confidence_for_offset(offset_days) == expected


def test_unknown_activity_is_rejected():
    with pytest.raises(InvalidAdviceRequest):
        evaluate_activity_day(
            "sunscreen",
            make_day(),
            confidence=Confidence.HIGH,
        )
