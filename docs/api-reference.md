# API Reference

## Interface Component: `chat_client_api`

### `Client`

- `send_message(channel_id: str, text: str) -> Message`
- `get_messages(channel_id: str, max_results: int = 10) -> Iterator[Message]`
- `delete_message(channel_id: str, message_id: str) -> bool`
- `get_channels() -> Iterator[Channel]`

### `Message`

- `id: str`
- `sender: str`
- `channel_id: str`
- `timestamp: str`
- `text: str`

### `Channel`

- `id: str`
- `name: str`
- `channel_type: str`

### Factory Hooks

- `get_client(*, interactive: bool = False) -> Client`
- `get_message(msg_id: str, raw_data: str) -> Message`

## Implementation Component: `telegram_client_impl`

`telegram_client_impl` provides scaffold implementations for:

- `TelegramClient`
- `TelegramMessage`
- `TelegramChannel`

Importing the package performs dependency injection:

```python
import telegram_client_impl
from chat_client_api import get_client
```

The current implementation is scaffold-only and intentionally raises
`NotImplementedError` for provider operations.
## Components

Documentation for chat client components will be added here as the implementation develops.
