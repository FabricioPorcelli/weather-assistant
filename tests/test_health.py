"""Tests del endpoint de salud."""

from app import __version__


async def test_health_returns_ok(api_client):
    response = await api_client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "weather-assistant",
        "version": __version__,
    }
