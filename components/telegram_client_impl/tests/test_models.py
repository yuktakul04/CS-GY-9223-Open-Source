"""Unit tests for Telegram scaffold against the shared API types."""

from chat_client_api import Channel, ChatClient, Message
from telegram_client_impl.client import TelegramClient
from telegram_client_impl.config import TelegramClientConfig


def test_shared_channel_dataclass_shape() -> None:
    """Shared Channel dataclass fields are available for assertions."""
    channel = Channel(
        channel_id="ch-1",
        name="general",
        is_private=False,
        channel_type="group",
    )
    assert channel.channel_id == "ch-1"
    assert channel.name == "general"
    assert channel.channel_type == "group"


def test_shared_message_dataclass_shape() -> None:
    """Shared Message uses opaque message_id and channel string."""
    message = Message(
        message_id="ch-1:99",
        channel="ch-1",
        text="hello",
        sender="alice",
        timestamp="2026-02-16T10:00:00Z",
    )
    assert message.message_id == "ch-1:99"
    assert message.channel == "ch-1"
    assert message.sender == "alice"
    assert message.timestamp == "2026-02-16T10:00:00Z"
    assert message.text == "hello"


def test_telegram_client_is_chat_client() -> None:
    """TelegramClient is constructible and conforms to ChatClient."""
    config = TelegramClientConfig(
        bot_token=None,
    )
    client = TelegramClient(config=config)

    assert isinstance(client, ChatClient)
