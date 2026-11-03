"""Custom errors for telegram_client_impl."""


class TelegramClientError(Exception):
    """Base exception for Telegram client errors."""


class TelegramAuthError(TelegramClientError):
    """Raised when authentication setup is invalid."""


class TelegramMappingError(TelegramClientError):
    """Raised when provider objects cannot be mapped to API models."""
