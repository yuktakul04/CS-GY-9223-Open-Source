# Telegram Implementation

## Package Layout

- `components/telegram_client_impl/pyproject.toml`
- `components/telegram_client_impl/README.md`
- `components/telegram_client_impl/src/telegram_client_impl/*.py`

## Injection Behavior

When `telegram_client_impl` is imported, it registers implementation factories into
`chat_client_api`:

- `chat_client_api.get_client`
- `chat_client_api.get_message`

This allows consumers to code against the interface while swapping implementation
by import.

## Authentication Scaffold

Configuration is read from environment variables:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_SESSION_NAME`

No credentials are hardcoded.

## Current Status

This is a first-draft scaffold for HW1. Client methods and mapping logic are
placeholders and raise `NotImplementedError`.
