"""Configuration for OpenAI client setup."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class OpenAIClientConfig:
    """Static configuration for :class:`OpenAIClient`."""

    api_key: str
    model: str

    @classmethod
    def from_env(cls) -> OpenAIClientConfig:
        """Load config from environment variables."""
        return cls(
            api_key=getenv("OPENAI_API_KEY", ""),
            model=getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )
