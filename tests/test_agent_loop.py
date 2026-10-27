"""Tests del loop de tool calling."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.agent.llm import LLMError, LLMResponse, ToolCall
from app.agent.loop import EMPTY_ANSWER, run_agent
from tests.fakes import FailingLLMClient, FakeLLMClient, FakeWeatherApi
from tests.helpers import (
    DEFAULT_DAY,
    make_day,
    make_forecast,
    make_forecast_range,
)

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=timezone(timedelta(hours=-3)))


def _tool_call(
    index: int,
    name: str,
    arguments: dict,
) -> ToolCall:
    return ToolCall(
        id=f"call_{index}",
        name=name,
        arguments=json.dumps(arguments, ensure_ascii=False),
    )


def _best_day_arguments(city: str) -> dict:
    return {
        "location": {"city": city},
        "activity": "outdoor_event",
        "start_date": DEFAULT_DAY.isoformat(),
        "end_date": (DEFAULT_DAY + timedelta(days=2)).isoformat(),
        "top_n": 2,
    }


async def test_tool_call_then_final_answer():
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

    answer = await run_agent(
        "¿Llevo paraguas en Madrid?",
        fake_weather,
        fake_llm,
        now=NOW,
    )

    assert answer == "Sí, llevá paraguas."
    assert len(fake_llm.calls) == 2
    tool_messages = [
        message
        for message in fake_llm.calls[1]["messages"]
        if message["role"] == "tool"
    ]
    assert len(tool_messages) == 1
    assert "umbrella" in tool_messages[0]["content"]
    assert len(fake_llm.calls[1]["tools"]) == 7


async def test_final_answer_without_tools():
    fake_llm = FakeLLMClient([LLMResponse(content="Hola")])

    answer = await run_agent(
        "Hola",
        FakeWeatherApi(),
        fake_llm,
        now=NOW,
    )

    assert answer == "Hola"
    assert len(fake_llm.calls) == 1


async def test_empty_final_answer_has_fallback():
    fake_llm = FakeLLMClient([LLMResponse(content="   ")])

    answer = await run_agent(
        "Hola",
        FakeWeatherApi(),
        fake_llm,
        now=NOW,
    )

    assert answer == EMPTY_ANSWER


async def test_tool_error_is_returned_to_model_and_loop_continues():
    fake_llm = FakeLLMClient(
        [
            LLMResponse(
                tool_calls=[
                    _tool_call(1, "get_moon_phase", {"location": {"city": "Madrid"}})
                ]
            ),
            LLMResponse(content="No pude consultar eso."),
        ]
    )

    answer = await run_agent(
        "¿Cómo está la luna?",
        FakeWeatherApi(),
        fake_llm,
        now=NOW,
    )

    assert answer == "No pude consultar eso."
    tool_message = next(
        message
        for message in fake_llm.calls[1]["messages"]
        if message["role"] == "tool"
    )
    assert "desconocida" in tool_message["content"]


async def test_more_than_four_tool_calls_are_rejected():
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

    answer = await run_agent(
        "Consultá cinco cosas",
        fake_weather,
        fake_llm,
        now=NOW,
    )

    assert "máximo de 4" in answer
    assert fake_weather.calls == []
    assert len(fake_llm.calls) == 1


async def test_four_identical_tool_calls_are_allowed_and_cached():
    calls = [
        _tool_call(
            index,
            "get_current_weather",
            {"location": {"city": "Madrid"}},
        )
        for index in range(4)
    ]
    fake_weather = FakeWeatherApi()
    fake_llm = FakeLLMClient(
        [
            LLMResponse(tool_calls=calls),
            LLMResponse(content="Listo."),
        ]
    )

    answer = await run_agent(
        "Consultá el clima cuatro veces",
        fake_weather,
        fake_llm,
        now=NOW,
    )

    assert answer == "Listo."
    assert len(fake_weather.calls) == 1
    tool_messages = [
        message
        for message in fake_llm.calls[1]["messages"]
        if message["role"] == "tool"
    ]
    assert len(tool_messages) == 4


async def test_multi_tool_comparison_of_two_locations():
    forecasts = {
        city: make_forecast(
            make_forecast_range(),
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
                        _best_day_arguments("Buenos Aires"),
                    ),
                    _tool_call(
                        2,
                        "find_best_day",
                        _best_day_arguments("Pinamar"),
                    ),
                ]
            ),
            LLMResponse(content="Conviene Pinamar."),
        ]
    )

    answer = await run_agent(
        "¿Dónde conviene ir el finde, Buenos Aires o Pinamar?",
        fake_weather,
        fake_llm,
        now=NOW,
    )

    assert answer == "Conviene Pinamar."
    forecast_calls = [call for call in fake_weather.calls if call[0] == "forecast"]
    assert {call[1] for call in forecast_calls} == {"Buenos Aires", "Pinamar"}
    tool_messages = [
        message
        for message in fake_llm.calls[1]["messages"]
        if message["role"] == "tool"
    ]
    assert len(tool_messages) == 2


async def test_llm_error_propagates():
    with pytest.raises(LLMError):
        await run_agent(
            "Hola",
            FakeWeatherApi(),
            FailingLLMClient(),
            now=NOW,
        )


async def test_invalid_tool_limit_is_rejected():
    with pytest.raises(ValueError):
        await run_agent(
            "Hola",
            FakeWeatherApi(),
            FakeLLMClient([]),
            max_tool_calls=0,
            now=NOW,
        )
