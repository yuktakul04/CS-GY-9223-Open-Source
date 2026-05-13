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

- **Live service:** `YOUR_RENDER_URL` (e.g. `https://chat-client-service-XXXX.onrender.com`)
- **Health check:** `YOUR_RENDER_URL/health`
- **API docs (Swagger UI):** `YOUR_RENDER_URL/docs`
- **Telemetry dashboard:** [OSPSD-HW3-ChatService on CloudWatch](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=OSPSD-HW3-ChatService)

CircleCI pings the Render deploy hook on green builds of `gemini-client` and
`main`; see [`.circleci/config.yml`](.circleci/config.yml).

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

## Deploying to Render

This repository includes a Render Blueprint at `render.yaml` for
`chat_client_service`.

Minimal working Render setup:

- `TELEGRAM_BOT_TOKEN`
- `SERVICE_BASE_URL`
- `GEMINI_API_KEY`

That is the setup the experimental branch optimized for: set the bot token and
base URL, then let the blueprint supply the rest.

The current `render.yaml` already provides defaults for:

- `TELEGRAM_UPDATE_MODE=polling`
- `TELEGRAM_POLL_INTERVAL_SECONDS=3`
- `APP_SESSION_TTL_SECONDS=3600`
- `CHAT_CLIENT_STORE_PATH=/tmp/chat_client.sqlite3`

So on the free Render plan, you do not need to set those manually unless you
are intentionally changing behavior.

Important storage note:

- the current free-plan blueprint uses `/tmp/chat_client.sqlite3`
- that is writable on free Render, but it is ephemeral
- if the service restarts or redeploys, auth sessions and stored bot-observed
  messages can be lost

If you move to a paid plan with a persistent disk, then switch to:

- `CHAT_CLIENT_STORE_PATH=/var/data/chat_client.sqlite3`

Optional variables:

- `APP_SESSION_SECRET` (signing override; defaults to the bot token)
- `APP_SESSION_TTL_SECONDS`
- `TELEGRAM_OIDC_CLIENT_ID` (optional override; otherwise derived from the bot id)
- `TELEGRAM_OIDC_CLIENT_SECRET` (optional override only for explicit code flow)
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_BOT_API_BASE_URL`

Do not set optional variables unless you actually need them. The more you
change away from the minimal working setup, the more ways there are to drift
from the proven deployment path.

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
