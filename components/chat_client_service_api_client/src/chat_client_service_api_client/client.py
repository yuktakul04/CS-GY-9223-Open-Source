"""Stable wrapper over the auto-generated OpenAPI client.

The generated package (chat_client_service_client) was produced by running:

    openapi-python-client generate --url http://localhost:8000/openapi.json

This wrapper translates generated attrs models into plain dataclasses (ChannelDTO,
MessageDTO) so that consumers are insulated from any future regeneration of the
underlying client.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from chat_client_service_client import AuthenticatedClient as _AuthenticatedClient
from chat_client_service_client import Client as _GeneratedClient
from chat_client_service_client.api.chat import (
    get_channels_chat_channels_get as _get_channels,
)
from chat_client_service_client.api.chat import (
    get_messages_chat_messages_get as _get_messages,
)
from chat_client_service_client.api.chat import (
    send_message_chat_messages_post as _send,
)
from chat_client_service_client.errors import UnexpectedStatus
from chat_client_service_client.models import (
    ChannelModel as _ChannelModel,
)
from chat_client_service_client.models import (
    MessageModel as _MessageModel,
)
from chat_client_service_client.models import (
    SendMessageRequest as _SendMessageRequest,
)

from chat_client_service_api_client.models import ChannelDTO, MessageDTO

if TYPE_CHECKING:
    import httpx


class ChatServiceApiClient:
    """HTTP client for chat_client_service.

    Acts as a stable abstraction layer so that consumers (e.g. chat_client_adapter)
    are insulated from any regeneration of the underlying OpenAPI client.

    Pass ``token`` (a Bearer token from ``/auth/verify``) to authenticate requests
    to the protected ``/chat/*`` endpoints.
    """

    _generated: _GeneratedClient | _AuthenticatedClient

    def __init__(self, *, base_url: str, token: str | None = None) -> None:
        """Initialize client with the service base URL and optional Bearer token."""
        self._base_url = base_url.rstrip("/")
        if token:
            self._generated = _AuthenticatedClient(
                base_url=self._base_url,
                token=token,
                raise_on_unexpected_status=True,
            )
        else:
            self._generated = _GeneratedClient(
                base_url=self._base_url,
                raise_on_unexpected_status=True,
            )

    @property
    def base_url(self) -> str:
        """Return normalized base URL."""
        return self._base_url

    def send_message(self, *, channel_id: str, text: str) -> MessageDTO:
        """POST /chat/messages — send a message to a channel."""
        result = _send.sync(
            client=self._generated,
            body=_SendMessageRequest(channel_id=channel_id, text=text),
        )
        if not isinstance(result, _MessageModel):
            msg = f"Unexpected response from send_message: {result!r}"
            raise TypeError(msg)
        return MessageDTO(
            id=result.id,
            sender=result.sender,
            channel_id=result.channel_id,
            timestamp=result.timestamp,
            text=result.text,
        )

    def get_messages(
        self,
        *,
        channel_id: str,
        max_results: int = 10,
    ) -> list[MessageDTO]:
        """GET /chat/messages — fetch messages from a channel."""
        result = _get_messages.sync(
            client=self._generated,
            channel_id=channel_id,
            max_results=max_results,
        )
        if not isinstance(result, list):
            msg = f"Unexpected response from get_messages: {result!r}"
            raise TypeError(msg)
        return [
            MessageDTO(
                id=m.id,
                sender=m.sender,
                channel_id=m.channel_id,
                timestamp=m.timestamp,
                text=m.text,
            )
            for m in result
        ]

    def get_message(self, *, message_id: str) -> MessageDTO:
        """GET /chat/messages/{message_id} — fetch a single message."""
        encoded_message_id = quote(message_id, safe="")
        response = self._generated.get_httpx_client().request(
            "GET",
            f"/chat/messages/{encoded_message_id}",
        )
        parsed = self._parse_message_response(response=response)
        return MessageDTO(
            id=parsed.id,
            sender=parsed.sender,
            channel_id=parsed.channel_id,
            timestamp=parsed.timestamp,
            text=parsed.text,
        )

    def delete_message(self, *, message_id: str) -> bool:
        """DELETE /chat/messages/{message_id} — delete a message."""
        encoded_message_id = quote(message_id, safe="")
        response = self._generated.get_httpx_client().request(
            "DELETE",
            f"/chat/messages/{encoded_message_id}",
        )
        result = self._parse_delete_response(response=response)
        return bool(result.get("success", False))

    def get_channels(self) -> list[ChannelDTO]:
        """GET /chat/channels — list available channels."""
        result = _get_channels.sync(client=self._generated)
        if not isinstance(result, list):
            msg = f"Unexpected response from get_channels: {result!r}"
            raise TypeError(msg)
        return [
            ChannelDTO(
                id=ch.id,
                name=ch.name,
                channel_type=ch.channel_type,
            )
            for ch in result
            if isinstance(ch, _ChannelModel)
        ]

    def _parse_message_response(self, response: httpx.Response) -> _MessageModel:
        if response.status_code != HTTPStatus.OK:
            raise UnexpectedStatus(response.status_code, response.content)
        payload = response.json()
        if not isinstance(payload, dict):
            msg = f"Unexpected response from get_message: {payload!r}"
            raise TypeError(msg)
        return _MessageModel.from_dict(payload)

    def _parse_delete_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code != HTTPStatus.OK:
            raise UnexpectedStatus(response.status_code, response.content)
        payload = response.json()
        if not isinstance(payload, dict):
            msg = f"Unexpected response from delete_message: {payload!r}"
            raise TypeError(msg)
        return payload
