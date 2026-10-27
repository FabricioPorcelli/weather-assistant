"""Loop de tool calling implementado a mano.

El objetivo es que el flujo sea visible: el LLM pide herramientas, nosotros
validamos y ejecutamos, devolvemos los resultados y repetimos hasta que haya
una respuesta final.
"""

from datetime import datetime
from typing import Any

from app.agent.llm import LLMClient
from app.agent.messages import assistant_message, tool_result_message
from app.agent.prompts import build_system_prompt
from app.agent.tools import TOOL_DEFINITIONS, execute_tool
from app.clients.request_cache import RequestWeatherClient
from app.clients.weather_api import WeatherApi

EMPTY_ANSWER = "No pude generar una respuesta con los datos disponibles."


async def run_agent(
    question: str,
    weather_client: WeatherApi,
    llm: LLMClient,
    *,
    max_tool_calls: int = 4,
    now: datetime | None = None,
) -> str:
    """Resuelve una pregunta usando herramientas hasta obtener texto final."""
    if max_tool_calls < 1:
        raise ValueError("max_tool_calls debe ser al menos 1")

    # La caché vive solo durante esta pregunta y se comparte entre herramientas.
    cached_weather = RequestWeatherClient(weather_client)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": build_system_prompt(
                now=now,
                max_tool_calls=max_tool_calls,
            ),
        },
        {"role": "user", "content": question},
    ]
    tool_calls_used = 0

    while True:
        response = await llm.complete(messages, TOOL_DEFINITIONS)

        if not response.tool_calls:
            content = (response.content or "").strip()
            return content or EMPTY_ANSWER

        if tool_calls_used + len(response.tool_calls) > max_tool_calls:
            return (
                "No pude completar la consulta porque se alcanzó el máximo de "
                f"{max_tool_calls} llamadas a herramientas."
            )

        messages.append(assistant_message(response.content, response.tool_calls))

        for call in response.tool_calls:
            result = await execute_tool(call.name, call.arguments, cached_weather)
            messages.append(tool_result_message(call.id, result))
            tool_calls_used += 1
