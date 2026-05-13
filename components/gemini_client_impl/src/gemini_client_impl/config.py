"""Configuration for Gemini client setup."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class GeminiClientConfig:
    """Static configuration for :class:`GeminiClient`."""

    api_key: str
    model: str

    @classmethod
    def from_env(cls) -> GeminiClientConfig:
        """Load config from environment variables."""
        return cls(
            api_key=getenv("GEMINI_API_KEY", ""),
            model=getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        )
