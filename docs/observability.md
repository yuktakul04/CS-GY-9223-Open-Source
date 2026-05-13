# Observability

Every HTTP request emits a structured metric event to CloudWatch. There is
no custom collector — CloudWatch parses the events directly via AWS
Embedded Metric Format (EMF).

## Telemetry Middleware

[`TelemetryMiddleware`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/blob/main/components/chat_client_service/src/chat_client_service/middleware/telemetry.py)
wraps every FastAPI request:

1. Records `perf_counter()` at request entry.
2. Calls the downstream handler, catching exceptions.
3. Classifies the response — `status_code >= 400` (or an uncaught
   exception) is a failure.
4. Builds an EMF JSON event and logs it via the dedicated telemetry
   logger.

Metric emission is wrapped in `_publish_request_metrics_safe`, which
swallows logging exceptions so telemetry can never break a real HTTP
response.

## EMF Format

Each event embeds a `_aws` block CloudWatch recognizes:

```json
{
  "Service": "chat_client_service",
  "Endpoint": "/messages/{message_id}",
  "StatusCode": 200,
  "RequestLatency": 42.3,
  "SuccessRate": 1,
  "FailureRate": 0,
  "_aws": {
    "Timestamp": 1736900000000,
    "CloudWatchMetrics": [{
      "Dimensions": [["Service", "Endpoint"]],
      "Metrics": [
        {"Name": "RequestLatency", "Unit": "Milliseconds"},
        {"Name": "SuccessRate", "Unit": "Count"},
        {"Name": "FailureRate", "Unit": "Count"}
      ],
      "Namespace": "OSPSD/HW3"
    }]
  }
}
```

## Metrics

Namespace: **`OSPSD/HW3`**. Dimensions: **`Service`** (constant
`chat_client_service`) and **`Endpoint`** (the FastAPI route template, e.g.
`/messages/{message_id}`, falling back to the raw URL path when no route
matches).

| Metric          | Unit         | Per request                    |
|-----------------|--------------|--------------------------------|
| `RequestLatency`| Milliseconds | Wall-clock latency             |
| `SuccessRate`   | Count        | `1` for `< 400`, else `0`      |
| `FailureRate`   | Count        | `1` for `>= 400` or exception  |

## Transport

[`middleware/cloudwatch.py`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/blob/main/components/chat_client_service/src/chat_client_service/middleware/cloudwatch.py)
builds the telemetry logger. When `CHAT_CLIENT_CLOUDWATCH_ENABLED=true`,
it attaches a `watchtower.CloudWatchLogHandler` against the log group
named by `CHAT_CLIENT_CLOUDWATCH_LOG_GROUP` (default
`chat-client-service-logs`). If the handler fails to construct (no AWS
creds, etc.) or the env var is unset, it falls back to a stdout handler so
events remain visible locally.

Region resolution: `CHAT_CLIENT_CLOUDWATCH_REGION` → `AWS_REGION` →
`AWS_DEFAULT_REGION`.

## Dashboard

[`infra/main.tf`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/blob/main/infra/main.tf)
provisions the `OSPSD-HW3-ChatService` dashboard with two widgets:

- **Request Latency** — average `RequestLatency` per endpoint.
- **Service Health** — `Sum(SuccessRate)` vs `Sum(FailureRate)`.

Both widgets use CloudWatch `SEARCH` expressions over
`{OSPSD/HW3, Service, Endpoint}`, so new endpoints appear automatically
the first time they emit a metric — no Terraform change is required to
chart a newly added route.
