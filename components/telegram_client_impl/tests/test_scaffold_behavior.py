"""Unit tests for Telegram Bot API implementation behavior and validation."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import httpx
import pytest

from telegram_client_impl.client import TelegramClient, get_client_impl
from telegram_client_impl.config import TelegramClientConfig
from telegram_client_impl.errors import TelegramAuthError, TelegramClientError
from telegram_client_impl.store import get_store, record_update

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Use an in-memory store for Bot API implementation tests."""
    monkeypatch.setenv("CHAT_CLIENT_STORE_PATH", ":memory:")
    get_store().clear()
    yield
    get_store().clear()


def _client(handler: httpx.MockTransport) -> TelegramClient:
    """Build a Bot API client using a fake HTTP transport."""
    http_client = httpx.Client(
        base_url="https://api.telegram.org/bottoken",
        transport=handler,
    )
    config = TelegramClientConfig(bot_token="token")
    return TelegramClient(config=config, http_client=http_client)


def _raw_message(*, message_id: int = 5, text: str = "hello") -> dict[str, object]:
    """Build a Bot API message fixture."""
    return {
        "message_id": message_id,
        "from": {"id": 100, "first_name": "Alice"},
        "chat": {"id": 123, "title": "OSSHWBOTTEST", "type": "group"},
        "date": 1_800_000_000,
        "text": text,
    }


def test_client_methods_use_bot_api_and_store_observed_state() -> None:
    """Client methods call Bot API and read bot-observed local state."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/getWebhookInfo"):
            return httpx.Response(
                200,
                json={"ok": True, "result": {"url": "https://example.com/hook"}},
                request=request,
            )
        if request.url.path.endswith("/sendMessage"):
            return httpx.Response(
                200,
                json={"ok": True, "result": _raw_message(message_id=5)},
                request=request,
            )
        if request.url.path.endswith("/deleteMessage"):
            return httpx.Response(
                200,
                json={"ok": True, "result": True},
                request=request,
            )
        return httpx.Response(404, json={"ok": False}, request=request)

    client = _client(httpx.MockTransport(handler))

    sent = client.send_message(channel_id="123", text="hello")
    assert sent.message_id == "123:5"
    assert sent.channel == "123"

    messages = client.get_messages("123", limit=2)
    assert len(messages) == 1
    assert messages[0].text == "hello"
    assert messages[0].message_id == "123:5"
    assert client.get_message("123:5").text == "hello"

    channels = client.get_channels()
    assert len(channels) == 1
    assert channels[0].name == "OSSHWBOTTEST"
    assert channels[0].channel_id == "123"
    assert channels[0].channel_type == "group"
    assert client.get_channel("123").name == "OSSHWBOTTEST"

    client.delete_message(message_id="123:5")
    assert client.get_messages("123") == []

    methods = [request.url.path.rsplit("/", 1)[-1] for request in requests]
    assert "sendMessage" in methods
    assert "deleteMessage" in methods


def test_client_requires_bot_token() -> None:
    """Bot API client fails fast without service-owned bot credentials."""
    client = TelegramClient(config=TelegramClientConfig(bot_token=None))

    with pytest.raises(TelegramAuthError, match="TELEGRAM_BOT_TOKEN"):
        client.get_channels()


def test_get_channel_fetches_chat_metadata_on_cache_miss() -> None:
    """get_channel can resolve a Telegram chat before any updates are observed."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/getWebhookInfo"):
            return httpx.Response(
                200,
                json={"ok": True, "result": {"url": "https://example.com/hook"}},
                request=request,
            )
        if request.url.path.endswith("/getChat"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "id": 123,
                        "title": "OSSHWBOTTEST",
                        "type": "supergroup",
                    },
                },
                request=request,
            )
        return httpx.Response(404, json={"ok": False}, request=request)

    client = _client(httpx.MockTransport(handler))

    channel = client.get_channel("123")
    cached = client.get_channel("123")

    assert channel.channel_id == "123"
    assert channel.name == "OSSHWBOTTEST"
    assert channel.channel_type == "supergroup"
    assert cached == channel
    methods = [request.url.path.rsplit("/", 1)[-1] for request in requests]
    assert methods.count("getChat") == 1


def test_bot_api_error_preserves_response_metadata() -> None:
    """Bot API error_code and parameters remain available to callers."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "ok": False,
                "error_code": 429,
                "description": "Too Many Requests",
                "parameters": {"retry_after": 6},
            },
            request=request,
        )

    client = _client(httpx.MockTransport(handler))

    with pytest.raises(TelegramClientError) as exc_info:
        client.send_message(channel_id="123", text="hello")

    assert exc_info.value.method == "sendMessage"
    assert exc_info.value.error_code == 429
    assert exc_info.value.parameters == {"retry_after": 6}


def test_bot_api_429_retries_once_when_retry_after_is_small(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Small Telegram retry_after values trigger one bounded retry."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                json={
                    "ok": False,
                    "error_code": 429,
                    "description": "Too Many Requests",
                    "parameters": {"retry_after": 1},
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={"ok": True, "result": _raw_message(message_id=7)},
            request=request,
        )

    sleep_calls: list[int] = []
    monkeypatch.setattr("telegram_client_impl.client.time.sleep", sleep_calls.append)
    client = _client(httpx.MockTransport(handler))

    sent = client.send_message(channel_id="123", text="hello")

    assert sent.message_id == "123:7"
    assert calls == 2
    assert sleep_calls == [1]


def test_transport_errors_do_not_expose_bot_token_in_error_message() -> None:
    """Transport failures should not leak the Bot API token in exception text."""
    timeout_message = "read timed out"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(timeout_message, request=request)

    client = _client(httpx.MockTransport(handler))

    with pytest.raises(TelegramClientError) as exc_info:
        client.send_message(channel_id="123", text="hello")

    assert exc_info.value.method == "sendMessage"
    assert "bottoken" not in str(exc_info.value)
    assert "sendMessage" in str(exc_info.value)


def test_bot_api_non_object_result_raises_client_error() -> None:
    """SendMessage requires a message object in the Bot API result."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": True}, request=request)

    client = _client(httpx.MockTransport(handler))

    with pytest.raises(TelegramClientError, match="missing message"):
        client.send_message(channel_id="123", text="hello")


def test_webhook_update_records_message_for_reads() -> None:
    """Webhook-style updates populate the bot-observed read model."""
    record_update({"update_id": 1, "message": _raw_message(message_id=8, text="seen")})

    client = _client(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"ok": True, "result": {"url": "https://example.com/hook"}},
                request=request,
            )
        )
    )
    messages = client.get_messages("123", limit=1)
    channels = client.get_channels()

    assert messages[0].message_id == "123:8"
    assert messages[0].text == "seen"
    assert channels[0].channel_id == "123"


def test_get_messages_cursor_returns_newer_messages() -> None:
    """Cursor reads let consumers process only newly observed messages."""
    client = _client(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"ok": True, "result": {"url": "https://example.com/hook"}},
                request=request,
            )
        )
    )

    for message_id in (8, 9, 10):
        record_update(
            {
                "update_id": message_id,
                "message": _raw_message(
                    message_id=message_id,
                    text=f"seen {message_id}",
                ),
            }
        )

    messages = client.get_messages("123", limit=10, cursor="123:8")

    assert [message.message_id for message in messages] == ["123:9", "123:10"]
    assert [message.text for message in messages] == ["seen 9", "seen 10"]


def test_client_polls_updates_when_webhook_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reads can ingest pending Bot API updates when no webhook is active."""
    monkeypatch.delenv("TELEGRAM_UPDATE_MODE", raising=False)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/getWebhookInfo"):
            return httpx.Response(
                200,
                json={"ok": True, "result": {"url": ""}},
                request=request,
            )
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [
                        {
                            "update_id": 11,
                            "message": _raw_message(message_id=9, text="polled"),
                        }
                    ],
                },
                request=request,
            )
        return httpx.Response(404, json={"ok": False}, request=request)

    client = _client(httpx.MockTransport(handler))

    messages = client.get_messages("123", limit=10)

    assert messages[0].message_id == "123:9"
    assert messages[0].text == "polled"
    assert get_store().get_int_state(key="telegram_get_updates_offset") == 12
    assert [request.url.path.rsplit("/", 1)[-1] for request in requests] == [
        "getWebhookInfo",
        "getUpdates",
    ]
    get_updates = requests[1]
    assert json.loads(get_updates.content)["timeout"] == 0


def test_client_skips_read_polling_when_background_poller_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Request-time reads do not race the service background poller."""
    monkeypatch.setenv("TELEGRAM_UPDATE_MODE", "polling")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500, json={"ok": False}, request=request)

    client = _client(httpx.MockTransport(handler))

    assert client.get_channels() == []
    assert requests == []


def test_forced_polling_still_fetches_updates_when_poller_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The background poller uses force=True to perform the actual getUpdates call."""
    monkeypatch.setenv("TELEGRAM_UPDATE_MODE", "polling")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/getWebhookInfo"):
            return httpx.Response(
                200,
                json={"ok": True, "result": {"url": ""}},
                request=request,
            )
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [
                        {
                            "update_id": 11,
                            "message": _raw_message(message_id=9, text="polled"),
                        }
                    ],
                },
                request=request,
            )
        return httpx.Response(404, json={"ok": False}, request=request)

    client = _client(httpx.MockTransport(handler))

    client.sync_updates(force=True)

    assert get_store().list_messages(channel_id="123", max_results=1)[0].text == (
        "polled"
    )
    assert [request.url.path.rsplit("/", 1)[-1] for request in requests] == [
        "getWebhookInfo",
        "getUpdates",
    ]
    get_updates = requests[1]
    assert json.loads(get_updates.content)["timeout"] == 3


def test_polling_errors_are_logged(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Polling failures are visible instead of being silently dropped."""
    monkeypatch.delenv("TELEGRAM_UPDATE_MODE", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getWebhookInfo"):
            return httpx.Response(
                200,
                json={"ok": True, "result": {"url": ""}},
                request=request,
            )
        return httpx.Response(
            429,
            json={"ok": False, "error_code": 429, "description": "Too Many Requests"},
            request=request,
        )

    caplog.set_level(logging.WARNING, logger="telegram_client_impl.client")
    client = _client(httpx.MockTransport(handler))

    assert client.get_channels() == []
    assert "Telegram getUpdates failed" in caplog.text


def test_webhook_records_bot_membership_chat() -> None:
    """Bot membership updates make newly added chats visible before messages."""
    record_update(
        {
            "update_id": 1,
            "my_chat_member": {
                "from": {"id": 100},
                "chat": {"id": -123, "title": "OSSHWBOTTEST", "type": "group"},
                "date": 1_800_000_000,
                "old_chat_member": {"status": "left"},
                "new_chat_member": {"status": "member"},
            },
        }
    )

    channels = get_store().list_channels()

    assert channels[0].channel_id == "-123"
    assert channels[0].name == "OSSHWBOTTEST"
    assert get_store().user_can_access(telegram_id="100", channel_id="-123") is True


def test_bot_membership_removal_revokes_cached_chat_access() -> None:
    """When the bot leaves a chat, cached access to that chat is removed."""
    get_store().grant_access(telegram_id="100", channel_id="-123")

    record_update(
        {
            "update_id": 1,
            "my_chat_member": {
                "from": {"id": 100},
                "chat": {"id": -123, "title": "OSSHWBOTTEST", "type": "group"},
                "date": 1_800_000_000,
                "old_chat_member": {"status": "member"},
                "new_chat_member": {"status": "kicked"},
            },
        }
    )

    assert get_store().user_can_access(telegram_id="100", channel_id="-123") is False


def test_client_can_check_membership_with_bot_api() -> None:
    """Access checks use Bot API getChatMember when local state is missing."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/getChatMember")
        return httpx.Response(
            200,
            json={"ok": True, "result": {"status": "member"}},
            request=request,
        )

    client = _client(httpx.MockTransport(handler))

    assert client.user_can_access_channel(user_id="100", channel_id="123") is True
    assert (
        client.user_can_access_channel(user_id="not-numeric", channel_id="123") is False
    )


def test_client_input_validation() -> None:
    """Input guards execute before Bot API operations."""
    client = TelegramClient(config=TelegramClientConfig(bot_token="token"))

    with pytest.raises(ValueError, match="channel_id must be non-empty"):
        client.send_message(channel_id="", text="hello")
    with pytest.raises(ValueError, match="text must be <= 4096 characters"):
        client.send_message(channel_id="ch-1", text="x" * 4097)
    with pytest.raises(ValueError, match="limit must be > 0"):
        client.get_messages(channel_id="ch-1", limit=0)
    with pytest.raises(ValueError, match="message_id must be non-empty"):
        client.delete_message(message_id="")
    with pytest.raises(ValueError, match="message_id must be formatted"):
        client.delete_message(message_id="7")


def test_get_client_impl_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory reads environment variables through TelegramClientConfig.from_env."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_BOT_API_BASE_URL", "https://api.telegram.example")

    client = get_client_impl(interactive=True)

    assert isinstance(client, TelegramClient)
    assert client._config.bot_token == "token"
    assert client._config.bot_api_base_url == "https://api.telegram.example"
    assert client._config.interactive is True
