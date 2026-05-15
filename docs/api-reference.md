# API Reference

## Interface Component: `chat_client_api`

The shared contract is defined by
[HarshithKoriRaj/Shared-API](https://github.com/HarshithKoriRaj/Shared-API).

### `ChatClient`

- `send_message(channel_id: str, text: str) -> Message`
- `get_channels() -> list[Channel]`
- `get_channel(channel_id: str) -> Channel`
- `get_messages(channel_id: str, limit: int = 10, cursor: str | None = None) -> list[Message]`
- `get_message(message_id: str) -> Message`
- `delete_message(message_id: str) -> None`

### `Message`

- `message_id: str`
- `channel: str`
- `text: str`
- `sender: str`
- `timestamp: str`

### `Channel`

- `channel_id: str`
- `name: str`
- `is_private: bool | None`
- `channel_type: str | None`

### Factory Hooks

- `get_client() -> ChatClient`
- `register_client(factory: Callable[[], ChatClient]) -> None`

## Implementation Component: `telegram_client_impl`

`telegram_client_impl` provides a Telegram-backed `ChatClient` implementation.

Importing the package performs dependency injection:

```python
import telegram_client_impl
from chat_client_api import get_client
```

The Telegram implementation uses the official Bot API. A deployed service needs
`TELEGRAM_BOT_TOKEN`, `SERVICE_BASE_URL`, and `CHAT_CLIENT_STORE_PATH`.
`get_messages` and `get_channels` read bot-observed state stored locally through
polling, webhook delivery, or service sends.

Bot setup assumptions for developers:

- the bot was created in [@BotFather](https://t.me/BotFather)
- `TELEGRAM_BOT_TOKEN` matches that bot
- if group reads matter, privacy mode is disabled via BotFather `/setprivacy`
  → `Disable`

Message objects use opaque `channel_id:message_id` identifiers so clients can
pass them directly to `DELETE /chat/messages/{message_id}`.

## Service Compatibility

The shared Python API uses `limit` for message retrieval. OpenAPI clients may
send `max_results` on `GET /chat/messages`, so the FastAPI service accepts both
query parameters and forwards the effective value to
`ChatClient.get_messages(..., limit=...)`.

`channel_id` remains explicit on the HTTP service surface. Use `"me"` to target
the authenticated user's direct chat with the bot. The service does not default
missing `channel_id` to `"me"`; callers should pass the alias explicitly.

## Service Auth Surface

`chat_client_service` keeps the `/chat/*` contract stable and adds Telegram
login/session endpoints for HTTP consumers:

- `POST /auth/sessions`
- `GET /auth/login`
- `GET /auth/login/config`
- `GET /auth/callback`
- `POST /auth/callback`
- `POST /auth/telegram-login`
- `POST /auth/verify` (compatibility bridge)
- `GET /auth/sessions/{session_id}`
- `DELETE /auth/sessions/{session_id}`
- `GET /auth/me`

The preferred adapter/client flow is `POST /auth/sessions` followed by
`X-Session-ID` on `/chat/*`. Direct Bearer tokens are still accepted.

`POST /auth/sessions` and `GET /auth/login/config` also return `bot_username`
and `bot_start_url`. Use that Telegram deep link to open the correct bot and
press Start before sending to `channel_id="me"` if the bot has never chatted
with the user before.

### Session-First API Client Flow

The intended HTTP client flow is:

1. `POST /auth/sessions`
2. Open the returned `login_url`
3. If present, use `bot_start_url` to open the configured bot in Telegram and
   press Start
4. Poll `GET /auth/sessions/{session_id}` until `authenticated=true`
5. Send `X-Session-ID: <session_id>` on `/chat/*`

Example PowerShell flow:

```powershell
$base = "https://chat-client-service.onrender.com"

$session = Invoke-RestMethod -Method POST -Uri "$base/auth/sessions"
Start-Process $session.login_url

Invoke-RestMethod -Uri $session.status_url | ConvertTo-Json -Depth 5

$headers = @{
  "X-Session-ID" = $session.session_id
}

Invoke-RestMethod -Uri "$base/auth/me" -Headers $headers | ConvertTo-Json -Depth 5

$sent = Invoke-RestMethod `
  -Method POST `
  -Uri "$base/chat/messages" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"channel_id":"me","text":"hello from powershell"}'

Invoke-RestMethod `
  -Uri "$base/chat/messages?channel_id=me" `
  -Headers $headers | ConvertTo-Json -Depth 5
```

Example macOS Terminal flow:

```bash
BASE="https://chat-client-service.onrender.com"

SESSION_JSON="$(curl -sS -X POST "$BASE/auth/sessions")"
SESSION_ID="$(printf '%s' "$SESSION_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')"
LOGIN_URL="$(printf '%s' "$SESSION_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["login_url"])')"
STATUS_URL="$(printf '%s' "$SESSION_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status_url"])')"
BOT_START_URL="$(printf '%s' "$SESSION_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("bot_start_url") or "")')"

open "$LOGIN_URL"
[ -n "$BOT_START_URL" ] && open "$BOT_START_URL"

curl -sS "$STATUS_URL"

AUTH_HEADER="X-Session-ID: $SESSION_ID"
curl -sS -H "$AUTH_HEADER" "$BASE/auth/me"

curl -sS \
  -X POST \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"channel_id":"me","text":"hello from mac terminal"}' \
  "$BASE/chat/messages"
```

`channel_id` remains explicit. Use `"me"` to target the logged-in user's DM
with the bot.

If `POST /chat/messages` returns a `"chat not found"`-style error for
`channel_id="me"`, the service should guide the user to:

- open the exact bot identified by `bot_username` / `bot_start_url`
- press Start
- retry the request
- if it still fails, log in again and make sure the same bot was used
## Components

Documentation for chat client components will be added here as the implementation develops.
