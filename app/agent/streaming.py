"""Loop de tool calling con streaming de texto y eventos intermedios."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.agent.llm import (
    LLMClient,
    LLMError,
    StreamCompleted,
    TextDelta,
)
from app.agent.messages import assistant_message, tool_result_message
from app.agent.prompts import build_system_prompt
from app.agent.tools import TOOL_DEFINITIONS, execute_tool
from app.clients.weather_api import WeatherApi

EMPTY_ANSWER = "No pude generar una respuesta con los datos disponibles."


@dataclass(frozen=True, slots=True)
class TokenEvent:
    """Fragmento de texto para mostrar en el navegador."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolCallStarted:
    """El LLM pidió una herramienta y todavía no terminó de ejecutarse."""

    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class ToolCallFinished:
    """La herramienta terminó, con éxito o con error."""

    call_id: str
    name: str
    arguments: str
    result: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AgentDone:
    """Texto final que se debe persistir y mostrar como cierre."""

    text: str


AgentEvent = TokenEvent | ToolCallStarted | ToolCallFinished | AgentDone


async def stream_agent(
    question: str,
    weather_client: WeatherApi,
    llm: LLMClient,
    *,
    history: list[dict[str, str]] | None = None,
    location_label: str | None = None,
    max_tool_calls: int = 4,
    now: datetime | None = None,
) -> AsyncIterator[AgentEvent]:
    """Resuelve una pregunta emitiendo texto y eventos de herramientas."""
    if max_tool_calls < 1:
        raise ValueError("max_tool_calls debe ser al menos 1")

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": build_system_prompt(
                now=now,
                max_tool_calls=max_tool_calls,
                location_label=location_label,
            ),
        }
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    tool_calls_used = 0

    while True:
        content_parts: list[str] = []
        completed = None

        async for event in llm.stream(messages, TOOL_DEFINITIONS):
            if isinstance(event, TextDelta):
                content_parts.append(event.text)
                yield TokenEvent(event.text)
            elif isinstance(event, StreamCompleted):
                completed = event.response

        if completed is None:
            raise LLMError("el proveedor del LLM no completó el stream")

        content = completed.content or "".join(content_parts)
        if not content_parts and content:
            content_parts.append(content)
            yield TokenEvent(content)

        if not completed.tool_calls:
            text = (content or "").strip()
            if not text:
                text = EMPTY_ANSWER
                yield TokenEvent(text)
            yield AgentDone(text)
            return

        if tool_calls_used + len(completed.tool_calls) > max_tool_calls:
            text = (
                "No pude completar la consulta porque se alcanzó el máximo de "
                f"{max_tool_calls} llamadas a herramientas."
            )
            yield TokenEvent(text)
            yield AgentDone(text)
            return

        messages.append(assistant_message(completed.content, completed.tool_calls))

        for call in completed.tool_calls:
            yield ToolCallStarted(call.id, call.name, call.arguments)
            result = await execute_tool(call.name, call.arguments, weather_client)
            yield ToolCallFinished(call.id, call.name, call.arguments, result)
            messages.append(tool_result_message(call.id, result))
            tool_calls_used += 1
