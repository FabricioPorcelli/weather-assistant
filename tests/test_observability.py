"""Tests del middleware de logging JSON."""

import json
import logging


async def test_health_adds_request_id_and_logs_json(api_client, caplog):
    caplog.set_level(logging.INFO, logger="app.request")

    response = await api_client.get("/v1/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]

    records = [record for record in caplog.records if record.name == "app.request"]
    assert records
    payload = json.loads(records[-1].message)
    assert payload["event"] == "request"
    assert payload["method"] == "GET"
    assert payload["path"] == "/v1/health"
    assert payload["status"] == 200
    assert payload["duration_ms"] >= 0
    assert "message" not in payload
    assert "query" not in payload
