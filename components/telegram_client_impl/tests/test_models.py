"""Unit tests for Telegram scaffold models."""

from chat_client_api.channel import Channel
from chat_client_api.client import Client
from chat_client_api.message import Message
from telegram_client_impl.channel import TelegramChannel
from telegram_client_impl.client import TelegramClient
from telegram_client_impl.config import TelegramClientConfig
from telegram_client_impl.message import TelegramMessage


def test_telegram_channel_contract() -> None:
    """TelegramChannel satisfies Channel contract properties."""
    channel = TelegramChannel(channel_id="ch-1", name="general", channel_type="group")

    assert isinstance(channel, Channel)
    assert channel.id == "ch-1"
    assert channel.name == "general"
    assert channel.channel_type == "group"


def test_telegram_message_contract() -> None:
    """TelegramMessage satisfies Message contract properties."""
    message = TelegramMessage(
        message_id="m-1",
        sender="alice",
        channel_id="ch-1",
        timestamp="2026-02-16T10:00:00Z",
        text="hello",
    )

    assert isinstance(message, Message)
    assert message.id == "m-1"
    assert message.sender == "alice"
    assert message.channel_id == "ch-1"
    assert message.timestamp == "2026-02-16T10:00:00Z"
    assert message.text == "hello"


def test_telegram_client_contract_shape() -> None:
    """TelegramClient is constructible and conforms to Client."""
    config = TelegramClientConfig(
        api_id=None,
        api_hash=None,
        bot_token=None,
        interactive=False,
    )
    client = TelegramClient(config=config)

    assert isinstance(client, Client)
