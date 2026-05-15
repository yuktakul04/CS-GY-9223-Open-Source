"""Unit tests for the service-backed adapter scaffold."""

from unittest.mock import Mock

from chat_client_adapter.client import ServiceBackedChatClient
from chat_client_service_api_client.models import ChannelDTO, MessageDTO


def _message_dto(*, message_id: str) -> MessageDTO:
    """Build a message DTO fixture."""
    return MessageDTO(
        id=message_id,
        sender="alice",
        channel_id="ch-1",
        timestamp="2026-03-20T00:00:00Z",
        text="hello",
    )


def test_send_message_delegates_to_service_client() -> None:
    """Adapter send_message delegates and maps DTO to Message contract."""
    service_client = Mock()
    service_client.send_message.return_value = _message_dto(message_id="m-1")
    adapter = ServiceBackedChatClient(service_client=service_client)

    message = adapter.send_message(channel_id="ch-1", text="hello")

    service_client.send_message.assert_called_once_with(channel_id="ch-1", text="hello")
    assert message.message_id == "m-1"
    assert message.text == "hello"


def test_get_messages_delegates_to_service_client() -> None:
    """Adapter get_messages delegates and yields mapped messages."""
    service_client = Mock()
    service_client.get_messages.return_value = [
        _message_dto(message_id="m-1"),
        _message_dto(message_id="m-2"),
    ]
    adapter = ServiceBackedChatClient(service_client=service_client)

    messages = list(adapter.get_messages(channel_id="ch-1", limit=2))

    service_client.get_messages.assert_called_once_with(
        channel_id="ch-1",
        max_results=2,
    )
    assert [m.message_id for m in messages] == ["m-1", "m-2"]


def test_delete_message_delegates_to_service_client() -> None:
    """Adapter delete_message delegates and returns provider response."""
    service_client = Mock()
    service_client.delete_message.return_value = True
    adapter = ServiceBackedChatClient(service_client=service_client)

    adapter.delete_message(message_id="opaque-m-1")

    service_client.delete_message.assert_called_once_with(message_id="opaque-m-1")


def test_get_message_delegates_to_service_client() -> None:
    """Adapter get_message delegates and maps DTO to Message contract."""
    service_client = Mock()
    service_client.get_message.return_value = _message_dto(message_id="opaque-m-1")
    adapter = ServiceBackedChatClient(service_client=service_client)

    message = adapter.get_message(message_id="opaque-m-1")

    service_client.get_message.assert_called_once_with(message_id="opaque-m-1")
    assert message.message_id == "opaque-m-1"


def test_get_channels_delegates_to_service_client() -> None:
    """Adapter get_channels delegates and yields mapped channels."""
    service_client = Mock()
    service_client.get_channels.return_value = [
        ChannelDTO(id="ch-1", name="general", channel_type="group"),
    ]
    adapter = ServiceBackedChatClient(service_client=service_client)

    channel_list = list(adapter.get_channels())

    service_client.get_channels.assert_called_once_with()
    assert channel_list[0].channel_id == "ch-1"
    assert channel_list[0].name == "general"
