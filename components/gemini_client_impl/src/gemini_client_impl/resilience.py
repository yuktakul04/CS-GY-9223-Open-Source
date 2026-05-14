"""Gemini-specific transient error classification for resilience helpers."""

from __future__ import annotations

from google.genai.errors import APIError, ServerError

_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR_THRESHOLD = 500


def is_transient_error(exc: BaseException) -> bool:
    """Return whether ``exc`` should be retried for Gemini requests."""
    if isinstance(exc, (TimeoutError, ServerError)):
        return True
    return isinstance(exc, APIError) and (
        exc.code == _HTTP_TOO_MANY_REQUESTS or exc.code >= _HTTP_SERVER_ERROR_THRESHOLD
    )
