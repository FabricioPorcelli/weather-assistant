"""Fixtures compartidas por los tests.

Los tests no tocan la red: respx intercepta las llamadas de httpx. El cliente
de pruebas apunta a un host ficticio que solo existe dentro del mock.
"""

import os
import tempfile

import httpx
import pytest
import respx

os.environ["WEATHER_API_BASE_URL"] = "http://weather-api"
os.environ["WEATHER_API_RETRIES"] = "0"
os.environ["WEATHER_API_RETRY_DELAY_SECONDS"] = "0"
os.environ["DATABASE_URL"] = (
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/weather-assistant-test-"
    f"{os.getpid()}.db"
)
os.environ["REDIS_URL"] = "redis://localhost:6379/1"

from app.clients.weather_api import WeatherApiClient  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.main import app  # noqa: E402

BASE_URL = "http://weather-api"


@pytest.fixture(autouse=True)
def _disable_rate_limit():
    """Evita que el rate limit haga fallar tests por tiempos compartidos."""
    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture
async def db_schema():
    """Crea y borra las tablas SQLite para un test de persistencia."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


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
    client = WeatherApiClient(BASE_URL, retries=0)
    yield client
    await client.aclose()
