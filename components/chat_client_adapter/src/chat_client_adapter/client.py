"""Service-backed adapter implementing ``chat_client_api.Client``."""

from __future__ import annotations

from os import getenv
from typing import TYPE_CHECKING

from chat_client_adapter.models import AdapterChannel, AdapterMessage
from chat_client_api.client import Client
from chat_client_service_api_client.client import ChatServiceApiClient

if TYPE_CHECKING:
    from collections.abc import Iterator

    from chat_client_api.message import Message


class ServiceBackedChatClient(Client):
    """Client adapter that delegates operations to chat_client_service API."""

    def __init__(self, *, service_client: ChatServiceApiClient) -> None:
        """Create adapter with a service API client."""
        self._service_client = service_client

    def send_message(self, channel_id: str, text: str) -> Message:
        """Send message via service API client."""
        dto = self._service_client.send_message(channel_id=channel_id, text=text)
        return AdapterMessage(
            message_id=dto.id,
            sender=dto.sender,
            channel_id=dto.channel_id,
            timestamp=dto.timestamp,
            text=dto.text,
        )

    def get_messages(self, channel_id: str, max_results: int = 10) -> Iterator[Message]:
        """Fetch messages via service API client."""
        messages = self._service_client.get_messages(
            channel_id=channel_id,
            max_results=max_results,
        )
        for dto in messages:
            yield AdapterMessage(
                message_id=dto.id,
                sender=dto.sender,
                channel_id=dto.channel_id,
                timestamp=dto.timestamp,
                text=dto.text,
            )

    def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Delete message via service API client."""
        return self._service_client.delete_message(
            channel_id=channel_id,
            message_id=message_id,
        )

    def get_channels(self) -> Iterator[AdapterChannel]:
        """Fetch channels via service API client."""
        channels = self._service_client.get_channels()
        for dto in channels:
            yield AdapterChannel(
                channel_id=dto.id,
                name=dto.name,
                channel_type=dto.channel_type,
            )


def get_client_impl(*, interactive: bool = False) -> Client:
    """Return adapter-backed client using service URL and token configuration."""
    _ = interactive
    base_url = getenv("CHAT_CLIENT_SERVICE_BASE_URL", "http://localhost:8000")
    if not base_url:
        msg = "CHAT_CLIENT_SERVICE_BASE_URL must not be empty"
        raise ValueError(msg)
    token = getenv("CHAT_CLIENT_SERVICE_TOKEN")
    service_client = ChatServiceApiClient(base_url=base_url, token=token)
    return ServiceBackedChatClient(service_client=service_client)
