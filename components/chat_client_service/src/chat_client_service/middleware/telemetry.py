"""Telemetry middleware for emitting AWS Embedded Metric Format metrics."""

from __future__ import annotations

import json
import logging
from time import perf_counter, time
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

from chat_client_service.middleware.cloudwatch import get_telemetry_logger

_LOGGER = logging.getLogger(__name__)

_NAMESPACE = "OSPSD/HW3"
_SERVICE = "chat_client_service"
# sentinel: 0 means an exception escaped before any HTTP response was produced
_UNHANDLED_EXCEPTION_STATUS_CODE = 0
_FAILURE_STATUS_THRESHOLD = 400

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import Request, Response


def _endpoint_from_request(request: Request) -> str:
    """Return the FastAPI route template when available."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path


def _build_request_metrics_event(  # noqa: PLR0913
    *,
    service: str,
    endpoint: str,
    latency_ms: float,
    status_code: int,
    success: int,
    failure: int,
) -> dict[str, object]:
    """Build an EMF event for an HTTP request."""
    return {
        "Service": service,
        "Endpoint": endpoint,
        "StatusCode": status_code,
        "RequestLatency": latency_ms,
        "SuccessRate": success,
        "FailureRate": failure,
        "_aws": {
            "Timestamp": int(time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Dimensions": [["Service", "Endpoint"]],
                    "Metrics": [
                        {"Name": "RequestLatency", "Unit": "Milliseconds"},
                        {"Name": "SuccessRate", "Unit": "Count"},
                        {"Name": "FailureRate", "Unit": "Count"},
                    ],
                    "Namespace": _NAMESPACE,
                }
            ],
        },
    }


async def _publish_request_metrics(  # noqa: PLR0913
    *,
    service: str,
    endpoint: str,
    latency_ms: float,
    status_code: int,
    success: int,
    failure: int,
) -> None:
    """Emit a single EMF event for an HTTP request."""
    event = _build_request_metrics_event(
        service=service,
        endpoint=endpoint,
        latency_ms=latency_ms,
        status_code=status_code,
        success=success,
        failure=failure,
    )
    get_telemetry_logger().info(json.dumps(event))


async def _publish_request_metrics_safe(  # noqa: PLR0913
    *,
    service: str,
    endpoint: str,
    latency_ms: float,
    status_code: int,
    success: int,
    failure: int,
) -> None:
    """Emit telemetry; swallow failures so logging cannot break HTTP responses."""
    try:
        await _publish_request_metrics(
            service=service,
            endpoint=endpoint,
            latency_ms=latency_ms,
            status_code=status_code,
            success=success,
            failure=failure,
        )
    except Exception:
        _LOGGER.exception(
            "Failed to publish request telemetry for endpoint %s",
            endpoint,
        )


class TelemetryMiddleware(BaseHTTPMiddleware):
    """Emit EMF telemetry for every HTTP request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Measure a request and emit telemetry for the response."""
        start = perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            latency_ms = (perf_counter() - start) * 1000
            await _publish_request_metrics_safe(
                service=_SERVICE,
                endpoint=_endpoint_from_request(request),
                latency_ms=latency_ms,
                status_code=_UNHANDLED_EXCEPTION_STATUS_CODE,
                success=0,
                failure=1,
            )
            raise

        latency_ms = (perf_counter() - start) * 1000
        is_failure = int(response.status_code >= _FAILURE_STATUS_THRESHOLD)
        await _publish_request_metrics_safe(
            service=_SERVICE,
            endpoint=_endpoint_from_request(request),
            latency_ms=latency_ms,
            status_code=response.status_code,
            success=1 - is_failure,
            failure=is_failure,
        )
        return response
