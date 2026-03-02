"""Tests for the chat client API abstract base classes."""

from unittest.mock import Mock

import pytest

from chat_client_api import Client, get_client
from chat_client_api.channel import Channel
from chat_client_api.message import Message

EXPECTED_MESSAGE_COUNT = 2


def test_client_send_message() -> None:
    """Verify send_message calls through and returns a Message."""
    mock_message = Mock(spec=Message)
    mock_message.id = "msg_1"
    mock_message.text = "Hello, world!"
    mock_message.channel_id = "ch_1"

    mock_client = Mock(spec=Client)
    mock_client.send_message.return_value = mock_message

    result = mock_client.send_message(channel_id="ch_1", text="Hello, world!")

    mock_client.send_message.assert_called_once_with(
        channel_id="ch_1", text="Hello, world!"
    )
    assert result.id == "msg_1"
    assert result.text == "Hello, world!"
    assert result.channel_id == "ch_1"


def test_client_get_messages() -> None:
    """Verify get_messages returns an iterator of Messages."""
    mock_msg_1 = Mock(spec=Message)
    mock_msg_1.id = "msg_1"
    mock_msg_1.text = "First message"

    mock_msg_2 = Mock(spec=Message)
    mock_msg_2.id = "msg_2"
    mock_msg_2.text = "Second message"

    mock_client = Mock(spec=Client)
    mock_client.get_messages.return_value = iter([mock_msg_1, mock_msg_2])

    messages = list(mock_client.get_messages(channel_id="ch_1", max_results=5))

    mock_client.get_messages.assert_called_once_with(channel_id="ch_1", max_results=5)
    assert len(messages) == EXPECTED_MESSAGE_COUNT
    assert messages[0].id == "msg_1"
    assert messages[1].id == "msg_2"


def test_client_delete_message() -> None:
    """Verify delete_message calls through and returns a boolean."""
    mock_client = Mock(spec=Client)
    mock_client.delete_message.return_value = True

    success = mock_client.delete_message(channel_id="ch_1", message_id="msg_to_delete")

    mock_client.delete_message.assert_called_once_with(
        channel_id="ch_1", message_id="msg_to_delete"
    )
    assert success is True


def test_client_get_channels() -> None:
    """Verify get_channels returns an iterator of Channels."""
    mock_channel = Mock(spec=Channel)
    mock_channel.id = "ch_1"
    mock_channel.name = "general"
    mock_channel.channel_type = "group"

    mock_client = Mock(spec=Client)
    mock_client.get_channels.return_value = iter([mock_channel])

    channels = list(mock_client.get_channels())

    mock_client.get_channels.assert_called_once_with()
    assert channels[0].id == "ch_1"
    assert channels[0].name == "general"
    assert channels[0].channel_type == "group"


def test_get_client_raises_not_implemented() -> None:
    """Verify get_client raises NotImplementedError without an implementation."""
    with pytest.raises(NotImplementedError):
        get_client()


def test_get_client_interactive_raises_not_implemented() -> None:
    """Verify get_client with interactive=True also raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        get_client(interactive=True)
