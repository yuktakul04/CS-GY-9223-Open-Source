# Telegram Client Implementation

This package implements the shared
[`chat_client_api`](https://github.com/HarshithKoriRaj/Shared-API)
`ChatClient` for Telegram using the official Bot API.

## Registration

On import, the package calls `register_client(get_client_impl)` so
`from chat_client_api import get_client` returns a configured `TelegramClient`.

## Usage

```python
import telegram_client_impl
from chat_client_api import get_client

client = get_client()
```

## Environment Variables

Required:

- `TELEGRAM_BOT_TOKEN`

Optional:

- `TELEGRAM_BOT_API_BASE_URL`
- `TELEGRAM_INTERACTIVE`
- `CHAT_CLIENT_STORE_PATH`
- `TELEGRAM_UPDATE_MODE`
- `TELEGRAM_POLL_INTERVAL_SECONDS`

## Opaque Message IDs

Telegram message ids are exposed as `<chat_id>:<telegram_message_id>`.
`get_message`, `delete_message`, and returned `Message.message_id` values use
that format.

## Behavior

- `get_messages` returns bot-observed messages stored locally
- `cursor=<last_message_id>` returns only newer stored messages
- `get_channel` / `get_message` raise `ValueError` when missing
- `delete_message(message_id)` expects the opaque id returned by reads/sends
- `channel_id="me"` is handled at the service layer as the logged-in user's DM
  with the bot

This is not a full Telegram account client. It does not list arbitrary user
dialogs or read arbitrary Telegram history. Reads are limited to messages the
configured bot observed through polling, webhook delivery, or service sends.
