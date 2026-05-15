# CS-GY-9223 Open Source

A chat client workspace with a shared vertical API, a Telegram-backed service,
AI client components, and issue tracker integration.

## Team

**Team name:** Team 4

**Members:**

- Yukta Kulkarni — yk3213 (yuktakul04)
- Sumanth Subramanian Ramesh — sr7420
- Karthik Subramanian — ks7886
- Pranav Raj N K — pn2330
- Mohamed Yaseen Mohamed Shuaib — mm14451

## Deployment

The service is deployed on Render via [`render.yaml`](render.yaml) and observed
through an AWS CloudWatch dashboard provisioned by Terraform.

- **Live service:** https://chat-client-service-xer8.onrender.com
- **Health check:** https://chat-client-service-xer8.onrender.com/health
- **API docs (Swagger UI):** https://chat-client-service-xer8.onrender.com/docs
- **Telemetry dashboard:** [OSPSD-HW3-ChatService on CloudWatch](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=OSPSD-HW3-ChatService)

CircleCI pings the Render deploy hook on green builds of `hw3`; see
[`.circleci/config.yml`](.circleci/config.yml).

## CI/CD

The CircleCI pipeline runs in four sequential tiers:

```
lint → unit-tests → integration-tests → e2e-tests → deploy
```

Each tier runs independently. Coverage threshold is enforced on unit tests.
Pushes to `hw3` automatically deploy to Render on green builds.

## Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
git clone https://github.com/yuktakul04/CS-GY-9223-Open-Source.git
cd CS-GY-9223-Open-Source

uv sync --all-packages --extra dev
```

The shared `chat-client-api` contract is installed from git; see the root
`pyproject.toml` `[tool.uv.sources]` section.

## Development

```bash
uv run pytest
uv run ruff check .
uv run mypy components tests
```

## Local Service Startup

From the repo root:

```bash
PYTHONPATH="$PWD/components/chat_client_service/src:$PWD/components/telegram_client_impl/src:$PWD/components/ai_client_api/src:$PWD/components/openai_client_impl/src:$PWD/components/gemini_client_impl/src:$PWD/components/issue_tracker_integration/src" \
uv run --package chat-client-service python -m uvicorn "chat_client_service.app:app" --reload
```

Core environment variables:

- `TELEGRAM_BOT_TOKEN`
- `SERVICE_BASE_URL`
- `TELEGRAM_UPDATE_MODE=polling` or `webhook`

Optional AI assistant variables:

- `CHAT_CLIENT_ASSISTANT_PROVIDER=openai` or `gemini`
- `OPENAI_API_KEY` or `GEMINI_API_KEY`

Optional issue tracker variables, only needed for issue-tracker AI tools:

- `TRELLO_API_KEY`
- `TRELLO_TOKEN`
- `TRELLO_BOARD_ID`

## Deploying with Terraform

Terraform in `infra/` is the authoritative deployment path for HW3:

- AWS resources in Terraform provision the CloudWatch telemetry layer
- Render resources in Terraform provision the application runtime

The legacy `render.yaml` remains in the repo only as reference. It is no longer
the source of truth once the Terraform-managed Render service is used.

### Required credentials

The repo now includes `scripts/terraform-with-env.sh`, which sources `.env`
and maps the existing simple variable names onto the `TF_VAR_*` aliases
Terraform expects.

Minimal `.env` setup for Terraform:

- `RENDER_API_KEY`
- `RENDER_OWNER_ID`
- `RENDER_SERVICE_PLAN`
- `TELEGRAM_BOT_TOKEN`
- `SERVICE_BASE_URL`
- `GEMINI_API_KEY` or `OPENAI_API_KEY`

Optional `.env` values that the wrapper also maps for Terraform:

- `RENDER_REPO_BRANCH`
- `RENDER_REPO_URL`
- `APP_SESSION_SECRET`
- `TELEGRAM_OIDC_CLIENT_ID`
- `TELEGRAM_OIDC_CLIENT_SECRET`
- `TELEGRAM_WEBHOOK_SECRET`
- `TRELLO_API_KEY`
- `TRELLO_TOKEN`
- `TRELLO_BOARD_ID`
- `CHAT_CLIENT_ASSISTANT_PROVIDER`
- `CHAT_CLIENT_STORE_PATH`
- `TELEGRAM_UPDATE_MODE`
- `TELEGRAM_POLL_INTERVAL_SECONDS`
- `APP_SESSION_TTL_SECONDS`

### Bring up the IaC stack

From the repository root, create or update `.env` with the values above. For
the current Render free-tier deployment, use:

```bash
RENDER_SERVICE_PLAN=free
RENDER_REPO_BRANCH=gemini-client
TELEGRAM_UPDATE_MODE=polling
CHAT_CLIENT_ASSISTANT_PROVIDER=gemini
```

Then initialize Terraform and verify the configuration:

```bash
scripts/terraform-with-env.sh init
scripts/terraform-with-env.sh validate
```

Preview the full infrastructure change before creating resources:

```bash
scripts/terraform-with-env.sh plan
```

Apply the stack when the plan shows the expected Render web service and
CloudWatch resources:

```bash
scripts/terraform-with-env.sh apply
```

After apply, inspect the created resources:

```bash
scripts/terraform-with-env.sh output
```

The output includes:

- `render_service_id`
- `render_service_slug`
- `render_service_url`
- `cloudwatch_dashboard_name`

Use the Render URL as `SERVICE_BASE_URL` in `.env`, then verify the deployed
service health endpoint:

```bash
curl -i "$SERVICE_BASE_URL/health"
```

If the Render URL changes after a replace, update `SERVICE_BASE_URL` in `.env`
to match `render_service_url`. On the free Render plan, direct Terraform
updates to the web service can be limited by Render's API behavior, so the
configuration ignores Render-managed service defaults after creation while
Terraform continues to own the runtime resource itself.

### Secret handling

Sensitive values are not committed to Terraform files. The wrapper reads them
from `.env` and exports the matching Terraform inputs at command runtime, after
which Terraform pushes them to Render as service environment variables.

Important caveat:

- Terraform state can still contain sensitive values
- keep state out of git
- use a secure backend or secure CI workspace when applying in shared contexts

### Default runtime behavior

The Terraform-managed Render service preserves the current deployment defaults:

- `TELEGRAM_UPDATE_MODE=polling`
- `TELEGRAM_POLL_INTERVAL_SECONDS=3`
- `APP_SESSION_TTL_SECONDS=3600`
- `CHAT_CLIENT_STORE_PATH=/tmp/chat_client.sqlite3`
- `CHAT_CLIENT_ASSISTANT_PROVIDER=gemini`

Important storage note:

- `/tmp/chat_client.sqlite3` is writable on Render but ephemeral
- if the service restarts or redeploys, auth sessions and stored bot-observed
  messages can be lost

If you move to a paid plan with persistent disk support, switch
`CHAT_CLIENT_STORE_PATH` to a durable mount path such as `/var/data/chat_client.sqlite3`.

## Infrastructure Setup

The AWS-side telemetry resources are managed by Terraform under [`infra/`](infra/):

```bash
cd infra
terraform init
terraform apply
```

This provisions:

- the `chat-client-service-logs` CloudWatch log group (7-day retention),
- the `ChatServiceTelemetryPolicy` IAM policy granting `logs:Put*` and
  `cloudwatch:PutMetricData`,
- the `OSPSD-HW3-ChatService` CloudWatch dashboard (latency + success/failure
  widgets).

Attach the printed IAM policy ARN to the IAM user whose credentials the Render
service uses, then set `CHAT_CLIENT_CLOUDWATCH_ENABLED=true` in Render so the
service emits EMF metrics to the log group.

## BotFather Setup

Before deploying, create and configure the Telegram bot itself.

Minimum setup:

1. Open [@BotFather](https://t.me/BotFather)
2. Run `/newbot`
3. Choose the bot name and username
4. Copy the generated token into `TELEGRAM_BOT_TOKEN`
5. Open the bot in Telegram and verify the username shown by BotFather matches
   the bot you intend to use for this service

Optional but recommended:

- set the bot description and about text in BotFather so users know what they
  are authenticating against
- set the bot commands if you want a cleaner Telegram UX

Privacy mode:

- private user-to-bot DMs do **not** require disabling privacy mode
- group-message visibility **does** depend on privacy mode

If you want the bot to observe ordinary group messages instead of only commands,
replies, and messages explicitly directed at the bot, disable privacy mode in
BotFather:

1. Open [@BotFather](https://t.me/BotFather)
2. Run `/setprivacy`
3. Select your bot
4. Choose `Disable`

Equivalent UI path in BotFather:

1. `/start`
2. select the bot
3. `Bot Settings`
4. `Group Privacy`
5. turn it off

Telegram documents this behavior in the Bots FAQ and Bot Features pages:

- [What messages will my bot get?](https://core.telegram.org/bots/faq)
- [Privacy Mode](https://core.telegram.org/bots/features)

## Telegram Service Semantics

This is a bot-scoped Telegram implementation:

- sends go out through the configured bot
- reads return messages the bot observed or sent
- `channel_id="me"` means the logged-in user's direct chat with the bot
- `GET /chat/channels` returns chats known to the bot, not arbitrary Telegram dialogs

Message responses return opaque ids in `channel_id:message_id` form. Pass that
value directly to `DELETE /chat/messages/{message_id}`. If a client only has a
simple message id, it must also provide channel context.

If an example uses `OSSHWBOTTEST`, replace it with any group or channel where
the bot is present.

## Auth Flow

The service uses Telegram Login/OIDC plus local service sessions for HTTP
clients.

Primary session-first path:

1. `POST /auth/sessions`
2. Open the returned `login_url`
3. Complete Telegram login
4. Poll `GET /auth/sessions/{session_id}` until `authenticated: true`
5. Use `X-Session-ID: <session_id>` on `/chat/*`

Compact terminal flow:

```bash
curl -X POST "$BASE_URL/auth/sessions" > session.json
open "$(python3 -c "import json; print(json.load(open('session.json'))['login_url'])")"
export SESSION_ID="$(python3 -c "import json; print(json.load(open('session.json'))['session_id'])")"
curl -H "X-Session-ID: $SESSION_ID" "$BASE_URL/auth/me"
curl -X POST "$BASE_URL/chat/messages" -H "X-Session-ID: $SESSION_ID" -H "Content-Type: application/json" -d '{"channel_id":"me", "text":"hello"}'
curl -H "X-Session-ID: $SESSION_ID" "$BASE_URL/chat/messages?channel_id=me"
curl -H "X-Session-ID: $SESSION_ID" "$BASE_URL/chat/channels"
```

Login surfaces:

- `GET /auth/login?flow=page` serves the hosted Telegram Login page
- `GET /auth/login/config` returns `client_id` and `nonce` for custom frontends
- `GET /auth/login?flow=code` forces Telegram OIDC Authorization Code Flow with PKCE
- `GET /auth/callback?code=...&state=...` completes OIDC code flow
- `POST /auth/callback` completes Telegram Login library `id_token` flow
- `POST /auth/telegram-login` completes signed `tgAuthResult` browser-fragment flow

Browser clients can use the HTTP-only `chat_client_session` cookie. Manual/API
clients can use `X-Session-ID` or the returned Bearer token. Logout deletes the
cookie and session-backed `X-Session-ID`; direct Bearer tokens remain valid
until `APP_SESSION_TTL_SECONDS` expires.

Telegram documents both login paths in
[Log In With Telegram](https://core.telegram.org/bots/telegram-login). When
`TELEGRAM_OIDC_CLIENT_SECRET` is configured, the service can use the standards-
based Authorization Code + PKCE path. Without it, the hosted Telegram Login
page and Login library remain available for the same local service session
model.

## Update Delivery

Telegram delivers bot updates one way at a time:

- `TELEGRAM_UPDATE_MODE=polling` starts the background `getUpdates` poller
- `TELEGRAM_UPDATE_MODE=webhook` expects Telegram to POST to `/telegram/webhook`

For Render, the recommended path is polling plus a persistent disk. Reads remain
bot-scoped and return messages stored locally from webhook delivery, background
polling, or messages sent through the service itself.

## AI Assistant Flow

The AI assistant is invoked by inbound Telegram updates, not by
`POST /chat/messages`.

Plain AI replies require:

- `CHAT_CLIENT_ASSISTANT_PROVIDER`
- `OPENAI_API_KEY` or `GEMINI_API_KEY`

Issue tracker tool calls additionally require:

- `TRELLO_API_KEY`
- `TRELLO_TOKEN`

### Resilience Patterns

Both OpenAI and Gemini clients include built-in resilience. Transient errors
(rate limits, timeouts, 5xx) are retried up to 3 times with exponential backoff
and jitter. A circuit breaker prevents repeated calls when the provider is
consistently failing.

Webhook smoke test:

```bash
curl -i -X POST "$BASE_URL/telegram/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "update_id": 999004,
    "message": {
      "message_id": 45,
      "date": 1715200000,
      "text": "Reply exactly with HELLO_TEST_123",
      "chat": {
        "id": 123456789,
        "type": "private",
        "first_name": "Test"
      },
      "from": {
        "id": 123456789,
        "is_bot": false,
        "first_name": "Test",
        "username": "testuser"
      }
    }
  }'
```

Expected behavior:

- the webhook returns `204`
- the assistant calls the configured AI provider
- the bot replies in the referenced Telegram chat

## Project Structure

```
.
├── components/
│   ├── telegram_client_impl/              # Telegram ChatClient implementation
│   ├── chat_client_service/               # FastAPI service wrapper
│   ├── chat_client_service_api_client/    # Generated + stable service client
│   ├── chat_client_adapter/               # Adapter implementing shared ChatClient
│   ├── issue_tracker_integration/         # Team integration component
│   ├── ai_client_api/                     # Shared AI interface
│   ├── openai_client_impl/                # OpenAI implementation
│   └── gemini_client_impl/                # Gemini implementation
├── src/nyu_ospsd_chat/                    # Root Hatch wheel meta-package
├── tests/                                 # Integration / e2e tests
├── docs/                                  # MkDocs documentation
├── .circleci/                             # CircleCI CI/CD configuration
├── infra/                                 # Terraform IaC
├── pyproject.toml                         # Workspace configuration
└── render.yaml                            # Render blueprint
```

## Dependency Injection Usage

```python
import telegram_client_impl
from chat_client_api import get_client

client = get_client()
```

## Documentation

```bash
uv run mkdocs serve
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
