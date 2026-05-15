"""Errors raised by the OpenAI client implementation."""


class OpenAIClientError(RuntimeError):
    """Raised when the OpenAI-backed client cannot complete a request."""
