"""Unit tests for :class:`openai_client_impl.OpenAIClient`."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIStatusError, OpenAI, RateLimitError

from ai_client_api.resilience import CircuitBreaker
from openai_client_impl import OpenAIClient
from openai_client_impl.config import OpenAIClientConfig
from openai_client_impl.errors import OpenAIClientError


def _mock_completion(content: str | None) -> MagicMock:
    response = MagicMock()
    message = MagicMock()
    message.content = content
    message.tool_calls = None
    choice = MagicMock()
    choice.message = message
    response.choices = [choice]
    return response


def _openai_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _rate_limit_error() -> RateLimitError:
    response = httpx.Response(429, request=_openai_request())
    return RateLimitError("rate limited", response=response, body=None)


def _server_error() -> APIStatusError:
    response = httpx.Response(503, request=_openai_request())
    return APIStatusError("server error", response=response, body=None)


def _bad_request_error() -> APIStatusError:
    response = httpx.Response(400, request=_openai_request())
    return APIStatusError("bad request", response=response, body=None)


def test_send_message_delegates_to_openai_sdk() -> None:
    """``send_message`` calls chat completions and returns assistant text."""
    mock_sdk = MagicMock(spec=OpenAI)
    mock_sdk.chat.completions.create.return_value = _mock_completion("ok")

    client = OpenAIClient(
        config=OpenAIClientConfig(api_key="sk-test", model="gpt-test"),
        client=mock_sdk,
    )
    result = client.send_message("ping")

    assert result == "ok"
    mock_sdk.chat.completions.create.assert_called_once()
    call_kw = mock_sdk.chat.completions.create.call_args.kwargs
    assert call_kw["model"] == "gpt-test"
    assert len(call_kw["messages"]) == 1
    assert call_kw["messages"][0]["role"] == "user"
    assert "ping" in call_kw["messages"][0]["content"]


def test_send_message_passes_tools_to_openai_sdk() -> None:
    """Optional ``tools`` are forwarded to chat completions."""
    mock_sdk = MagicMock(spec=OpenAI)
    mock_sdk.chat.completions.create.return_value = _mock_completion("ok")

    client = OpenAIClient(
        config=OpenAIClientConfig(api_key="sk-test", model="gpt-test"),
        client=mock_sdk,
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather by city.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]
    client.send_message("weather?", tools=tools)

    call_kw = mock_sdk.chat.completions.create.call_args.kwargs
    assert call_kw["tools"] == tools


def test_send_message_includes_context_in_user_content() -> None:
    """Optional ``context`` is embedded in the user message."""
    mock_sdk = MagicMock(spec=OpenAI)
    mock_sdk.chat.completions.create.return_value = _mock_completion("done")

    client = OpenAIClient(
        config=OpenAIClientConfig(api_key="sk-test", model="gpt-test"),
        client=mock_sdk,
    )
    ctx: dict[str, Any] = {"k": 1}
    client.send_message("go", context=ctx)

    content = mock_sdk.chat.completions.create.call_args.kwargs["messages"][0][
        "content"
    ]
    assert "Context (JSON):" in content
    assert '"k":1' in content
    assert "go" in content


def test_missing_api_key_raises() -> None:
    """Constructing without SDK client or API key fails fast."""
    with pytest.raises(OpenAIClientError, match="OPENAI_API_KEY"):
        OpenAIClient(config=OpenAIClientConfig(api_key="", model="gpt-test"))


def test_empty_model_response_raises() -> None:
    """Null assistant content surfaces as ``OpenAIClientError``."""
    mock_sdk = MagicMock(spec=OpenAI)
    mock_sdk.chat.completions.create.return_value = _mock_completion(None)

    client = OpenAIClient(
        config=OpenAIClientConfig(api_key="sk-test", model="gpt-test"),
        client=mock_sdk,
    )
    with pytest.raises(OpenAIClientError, match="empty content"):
        client.send_message("hi")


def test_tool_call_returns_structured_response() -> None:
    """Tool calls return function name and parsed JSON arguments."""
    mock_sdk = MagicMock(spec=OpenAI)
    completion = _mock_completion(None)
    tool_call = MagicMock()
    tool_call.function.name = "get_weather"
    tool_call.function.arguments = '{"city":"NYC"}'
    completion.choices[0].message.tool_calls = [tool_call]
    mock_sdk.chat.completions.create.return_value = completion

    client = OpenAIClient(
        config=OpenAIClientConfig(api_key="sk-test", model="gpt-test"),
        client=mock_sdk,
    )
    result = client.send_message("weather?")
    assert result == {"name": "get_weather", "arguments": {"city": "NYC"}}


def test_tool_call_invalid_json_raises() -> None:
    """Invalid tool-call JSON arguments raise ``OpenAIClientError``."""
    mock_sdk = MagicMock(spec=OpenAI)
    completion = _mock_completion(None)
    tool_call = MagicMock()
    tool_call.function.name = "get_weather"
    tool_call.function.arguments = "{bad json"
    completion.choices[0].message.tool_calls = [tool_call]
    mock_sdk.chat.completions.create.return_value = completion

    client = OpenAIClient(
        config=OpenAIClientConfig(api_key="sk-test", model="gpt-test"),
        client=mock_sdk,
    )
    with pytest.raises(OpenAIClientError, match="invalid JSON"):
        client.send_message("weather?")


def test_send_message_retries_transient_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient OpenAI failures are retried before succeeding."""
    sleeps: list[float] = []
    monkeypatch.setattr("ai_client_api.resilience.time.sleep", sleeps.append)
    monkeypatch.setattr("ai_client_api.resilience.random.uniform", lambda _a, _b: 0.0)

    mock_sdk = MagicMock(spec=OpenAI)
    mock_sdk.chat.completions.create.side_effect = [
        _rate_limit_error(),
        _server_error(),
        _mock_completion("ok"),
    ]
    client = OpenAIClient(
        config=OpenAIClientConfig(api_key="sk-test", model="gpt-test"),
        client=mock_sdk,
        circuit_breaker=CircuitBreaker(failure_threshold=5),
    )

    assert client.send_message("ping") == "ok"
    assert mock_sdk.chat.completions.create.call_count == 3
    assert sleeps == [0.5, 1.0]


def test_send_message_stops_after_max_three_retries() -> None:
    """OpenAI requests stop after one initial attempt and three retries."""
    mock_sdk = MagicMock(spec=OpenAI)
    mock_sdk.chat.completions.create.side_effect = _rate_limit_error()
    client = OpenAIClient(
        config=OpenAIClientConfig(api_key="sk-test", model="gpt-test"),
        client=mock_sdk,
        circuit_breaker=CircuitBreaker(failure_threshold=5),
    )

    with pytest.raises(OpenAIClientError, match="rate limited"):
        client.send_message("ping")

    assert mock_sdk.chat.completions.create.call_count == 4


def test_send_message_does_not_retry_non_transient_error() -> None:
    """Non-transient OpenAI failures are not retried."""
    mock_sdk = MagicMock(spec=OpenAI)
    mock_sdk.chat.completions.create.side_effect = _bad_request_error()
    client = OpenAIClient(
        config=OpenAIClientConfig(api_key="sk-test", model="gpt-test"),
        client=mock_sdk,
        circuit_breaker=CircuitBreaker(failure_threshold=5),
    )

    with pytest.raises(OpenAIClientError, match="bad request"):
        client.send_message("ping")

    assert mock_sdk.chat.completions.create.call_count == 1


def test_send_message_circuit_breaker_blocks_after_consecutive_failures() -> None:
    """An open circuit breaker rejects further OpenAI calls without retrying."""
    mock_sdk = MagicMock(spec=OpenAI)
    mock_sdk.chat.completions.create.side_effect = _rate_limit_error()
    breaker = CircuitBreaker(failure_threshold=2)
    client = OpenAIClient(
        config=OpenAIClientConfig(api_key="sk-test", model="gpt-test"),
        client=mock_sdk,
        circuit_breaker=breaker,
    )

    for _ in range(2):
        with pytest.raises(OpenAIClientError, match="rate limited"):
            client.send_message("ping")

    mock_sdk.chat.completions.create.reset_mock()
    with pytest.raises(OpenAIClientError, match="circuit breaker is open"):
        client.send_message("ping")

    mock_sdk.chat.completions.create.assert_not_called()
