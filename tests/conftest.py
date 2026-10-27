"""Fixtures compartidas por los tests.

Los tests no tocan la red: respx intercepta las llamadas de httpx. El cliente
de pruebas apunta a un host ficticio que solo existe dentro del mock.
"""

import os

import httpx
import pytest
import respx

os.environ["WEATHER_API_BASE_URL"] = "http://weather-api"

from app.clients.weather_api import WeatherApiClient  # noqa: E402
from app.main import app  # noqa: E402

BASE_URL = "http://weather-api"


@pytest.fixture
def api_mock():
    """Intercepta las llamadas httpx hacia el host ficticio de weather-api."""
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
async def api_client():
    """Cliente HTTP que ejecuta la app en el mismo proceso, sin abrir puertos.

    El lifespan se ejecuta igual que en un servidor real: abre el cliente de
    weather-api al arrancar y lo cierra al terminar el test.
    """
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


@pytest.fixture
async def weather_client():
    """Cliente de weather-api con limpieza automática de conexiones."""
    client = WeatherApiClient(BASE_URL)
    yield client
    await client.aclose()
