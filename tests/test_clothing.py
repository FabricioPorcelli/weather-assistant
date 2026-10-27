"""Tests de la regla de ropa y abrigo."""

import pytest

from app.advice.clothing import evaluate_clothing
from app.advice.models import AdviceKind
from tests.helpers import DEFAULT_DAY, make_day


@pytest.mark.parametrize(
    ("reference_temperature_c", "expected"),
    [
        (28.0, "muy_liviana"),
        (27.9, "liviana"),
        (22.0, "liviana"),
        (21.9, "capa_intermedia"),
        (16.0, "capa_intermedia"),
        (15.9, "campera"),
        (10.0, "campera"),
        (9.9, "abrigo_con_bufanda"),
        (4.0, "abrigo_con_bufanda"),
        (3.9, "abrigo_grueso"),
    ],
)
def test_clothing_temperature_boundaries(reference_temperature_c, expected):
    day = make_day(
        temp_max_c=reference_temperature_c + 2,
        temp_min_c=reference_temperature_c - 2,
    )

    advice = evaluate_clothing(
        day,
        reference_temperature_c=reference_temperature_c,
        reference_source="daily_average",
        location_label="Madrid",
    )

    assert advice.verdict == expected
    assert advice.kind == AdviceKind.CLOTHING
    assert advice.target_date == DEFAULT_DAY
    assert advice.location_label == "Madrid"


@pytest.mark.parametrize(
    ("wind_speed_kmh", "expected"),
    [
        (29.9, "capa_intermedia"),
        (30.0, "campera"),
        (45.0, "campera"),
    ],
)
def test_wind_adds_one_clothing_layer(wind_speed_kmh, expected):
    day = make_day(
        wind_speed_kmh=wind_speed_kmh,
        temp_max_c=24.0,
        temp_min_c=16.0,
    )

    advice = evaluate_clothing(
        day,
        reference_temperature_c=20.0,
        reference_source="daily_average",
        location_label="Madrid",
    )

    assert advice.verdict == expected
    has_wind_reason = any(
        reason.metric == "wind_speed_kmh" for reason in advice.reasons
    )
    assert has_wind_reason is (wind_speed_kmh >= 30)


def test_wind_at_max_level_keeps_level_and_suggests_windbreaker():
    day = make_day(
        wind_speed_kmh=35.0,
        temp_max_c=4.0,
        temp_min_c=0.0,
    )

    advice = evaluate_clothing(
        day,
        reference_temperature_c=2.0,
        reference_source="daily_average",
        location_label="Madrid",
    )

    assert advice.verdict == "abrigo_grueso"
    assert "cortaviento" in advice.summary


def test_wide_temperature_range_adds_extra_layer_caveat():
    day = make_day(temp_max_c=25.0, temp_min_c=15.0)

    advice = evaluate_clothing(
        day,
        reference_temperature_c=20.0,
        reference_source="daily_average",
        location_label="Madrid",
    )

    assert any("Amplitud térmica de 10.0" in caveat for caveat in advice.caveats)
    assert any(reason.metric == "temperature_range_c" for reason in advice.reasons)


def test_narrow_temperature_range_does_not_add_extra_layer():
    day = make_day(temp_max_c=24.9, temp_min_c=15.0)

    advice = evaluate_clothing(
        day,
        reference_temperature_c=20.0,
        reference_source="daily_average",
        location_label="Madrid",
    )

    assert not any("Amplitud térmica" in caveat for caveat in advice.caveats)


def test_umbrella_yes_suggests_raincoat():
    day = make_day(probability=60, precipitation_mm=0.0)

    advice = evaluate_clothing(
        day,
        reference_temperature_c=20.0,
        reference_source="daily_average",
        location_label="Madrid",
    )

    assert any("impermeable" in caveat for caveat in advice.caveats)


def test_feels_like_source_includes_current_weather():
    advice = evaluate_clothing(
        make_day(),
        reference_temperature_c=20.0,
        reference_source="feels_like",
        location_label="Madrid",
    )

    assert advice.data_sources == ["/v1/weather", "/v1/forecast"]


def test_daily_average_source_reports_caveat():
    advice = evaluate_clothing(
        make_day(),
        reference_temperature_c=20.0,
        reference_source="daily_average",
        location_label="Madrid",
    )

    assert advice.data_sources == ["/v1/forecast"]
    assert any("promedio de máxima y mínima" in caveat for caveat in advice.caveats)
