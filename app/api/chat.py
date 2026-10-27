"""Endpoint de chat con streaming SSE."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import LLMClientDep, WeatherClientDep
from app.chat.service import (
    ChatRequest,
    ChatSessionNotFound,
    prepare_chat,
    stream_chat,
)
from app.config import get_settings
from app.limiter import RATE_LIMIT, limiter

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat")
@limiter.limit(RATE_LIMIT)
async def chat(
    request: Request,
    payload: ChatRequest,
    weather_client: WeatherClientDep,
    llm: LLMClientDep,
) -> StreamingResponse:
    """Abre un stream SSE con la respuesta del asistente."""
    settings = get_settings()
    if len(payload.message) > settings.max_message_chars:
        raise HTTPException(
            status_code=422,
            detail=(
                "El mensaje supera el máximo de "
                f"{settings.max_message_chars} caracteres"
            ),
        )

    try:
        context = await prepare_chat(payload, settings)
    except ChatSessionNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail="La sesión indicada no existe",
        ) from exc

    return StreamingResponse(
        stream_chat(context, weather_client, llm, settings),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
