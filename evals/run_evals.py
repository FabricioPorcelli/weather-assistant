"""Runner de evals con LLM real y clima simulado."""

import argparse
import asyncio
import json
import math
import re
import sys
import time
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.agent.llm import (  # noqa: E402
    LLMClient,
    LLMResponse,
    OpenAICompatClient,
)
from app.agent.loop import run_agent  # noqa: E402
from app.clients.weather_api import (  # noqa: E402
    CurrentWeather,
    DailyForecast,
    Forecast,
    History,
    Location,
    LocationNotFound,
    UpstreamError,
)
from app.config import get_settings  # noqa: E402

DEFAULT_TODAY = "2026-03-04"
DEFAULT_CASES = EVALS_DIR / "cases.yaml"
DEFAULT_OUTPUT = EVALS_DIR / "reports"

# USD por 1M de tokens (entrada, salida). Revisar si el proveedor cambia precios.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
}


class EmptyWeatherApi:
    """Cliente que no tiene datos: se usa en casos sin ubicación."""

    async def get_current(self, location: Location) -> CurrentWeather:
        raise LocationNotFound("no hay ubicación para consultar")

    async def get_forecast(
        self,
        location: Location,
        days: int = 5,
    ) -> Forecast:
        raise LocationNotFound("no hay ubicación para consultar")

    async def get_history(
        self,
        location: Location,
        start: date,
        end: date,
    ) -> History:
        raise LocationNotFound("no hay ubicación para consultar")


class FixtureWeatherApi:
    """Cliente de clima que lee respuestas guardadas en un JSON."""

    def __init__(self, fixture_path: Path) -> None:
        payload = json.loads(fixture_path.read_text())
        self._locations = payload.get("locations", {})
        self.calls: list[tuple[Any, ...]] = []

    def _lookup(self, location: Location) -> dict[str, Any]:
        key = (location.city or location.label or "").casefold()
        for name, data in self._locations.items():
            if name.casefold() == key:
                return data
        raise LocationNotFound(f"No se encontró la ubicación: {key}")

    async def get_current(self, location: Location) -> CurrentWeather:
        self.calls.append(("current", location.city or location.label))
        data = self._lookup(location)
        return CurrentWeather.model_validate(data["current"])

    async def get_forecast(
        self,
        location: Location,
        days: int = 5,
    ) -> Forecast:
        self.calls.append(("forecast", location.city or location.label, days))
        data = self._lookup(location)
        raw_days = data.get("forecast") or []
        daily = [DailyForecast.model_validate(item) for item in raw_days[:days]]
        if not daily:
            raise UpstreamError("el fixture no tiene pronóstico")
        return Forecast(
            location=data["current"]["location"],
            days=daily,
        )

    async def get_history(
        self,
        location: Location,
        start: date,
        end: date,
    ) -> History:
        self.calls.append(("history", location.city or location.label, start, end))
        data = self._lookup(location)
        daily = [
            DailyForecast.model_validate(item)
            for item in data.get("history") or []
            if start <= date.fromisoformat(item["date"]) <= end
        ]
        if not daily:
            raise UpstreamError("el fixture no tiene histórico para ese rango")
        return History(
            location=data["current"]["location"],
            days=daily,
        )


class RecordingLLMClient:
    """Envuelve un LLM real y registra mensajes, respuestas y uso."""

    def __init__(self, inner: LLMClient, *, delay_seconds: float = 0.0) -> None:
        self.inner = inner
        self.delay_seconds = delay_seconds
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        started_at = time.perf_counter()
        response = await self.inner.complete(messages, tools)
        self.calls.append(
            {
                "messages": deepcopy(messages),
                "response": response,
                "duration_ms": round(
                    (time.perf_counter() - started_at) * 1000,
                    2,
                ),
            }
        )
        return response

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ):
        async for event in self.inner.stream(messages, tools):
            yield event

    async def aclose(self) -> None:
        """El runner cierra el cliente base al terminar el modelo."""


def _normalize_text(value: str) -> str:
    return value.casefold().strip()


def _is_subset(expected: Any, actual: Any) -> bool:
    """Compara un subconjunto de JSON: las claves extra no fallan."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(
            key in actual and _is_subset(value, actual[key])
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) < len(expected):
            return False
        return all(
            _is_subset(expected_item, actual[index])
            for index, expected_item in enumerate(expected)
        )
    return expected == actual


def _expected_args(expect: dict[str, Any]) -> list[dict[str, Any]]:
    raw = expect.get("args")
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    return list(raw)


def _extract_numbers(text: str) -> list[float]:
    values = []
    for raw in re.findall(r"-?\d+(?:[.,]\d+)?", text):
        values.append(float(raw.replace(",", ".")))
    return values


def _numbers_grounded(answer: str, tool_results: dict[str, Any]) -> bool:
    answer_numbers = _extract_numbers(answer)
    if not answer_numbers:
        return True

    available = _extract_numbers(json.dumps(tool_results, ensure_ascii=False))
    for number in answer_numbers:
        if not any(
            math.isclose(number, candidate, rel_tol=0.02, abs_tol=0.6)
            for candidate in available
        ):
            return False
    return True


def _tool_results(recording: RecordingLLMClient) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for call in recording.calls:
        for message in call["messages"]:
            if message.get("role") != "tool":
                continue
            call_id = message.get("tool_call_id")
            try:
                results[call_id] = json.loads(message.get("content", "{}"))
            except ValueError:
                results[call_id] = {"raw": message.get("content")}
    return results


def _usage_totals(recording: RecordingLLMClient) -> dict[str, int]:
    prompt = completion = total = 0
    for call in recording.calls:
        usage = call["response"].usage
        if usage is None:
            continue
        prompt += usage.prompt_tokens
        completion += usage.completion_tokens
        total += usage.total_tokens
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _estimate_cost(model: str, usage: dict[str, int]) -> float:
    input_price, output_price = MODEL_PRICING.get(model, (0.0, 0.0))
    return round(
        usage["prompt_tokens"] / 1_000_000 * input_price
        + usage["completion_tokens"] / 1_000_000 * output_price,
        6,
    )


def _check_case(
    case: dict[str, Any],
    answer: str,
    tool_calls: list[Any],
    results: dict[str, Any],
    error: str | None,
) -> dict[str, Any]:
    expect = case.get("expect") or {}
    expected_tools = list(expect.get("tools") or [])
    actual_tools = [call.name for call in tool_calls]
    actual_args = []
    for call in tool_calls:
        try:
            actual_args.append(json.loads(call.arguments))
        except ValueError:
            actual_args.append({})

    tools_match = actual_tools == expected_tools
    expected_args = _expected_args(expect)
    args_match = None
    if expected_args:
        padded_expected = expected_args + [
            {} for _ in range(max(0, len(expected_tools) - len(expected_args)))
        ]
        args_match = (
            tools_match
            and len(actual_args) >= len(padded_expected)
            and all(
                _is_subset(expected, actual_args[index])
                for index, expected in enumerate(padded_expected)
            )
        )

    expected_verdict = expect.get("verdict")
    verdict_match = None
    if expected_verdict is not None:
        verdict_match = any(
            isinstance(result, dict) and result.get("verdict") == expected_verdict
            for result in results.values()
        )

    expected_best_date = expect.get("best_date")
    best_date_match = None
    if expected_best_date is not None:
        best_date_match = any(
            isinstance(result, dict)
            and isinstance(result.get("ranking"), list)
            and result["ranking"]
            and result["ranking"][0].get("date") == expected_best_date
            for result in results.values()
        )

    mentions = expect.get("answer_must_mention") or []
    mentions_match = None
    if mentions:
        normalized_answer = _normalize_text(answer)
        mentions_match = all(
            _normalize_text(mention) in normalized_answer for mention in mentions
        )

    forbidden = expect.get("answer_must_not_mention") or []
    forbidden_ok = None
    if forbidden:
        normalized_answer = _normalize_text(answer)
        forbidden_ok = not any(
            _normalize_text(item) in normalized_answer for item in forbidden
        )

    grounded = False if error else _numbers_grounded(answer, results)

    checks = [tools_match, grounded]
    for value in (
        args_match,
        verdict_match,
        best_date_match,
        mentions_match,
        forbidden_ok,
    ):
        if value is not None:
            checks.append(value)

    return {
        "tools_match": tools_match,
        "args_match": args_match,
        "verdict_match": verdict_match,
        "best_date_match": best_date_match,
        "mentions_match": mentions_match,
        "forbidden_ok": forbidden_ok,
        "grounded": grounded,
        "passed": all(checks) and error is None,
        "actual_tools": actual_tools,
        "actual_args": actual_args,
    }


async def run_case(
    case: dict[str, Any],
    *,
    model: str,
    llm: LLMClient,
    delay_seconds: float,
) -> dict[str, Any]:
    """Ejecuta un caso y devuelve el resultado con todas sus métricas."""
    today = case.get("today", DEFAULT_TODAY)
    now = datetime.fromisoformat(f"{today}T09:00:00+00:00")
    context = case.get("context") or {}
    location = context.get("location") or {}
    location_label = location.get("label") or location.get("city")

    fixture_name = case.get("weather_fixture")
    weather = (
        FixtureWeatherApi(EVALS_DIR / fixture_name)
        if fixture_name
        else EmptyWeatherApi()
    )
    recording = RecordingLLMClient(llm, delay_seconds=delay_seconds)

    started_at = time.perf_counter()
    error = None
    answer = ""
    try:
        answer = await run_agent(
            case["question"],
            weather,
            recording,
            max_tool_calls=4,
            now=now,
            location_label=location_label,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    tool_calls = [
        call for recorded in recording.calls for call in recorded["response"].tool_calls
    ]
    results = _tool_results(recording)
    checks = _check_case(case, answer, tool_calls, results, error)
    usage = _usage_totals(recording)

    return {
        "id": case["id"],
        "question": case["question"],
        "today": today,
        "fixture": fixture_name,
        "expected": case.get("expect") or {},
        "answer": answer,
        "error": error,
        "latency_ms": latency_ms,
        "usage": usage,
        "cost_usd": _estimate_cost(model, usage),
        "tool_results": results,
        **checks,
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    def average(key: str) -> float | None:
        values = [result[key] for result in results if result.get(key) is not None]
        if not values:
            return None
        return round(sum(1 for value in values if value) / len(values), 3)

    latencies = [result["latency_ms"] for result in results]
    return {
        "cases": len(results),
        "passed": sum(1 for result in results if result["passed"]),
        "pass_rate": round(
            sum(1 for result in results if result["passed"]) / len(results),
            3,
        )
        if results
        else 0.0,
        "tools_accuracy": average("tools_match"),
        "args_accuracy": average("args_match"),
        "verdict_accuracy": average("verdict_match"),
        "best_date_accuracy": average("best_date_match"),
        "mentions_accuracy": average("mentions_match"),
        "groundedness": average("grounded"),
        "latency_p50_ms": round(_percentile(latencies, 0.50), 2),
        "latency_p95_ms": round(_percentile(latencies, 0.95), 2),
        "prompt_tokens": sum(result["usage"]["prompt_tokens"] for result in results),
        "completion_tokens": sum(
            result["usage"]["completion_tokens"] for result in results
        ),
        "total_tokens": sum(result["usage"]["total_tokens"] for result in results),
        "cost_usd": round(sum(result["cost_usd"] for result in results), 6),
    }


def _model_slug(model: str) -> str:
    return model.replace("/", "-").replace(":", "-")


def _write_report(
    model: str,
    results: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    summary = summarize(results)
    report = {
        "model": model,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "results": results,
    }
    slug = _model_slug(model)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{slug}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )

    lines = [
        f"# Evals — {model}",
        "",
        f"Generado: {report['generated_at']}",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Casos | {summary['cases']} |",
        f"| Pasaron | {summary['passed']} |",
        f"| Pass rate | {summary['pass_rate']} |",
        f"| Herramientas | {summary['tools_accuracy']} |",
        f"| Argumentos | {summary['args_accuracy']} |",
        f"| Veredicto | {summary['verdict_accuracy']} |",
        f"| Mejor día | {summary['best_date_accuracy']} |",
        f"| Menciones | {summary['mentions_accuracy']} |",
        f"| Groundedness | {summary['groundedness']} |",
        f"| Latencia p50 | {summary['latency_p50_ms']} ms |",
        f"| Latencia p95 | {summary['latency_p95_ms']} ms |",
        f"| Tokens | {summary['total_tokens']} |",
        f"| Costo estimado | USD {summary['cost_usd']} |",
        "",
        "| Caso | Pasa | Herramientas | Error |",
        "|---|---|---|---|",
    ]
    for result in results:
        tools = ", ".join(result["actual_tools"]) or "—"
        error = (result["error"] or "").replace("|", "\\|")
        passed_label = "sí" if result["passed"] else "no"
        lines.append(f"| {result['id']} | {passed_label} | {tools} | {error} |")
    (output_dir / f"{slug}.md").write_text("\n".join(lines) + "\n")
    return report


def _write_summary(reports: list[dict[str, Any]], output_dir: Path) -> None:
    lines = [
        "# Resumen de evals",
        "",
        "| Modelo | Pass rate | Herramientas | Argumentos | Groundedness | "
        "p50 | p95 | Tokens | Costo USD |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for report in reports:
        summary = report["summary"]
        lines.append(
            "| {model} | {pass_rate} | {tools} | {args} | {grounded} | "
            "{p50} | {p95} | {tokens} | {cost} |".format(
                model=report["model"],
                pass_rate=summary["pass_rate"],
                tools=summary["tools_accuracy"],
                args=summary["args_accuracy"],
                grounded=summary["groundedness"],
                p50=summary["latency_p50_ms"],
                p95=summary["latency_p95_ms"],
                tokens=summary["total_tokens"],
                cost=summary["cost_usd"],
            )
        )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n")


async def _run_with_retries(
    case: dict[str, Any],
    *,
    model: str,
    llm: LLMClient,
    delay_seconds: float,
) -> dict[str, Any]:
    result = None
    for attempt in range(4):
        result = await run_case(
            case,
            model=model,
            llm=llm,
            delay_seconds=delay_seconds,
        )
        if result["error"] and "429" in result["error"]:
            wait_seconds = 10 * (attempt + 1)
            print(f"  429 en {case['id']}; esperando {wait_seconds}s…")
            await asyncio.sleep(wait_seconds)
            continue
        return result
    return result


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.llm_base_url:
        print("Falta LLM_BASE_URL en el entorno.", file=sys.stderr)
        return 2

    cases = yaml.safe_load(args.cases.read_text())
    if args.case_ids:
        cases = [case for case in cases if case["id"] in args.case_ids]
    if args.limit:
        cases = cases[: args.limit]

    models = args.models or [settings.llm_model]
    reports = []
    for model in models:
        if not model:
            print("Falta LLM_MODEL en el entorno.", file=sys.stderr)
            return 2

        print(f"Modelo: {model} — {len(cases)} casos")
        base_llm = OpenAICompatClient(
            settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=model,
            timeout=settings.llm_timeout_seconds,
        )
        results = []
        try:
            for index, case in enumerate(cases, start=1):
                result = await _run_with_retries(
                    case,
                    model=model,
                    llm=base_llm,
                    delay_seconds=args.delay_seconds,
                )
                results.append(result)
                print(
                    f"  [{index}/{len(cases)}] {case['id']}: "
                    f"{'OK' if result['passed'] else 'FALLA'}"
                )
        finally:
            await base_llm.aclose()

        reports.append(_write_report(model, results, args.output_dir))

    _write_summary(reports, args.output_dir)
    print(f"Reportes en {args.output_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta evals del agente.")
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help="Modelos a evaluar. Por defecto usa LLM_MODEL.",
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--case", dest="case_ids", nargs="+", default=None)
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.5,
        help="Espera antes de cada llamada al LLM (por rate limit).",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
