"""OpenAI-specific transient error classification for resilience helpers."""

from __future__ import annotations

from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

_HTTP_SERVER_ERROR_THRESHOLD = 500


def is_transient_error(exc: BaseException) -> bool:
    """Return whether ``exc`` should be retried for OpenAI requests."""
    if isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)):
        return True
    return (
        isinstance(exc, APIStatusError)
        and exc.status_code >= _HTTP_SERVER_ERROR_THRESHOLD
    )
