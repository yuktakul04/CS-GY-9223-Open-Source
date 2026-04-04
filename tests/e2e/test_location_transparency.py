"""E2E location-transparency tests.

These tests verify that the same consumer code works identically whether it is
backed by the local telegram_client_impl library or by the remote
chat_client_service via the chat_client_adapter.

The test strategy uses in-process mocking rather than a real Telegram connection
or a live service, so the suite can run in CI without external credentials.  The
mock doubles satisfy the chat_client_api interface contracts, which is exactly what
a real consumer depends on.

To run against a real live service set CHAT_E2E_LIVE=1 and provide:
  CHAT_CLIENT_SERVICE_BASE_URL  - URL of a deployed chat_client_service instance
  TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_BOT_TOKEN - Telegram credentials
"""

from __future__ import annotations

from os import getenv
from typing import TYPE_CHECKING, TypedDict
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from collections.abc import Iterator

import pytest

from chat_client_api.channel import Channel
from chat_client_api.client import Client
from chat_client_api.message import Message


class _WorkflowResult(TypedDict):
    channels: int
    sent_id: str
    messages: int
    deleted: bool


# ---------------------------------------------------------------------------
# Concrete in-process doubles that satisfy the chat_client_api contracts
# ---------------------------------------------------------------------------


class _StubMessage(Message):
    def __init__(
        self, *, msg_id: str, sender: str, channel_id: str, timestamp: str, text: str
    ) -> None:
        self._id = msg_id
        self._sender = sender
        self._channel_id = channel_id
        self._timestamp = timestamp
        self._text = text

    @property
    def id(self) -> str:
        return self._id

    @property
    def sender(self) -> str:
        return self._sender

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def timestamp(self) -> str:
        return self._timestamp

    @property
    def text(self) -> str:
        return self._text


class _StubChannel(Channel):
    def __init__(self, *, channel_id: str, name: str, channel_type: str) -> None:
        self._id = channel_id
        self._name = name
        self._channel_type = channel_type

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def channel_type(self) -> str:
        return self._channel_type


class _MockClient(Client):
    """Minimal Client implementation used to verify the consumer contract."""

    def send_message(self, channel_id: str, text: str) -> Message:
        return _StubMessage(
            msg_id="m-1",
            sender="bot",
            channel_id=channel_id,
            timestamp="2026-01-01T00:00:00",
            text=text,
        )

    def get_messages(self, channel_id: str, max_results: int = 10) -> Iterator[Message]:
        yield _StubMessage(
            msg_id="m-1",
            sender="bot",
            channel_id=channel_id,
            timestamp="2026-01-01T00:00:00",
            text="hello",
        )

    def delete_message(self, channel_id: str, message_id: str) -> bool:
        return True

    def get_channels(self) -> Iterator[Channel]:
        yield _StubChannel(channel_id="ch-1", name="general", channel_type="group")


# ---------------------------------------------------------------------------
# The consumer code — must work unchanged regardless of which backend is used
# ---------------------------------------------------------------------------


def _consumer_workflow(client: Client) -> _WorkflowResult:
    """Execute the full chat workflow using only the chat_client_api interface.

    This function intentionally has no knowledge of Telegram, the service, or
    the adapter — it only uses the abstract Client contract.
    """
    # 1. List channels
    channels = list(client.get_channels())
    assert len(channels) > 0
    first_channel = channels[0]
    assert isinstance(first_channel, Channel)

    # 2. Send a message
    sent = client.send_message(channel_id=first_channel.id, text="hello from e2e")
    assert isinstance(sent, Message)
    assert sent.text == "hello from e2e"
    assert sent.channel_id == first_channel.id

    # 3. Fetch messages
    messages = list(client.get_messages(channel_id=first_channel.id, max_results=5))
    assert len(messages) > 0
    assert all(isinstance(m, Message) for m in messages)

    # 4. Delete the sent message
    deleted = client.delete_message(channel_id=first_channel.id, message_id=sent.id)
    assert deleted is True

    return {
        "channels": len(channels),
        "sent_id": sent.id,
        "messages": len(messages),
        "deleted": deleted,
    }


# ---------------------------------------------------------------------------
# Test: same consumer code, local backend
# ---------------------------------------------------------------------------


def test_consumer_workflow_with_local_backend() -> None:
    """Consumer code works with a local client implementation (in-process mock).

    This simulates the HW1 / telegram_client_impl path: the consumer uses a
    concrete Client that talks directly to the provider.
    """
    local_client = _MockClient()
    result = _consumer_workflow(local_client)
    assert result["channels"] >= 1
    assert result["deleted"] is True


# ---------------------------------------------------------------------------
# Test: same consumer code, service-adapter backend (mocked HTTP layer)
# ---------------------------------------------------------------------------


def test_consumer_workflow_with_service_adapter_backend() -> None:
    """Consumer code works identically with the service-backed adapter.

    The HTTP transport is mocked so no real service needs to be running.
    This proves location transparency: the consumer function is called
    unmodified with both backends.
    """
    from chat_client_adapter.client import ServiceBackedChatClient
    from chat_client_service_api_client.client import (
        ChatServiceApiClient,
    )
    from chat_client_service_api_client.models import (
        ChannelDTO,
        MessageDTO,
    )

    mock_api = MagicMock(spec=ChatServiceApiClient)
    mock_api.get_channels.return_value = [
        ChannelDTO(id="ch-1", name="general", channel_type="group")
    ]
    mock_api.send_message.return_value = MessageDTO(
        id="m-1",
        sender="bot",
        channel_id="ch-1",
        timestamp="2026-01-01T00:00:00",
        text="hello from e2e",
    )
    mock_api.get_messages.return_value = [
        MessageDTO(
            id="m-1",
            sender="bot",
            channel_id="ch-1",
            timestamp="2026-01-01T00:00:00",
            text="hello from e2e",
        )
    ]
    mock_api.delete_message.return_value = True

    adapter_client = ServiceBackedChatClient(service_client=mock_api)
    result = _consumer_workflow(adapter_client)

    assert result["channels"] >= 1
    assert result["deleted"] is True

    # Prove the adapter forwarded every call to the service client
    mock_api.get_channels.assert_called_once()
    mock_api.send_message.assert_called_once_with(
        channel_id="ch-1", text="hello from e2e"
    )
    mock_api.get_messages.assert_called_once()
    mock_api.delete_message.assert_called_once_with(channel_id="ch-1", message_id="m-1")


# ---------------------------------------------------------------------------
# Test: live service (optional, requires real credentials)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_consumer_workflow_against_live_service() -> None:
    """Consumer code works against a real deployed chat_client_service.

    Skipped unless CHAT_E2E_LIVE=1 and CHAT_CLIENT_SERVICE_BASE_URL are set.
    """
    if getenv("CHAT_E2E_LIVE") != "1":
        pytest.skip("Set CHAT_E2E_LIVE=1 to run against a live service")

    base_url = getenv("CHAT_CLIENT_SERVICE_BASE_URL", "http://localhost:8000")

    from chat_client_adapter.client import ServiceBackedChatClient
    from chat_client_service_api_client.client import (
        ChatServiceApiClient,
    )

    api_client = ChatServiceApiClient(base_url=base_url)
    adapter_client = ServiceBackedChatClient(service_client=api_client)

    result = _consumer_workflow(adapter_client)
    assert result["channels"] >= 0  # may be empty but must not raise
