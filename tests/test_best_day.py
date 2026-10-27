"""Tests del recorte de rangos y del ranking de días."""

from datetime import timedelta

import pytest

from app.advice.best_day import clip_range, range_caveat, rank_evaluations
from app.advice.errors import InvalidAdviceRequest, OutOfRangeError
from app.advice.models import ActivityVerdict
from tests.helpers import (
    DEFAULT_DAY,
    make_evaluation,
    make_forecast,
    make_forecast_range,
)


def _forecast():
    return make_forecast(make_forecast_range(count=15))


def test_range_within_horizon_is_not_clipped():
    forecast = _forecast()
    start = DEFAULT_DAY + timedelta(days=2)
    end = DEFAULT_DAY + timedelta(days=5)

    effective_start, effective_end, was_clipped = clip_range(
        forecast,
        start,
        end,
    )

    assert effective_start == start
    assert effective_end == end
    assert was_clipped is False


def test_range_is_clipped_to_forecast_horizon():
    forecast = _forecast()
    last_day = DEFAULT_DAY + timedelta(days=14)

    effective_start, effective_end, was_clipped = clip_range(
        forecast,
        DEFAULT_DAY - timedelta(days=3),
        last_day + timedelta(days=3),
    )

    assert effective_start == DEFAULT_DAY
    assert effective_end == last_day
    assert was_clipped is True


def test_reversed_range_is_rejected():
    with pytest.raises(InvalidAdviceRequest):
        clip_range(
            _forecast(),
            DEFAULT_DAY + timedelta(days=2),
            DEFAULT_DAY,
        )


def test_range_without_forecast_days_is_rejected():
    last_day = DEFAULT_DAY + timedelta(days=14)

    with pytest.raises(OutOfRangeError):
        clip_range(
            _forecast(),
            last_day + timedelta(days=1),
            last_day + timedelta(days=3),
        )


def test_ranking_sorts_by_score_and_breaks_ties_by_date():
    later = DEFAULT_DAY + timedelta(days=2)
    evaluations = [
        make_evaluation(day=later, score=90),
        make_evaluation(day=DEFAULT_DAY, score=90),
        make_evaluation(
            day=DEFAULT_DAY + timedelta(days=1),
            score=50,
            verdict=ActivityVerdict.ACCEPTABLE,
        ),
    ]

    ranking, has_acceptable_day = rank_evaluations(evaluations, top_n=2)

    assert [evaluation.date for evaluation in ranking] == [
        DEFAULT_DAY,
        later,
    ]
    assert has_acceptable_day is True


def test_has_acceptable_day_uses_all_evaluations_not_only_top():
    evaluations = [
        make_evaluation(
            day=DEFAULT_DAY,
            score=90,
            verdict=ActivityVerdict.IDEAL,
        ),
        make_evaluation(
            day=DEFAULT_DAY + timedelta(days=1),
            score=0,
            verdict=ActivityVerdict.NOT_RECOMMENDED,
        ),
    ]

    ranking, has_acceptable_day = rank_evaluations(evaluations, top_n=1)

    assert len(ranking) == 1
    assert has_acceptable_day is True


def test_all_days_not_recommended():
    evaluations = [
        make_evaluation(
            day=DEFAULT_DAY,
            score=45,
            verdict=ActivityVerdict.NOT_RECOMMENDED,
        )
    ]

    _, has_acceptable_day = rank_evaluations(evaluations, top_n=3)

    assert has_acceptable_day is False


def test_top_n_must_be_positive():
    with pytest.raises(InvalidAdviceRequest):
        rank_evaluations([], top_n=0)


def test_range_caveat_mentions_requested_and_effective_dates():
    message = range_caveat(
        DEFAULT_DAY - timedelta(days=2),
        DEFAULT_DAY + timedelta(days=20),
        DEFAULT_DAY,
        DEFAULT_DAY + timedelta(days=14),
    )

    assert "2026-10-25" in message
    assert "2026-11-10" in message
    assert "2026-11-16" in message
    assert "15 días" in message
