"""Tests de la regla de paraguas."""

from datetime import date

import pytest

from app.advice.models import AdviceKind
from app.advice.umbrella import evaluate_umbrella
from tests.helpers import DEFAULT_DAY, make_day


@pytest.mark.parametrize(
    ("probability", "precipitation_mm", "expected"),
    [
        (50, 0.0, "yes"),
        (49, 0.0, "maybe"),
        (25, 0.0, "maybe"),
        (24, 0.0, "no"),
        (0, 1.0, "yes"),
        (0, 0.99, "maybe"),
        (0, 0.2, "maybe"),
        (0, 0.19, "no"),
        (60, 1.5, "yes"),
        (None, 0.0, "no"),
        (None, 1.0, "yes"),
    ],
)
def test_umbrella_thresholds(probability, precipitation_mm, expected):
    day = make_day(probability=probability, precipitation_mm=precipitation_mm)

    advice = evaluate_umbrella(day, "Madrid")

    assert advice.verdict == expected
    assert advice.kind == AdviceKind.UMBRELLA
    assert advice.target_date == DEFAULT_DAY
    assert advice.location_label == "Madrid"
    assert advice.data_sources == ["/v1/forecast"]


def test_umbrella_reasons_include_both_metrics():
    advice = evaluate_umbrella(
        make_day(probability=60, precipitation_mm=1.5),
        "Madrid",
    )

    reasons = {reason.metric: reason for reason in advice.reasons}
    assert reasons["precipitation_probability"].value == 60
    assert reasons["precipitation_probability"].unit == "%"
    assert reasons["precipitation_mm"].value == 1.5
    assert reasons["precipitation_mm"].unit == "mm"


def test_umbrella_always_reports_daily_caveat():
    advice = evaluate_umbrella(make_day(probability=10), "Madrid")

    assert any("diario" in caveat for caveat in advice.caveats)


def test_missing_probability_adds_caveat():
    advice = evaluate_umbrella(
        make_day(probability=None, precipitation_mm=0.0), "Madrid"
    )

    assert advice.verdict == "no"
    assert any("no informó probabilidad" in caveat for caveat in advice.caveats)


def test_umbrella_summary_mentions_umbrella():
    advice = evaluate_umbrella(make_day(probability=25), "Madrid")

    assert "paraguas" in advice.summary.lower()


def test_umbrella_target_date_comes_from_day():
    day = make_day(day=date(2026, 10, 29), probability=0)

    advice = evaluate_umbrella(day, "Madrid")

    assert advice.target_date == date(2026, 10, 29)
