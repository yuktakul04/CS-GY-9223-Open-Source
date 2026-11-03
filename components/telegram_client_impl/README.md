# Telegram Client Implementation (Scaffold)

This package provides a scaffold implementation of `chat_client_api` for Telegram.

## Purpose

- Register a concrete implementation via dependency injection
- Keep the interface (`chat_client_api`) free of Telegram-specific details
- Provide typed placeholders for authentication, mapping, and client operations

## Usage

```python
import telegram_client_impl  # Registers factory injection
from chat_client_api import get_client

client = get_client(interactive=False)
```

## Environment Variables

The scaffold reads these variables:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_SESSION_NAME` (optional)

No secrets are hardcoded.

## Scaffold Status

Core methods are intentionally unimplemented and raise `NotImplementedError`.
