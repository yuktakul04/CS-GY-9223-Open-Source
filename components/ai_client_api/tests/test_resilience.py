"""Unit tests for :mod:`ai_client_api.resilience`."""

from __future__ import annotations

import pytest

from ai_client_api.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    call_with_resilience,
)


def test_call_with_resilience_retries_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient failures are retried up to ``max_retries``."""
    sleeps: list[float] = []
    attempts = {"count": 0}

    def operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            msg = "temporary"
            raise TimeoutError(msg)
        return "ok"

    monkeypatch.setattr("ai_client_api.resilience.time.sleep", sleeps.append)
    monkeypatch.setattr("ai_client_api.resilience.random.uniform", lambda _a, _b: 0.0)

    breaker = CircuitBreaker(failure_threshold=5)
    result = call_with_resilience(
        operation,
        is_transient=lambda exc: isinstance(exc, TimeoutError),
        circuit_breaker=breaker,
        max_retries=3,
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleeps == [0.5, 1.0]


def test_call_with_resilience_records_failure_after_exhausted_retries() -> None:
    """A fully exhausted retry loop records one circuit-breaker failure."""
    breaker = CircuitBreaker(failure_threshold=2)

    def operation() -> str:
        msg = "temporary"
        raise TimeoutError(msg)

    with pytest.raises(TimeoutError):
        call_with_resilience(
            operation,
            is_transient=lambda exc: isinstance(exc, TimeoutError),
            circuit_breaker=breaker,
            max_retries=3,
        )

    assert breaker.consecutive_failures == 1


def test_circuit_breaker_recovers_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An open breaker allows calls again after the recovery timeout."""
    current = {"value": 10.0}

    def monotonic() -> float:
        return current["value"]

    monkeypatch.setattr("ai_client_api.resilience.time.monotonic", monotonic)

    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=30.0)
    breaker.record_failure()

    current["value"] = 20.0
    with pytest.raises(CircuitBreakerOpenError, match="circuit breaker is open"):
        breaker.before_call()

    current["value"] = 41.0
    breaker.before_call()
    assert breaker.consecutive_failures == 0
