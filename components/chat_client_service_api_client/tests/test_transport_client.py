"""Tests for the auto-generated OpenAPI client and the stable wrapper."""

import contextlib
import json
from collections.abc import Callable, Iterator

import httpx
import pytest
from chat_client_service_client.client import Client as GeneratedClient
from chat_client_service_client.errors import UnexpectedStatus
from chat_client_service_client.models.channel_model import (
    ChannelModel as GeneratedChannelModel,
)
from chat_client_service_client.models.message_model import (
    MessageModel as GeneratedMessageModel,
)

from chat_client_service_api_client.client import ChatServiceApiClient
from chat_client_service_api_client.models import ChannelDTO, MessageDTO


class RecordingTransport(httpx.BaseTransport):
    """Base transport that records requests and serves canned responses."""

    def __init__(
        self,
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> None:
        """Store the response handler and captured requests."""
        self._handler = handler
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Record a request and delegate response generation."""
        self.requests.append(request)
        return self._handler(request)


@contextlib.contextmanager
def _transport_api(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Iterator[tuple[ChatServiceApiClient, RecordingTransport]]:
    api = ChatServiceApiClient(base_url="http://localhost:8000/")
    transport = RecordingTransport(handler)
    with httpx.Client(base_url=api.base_url, transport=transport) as client:
        api._generated.set_httpx_client(client)
        yield api, transport


def test_generated_client_package_is_importable() -> None:
    """The auto-generated chat_client_service_client package imports correctly."""
    assert GeneratedClient is not None
    assert GeneratedMessageModel is not None
    assert GeneratedChannelModel is not None


def test_stable_wrapper_initializes_with_base_url() -> None:
    """ChatServiceApiClient initializes and normalizes the base URL."""
    api = ChatServiceApiClient(base_url="http://localhost:8000/")
    assert api.base_url == "http://localhost:8000"


def test_stable_wrapper_holds_generated_client() -> None:
    """ChatServiceApiClient wraps a GeneratedClient instance internally."""
    api = ChatServiceApiClient(base_url="http://localhost:8000")
    assert isinstance(api._generated, GeneratedClient)


def test_send_message_posts_json_and_returns_dto() -> None:
    """send_message exercises request construction and response parsing."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "m-1",
                "sender": "alice",
                "channel_id": "ch-1",
                "timestamp": "2026-01-01T00:00:00",
                "text": "hi",
            },
            request=request,
        )

    with _transport_api(handler) as (api, transport):
        result = api.send_message(channel_id="ch-1", text="hi")

    assert isinstance(result, MessageDTO)
    assert result.id == "m-1"
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/chat/messages"
    assert request.headers["Content-Type"] == "application/json"
    assert json.loads(request.content.decode()) == {
        "channel_id": "ch-1",
        "text": "hi",
    }


def test_send_message_raises_type_error_on_validation_error() -> None:
    """send_message rejects documented error payloads that are not MessageModel."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": [
                    {
                        "loc": ["body", "text"],
                        "msg": "Field required",
                        "type": "missing",
                    }
                ]
            },
            request=request,
        )

    with (
        _transport_api(handler) as (api, _transport),
        pytest.raises(TypeError, match="Unexpected response from send_message"),
    ):
        api.send_message(channel_id="ch-1", text="hi")


def test_get_messages_sends_query_params_and_returns_dtos() -> None:
    """get_messages maps a parsed response list to MessageDTOs."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "m-1",
                    "sender": "alice",
                    "channel_id": "ch-1",
                    "timestamp": "2026-01-01T00:00:00",
                    "text": "hi",
                }
            ],
            request=request,
        )

    with _transport_api(handler) as (api, transport):
        result = api.get_messages(channel_id="ch-1", max_results=25)

    assert len(result) == 1
    assert isinstance(result[0], MessageDTO)
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.url.path == "/chat/messages"
    assert dict(request.url.params) == {"channel_id": "ch-1", "max_results": "25"}


def test_get_messages_raises_type_error_on_validation_error() -> None:
    """get_messages rejects documented error payloads that are not message lists."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": [
                    {
                        "loc": ["query", "channel_id"],
                        "msg": "Field required",
                        "type": "missing",
                    }
                ]
            },
            request=request,
        )

    with (
        _transport_api(handler) as (api, _transport),
        pytest.raises(TypeError, match="Unexpected response from get_messages"),
    ):
        api.get_messages(channel_id="ch-1")


def test_get_channels_requests_expected_path_and_returns_dtos() -> None:
    """get_channels maps generated ChannelModels to ChannelDTOs."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"id": "ch-1", "name": "general", "channel_type": "group"}],
            request=request,
        )

    with _transport_api(handler) as (api, transport):
        result = api.get_channels()

    assert len(result) == 1
    assert isinstance(result[0], ChannelDTO)
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.url.path == "/chat/channels"


def test_get_channels_raises_for_undocumented_status() -> None:
    """get_channels surfaces generated-client errors for undocumented statuses."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"detail": "service unavailable"},
            request=request,
        )

    with (
        _transport_api(handler) as (api, _transport),
        pytest.raises(UnexpectedStatus, match="Unexpected status code: 503"),
    ):
        api.get_channels()


def test_delete_message_sends_expected_request_and_returns_true() -> None:
    """delete_message returns True when the service reports success."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True}, request=request)

    with _transport_api(handler) as (api, transport):
        result = api.delete_message(channel_id="ch-1", message_id="m/1")

    assert result is True
    request = transport.requests[0]
    assert request.method == "DELETE"
    assert request.url.raw_path == b"/chat/messages/m%2F1?channel_id=ch-1"
    assert dict(request.url.params) == {"channel_id": "ch-1"}


def test_delete_message_returns_false_when_service_reports_failure() -> None:
    """delete_message returns False when the parsed response says success=False."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False}, request=request)

    with _transport_api(handler) as (api, _transport):
        assert api.delete_message(channel_id="ch-1", message_id="m-1") is False


def test_dto_models_are_dataclasses() -> None:
    """ChannelDTO and MessageDTO are frozen dataclasses usable as value objects."""
    ch = ChannelDTO(id="ch-1", name="general", channel_type="group")
    msg = MessageDTO(
        id="m-1",
        sender="alice",
        channel_id="ch-1",
        timestamp="2026-01-01T00:00:00",
        text="hello",
    )
    assert ch.id == "ch-1"
    assert msg.text == "hello"
