"""Unit tests for Telegram implementation behavior and validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from telegram_client_impl.client import TelegramClient, get_client_impl
from telegram_client_impl.config import TelegramClientConfig
from telegram_client_impl.errors import TelegramMappingError
from telegram_client_impl.mappers import to_channel, to_message
from telegram_client_impl.message import TelegramMessage, get_message_impl

EXPECTED_MESSAGE_COUNT = 2


def _client() -> TelegramClient:
    """Build a client with minimal, non-empty config."""
    config = TelegramClientConfig(api_id="1", api_hash="hash", bot_token="token")
    return TelegramClient(config=config)


def test_client_methods_delegate_to_telethon() -> None:
    """Client methods call through to the Telethon client and mappers."""
    client = _client()

    with (
        patch.object(client, "_ensure_connected") as mock_ensure,
        patch(
            "telegram_client_impl.client.to_message",
        ) as mock_to_message,
        patch(
            "telegram_client_impl.client.to_channel",
        ) as mock_to_channel,
    ):
        # Arrange Telethon client on the instance.
        tele_client = MagicMock()
        client._client = tele_client

        # send_message
        tele_client.send_message.return_value = object()
        mock_msg = MagicMock(spec=TelegramMessage)
        mock_to_message.return_value = mock_msg
        result = client.send_message(channel_id="123", text="hello")
        mock_ensure.assert_called()
        tele_client.send_message.assert_called_with(123, "hello")
        assert result is mock_msg

        # get_messages
        tele_client.iter_messages.return_value = [
            object(),
            object(),
        ]
        mock_to_message.reset_mock()
        messages = list(
            client.get_messages(
                channel_id="123",
                max_results=EXPECTED_MESSAGE_COUNT,
            ),
        )
        tele_client.iter_messages.assert_called_with(
            123,
            limit=EXPECTED_MESSAGE_COUNT,
        )
        assert mock_to_message.call_count == EXPECTED_MESSAGE_COUNT
        assert len(messages) == EXPECTED_MESSAGE_COUNT

        # delete_message
        tele_client.delete_messages.reset_mock()
        deleted = client.delete_message(channel_id="123", message_id="5")
        tele_client.delete_messages.assert_called_with(123, 5)
        assert deleted is True

        # get_channels
        tele_client.get_dialogs.return_value = [object()]
        mock_channel = MagicMock()
        mock_to_channel.return_value = mock_channel
        channels = list(client.get_channels())
        tele_client.get_dialogs.assert_called_once()
        mock_to_channel.assert_called_once()
        assert channels == [mock_channel]


def test_client_input_validation() -> None:
    """Input guards execute before scaffold exceptions."""
    client = _client()

    with pytest.raises(ValueError, match="channel_id must be non-empty"):
        client.send_message(channel_id="", text="hello")
    with pytest.raises(ValueError, match="max_results must be > 0"):
        list(client.get_messages(channel_id="ch-1", max_results=0))
    with pytest.raises(ValueError, match="message_id must be non-empty"):
        client.delete_message(channel_id="ch-1", message_id="")


def test_message_factory_validation_and_construction() -> None:
    """Message factory validates shape and constructs TelegramMessage."""
    with pytest.raises(ValueError, match="msg_id must be non-empty"):
        get_message_impl(msg_id="", raw_data="{}")
    with pytest.raises(ValueError, match="raw_data must be non-empty"):
        get_message_impl(msg_id="m-1", raw_data="")

    payload = {
        "sender": "alice",
        "channel_id": "ch-1",
        "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
        "text": "hello",
    }
    message = get_message_impl(msg_id="m-1", raw_data=json.dumps(payload))
    assert isinstance(message, TelegramMessage)
    assert message.id == "m-1"
    assert message.sender == "alice"
    assert message.channel_id == "ch-1"
    assert message.text == "hello"


def test_mapper_validation_and_errors() -> None:
    """Mappers validate inputs and raise mapping errors for unsupported types."""
    with pytest.raises(ValueError, match="raw_channel cannot be None"):
        to_channel(None)
    with pytest.raises(ValueError, match="raw_message cannot be None"):
        to_message(None)
    with pytest.raises(TelegramMappingError):
        to_channel(object())
    with pytest.raises(TelegramMappingError):
        to_message(object())


def test_mapper_positive_channel_and_message() -> None:
    """Mappers convert Telethon-like objects into domain models."""
    # Fake Telethon channel entity via SimpleNamespace with required attributes.
    channel_entity = SimpleNamespace(id=42, title="My Channel", broadcast=True)
    channel = to_channel(channel_entity)
    assert channel.id == "42"
    assert channel.name == "My Channel"
    assert channel.channel_type == "channel"

    # Fake Telethon message-like object with a peer namespace.
    peer = SimpleNamespace(channel_id=99, chat_id=None, user_id=None)
    msg_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    raw_message = SimpleNamespace(
        id=7,
        sender_id=123,
        peer_id=peer,
        date=msg_date,
        message="hi",
    )

    message = to_message(raw_message)
    assert message.id == "7"
    assert message.sender == "123"
    assert message.channel_id == "99"
    assert message.timestamp == msg_date.isoformat()
    assert message.text == "hi"


def test_get_client_impl_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory reads environment variables through TelegramClientConfig.from_env."""
    monkeypatch.setenv("TELEGRAM_API_ID", "123")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")

    client = get_client_impl(interactive=True)

    assert isinstance(client, TelegramClient)
