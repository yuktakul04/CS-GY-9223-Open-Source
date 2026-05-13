"""Abstract base class for AI client implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable


class ToolCallResponse(TypedDict):
    """Structured tool invocation returned by an LLM response."""

    name: str
    arguments: dict[str, Any]


class AIClient(ABC):
    """Protocol for LLM-backed text generation."""

    @abstractmethod
    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str | ToolCallResponse:
        """Return model text or a structured tool call for ``prompt``."""


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
