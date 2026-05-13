"""Unit tests for :class:`gemini_client_impl.GeminiClient`."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from gemini_client_impl import GeminiClient
from gemini_client_impl.config import GeminiClientConfig
from gemini_client_impl.errors import GeminiClientError


def _mock_response(content: str | None) -> MagicMock:
    response = MagicMock()
    response.text = content
    response.function_calls = None
    return response


def test_send_message_delegates_to_gemini_sdk() -> None:
    """``send_message`` calls Gemini content generation and returns text."""
    mock_sdk = MagicMock()
    mock_sdk.models.generate_content.return_value = _mock_response("ok")

    client = GeminiClient(
        config=GeminiClientConfig(api_key="gemini-test", model="gemini-test"),
        client=mock_sdk,
    )
    result = client.send_message("ping")

    assert result == "ok"
    mock_sdk.models.generate_content.assert_called_once()
    call_kw = mock_sdk.models.generate_content.call_args.kwargs
    assert call_kw["model"] == "gemini-test"
    assert "ping" in call_kw["contents"]


def test_send_message_passes_tools_to_gemini_sdk() -> None:
    """OpenAI-style function tools are adapted for Gemini generation config."""
    mock_sdk = MagicMock()
    mock_sdk.models.generate_content.return_value = _mock_response("ok")

    client = GeminiClient(
        config=GeminiClientConfig(api_key="gemini-test", model="gemini-test"),
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

    config = mock_sdk.models.generate_content.call_args.kwargs["config"]
    assert config["tools"] == [
        {
            "function_declarations": [
                {
                    "name": "get_weather",
                    "description": "Get weather by city.",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                }
            ]
        }
    ]


def test_send_message_includes_context_in_user_content() -> None:
    """Optional ``context`` is embedded in the user content."""
    mock_sdk = MagicMock()
    mock_sdk.models.generate_content.return_value = _mock_response("done")

    client = GeminiClient(
        config=GeminiClientConfig(api_key="gemini-test", model="gemini-test"),
        client=mock_sdk,
    )
    ctx: dict[str, Any] = {"k": 1}
    client.send_message("go", context=ctx)

    content = mock_sdk.models.generate_content.call_args.kwargs["contents"]
    assert "Context (JSON):" in content
    assert '"k":1' in content
    assert "go" in content


def test_missing_api_key_raises() -> None:
    """Constructing without SDK client or API key fails fast."""
    with pytest.raises(GeminiClientError, match="GEMINI_API_KEY"):
        GeminiClient(config=GeminiClientConfig(api_key="", model="gemini-test"))


def test_empty_model_response_raises() -> None:
    """Null text content surfaces as ``GeminiClientError``."""
    mock_sdk = MagicMock()
    mock_sdk.models.generate_content.return_value = _mock_response(None)

    client = GeminiClient(
        config=GeminiClientConfig(api_key="gemini-test", model="gemini-test"),
        client=mock_sdk,
    )
    with pytest.raises(GeminiClientError, match="empty content"):
        client.send_message("hi")


def test_tool_call_returns_structured_response() -> None:
    """Function calls return function name and arguments."""
    mock_sdk = MagicMock()
    response = _mock_response(None)
    function_call = MagicMock()
    function_call.name = "get_weather"
    function_call.args = {"city": "NYC"}
    response.function_calls = [function_call]
    mock_sdk.models.generate_content.return_value = response

    client = GeminiClient(
        config=GeminiClientConfig(api_key="gemini-test", model="gemini-test"),
        client=mock_sdk,
    )
    result = client.send_message("weather?")
    assert result == {"name": "get_weather", "arguments": {"city": "NYC"}}


def test_tool_call_non_object_args_raises() -> None:
    """Non-object function call arguments raise ``GeminiClientError``."""
    mock_sdk = MagicMock()
    response = _mock_response(None)
    function_call = MagicMock()
    function_call.name = "get_weather"
    function_call.args = ["NYC"]
    response.function_calls = [function_call]
    mock_sdk.models.generate_content.return_value = response

    client = GeminiClient(
        config=GeminiClientConfig(api_key="gemini-test", model="gemini-test"),
        client=mock_sdk,
    )
    with pytest.raises(GeminiClientError, match="arguments"):
        client.send_message("weather?")
