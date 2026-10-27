"""Engine y fábrica de sesiones async de SQLAlchemy."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import get_settings

settings = get_settings()

_engine_options: dict = {}
if settings.database_url.startswith("sqlite"):
    _engine_options["connect_args"] = {"check_same_thread": False}
    if ":memory:" in settings.database_url:
        _engine_options["poolclass"] = StaticPool
else:
    _engine_options["pool_pre_ping"] = True

engine = create_async_engine(settings.database_url, **_engine_options)
async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Dependencia de FastAPI que entrega una sesión por pedido."""
    async with async_session_factory() as session:
        yield session


async def dispose_engine() -> None:
    """Cierra el pool de conexiones al apagar la aplicación."""
    await engine.dispose()
