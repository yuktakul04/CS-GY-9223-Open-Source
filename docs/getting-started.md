# Getting Started

## Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yuktakul04/CS-GY-9223-Open-Source.git
   cd CS-GY-9223-Open-Source
   ```

2. Install dependencies using uv:
   ```bash
   uv sync --all-packages --extra dev
   ```

## Local Service Startup

Start the service from the repo root:

```bash
PYTHONPATH="$PWD/components/chat_client_service/src:$PWD/components/telegram_client_impl/src:$PWD/components/ai_client_api/src:$PWD/components/openai_client_impl/src:$PWD/components/gemini_client_impl/src:$PWD/components/issue_tracker_integration/src" \
uv run --package chat-client-service python -m uvicorn "chat_client_service.app:app" --reload
```

Required environment variables:

- `CHAT_CLIENT_PROVIDER=telegram` or `slack`
- `TELEGRAM_BOT_TOKEN`
- `SERVICE_BASE_URL`
- `TELEGRAM_UPDATE_MODE=polling` or `webhook`
- `SLACK_BOT_TOKEN` when using the Slack provider

The Slack provider swap only changes the backend used by `/chat/...`. Team 4's
Telegram login/session auth still protects those endpoints, so keep
`TELEGRAM_BOT_TOKEN` and `SERVICE_BASE_URL` configured even when
`CHAT_CLIENT_PROVIDER=slack`.

Optional AI variables:

- `CHAT_CLIENT_ASSISTANT_PROVIDER=openai` or `gemini`
- `OPENAI_API_KEY` or `GEMINI_API_KEY`

Optional issue tracker variables:

- `TRELLO_API_KEY`
- `TRELLO_TOKEN`
- `TRELLO_BOARD_ID`

## Local Client Session Flow

```bash
curl -X POST "$BASE_URL/auth/sessions" > session.json
open "$(python3 -c "import json; print(json.load(open('session.json'))['login_url'])")"
export SESSION_ID="$(python3 -c "import json; print(json.load(open('session.json'))['session_id'])")"
curl -H "X-Session-ID: $SESSION_ID" "$BASE_URL/auth/me"
curl -X POST "$BASE_URL/chat/messages" -H "X-Session-ID: $SESSION_ID" -H "Content-Type: application/json" -d '{"channel_id":"me", "text":"hello"}'
curl -H "X-Session-ID: $SESSION_ID" "$BASE_URL/chat/messages?channel_id=me"
curl -H "X-Session-ID: $SESSION_ID" "$BASE_URL/chat/channels"
```

For the Slack provider swap, use the same session header and change only the
provider env and channel id:

```bash
export CHAT_CLIENT_PROVIDER=slack
export SLACK_BOT_TOKEN=xoxb-...
curl -X POST "$BASE_URL/chat/messages" \
  -H "X-Session-ID: $SESSION_ID" \
  -H "Content-Type: application/json" \
  -d '{"channel_id":"C1234567890","text":"hello from Slack provider"}'
```

Team 9's standalone Slack OAuth auth uses `SLACK_CLIENT_ID`,
`SLACK_CLIENT_SECRET`, and `SLACK_REDIRECT_URI`. This branch imports Team 9's
`slack_client_impl` chat provider through a pinned git dependency only, not that
auth layer.

## AI Assistant Webhook Test

The AI assistant is triggered by inbound Telegram updates, not by
`POST /chat/messages`.

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

Plain AI replies require only the AI env vars. Issue tracker AI tool calls also
require `TRELLO_API_KEY` and `TRELLO_TOKEN`.

## Running Tests

```bash
uv run pytest
```

## Using Dependency Injection

```python
import telegram_client_impl
from chat_client_api import get_client

client = get_client(interactive=False)
```

## Building Documentation

```bash
uv run mkdocs serve
```
