"""Custom errors for telegram_client_impl."""

from __future__ import annotations

from typing import Any


class TelegramClientError(Exception):
    """Base exception for Telegram client errors."""

    def __init__(
        self,
        message: str,
        *,
        method: str | None = None,
        error_code: int | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        """Initialize an error while preserving Telegram response metadata."""
        super().__init__(message)
        self.method = method
        self.error_code = error_code
        self.parameters = parameters or {}


class TelegramAuthError(TelegramClientError):
    """Raised when authentication setup is invalid."""


class TelegramMappingError(TelegramClientError):
    """Raised when provider objects cannot be mapped to API models."""
