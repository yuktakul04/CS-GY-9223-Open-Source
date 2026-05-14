# Deployment

The chat service ships as a single FastAPI application deployed to Render,
with AWS-side telemetry resources provisioned by Terraform.

## Render Blueprint

[`render.yaml`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/blob/main/render.yaml)
defines a single `web` service:

```yaml
type: web
name: chat-client-service
runtime: python
buildCommand: python -m pip install --upgrade pip && python -m pip install -r requirements-render.txt
startCommand: python -m uvicorn chat_client_service.app:app --host 0.0.0.0 --port $PORT
healthCheckPath: /health
```

Render builds against
[`requirements-render.txt`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/blob/main/requirements-render.txt) — a flat lockfile usable
outside the uv workspace — and runs the FastAPI app under uvicorn.
`/health` is the liveness probe.

### Environment Variables

| Variable | Purpose | Notes |
|----------|---------|-------|
| `TELEGRAM_BOT_TOKEN` | Bot API auth | Secret, set in Render UI |
| `SERVICE_BASE_URL` | Public URL for webhooks/links | Secret |
| `APP_SESSION_TTL_SECONDS` | OIDC session lifetime | Default `3600` |
| `CHAT_CLIENT_PROVIDER` | `telegram` or `slack` | Selects ChatClient backend |
| `CHAT_CLIENT_STORE_PATH` | SQLite path | Default `/tmp/chat_client.sqlite3` (Render ephemeral) |
| `SLACK_BOT_TOKEN` | Slack bot auth | Required when `CHAT_CLIENT_PROVIDER=slack` |
| `CHAT_CLIENT_ALLOWED_CHANNEL_IDS` | Provider-neutral channel allowlist | Required for Slack demo channels |
| `TELEGRAM_UPDATE_MODE` | `polling` or `webhook` | Default `polling` |
| `TELEGRAM_POLL_INTERVAL_SECONDS` | Long-poll interval | Default `3` |
| `CHAT_CLIENT_ASSISTANT_PROVIDER` | `openai` or `gemini` | Selects AI backend |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | Provider auth | Whichever provider is selected |
| `TRELLO_API_KEY` / `TRELLO_TOKEN` | Issue tracker auth | Optional; tools disabled if absent |
| `TRELLO_BOARD_ID` | Default board scope | Optional |
| `CHAT_CLIENT_CLOUDWATCH_ENABLED` | Enable EMF transport | `true` for cloud, off otherwise |
| `AWS_REGION` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | AWS auth | Required when CloudWatch enabled |

### Slack Provider-Swap Variables

Team 4's production path should stay Telegram-first:

```bash
CHAT_CLIENT_PROVIDER=telegram
```

For the same-vertical Slack demo, use a separate Render service or temporarily
switch the existing service and redeploy/restart:

```bash
CHAT_CLIENT_PROVIDER=slack
SLACK_BOT_TOKEN=xoxb-...
CHAT_CLIENT_ALLOWED_CHANNEL_IDS=C1234567890
```

Keep Team 4's existing service-auth variables such as `TELEGRAM_BOT_TOKEN`,
`SERVICE_BASE_URL`, and `APP_SESSION_SECRET`. The generic `/chat/...` endpoints
still require Team 4 service auth through `X-Session-ID` or `Authorization`.

Do not add `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, or `SLACK_REDIRECT_URI`
unless you are building a separate Slack OAuth auth integration. Those variables
belong to Team 9's standalone Slack OAuth service auth, which this branch does
not import.

## Terraform IaC

[`infra/main.tf`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/blob/main/infra/main.tf)
provisions four AWS resources in `us-east-1`:

1. `aws_iam_policy.telemetry_policy` — `logs:Create*`, `logs:PutLogEvents`,
   and `cloudwatch:PutMetricData` for the service.
2. `aws_cloudwatch_log_group.chat_service_logs` — log group
   `chat-client-service-logs`, 7-day retention.
3. `aws_cloudwatch_dashboard.main` — the `OSPSD-HW3-ChatService`
   dashboard.

State is local (`infra/*.tfstate`, gitignored).

## Bootstrap

1. **Provision AWS**:
   ```sh
   cd infra
   terraform init
   terraform apply
   ```
   Attach the printed IAM policy ARN to the IAM user whose credentials
   the Render service uses.

2. **Create the Render service** by connecting the GitHub repo with the
   blueprint; fill in the secret env vars listed above.

3. **Verify**: hit `/health`, then watch the
   `OSPSD-HW3-ChatService` dashboard — first request populates both
   widgets within ~60s.
