"""Tests for the chat_client_api message and channel abstractions."""

from unittest.mock import Mock

import pytest

from chat_client_api.channel import Channel
from chat_client_api.message import Message, get_message


def test_message_properties() -> None:
    """Verify all Message abstract properties via a mock."""
    mock_message = Mock(spec=Message)
    mock_message.id = "msg_12345"
    mock_message.sender = "alice"
    mock_message.channel_id = "ch_general"
    mock_message.timestamp = "2025-02-16T10:30:00Z"
    mock_message.text = "Hello everyone!"

    assert mock_message.id == "msg_12345"
    assert mock_message.sender == "alice"
    assert mock_message.channel_id == "ch_general"
    assert mock_message.timestamp == "2025-02-16T10:30:00Z"
    assert mock_message.text == "Hello everyone!"

    for value in [
        mock_message.id,
        mock_message.sender,
        mock_message.channel_id,
        mock_message.timestamp,
        mock_message.text,
    ]:
        assert isinstance(value, str)


def test_channel_properties() -> None:
    """Verify all Channel abstract properties via a mock."""
    mock_channel = Mock(spec=Channel)
    mock_channel.id = "ch_1"
    mock_channel.name = "general"
    mock_channel.channel_type = "group"

    assert mock_channel.id == "ch_1"
    assert mock_channel.name == "general"
    assert mock_channel.channel_type == "group"


def test_get_message_raises_not_implemented() -> None:
    """Verify get_message raises NotImplementedError without an implementation."""
    with pytest.raises(NotImplementedError):
        get_message(msg_id="msg_1", raw_data="{}")
