"""Preparación y transmisión de un turno de chat."""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.agent.llm import LLMClient, LLMError
from app.agent.streaming import (
    AgentDone,
    TokenEvent,
    ToolCallFinished,
    ToolCallStarted,
    stream_agent,
)
from app.clients.weather_api import Location, WeatherApi
from app.config import Settings
from app.db.repositories import (
    add_message,
    add_tool_call,
    create_session,
    get_recent_messages,
    get_session,
)
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


class ChatSessionNotFound(Exception):
    """El session_id enviado no existe."""


class ChatRequest(BaseModel):
    """Body de POST /v1/chat."""

    session_id: UUID | None = None
    message: str = Field(min_length=1)
    location: Location | None = None

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        """Rechaza mensajes que son solo espacios."""
        value = value.strip()
        if not value:
            raise ValueError("el mensaje no puede estar vacío")
        return value


@dataclass(frozen=True, slots=True)
class ChatContext:
    """Datos necesarios para transmitir un turno."""

    session_id: UUID
    history: list[dict[str, str]]
    message: str
    location_label: str | None


def _location_label(location: Location | None) -> str | None:
    """Convierte una ubicación en texto para el prompt y la sesión."""
    if location is None:
        return None
    if location.label:
        return location.label
    if location.city:
        return location.city
    if location.lat is not None and location.lon is not None:
        return f"{location.lat:.2f}, {location.lon:.2f}"
    return None


async def prepare_chat(
    payload: ChatRequest,
    settings: Settings,
) -> ChatContext:
    """Crea o recupera la sesión y guarda el mensaje del usuario."""
    location_label = _location_label(payload.location)

    async with async_session_factory() as db:
        if payload.session_id is not None:
            session = await get_session(db, payload.session_id)
            if session is None:
                raise ChatSessionNotFound(str(payload.session_id))
        else:
            session = await create_session(db, location_label=location_label)

        previous_messages = await get_recent_messages(
            db,
            session_id=session.id,
            turns=settings.history_turns,
        )
        history = [
            {"role": message.role, "content": message.content}
            for message in previous_messages
        ]

        if location_label:
            session.location_label = location_label

        await add_message(
            db,
            session_id=session.id,
            role="user",
            content=payload.message,
        )
        await db.commit()

        return ChatContext(
            session_id=session.id,
            history=history,
            message=payload.message,
            location_label=location_label or session.location_label,
        )


def _sse(event: str, data: dict[str, Any]) -> bytes:
    """Formatea un evento SSE."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode()


def _parse_arguments(arguments: str) -> dict[str, Any]:
    """Convierte los argumentos JSON en dict; si fallan, conserva el texto."""
    try:
        parsed = json.loads(arguments)
    except ValueError:
        return {"raw": arguments}
    return parsed if isinstance(parsed, dict) else {"raw": arguments}


def _advice_event(event: ToolCallFinished) -> dict[str, Any] | None:
    """Convierte resultados del motor en payloads para la tarjeta del front."""
    if "error" in event.result:
        return None

    if event.name in {
        "get_umbrella_advice",
        "get_clothing_advice",
        "get_watering_advice",
    }:
        return event.result

    if event.name == "get_activity_advice":
        payload = dict(event.result)
        payload["kind"] = "activity"
        activity = _parse_arguments(event.arguments).get("activity")
        if activity:
            payload["activity"] = activity
        return payload

    if event.name == "find_best_day":
        payload = dict(event.result)
        payload["kind"] = "best_day"
        return payload

    return None


async def _save_tool_call(context: ChatContext, event: ToolCallFinished) -> None:
    """Guarda la auditoría de una herramienta en su propia transacción."""
    async with async_session_factory() as db:
        await add_tool_call(
            db,
            session_id=context.session_id,
            provider_call_id=event.call_id,
            name=event.name,
            arguments=_parse_arguments(event.arguments),
            result=event.result,
        )
        await db.commit()


async def _save_assistant_message(context: ChatContext, text: str) -> None:
    """Guarda la respuesta final del asistente."""
    async with async_session_factory() as db:
        await add_message(
            db,
            session_id=context.session_id,
            role="assistant",
            content=text,
        )
        await db.commit()


async def stream_chat(
    context: ChatContext,
    weather_client: WeatherApi,
    llm: LLMClient,
    settings: Settings,
) -> AsyncIterator[bytes]:
    """Genera los eventos SSE de un turno completo."""
    yield _sse("session", {"session_id": str(context.session_id)})

    try:
        async for event in stream_agent(
            context.message,
            weather_client,
            llm,
            history=context.history,
            location_label=context.location_label,
            max_tool_calls=settings.max_tool_calls_per_turn,
        ):
            if isinstance(event, TokenEvent):
                yield _sse("token", {"text": event.text})
            elif isinstance(event, ToolCallStarted):
                yield _sse(
                    "tool_call",
                    {"id": event.call_id, "name": event.name},
                )
            elif isinstance(event, ToolCallFinished):
                await _save_tool_call(context, event)
                advice = _advice_event(event)
                if advice is not None:
                    yield _sse("advice", advice)
            elif isinstance(event, AgentDone):
                await _save_assistant_message(context, event.text)
                yield _sse("done", {"session_id": str(context.session_id)})
                return

        yield _sse("error", {"detail": "El agente no completó la respuesta."})
    except LLMError:
        yield _sse(
            "error",
            {"detail": "No pude completar la consulta con el proveedor del LLM."},
        )
    except Exception:
        logger.exception("Error inesperado durante el stream del chat")
        yield _sse(
            "error",
            {"detail": "Ocurrió un error inesperado al procesar el mensaje."},
        )
