"""Retry and circuit-breaker helpers for AI client implementations."""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class CircuitBreakerOpenError(RuntimeError):
    """Raised when the circuit breaker is open and calls are rejected."""


class CircuitBreaker:
    """Fail fast after consecutive request failures until recovery."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        """Configure failure threshold and recovery timeout in seconds."""
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def consecutive_failures(self) -> int:
        """Return the current consecutive failure count."""
        return self._consecutive_failures

    @property
    def is_open(self) -> bool:
        """Return whether the breaker is currently rejecting calls."""
        if self._opened_at is None:
            return False
        return time.monotonic() - self._opened_at < self._recovery_timeout

    def before_call(self) -> None:
        """Reject the call when the breaker is open and not yet recovered."""
        if self._opened_at is None:
            return
        if time.monotonic() - self._opened_at >= self._recovery_timeout:
            self._opened_at = None
            self._consecutive_failures = 0
            return
        msg = "circuit breaker is open"
        raise CircuitBreakerOpenError(msg)

    def record_success(self) -> None:
        """Reset breaker state after a successful request."""
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        """Track a failed request and open the breaker at the threshold."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._opened_at = time.monotonic()


def call_with_resilience[T](
    operation: Callable[[], T],
    *,
    is_transient: Callable[[BaseException], bool],
    circuit_breaker: CircuitBreaker,
    max_retries: int = 3,
    base_delay: float = 0.5,
) -> T:
    """Execute ``operation`` with bounded retries and circuit-breaker tracking."""
    circuit_breaker.before_call()
    for attempt in range(max_retries + 1):
        try:
            result = operation()
        except BaseException as exc:
            if not is_transient(exc) or attempt >= max_retries:
                circuit_breaker.record_failure()
                raise
            delay = base_delay * (2**attempt) + random.uniform(0.0, base_delay)  # noqa: S311
            time.sleep(delay)
        else:
            circuit_breaker.record_success()
            return result
    msg = "resilience retry loop exhausted without result"
    raise RuntimeError(msg)
