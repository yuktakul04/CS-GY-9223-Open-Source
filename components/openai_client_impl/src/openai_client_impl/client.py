"""OpenAI SDK-backed implementation of :class:`ai_client_api.AIClient`."""

from __future__ import annotations

import json
from typing import Any, cast

from openai import OpenAI

from ai_client_api import AIClient, ToolCallResponse
from ai_client_api.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    call_with_resilience,
)
from openai_client_impl.config import OpenAIClientConfig
from openai_client_impl.errors import OpenAIClientError
from openai_client_impl.resilience import is_transient_error


class OpenAIClient(AIClient):
    """``AIClient`` that delegates to OpenAI chat completions."""

    def __init__(
        self,
        *,
        config: OpenAIClientConfig | None = None,
        client: OpenAI | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        """Create an OpenAI-backed client with env/default configuration."""
        self._config = config or OpenAIClientConfig.from_env()
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        if client is not None:
            self._client = client
        elif not self._config.api_key:
            msg = "OPENAI_API_KEY is required when client is not injected"
            raise OpenAIClientError(msg)
        else:
            self._client = OpenAI(api_key=self._config.api_key)

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
            "messages": [{"role": "user", "content": user_content}],
        }
        if tools:
            payload["tools"] = tools
        try:
            response = call_with_resilience(
                lambda: self._client.chat.completions.create(**payload),
                is_transient=is_transient_error,
                circuit_breaker=self._circuit_breaker,
            )
        except CircuitBreakerOpenError as exc:
            msg = "OpenAI circuit breaker is open"
            raise OpenAIClientError(msg) from exc
        except Exception as exc:
            msg = f"OpenAI request failed: {exc}"
            raise OpenAIClientError(msg) from exc

        choice = response.choices[0].message
        tool_calls = choice.tool_calls
        if tool_calls:
            first_call = tool_calls[0]
            try:
                arguments = json.loads(first_call.function.arguments)
            except json.JSONDecodeError as exc:
                msg = "OpenAI returned invalid JSON tool-call arguments"
                raise OpenAIClientError(msg) from exc
            if not isinstance(arguments, dict):
                msg = "OpenAI tool-call arguments must decode to a JSON object"
                raise OpenAIClientError(msg)
            return {
                "name": first_call.function.name,
                "arguments": arguments,
            }

        text = choice.content
        if text is None:
            msg = "OpenAI returned empty content"
            raise OpenAIClientError(msg)
        return cast("str", text)


def get_client_impl() -> AIClient:
    """Construct the default OpenAI-backed ``AIClient`` implementation."""
    return OpenAIClient()


def _build_user_content(
    *,
    prompt: str,
    context: dict[str, Any] | None,
) -> str:
    if not context:
        return prompt
    encoded = json.dumps(context, separators=(",", ":"), default=str)
    return f"Context (JSON): {encoded}\n\nUser:\n{prompt}"
