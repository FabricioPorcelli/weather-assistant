"""Tests del cliente HTTP compatible con OpenAI."""

import json

import httpx
import pytest
import respx

from app.agent.llm import LLMError, OpenAICompatClient

BASE_URL = "https://llm.test/v1"
ENDPOINT = "https://llm.test/v1/chat/completions"
MESSAGES = [{"role": "user", "content": "Hola"}]
TOOLS = [{"type": "function", "function": {"name": "test", "parameters": {}}}]


async def test_complete_sends_model_messages_and_tools():
    with respx.mock(base_url="https://llm.test") as mock:
        route = mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Hola"}}]},
            )
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            response = await client.complete(MESSAGES, TOOLS)

    assert response.content == "Hola"
    assert response.tool_calls == []
    request = route.calls.last.request
    body = json.loads(request.content)
    assert body["model"] == "modelo"
    assert body["messages"] == MESSAGES
    assert body["tools"] == TOOLS
    assert body["tool_choice"] == "auto"
    assert request.headers["Authorization"] == "Bearer clave"


async def test_complete_omits_authorization_without_key():
    with respx.mock(base_url="https://llm.test") as mock:
        route = mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Hola"}}]},
            )
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="",
            model="modelo",
        ) as client:
            await client.complete(MESSAGES, TOOLS)

    assert "Authorization" not in route.calls.last.request.headers


async def test_complete_parses_token_usage():
    payload = {
        "choices": [{"message": {"content": "Hola"}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }
    with respx.mock(base_url="https://llm.test") as mock:
        mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            response = await client.complete(MESSAGES, TOOLS)

    assert response.usage is not None
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 5
    assert response.usage.total_tokens == 15


async def test_complete_parses_tool_calls():
    payload = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_forecast",
                                "arguments": '{"days": 5}',
                            },
                        }
                    ],
                }
            }
        ]
    }
    with respx.mock(base_url="https://llm.test") as mock:
        mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            response = await client.complete(MESSAGES, TOOLS)

    assert response.content is None
    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call.id == "call_1"
    assert call.name == "get_forecast"
    assert call.arguments == '{"days": 5}'


@pytest.mark.parametrize("status_code", [401, 403, 500])
async def test_http_errors_are_mapped(status_code):
    with respx.mock(base_url="https://llm.test") as mock:
        mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(status_code, json={"error": "falló"})
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            with pytest.raises(LLMError):
                await client.complete(MESSAGES, TOOLS)


async def test_timeout_is_mapped():
    with respx.mock(base_url="https://llm.test") as mock:
        mock.post("/v1/chat/completions").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            with pytest.raises(LLMError):
                await client.complete(MESSAGES, TOOLS)


async def test_connection_error_is_mapped():
    with respx.mock(base_url="https://llm.test") as mock:
        mock.post("/v1/chat/completions").mock(
            side_effect=httpx.ConnectError("sin conexión")
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            with pytest.raises(LLMError):
                await client.complete(MESSAGES, TOOLS)


async def test_invalid_json_is_mapped():
    with respx.mock(base_url="https://llm.test") as mock:
        mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(200, text="no es JSON")
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            with pytest.raises(LLMError):
                await client.complete(MESSAGES, TOOLS)


async def test_missing_choices_is_mapped():
    with respx.mock(base_url="https://llm.test") as mock:
        mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={})
        )
        async with OpenAICompatClient(
            BASE_URL,
            api_key="clave",
            model="modelo",
        ) as client:
            with pytest.raises(LLMError):
                await client.complete(MESSAGES, TOOLS)


@pytest.mark.parametrize(
    ("base_url", "model", "timeout"),
    [
        ("llm.test/v1", "modelo", 30),
        (BASE_URL, "", 30),
        (BASE_URL, "modelo", 0),
    ],
)
def test_invalid_client_configuration(base_url, model, timeout):
    with pytest.raises(ValueError):
        OpenAICompatClient(
            base_url,
            api_key="clave",
            model=model,
            timeout=timeout,
        )
