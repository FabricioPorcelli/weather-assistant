"""Tests del loop de agente con streaming."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.agent.llm import LLMError, LLMResponse, ToolCall
from app.agent.streaming import (
    AgentDone,
    TokenEvent,
    ToolCallFinished,
    ToolCallStarted,
    stream_agent,
)
from tests.fakes import FailingLLMClient, FakeLLMClient, FakeWeatherApi
from tests.helpers import DEFAULT_DAY, make_day, make_forecast

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=timezone(timedelta(hours=-3)))


def _tool_call(index: int, name: str, arguments: dict) -> ToolCall:
    return ToolCall(
        id=f"call_{index}",
        name=name,
        arguments=json.dumps(arguments, ensure_ascii=False),
    )


async def _collect(question, weather, llm, **kwargs):
    return [
        event
        async for event in stream_agent(
            question,
            weather,
            llm,
            now=NOW,
            **kwargs,
        )
    ]


async def test_streaming_tool_call_then_final_answer():
    forecast = make_forecast([make_day(probability=70, precipitation_mm=2.0)])
    fake_weather = FakeWeatherApi(forecasts={"Madrid": forecast})
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

    events = await _collect("¿Llevo paraguas en Madrid?", fake_weather, fake_llm)

    assert any(isinstance(event, ToolCallStarted) for event in events)
    finished = next(event for event in events if isinstance(event, ToolCallFinished))
    assert finished.name == "get_umbrella_advice"
    assert finished.result["verdict"] == "yes"

    tokens = "".join(event.text for event in events if isinstance(event, TokenEvent))
    assert tokens == "Sí, llevá paraguas."
    done = events[-1]
    assert isinstance(done, AgentDone)
    assert done.text == "Sí, llevá paraguas."


async def test_streaming_includes_history_and_location_in_messages():
    fake_llm = FakeLLMClient([LLMResponse(content="Hola")])
    history = [
        {"role": "user", "content": "Mensaje anterior"},
        {"role": "assistant", "content": "Respuesta anterior"},
    ]

    await _collect(
        "¿Y mañana?",
        FakeWeatherApi(),
        fake_llm,
        history=history,
        location_label="Rosario",
    )

    messages = fake_llm.calls[0]["messages"]
    assert "Ubicación del contexto: Rosario" in messages[0]["content"]
    assert messages[1:3] == history
    assert messages[-1] == {"role": "user", "content": "¿Y mañana?"}


async def test_streaming_tool_error_continues():
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
            LLMResponse(content="No pude consultar eso."),
        ]
    )

    events = await _collect("¿Cómo está la luna?", FakeWeatherApi(), fake_llm)

    finished = next(event for event in events if isinstance(event, ToolCallFinished))
    assert "desconocida" in finished.result["error"]
    assert events[-1] == AgentDone(text="No pude consultar eso.")


async def test_streaming_respects_tool_limit():
    calls = [
        _tool_call(
            index,
            "get_current_weather",
            {"location": {"city": "Madrid"}},
        )
        for index in range(5)
    ]
    fake_weather = FakeWeatherApi()
    fake_llm = FakeLLMClient([LLMResponse(tool_calls=calls)])

    events = await _collect("Consultá cinco cosas", fake_weather, fake_llm)

    assert fake_weather.calls == []
    tokens = "".join(event.text for event in events if isinstance(event, TokenEvent))
    assert "máximo de 4" in tokens
    assert isinstance(events[-1], AgentDone)


async def test_streaming_supports_two_locations():
    forecasts = {
        city: make_forecast(
            [make_day(day=DEFAULT_DAY + timedelta(days=index)) for index in range(3)],
            location=f"{city}, Argentina",
        )
        for city in ("Buenos Aires", "Pinamar")
    }
    fake_weather = FakeWeatherApi(forecasts=forecasts)
    fake_llm = FakeLLMClient(
        [
            LLMResponse(
                tool_calls=[
                    _tool_call(
                        1,
                        "find_best_day",
                        {
                            "location": {"city": "Buenos Aires"},
                            "activity": "outdoor_event",
                            "start_date": DEFAULT_DAY.isoformat(),
                            "end_date": (DEFAULT_DAY + timedelta(days=2)).isoformat(),
                            "top_n": 2,
                        },
                    ),
                    _tool_call(
                        2,
                        "find_best_day",
                        {
                            "location": {"city": "Pinamar"},
                            "activity": "outdoor_event",
                            "start_date": DEFAULT_DAY.isoformat(),
                            "end_date": (DEFAULT_DAY + timedelta(days=2)).isoformat(),
                            "top_n": 2,
                        },
                    ),
                ]
            ),
            LLMResponse(content="Conviene Pinamar."),
        ]
    )

    events = await _collect(
        "¿Dónde conviene ir el finde?",
        fake_weather,
        fake_llm,
    )

    finished = [event for event in events if isinstance(event, ToolCallFinished)]
    assert len(finished) == 2
    assert events[-1] == AgentDone(text="Conviene Pinamar.")


async def test_streaming_llm_error_propagates():
    with pytest.raises(LLMError):
        await _collect("Hola", FakeWeatherApi(), FailingLLMClient())


async def test_streaming_invalid_tool_limit_is_rejected():
    with pytest.raises(ValueError):
        await _collect(
            "Hola",
            FakeWeatherApi(),
            FakeLLMClient([]),
            max_tool_calls=0,
        )
