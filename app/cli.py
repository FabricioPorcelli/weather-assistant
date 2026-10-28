"""Entrada de terminal para el agente."""

import argparse
import asyncio
import sys

from app.agent.llm import LLMError, OpenAICompatClient
from app.agent.loop import run_agent
from app.clients.weather_api import WeatherApiClient
from app.config import Settings, get_settings


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Asistente de clima en la terminal.",
    )
    parser.add_argument(
        "question",
        nargs="+",
        help="Pregunta en lenguaje natural, por ejemplo: ¿Llevo paraguas en Madrid?",
    )
    return parser.parse_args(argv)


async def _run(question: str, settings: Settings) -> str:
    """Configura los clientes y ejecuta un turno del agente."""
    if not settings.llm_base_url or not settings.llm_model:
        raise ValueError("configurá LLM_BASE_URL y LLM_MODEL en el archivo .env")

    async with WeatherApiClient(
        settings.weather_api_base_url,
        timeout=settings.weather_api_timeout_seconds,
        retries=settings.weather_api_retries,
        retry_delay=settings.weather_api_retry_delay_seconds,
    ) as weather_client:
        async with OpenAICompatClient(
            settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        ) as llm:
            return await run_agent(
                question,
                weather_client,
                llm,
                max_tool_calls=settings.max_tool_calls_per_turn,
            )


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada del CLI. Devuelve el código de salida del proceso."""
    args = _parse_args(argv)
    question = " ".join(args.question)

    try:
        answer = asyncio.run(_run(question, get_settings()))
    except ValueError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2
    except LLMError as exc:
        print(f"Error del LLM: {exc}", file=sys.stderr)
        return 1

    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
