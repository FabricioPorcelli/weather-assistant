"""Endpoint de salud del servicio.

Es un chequeo de vida: responde si el proceso está escuchando. No consulta a
weather-api para no gastar rate limit ni acoplar el arranque a otro servicio.
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter(prefix="/v1", tags=["health"])


class HealthResponse(BaseModel):
    """Respuesta del chequeo de salud."""

    status: Literal["ok"] = "ok"
    service: str = "weather-assistant"
    version: str = __version__


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Devuelve el estado básico del asistente."""
    return HealthResponse()
