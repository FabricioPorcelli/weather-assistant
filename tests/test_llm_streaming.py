"""Tests del streaming SSE del cliente LLM."""

import json

import httpx
import pytest
import respx

from app.agent.llm import (
    LLMError,
    OpenAICompatClient,
    StreamCompleted,
    TextDelta,
)

BASE_URL = "https://llm.test/v1"
MESSAGES = [{"role": "user", "content": "Hola"}]
TOOLS = [{"type": "function", "function": {"name": "test", "parameters": {}}}]


def _sse(*events: dict | str) -> str:
    lines = []
    for event in events:
        data = event if isinstance(event, str) else json.dumps(event)
        lines.append(f"data: {data}\n\n")
    return "".join(lines)


async def _collect(client: OpenAICompatClient):
    return [event async for event in client.stream(MESSAGES, TOOLS)]


async def test_stream_emits_text_deltas_and_completion():
    body = _sse(
        {"choices": [{"delta": {"content": "Hola"}}]},
        {"choices": [{"delta": {"content": " mundo"}}]},
        "[DONE]",
    )
    with respx.mock(base_url="https://llm.test") as mock:
        route = mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(200, text=body)
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            events = await _collect(client)

    text_events = [event for event in events if isinstance(event, TextDelta)]
    assert [event.text for event in text_events] == ["Hola", " mundo"]
    completed = events[-1]
    assert isinstance(completed, StreamCompleted)
    assert completed.response.content == "Hola mundo"
    assert completed.response.tool_calls == []

    request = route.calls.last.request
    payload = json.loads(request.content)
    assert payload["stream"] is True
    assert payload["model"] == "modelo"


async def test_stream_accumulates_tool_call_deltas():
    body = _sse(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {
                                    "name": "get_forecast",
                                    "arguments": '{"loc',
                                },
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {
                                    "arguments": 'ation":{"city":"Madrid"}}',
                                },
                            }
                        ]
                    }
                }
            ]
        },
        "[DONE]",
    )
    with respx.mock(base_url="https://llm.test") as mock:
        mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(200, text=body)
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            events = await _collect(client)

    completed = events[-1]
    assert isinstance(completed, StreamCompleted)
    assert len(completed.response.tool_calls) == 1
    call = completed.response.tool_calls[0]
    assert call.id == "call_1"
    assert call.name == "get_forecast"
    assert call.arguments == '{"location":{"city":"Madrid"}}'


async def test_stream_http_error_is_mapped():
    with respx.mock(base_url="https://llm.test") as mock:
        mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(500, json={"error": "falló"})
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            with pytest.raises(LLMError):
                await _collect(client)


async def test_stream_invalid_event_is_mapped():
    with respx.mock(base_url="https://llm.test") as mock:
        mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(200, text="data: no-es-json\n\n")
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            with pytest.raises(LLMError):
                await _collect(client)
