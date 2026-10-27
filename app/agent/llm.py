"""Cliente LLM delgado contra APIs compatibles con OpenAI Chat Completions.

No usamos el SDK de OpenAI: hacemos un POST HTTP con httpx. Así el mismo
cliente sirve para Groq, Ollama, OpenCode u otro proveedor compatible.
"""

from types import TracebackType
from typing import Any, Protocol, Self

import httpx
from pydantic import BaseModel, Field


class LLMError(Exception):
    """Error al llamar al proveedor del LLM."""


class ToolCall(BaseModel):
    """Pedido de herramienta devuelto por el LLM."""

    id: str
    name: str
    arguments: str


class LLMResponse(BaseModel):
    """Respuesta normalizada del LLM."""

    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class LLMClient(Protocol):
    """Contrato mínimo que necesita el loop del agente."""

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse: ...

    async def aclose(self) -> None: ...


class OpenAICompatClient:
    """Cliente para cualquier API compatible con OpenAI Chat Completions."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str,
        model: str,
        timeout: float = 30.0,
    ) -> None:
        base_url = base_url.strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url del LLM debe empezar con http:// o https://")
        if not model.strip():
            raise ValueError("el modelo del LLM no puede estar vacío")
        if timeout <= 0:
            raise ValueError("el timeout del LLM debe ser mayor que cero")

        self._endpoint = f"{base_url}/chat/completions"
        self._model = model.strip()
        self._api_key = api_key.strip()
        self._http = httpx.AsyncClient(timeout=timeout)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Envía mensajes y herramientas, y normaliza la respuesta."""
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = await self._http.post(
                self._endpoint,
                headers=headers,
                json={
                    "model": self._model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                },
            )
        except httpx.TimeoutException as exc:
            raise LLMError("el proveedor del LLM no respondió a tiempo") from exc
        except httpx.RequestError as exc:
            raise LLMError("no se pudo conectar con el proveedor del LLM") from exc

        if response.status_code in (401, 403):
            raise LLMError("la API key del LLM es inválida o no tiene permisos")
        if response.is_error:
            raise LLMError(
                f"el proveedor del LLM respondió con estado {response.status_code}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError(
                "el proveedor del LLM devolvió una respuesta inválida"
            ) from exc

        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                "el proveedor del LLM devolvió una respuesta inesperada"
            ) from exc

        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise LLMError("el proveedor del LLM devolvió contenido inválido")

        tool_calls: list[ToolCall] = []
        for index, raw_call in enumerate(message.get("tool_calls") or []):
            try:
                function = raw_call["function"]
                tool_calls.append(
                    ToolCall(
                        id=str(raw_call.get("id") or f"call_{index}"),
                        name=str(function["name"]),
                        arguments=str(function.get("arguments") or "{}"),
                    )
                )
            except (KeyError, TypeError) as exc:
                raise LLMError(
                    "el proveedor del LLM devolvió un tool_call inválido"
                ) from exc

        return LLMResponse(content=content, tool_calls=tool_calls)

    async def aclose(self) -> None:
        """Cierra las conexiones HTTP."""
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
