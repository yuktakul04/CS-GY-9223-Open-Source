"""Gemini SDK-backed implementation of :class:`ai_client_api.AIClient`."""

from __future__ import annotations

import json
from typing import Any

from google import genai

from ai_client_api import AIClient, ToolCallResponse
from ai_client_api.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    call_with_resilience,
)
from gemini_client_impl.config import GeminiClientConfig
from gemini_client_impl.errors import GeminiClientError
from gemini_client_impl.resilience import is_transient_error


class GeminiClient(AIClient):
    """``AIClient`` that delegates to Gemini content generation."""

    def __init__(
        self,
        *,
        config: GeminiClientConfig | None = None,
        client: genai.Client | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        """Create a Gemini-backed client with env/default configuration."""
        self._config = config or GeminiClientConfig.from_env()
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        if client is not None:
            self._client = client
        elif not self._config.api_key:
            msg = "GEMINI_API_KEY is required when client is not injected"
            raise GeminiClientError(msg)
        else:
            self._client = genai.Client(api_key=self._config.api_key)

    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str | ToolCallResponse:
        """Return assistant text or tool-call payload for ``prompt``."""
        user_content = _build_user_content(prompt=prompt, context=context)
        payload: dict[str, Any] = {
            "model": self._config.model,
            "contents": user_content,
        }
        if tools:
            payload["config"] = {"tools": _to_gemini_tools(tools)}
        try:
            response = call_with_resilience(
                lambda: self._client.models.generate_content(**payload),
                is_transient=is_transient_error,
                circuit_breaker=self._circuit_breaker,
            )
        except CircuitBreakerOpenError as exc:
            msg = "Gemini circuit breaker is open"
            raise GeminiClientError(msg) from exc
        except Exception as exc:
            msg = f"Gemini request failed: {exc}"
            raise GeminiClientError(msg) from exc

        function_calls = response.function_calls
        if function_calls:
            first_call = function_calls[0]
            name = first_call.name
            if name is None:
                msg = "Gemini function-call name is required"
                raise GeminiClientError(msg)
            arguments = first_call.args
            if not isinstance(arguments, dict):
                msg = "Gemini function-call arguments must be a JSON object"
                raise GeminiClientError(msg)
            return {
                "name": name,
                "arguments": arguments,
            }

        text = response.text
        if text is None:
            msg = "Gemini returned empty content"
            raise GeminiClientError(msg)
        return text


def get_client_impl() -> AIClient:
    """Construct the default Gemini-backed ``AIClient`` implementation."""
    return GeminiClient()


def _build_user_content(
    *,
    prompt: str,
    context: dict[str, Any] | None,
) -> str:
    if not context:
        return prompt
    encoded = json.dumps(context, separators=(",", ":"), default=str)
    return f"Context (JSON): {encoded}\n\nUser:\n{prompt}"


def _to_gemini_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        declaration: dict[str, Any] = {
            "name": function["name"],
            "description": function.get("description", ""),
            "parameters": function.get(
                "parameters",
                {"type": "object", "properties": {}, "required": []},
            ),
        }
        declarations.append(declaration)
    if not declarations:
        return []
    return [{"function_declarations": declarations}]
