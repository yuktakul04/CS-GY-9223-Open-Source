"""Abstract base class for AI client implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable


class _ToolCallResponseRequired(TypedDict):
    name: str
    arguments: dict[str, Any]


class ToolCallResponse(_ToolCallResponseRequired, total=False):
    """Structured tool invocation returned by an LLM response.

    ``name`` and ``arguments`` are always present. ``output`` is optional
    and may be populated after the tool has been executed with its result.
    """

    output: str | None


class AIClient(ABC):
    """Protocol for LLM-backed text generation."""

    @abstractmethod
    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str | ToolCallResponse:
        """Process ``prompt`` and return the model's response.

        Returns a plain ``str`` for text-only responses, or a
        ``ToolCallResponse`` dict when the model invokes a tool. The
        ``ToolCallResponse`` includes the tool ``name``, its ``arguments``,
        and optionally an ``output`` field populated after the tool has been
        executed and its result recorded.
        """


class _ClientRegistry:
    """Holds the registered AI client factory."""

    _factory: Callable[[], AIClient] | None = None

    @classmethod
    def set(cls, factory: Callable[[], AIClient]) -> None:
        """Register a factory that constructs an ``AIClient``."""
        cls._factory = factory

    @classmethod
    def get(cls) -> Callable[[], AIClient] | None:
        """Return the registered factory, if any."""
        return cls._factory


def get_client() -> AIClient:
    """Return an instance of the registered ``AIClient`` implementation."""
    factory = _ClientRegistry.get()
    if factory is None:
        msg = (
            "No AI client implementation registered. "
            "Import an implementation package to register it."
        )
        raise RuntimeError(msg)
    return factory()


def register_client(factory: Callable[[], AIClient]) -> None:
    """Register an ``AIClient`` implementation factory."""
    _ClientRegistry.set(factory)
