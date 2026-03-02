# Chat Client API

## Overview

`chat_client_api` defines the abstract base classes that every chat client implementation must follow.
This package contains only the abstraction and a factory hook — no concrete logic.

## Purpose

- Document the operations available to consumers of any chat client.
- Provide a single factory (`get_client`) that implementations can override via dependency injection.
- Keep all abstractions explicit through separate modules: `client`, `message`, and `channel`.

## Architecture

### Abstract Base Classes

- **`Client`** — defines chat operations (send, fetch, delete messages; list channels).
- **`Message`** — defines the message contract (id, sender, channel_id, timestamp, text).
- **`Channel`** — defines the channel contract (id, name, channel_type).

### API Usage

```python
from chat_client_api import Client, get_client
from chat_client_api.message import Message

client: Client = get_client()
for msg in client.get_messages(channel_id="general", max_results=5):
    print(msg.text)
```

### Dependency Injection

Implementation packages (e.g. `telegram_client_impl`) replace the factory at import time:

```python
import telegram_client_impl  # rebinds chat_client_api.get_client
from chat_client_api import get_client

client = get_client(interactive=False)
```

## API Reference

### Client Abstract Base Class

| Method | Signature | Description |
|--------|-----------|-------------|
| `send_message` | `(channel_id: str, text: str) -> Message` | Send a message to a channel |
| `get_messages` | `(channel_id: str, max_results: int = 10) -> Iterator[Message]` | Fetch messages from a channel |
| `delete_message` | `(channel_id: str, message_id: str) -> bool` | Delete a message |
| `get_channels` | `() -> Iterator[Channel]` | List available channels |

### Factory Function

`get_client(*, interactive: bool = False) -> Client`

Raises `NotImplementedError` until an implementation package injects itself.

## Implementation Checklist

1. Implement every abstract method in `Client`.
2. Implement every abstract property in `Message` and `Channel`.
3. Publish a factory (`get_client_impl`) and assign it to `chat_client_api.get_client`.
4. Honour the `interactive` flag for authentication flows.
