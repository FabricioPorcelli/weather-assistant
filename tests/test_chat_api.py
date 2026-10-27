"""Tests end-to-end de POST /v1/chat."""

import json
from uuid import UUID, uuid4

import httpx
import pytest

from app.agent.llm import LLMResponse, ToolCall
from app.api.dependencies import get_llm_client
from app.db.repositories import (
    get_recent_messages,
    get_session,
    get_tool_calls,
)
from app.db.session import async_session_factory
from app.main import app
from tests.fakes import FailingLLMClient, FakeLLMClient
from tests.helpers import make_day, make_forecast


def _tool_call(index: int, name: str, arguments: dict) -> ToolCall:
    return ToolCall(
        id=f"call_{index}",
        name=name,
        arguments=json.dumps(arguments, ensure_ascii=False),
    )


async def _read_sse(response: httpx.Response):
    events = []
    current_event = None
    data_lines = []

    async for line in response.aiter_lines():
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            data_lines.append(line[6:])
        elif line == "" and current_event is not None:
            events.append((current_event, json.loads("\n".join(data_lines))))
            current_event = None
            data_lines = []

    return events


async def _chat(client: httpx.AsyncClient, payload: dict):
    async with client.stream("POST", "/v1/chat", json=payload) as response:
        assert response.status_code == 200
        return await _read_sse(response)


@pytest.fixture
def override_llm():
    def _override(client):
        app.dependency_overrides[get_llm_client] = lambda: client

    yield _override
    app.dependency_overrides.pop(get_llm_client, None)


async def test_chat_streams_events_and_persists(
    db_schema,
    api_client,
    api_mock,
    override_llm,
):
    forecast = make_forecast([make_day(probability=70, precipitation_mm=2.0)])
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    fake_llm = FakeLLMClient(
        [
            LLMResponse(
                tool_calls=[
                    _tool_call(
                        1,
                        "get_umbrella_advice",
                        {"location": {"city": "Madrid"}},
                    )
                ]
            ),
            LLMResponse(content="Sí, llevá paraguas."),
        ]
    )
    override_llm(fake_llm)

    events = await _chat(
        api_client,
        {
            "message": "¿Llevo paraguas en Madrid?",
            "location": {"city": "Madrid"},
        },
    )

    names = [name for name, _ in events]
    assert names[0] == "session"
    assert "tool_call" in names
    assert "advice" in names
    assert "token" in names
    assert names[-1] == "done"

    session_id = UUID(events[0][1]["session_id"])
    advice = next(data for name, data in events if name == "advice")
    assert advice["kind"] == "umbrella"
    assert advice["verdict"] == "yes"

    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == "Sí, llevá paraguas."

    async with async_session_factory() as db:
        session = await get_session(db, session_id)
        messages = await get_recent_messages(
            db,
            session_id=session_id,
            turns=10,
        )
        tool_calls = await get_tool_calls(db, session_id=session_id)

    assert session is not None
    assert [message.role for message in messages] == ["user", "assistant"]
    assert [message.content for message in messages] == [
        "¿Llevo paraguas en Madrid?",
        "Sí, llevá paraguas.",
    ]
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "get_umbrella_advice"
    assert tool_calls[0].provider_call_id == "call_1"


async def test_chat_passes_location_context_and_persists_label(
    db_schema,
    api_client,
    override_llm,
):
    fake_llm = FakeLLMClient([LLMResponse(content="Hola")])
    override_llm(fake_llm)

    events = await _chat(
        api_client,
        {
            "message": "¿Qué clima hace?",
            "location": {"city": "Rosario", "label": "Rosario"},
        },
    )

    prompt = fake_llm.calls[0]["messages"][0]["content"]
    assert "Ubicación del contexto: Rosario" in prompt

    session_id = UUID(events[0][1]["session_id"])
    async with async_session_factory() as db:
        session = await get_session(db, session_id)

    assert session is not None
    assert session.location_label == "Rosario"


async def test_second_turn_receives_previous_history(
    db_schema,
    api_client,
    override_llm,
):
    fake_llm = FakeLLMClient(
        [
            LLMResponse(content="Respuesta uno."),
            LLMResponse(content="Respuesta dos."),
        ]
    )
    override_llm(fake_llm)

    first_events = await _chat(api_client, {"message": "Primera pregunta"})
    session_id = first_events[0][1]["session_id"]

    second_events = await _chat(
        api_client,
        {
            "session_id": session_id,
            "message": "Segunda pregunta",
        },
    )

    assert second_events[0][1]["session_id"] == session_id
    assert second_events[-1][0] == "done"
    second_messages = fake_llm.calls[1]["messages"]
    assert {"role": "user", "content": "Primera pregunta"} in second_messages
    assert {"role": "assistant", "content": "Respuesta uno."} in second_messages
    assert second_messages[-1] == {
        "role": "user",
        "content": "Segunda pregunta",
    }


async def test_unknown_session_returns_404(db_schema, api_client, override_llm):
    override_llm(FakeLLMClient([]))

    response = await api_client.post(
        "/v1/chat",
        json={
            "session_id": str(uuid4()),
            "message": "Hola",
        },
    )

    assert response.status_code == 404


async def test_too_long_message_returns_422(
    db_schema,
    api_client,
    override_llm,
):
    override_llm(FakeLLMClient([]))

    response = await api_client.post(
        "/v1/chat",
        json={"message": "x" * 501},
    )

    assert response.status_code == 422


async def test_blank_message_returns_422(db_schema, api_client, override_llm):
    override_llm(FakeLLMClient([]))

    response = await api_client.post(
        "/v1/chat",
        json={"message": "   "},
    )

    assert response.status_code == 422


async def test_llm_error_becomes_sse_error_event(
    db_schema,
    api_client,
    override_llm,
):
    override_llm(FailingLLMClient())

    events = await _chat(api_client, {"message": "Hola"})

    assert events[-1][0] == "error"
    assert "LLM" in events[-1][1]["detail"]


async def test_tool_error_is_persisted_and_model_can_explain(
    db_schema,
    api_client,
    override_llm,
):
    fake_llm = FakeLLMClient(
        [
            LLMResponse(
                tool_calls=[
                    _tool_call(
                        1,
                        "get_moon_phase",
                        {"location": {"city": "Madrid"}},
                    )
                ]
            ),
            LLMResponse(content="No puedo consultar la luna."),
        ]
    )
    override_llm(fake_llm)

    events = await _chat(api_client, {"message": "¿Cómo está la luna?"})

    assert [name for name, _ in events][-1] == "done"
    assert not any(name == "advice" for name, _ in events)
    session_id = UUID(events[0][1]["session_id"])

    async with async_session_factory() as db:
        tool_calls = await get_tool_calls(db, session_id=session_id)

    assert len(tool_calls) == 1
    assert "error" in tool_calls[0].result
