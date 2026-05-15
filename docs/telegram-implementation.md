# Telegram Implementation

## Package Layout

- `components/telegram_client_impl/pyproject.toml`
- `components/telegram_client_impl/README.md`
- `components/telegram_client_impl/src/telegram_client_impl/*.py`
- `components/chat_client_service/src/chat_client_service/*.py`

## Injection Behavior

When `telegram_client_impl` is imported, it registers an implementation factory
into `chat_client_api` through `register_client(get_client_impl)`.

Application code depends on the shared `chat_client_api` contract, not on
Telegram-specific implementation details.

## Authentication

The service uses Telegram OIDC / Login plus a local service session.

- `POST /auth/sessions` creates a pending service session
- `GET /auth/login?flow=page` serves the hosted Telegram Login page
- `GET /auth/login?flow=code` starts Telegram OIDC Authorization Code Flow with PKCE
- `GET /auth/login/config` supports Telegram's Login library for custom frontends
- `GET /auth/callback` completes OIDC code flow
- `POST /auth/callback` verifies Telegram Login library `id_token`
- `POST /auth/telegram-login` verifies signed `tgAuthResult` payloads
- `GET /auth/sessions/{session_id}` reports whether browser login completed
- `X-Session-ID` and the browser cookie both identify the same local service session

Required service variables:

- `TELEGRAM_BOT_TOKEN`
- `SERVICE_BASE_URL`
- `CHAT_CLIENT_STORE_PATH`

Optional variables:

- `APP_SESSION_SECRET` (optional signing override; defaults to bot token)
- `APP_SESSION_TTL_SECONDS`
- `TELEGRAM_OIDC_CLIENT_ID` (optional override; otherwise derived from the bot id)
- `TELEGRAM_OIDC_CLIENT_SECRET` (optional override only for explicit code flow)
- `TELEGRAM_UPDATE_MODE`
- `TELEGRAM_POLL_INTERVAL_SECONDS`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_BOT_API_BASE_URL`

API consumers do not need Telegram API ID/hash values or user session strings.
Telegram documents both supported login paths in
[Log In With Telegram](https://core.telegram.org/bots/telegram-login).

## Bot-Scoped Chat Behavior

Bot API does not expose arbitrary user Telegram history. Therefore:

- `POST /chat/messages` sends through the service bot
- `GET /chat/messages` returns stored bot-observed or bot-sent messages
- `GET /chat/messages/{message_id}` returns one stored message by opaque id
- `GET /chat/channels` returns chats known to the bot
- `GET /chat/channels/{channel_id}` returns one known chat
- `DELETE /chat/messages/{message_id}` deletes when Telegram allows it

`channel_id="me"` means the logged-in user's direct chat with the bot.
If an example uses `OSSHWBOTTEST`, replace it with any group or channel where
the bot is present.

## Update Ingestion

Telegram bot updates arrive in one of two mutually exclusive ways:

- polling with `getUpdates`
- webhook delivery to `/telegram/webhook`

Telegram only stores unconsumed updates for a limited time, so this service does
not treat Bot API updates as durable history. Reads come from local SQLite state
populated by messages sent through the service, polling, or webhook delivery.

For Render, the recommended path is:

- `TELEGRAM_UPDATE_MODE=polling`
- persistent disk mounted at `/var/data`
- `CHAT_CLIENT_STORE_PATH=/var/data/chat_client.sqlite3`

The service starts a singleton background poller and stores observed messages in
SQLite. `/chat/*` then reads from that stored bot state.

Webhook mode is still supported. If `TELEGRAM_WEBHOOK_SECRET` is set, the
service verifies `X-Telegram-Bot-Api-Secret-Token` before recording updates.

## Access Checks

The service checks chat access with Telegram `getChatMember` when local access
state is missing. This is authoritative for groups and supergroups where the bot
can query membership. For channels, Telegram may require the bot to be an
administrator before it can query non-admin member status; in that case the
service denies access conservatively.
