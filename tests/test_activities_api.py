"""Tests de los endpoints de actividades."""

from datetime import timedelta

import httpx
import pytest

from tests.helpers import (
    DEFAULT_DAY,
    make_day,
    make_forecast,
    make_forecast_range,
    make_history,
)


def _json_forecast(days):
    return make_forecast(days).model_dump(mode="json")


async def test_evaluate_activity_by_city(api_client, api_mock):
    forecast = make_forecast(make_forecast_range(temp_max_c=25.0, temp_min_c=21.0))
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )

    response = await api_client.get(
        "/v1/activities/outdoor_event/evaluate",
        params={"city": "Madrid", "date": DEFAULT_DAY.isoformat()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == DEFAULT_DAY.isoformat()
    assert body["score"] == 100
    assert body["verdict"] == "ideal"
    assert body["confidence"] == "high"


async def test_evaluate_future_day_has_lower_confidence(api_client, api_mock):
    forecast = make_forecast(make_forecast_range(count=15))
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    target_date = DEFAULT_DAY + timedelta(days=7)

    response = await api_client.get(
        "/v1/activities/outdoor_event/evaluate",
        params={"city": "Madrid", "date": target_date.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["confidence"] == "low"


async def test_painting_today_reads_yesterday_history(api_client, api_mock):
    forecast = make_forecast(make_forecast_range(count=15))
    history = make_history(
        [make_day(day=DEFAULT_DAY - timedelta(days=1), precipitation_mm=1.0)]
    )
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    history_route = api_mock.get(
        "/v1/history/Madrid",
        params={"start": "2026-10-26", "end": "2026-10-26"},
    ).mock(return_value=httpx.Response(200, json=history.model_dump(mode="json")))

    response = await api_client.get(
        "/v1/activities/exterior_painting/evaluate",
        params={"city": "Madrid", "date": DEFAULT_DAY.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "not_recommended"
    assert any("día anterior" in item for item in response.json()["blockers"])
    assert history_route.called


async def test_painting_future_day_uses_forecast_previous_day(
    api_client,
    api_mock,
):
    days = make_forecast_range(count=15)
    days[0] = make_day(day=DEFAULT_DAY, precipitation_mm=1.0)
    forecast = make_forecast(days)
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    history_route = api_mock.get(
        "/v1/history/Madrid",
        params={"start": "2026-10-26", "end": "2026-10-26"},
    ).mock(
        return_value=httpx.Response(
            200,
            json=make_history([make_day()]).model_dump(mode="json"),
        )
    )
    target_date = DEFAULT_DAY + timedelta(days=1)

    response = await api_client.get(
        "/v1/activities/exterior_painting/evaluate",
        params={"city": "Madrid", "date": target_date.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "not_recommended"
    assert not history_route.called


async def test_best_day_painting_range_starting_today_reads_history(
    api_client,
    api_mock,
):
    forecast = make_forecast(make_forecast_range(count=15))
    history = make_history(
        [
            make_day(
                day=DEFAULT_DAY - timedelta(days=1),
                precipitation_mm=0.0,
            )
        ]
    )
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    history_route = api_mock.get(
        "/v1/history/Madrid",
        params={"start": "2026-10-26", "end": "2026-10-26"},
    ).mock(return_value=httpx.Response(200, json=history.model_dump(mode="json")))

    response = await api_client.get(
        "/v1/activities/exterior_painting/best-day",
        params={
            "city": "Madrid",
            "start": DEFAULT_DAY.isoformat(),
            "end": DEFAULT_DAY.isoformat(),
        },
    )

    assert response.status_code == 200
    assert history_route.called


async def test_best_day_returns_sorted_ranking(api_client, api_mock):
    days = [
        make_day(
            day=DEFAULT_DAY,
            temp_max_c=25.0,
            temp_min_c=21.0,
        ),
        make_day(
            day=DEFAULT_DAY + timedelta(days=1),
            probability=25,
        ),
        make_day(
            day=DEFAULT_DAY + timedelta(days=2),
            temp_max_c=35.0,
            temp_min_c=31.0,
        ),
    ]
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=_json_forecast(days))
    )

    response = await api_client.get(
        "/v1/activities/outdoor_event/best-day",
        params={
            "city": "Madrid",
            "start": DEFAULT_DAY.isoformat(),
            "end": (DEFAULT_DAY + timedelta(days=2)).isoformat(),
            "top": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["activity"] == "outdoor_event"
    assert body["range"] == {
        "start": DEFAULT_DAY.isoformat(),
        "end": (DEFAULT_DAY + timedelta(days=2)).isoformat(),
    }
    assert [day["date"] for day in body["ranking"]] == [
        DEFAULT_DAY.isoformat(),
        (DEFAULT_DAY + timedelta(days=1)).isoformat(),
    ]
    assert body["has_acceptable_day"] is True
    assert any("diario" in caveat for caveat in body["caveats"])


async def test_best_day_all_vetoed(api_client, api_mock):
    days = make_forecast_range(count=3, probability=80)
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=_json_forecast(days))
    )

    response = await api_client.get(
        "/v1/activities/outdoor_event/best-day",
        params={
            "city": "Madrid",
            "start": DEFAULT_DAY.isoformat(),
            "end": (DEFAULT_DAY + timedelta(days=2)).isoformat(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_acceptable_day"] is False
    assert all(day["score"] == 0 for day in body["ranking"])
    assert all(day["verdict"] == "not_recommended" for day in body["ranking"])


async def test_best_day_clips_range_to_horizon(api_client, api_mock):
    forecast = make_forecast(make_forecast_range(count=15))
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    last_day = DEFAULT_DAY + timedelta(days=14)

    response = await api_client.get(
        "/v1/activities/outdoor_event/best-day",
        params={
            "city": "Madrid",
            "start": (DEFAULT_DAY - timedelta(days=2)).isoformat(),
            "end": (last_day + timedelta(days=2)).isoformat(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["range"] == {
        "start": DEFAULT_DAY.isoformat(),
        "end": last_day.isoformat(),
    }
    assert any("recortó" in caveat for caveat in body["caveats"])


async def test_best_day_without_forecast_days_returns_422(
    api_client,
    api_mock,
):
    forecast = make_forecast(make_forecast_range(count=15))
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    last_day = DEFAULT_DAY + timedelta(days=14)

    response = await api_client.get(
        "/v1/activities/outdoor_event/best-day",
        params={
            "city": "Madrid",
            "start": (last_day + timedelta(days=1)).isoformat(),
            "end": (last_day + timedelta(days=3)).isoformat(),
        },
    )

    assert response.status_code == 422
    assert "No hay días" in response.json()["detail"]


async def test_best_day_reversed_range_returns_422_without_calls(
    api_client,
    api_mock,
):
    response = await api_client.get(
        "/v1/activities/outdoor_event/best-day",
        params={
            "city": "Madrid",
            "start": (DEFAULT_DAY + timedelta(days=2)).isoformat(),
            "end": DEFAULT_DAY.isoformat(),
        },
    )

    assert response.status_code == 422
    assert len(api_mock.calls) == 0


@pytest.mark.parametrize("top", [0, 16])
async def test_best_day_top_out_of_range_returns_422(api_client, api_mock, top):
    response = await api_client.get(
        "/v1/activities/outdoor_event/best-day",
        params={
            "city": "Madrid",
            "start": DEFAULT_DAY.isoformat(),
            "end": (DEFAULT_DAY + timedelta(days=2)).isoformat(),
            "top": top,
        },
    )

    assert response.status_code == 422
    assert len(api_mock.calls) == 0


async def test_unknown_activity_returns_422(api_client, api_mock):
    response = await api_client.get(
        "/v1/activities/sunscreen/evaluate",
        params={"city": "Madrid", "date": DEFAULT_DAY.isoformat()},
    )

    assert response.status_code == 422
    assert len(api_mock.calls) == 0


async def test_activity_requires_location(api_client, api_mock):
    response = await api_client.get(
        "/v1/activities/outdoor_event/evaluate",
        params={"date": DEFAULT_DAY.isoformat()},
    )

    assert response.status_code == 422
    assert len(api_mock.calls) == 0


async def test_activity_requires_date(api_client, api_mock):
    response = await api_client.get(
        "/v1/activities/outdoor_event/evaluate",
        params={"city": "Madrid"},
    )

    assert response.status_code == 422
    assert len(api_mock.calls) == 0


async def test_best_day_requires_start_and_end(api_client, api_mock):
    response = await api_client.get(
        "/v1/activities/outdoor_event/best-day",
        params={"city": "Madrid"},
    )

    assert response.status_code == 422
    assert len(api_mock.calls) == 0


async def test_best_day_uses_default_top_of_three(api_client, api_mock):
    forecast = make_forecast(make_forecast_range(count=15))
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )

    response = await api_client.get(
        "/v1/activities/outdoor_event/best-day",
        params={
            "city": "Madrid",
            "start": DEFAULT_DAY.isoformat(),
            "end": (DEFAULT_DAY + timedelta(days=5)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert len(response.json()["ranking"]) == 3


@pytest.mark.parametrize(
    ("upstream_status", "expected_status"),
    [
        (404, 404),
        (429, 429),
        (502, 502),
        (504, 504),
    ],
)
async def test_activity_upstream_errors_are_mapped(
    api_client,
    api_mock,
    upstream_status,
    expected_status,
):
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(
            upstream_status,
            json={"detail": "error del proveedor"},
        )
    )

    response = await api_client.get(
        "/v1/activities/outdoor_event/evaluate",
        params={"city": "Madrid", "date": DEFAULT_DAY.isoformat()},
    )

    assert response.status_code == expected_status
