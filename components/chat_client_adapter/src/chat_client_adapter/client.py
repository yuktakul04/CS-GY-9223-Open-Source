"""Service-backed adapter implementing ``chat_client_api.ChatClient``."""

from __future__ import annotations

from os import getenv

from chat_client_adapter.models import AdapterChannel, AdapterMessage
from chat_client_api import Channel, ChatClient, Message
from chat_client_service_api_client.client import ChatServiceApiClient


class ServiceBackedChatClient(ChatClient):
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
            channel=dto.channel_id,
            timestamp=dto.timestamp,
            text=dto.text,
        )

    def get_messages(
        self,
        channel_id: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        """Fetch messages via service API client."""
        del cursor
        messages = self._service_client.get_messages(
            channel_id=channel_id,
            max_results=limit,
        )
        return [
            AdapterMessage(
                message_id=dto.id,
                sender=dto.sender,
                channel=dto.channel_id,
                timestamp=dto.timestamp,
                text=dto.text,
            )
            for dto in messages
        ]

    def get_message(self, message_id: str) -> Message:
        """Get a single message by opaque ID."""
        dto = self._service_client.get_message(message_id=message_id)
        return AdapterMessage(
            message_id=dto.id,
            sender=dto.sender,
            channel=dto.channel_id,
            timestamp=dto.timestamp,
            text=dto.text,
        )

    def delete_message(self, message_id: str) -> None:
        """Delete message via service API client."""
        deleted = self._service_client.delete_message(message_id=message_id)
        if not deleted:
            msg = f"Message not found or could not be deleted: {message_id}"
            raise ValueError(msg)

    def get_channels(self) -> list[AdapterChannel]:
        """Fetch channels via service API client."""
        channels = self._service_client.get_channels()
        return [
            AdapterChannel(
                channel_id=dto.id,
                name=dto.name,
                is_private=None,
                channel_type=dto.channel_type,
            )
            for dto in channels
        ]

    def get_channel(self, channel_id: str) -> Channel:
        """Get a single channel by ID."""
        for channel in self.get_channels():
            if channel.channel_id == channel_id:
                return channel
        msg = f"Channel not found: {channel_id}"
        raise ValueError(msg)


def get_client_impl(*, interactive: bool = False) -> ChatClient:
    """Return adapter-backed client using service URL and token configuration."""
    _ = interactive
    base_url = getenv("CHAT_CLIENT_SERVICE_BASE_URL", "http://localhost:8000")
    if not base_url:
        msg = "CHAT_CLIENT_SERVICE_BASE_URL must not be empty"
        raise ValueError(msg)
    token = getenv("CHAT_CLIENT_SERVICE_TOKEN")
    service_client = ChatServiceApiClient(base_url=base_url, token=token)
    return ServiceBackedChatClient(service_client=service_client)
