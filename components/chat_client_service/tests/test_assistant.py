"""Tests for the private Telegram assistant flow in chat_client_service."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from chat_client_service import update_poller
from chat_client_service.app import app
from chat_client_service.assistant import (
    TelegramAssistantOrchestrator,
    _build_ai_client,
    build_default_orchestrator,
)
from chat_client_service.routers.telegram import get_telegram_assistant
from telegram_client_impl.store import get_store

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


client = TestClient(app, follow_redirects=False)


def _telegram_message_update(
    *,
    text: str = "list boards",
    chat_id: int = 123,
    user_id: int = 42,
    message_id: int = 5,
    is_bot: bool = False,
) -> dict[str, object]:
    return {
        "update_id": 99,
        "message": {
            "message_id": message_id,
            "date": 1_715_200_000,
            "text": text,
            "chat": {
                "id": chat_id,
                "type": "private",
                "first_name": "Alice",
            },
            "from": {
                "id": user_id,
                "is_bot": is_bot,
                "first_name": "Alice",
                "username": "alice",
            },
        },
    }


@pytest.fixture(autouse=True)
def assistant_test_env(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Use deterministic env and clean shared state for assistant tests."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "osshwbot")
    monkeypatch.setenv("APP_SESSION_SECRET", "app-secret")
    monkeypatch.setenv("CHAT_CLIENT_STORE_PATH", ":memory:")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    get_store().clear()
    app.dependency_overrides.clear()
    yield
    get_store().clear()
    app.dependency_overrides.clear()


def test_orchestrator_ignores_non_message_updates() -> None:
    """Assistant ignores Telegram updates that do not contain a message payload."""
    ai_client = Mock()
    bridge = Mock()
    chat_client = Mock()

    reply = TelegramAssistantOrchestrator(ai_client, bridge, chat_client).handle_update(
        {"update_id": 1}
    )

    assert reply is None
    ai_client.send_message.assert_not_called()
    chat_client.send_message.assert_not_called()


def test_orchestrator_ignores_bot_authored_messages() -> None:
    """Assistant ignores messages authored by bots to avoid reply loops."""
    ai_client = Mock()
    bridge = Mock()
    chat_client = Mock()

    reply = TelegramAssistantOrchestrator(ai_client, bridge, chat_client).handle_update(
        _telegram_message_update(is_bot=True)
    )

    assert reply is None
    ai_client.send_message.assert_not_called()
    chat_client.send_message.assert_not_called()


def test_orchestrator_posts_plain_text_reply() -> None:
    """Assistant sends the AI's plain-text reply back to the originating chat."""
    ai_client = Mock()
    ai_client.send_message.return_value = "Hello from the assistant."
    bridge = Mock()
    chat_client = Mock()

    reply = TelegramAssistantOrchestrator(ai_client, bridge, chat_client).handle_update(
        _telegram_message_update(text="hello")
    )

    assert reply == "Hello from the assistant."
    ai_client.send_message.assert_called_once()
    chat_client.send_message.assert_called_once_with(
        channel_id="123",
        text="Hello from the assistant.",
    )


def test_orchestrator_dispatches_issue_tracker_tool_calls() -> None:
    """Assistant turns tool calls into bridge operations before replying."""
    ai_client = Mock()
    ai_client.send_message.return_value = {
        "name": "get_boards",
        "arguments": {},
    }
    board = Mock()
    board.id = "b-1"
    board.board_name = "Sprint"
    bridge = Mock()
    bridge.get_boards.return_value = iter([board])
    chat_client = Mock()

    reply = TelegramAssistantOrchestrator(ai_client, bridge, chat_client).handle_update(
        _telegram_message_update(text="list boards")
    )

    assert reply == "Boards:\n• Sprint (id: b-1)"
    bridge.get_boards.assert_called_once_with()
    chat_client.send_message.assert_called_once_with(
        channel_id="123",
        text="Boards:\n• Sprint (id: b-1)",
    )


def test_orchestrator_dispatches_chat_tool_calls_in_current_chat() -> None:
    """Chat tool calls execute against the injected ChatClient in the origin chat."""
    ai_client = Mock()
    ai_client.send_message.return_value = {
        "name": "send_message",
        "arguments": {"channel_id": "999", "text": "Roger that."},
    }
    bridge = Mock()
    sent_message = Mock()
    sent_message.message_id = "123:7"
    sent_message.sender = "assistant"
    sent_message.channel = "123"
    sent_message.timestamp = "2026-05-09T00:00:00Z"
    sent_message.text = "Roger that."
    chat_client = Mock()
    chat_client.send_message.return_value = sent_message

    reply = TelegramAssistantOrchestrator(ai_client, bridge, chat_client).handle_update(
        _telegram_message_update(text="send a reply")
    )

    assert reply is not None
    assert "Sent message 123:7" in reply
    chat_client.send_message.assert_any_call(channel_id="123", text="Roger that.")
    assert chat_client.send_message.call_count == 2


def test_build_ai_client_uses_registry_after_importing_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service AI construction imports the configured provider via the registry."""
    sentinel = object()
    get_client = Mock(return_value=sentinel)
    imported: list[str] = []

    monkeypatch.setenv("CHAT_CLIENT_ASSISTANT_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    monkeypatch.setattr("ai_client_api.get_client", get_client)

    def _tracking_import(name: str) -> object:
        imported.append(name)
        return import_module(name)

    monkeypatch.setattr(
        "chat_client_service.assistant.importlib.import_module",
        _tracking_import,
    )

    client_obj = _build_ai_client()

    assert client_obj is sentinel
    assert imported == ["gemini_client_impl"]
    get_client.assert_called_once_with()


def test_build_default_orchestrator_does_not_require_trello_for_plain_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assistant construction should succeed with AI config only."""
    chat_client = Mock()
    ai_client = Mock()

    monkeypatch.setenv("CHAT_CLIENT_ASSISTANT_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    monkeypatch.delenv("TRELLO_API_KEY", raising=False)
    monkeypatch.delenv("TRELLO_TOKEN", raising=False)
    monkeypatch.setattr(
        "chat_client_service.assistant._build_ai_client",
        lambda: ai_client,
    )

    orchestrator = build_default_orchestrator(chat_client)

    assert orchestrator is not None


def test_orchestrator_raises_readable_error_for_issue_tools_without_trello() -> None:
    """Issue-tracker tools should fail only when invoked without a configured bridge."""
    ai_client = Mock()
    ai_client.send_message.return_value = {
        "name": "get_boards",
        "arguments": {},
    }
    chat_client = Mock()

    reply = TelegramAssistantOrchestrator(
        ai_client=ai_client,
        bridge=None,
        chat_client=chat_client,
    ).handle_update(_telegram_message_update(text="list boards"))

    assert reply == "Issue tracker integration is not configured."
    chat_client.send_message.assert_called_once_with(
        channel_id="123",
        text="Issue tracker integration is not configured.",
    )


def test_telegram_webhook_records_update_and_invokes_assistant() -> None:
    """Webhook ingress records the update and forwards it to the service assistant."""
    assistant = Mock()
    assistant.handle_update.return_value = "processed"
    app.dependency_overrides[get_telegram_assistant] = lambda: assistant
    payload = _telegram_message_update()

    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 204
    stored = get_store().get_message(message_id="123:5")
    assert stored is not None
    assert stored.text == "list boards"
    assistant.handle_update.assert_called_once_with(payload)


def test_telegram_webhook_rejects_invalid_secret_before_assistant() -> None:
    """Secret validation still short-circuits assistant execution."""
    assistant = Mock()
    app.dependency_overrides[get_telegram_assistant] = lambda: assistant

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected-secret")
        response = client.post(
            "/telegram/webhook",
            json=_telegram_message_update(),
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )

    assert response.status_code == 401
    assistant.handle_update.assert_not_called()


def test_orchestrator_returns_error_reply_for_invalid_tool_args() -> None:
    """Invalid tool-call arguments produce an error string reply instead of crashing."""
    ai_client = Mock()
    ai_client.send_message.return_value = {
        "name": "get_issues",
        "arguments": {},  # missing required board_id
    }
    bridge = Mock()
    chat_client = Mock()

    reply = TelegramAssistantOrchestrator(ai_client, bridge, chat_client).handle_update(
        _telegram_message_update(text="list issues")
    )

    assert reply is not None
    assert "Invalid arguments" in reply
    bridge.get_issues.assert_not_called()
    chat_client.send_message.assert_called_once()


def test_update_poller_forwards_updates_to_callback() -> None:
    """Background polling should forward raw updates to the assistant callback."""

    class _FakeTelegramClient:
        def sync_updates(
            self,
            *,
            force: bool = False,
            on_update: Callable[[object], None] | None = None,
        ) -> None:
            assert force is True
            assert on_update is not None
            on_update(_telegram_message_update())

        def close(self) -> None:
            return None

    captured: list[dict[str, object]] = []

    poller = update_poller.TelegramUpdatePoller(
        interval_seconds=1.0,
        on_update=captured.append,
    )

    def _fake_get_client_impl(*, interactive: bool = False) -> _FakeTelegramClient:
        del interactive
        return _FakeTelegramClient()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "chat_client_service.update_poller.get_client_impl",
            _fake_get_client_impl,
        )
        poller._poll_once()

    assert captured == [_telegram_message_update()]
