"""Tests for the abstract AI client contract."""

from typing import Any

import pytest

from ai_client_api import AIClient


def test_ai_client_cannot_be_instantiated() -> None:
    """``AIClient`` is abstract and must be subclassed."""
    with pytest.raises(TypeError, match="abstract"):
        AIClient()  # type: ignore[abstract]


def test_concrete_subclass_must_implement_send_message() -> None:
    """Missing ``send_message`` keeps the class abstract."""

    class Incomplete(AIClient):
        """Stub missing ``send_message``."""

    with pytest.raises(TypeError, match="abstract"):
        Incomplete()  # type: ignore[abstract]


def test_concrete_implementation() -> None:
    """A minimal subclass satisfies the contract."""

    class Echo(AIClient):
        def send_message(
            self,
            prompt: str,
            context: dict[str, Any] | None = None,
            tools: list[dict[str, Any]] | None = None,
        ) -> str:
            del context
            del tools
            return prompt.upper()

    client = Echo()
    assert client.send_message("hello") == "HELLO"
