"""Conversión de eventos del agente al formato de Chat Completions."""

import json
from typing import Any

from app.agent.llm import ToolCall


def assistant_message(
    content: str | None,
    tool_calls: list[ToolCall],
) -> dict[str, Any]:
    """Arma el mensaje assistant con sus tool calls."""
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.arguments,
                },
            }
            for call in tool_calls
        ],
    }


def tool_result_message(
    call_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Arma el mensaje tool con el resultado serializado."""
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }
