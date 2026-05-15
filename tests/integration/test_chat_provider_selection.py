"""Integration tests for same-vertical chat provider selection."""

from __future__ import annotations

import importlib

import pytest

import chat_client_api
import chat_client_api.client as client_module
from chat_client_service.provider import load_chat_provider


def _reset_chat_registry() -> None:
    importlib.reload(client_module)
    importlib.reload(chat_client_api)


def test_load_chat_provider_selects_telegram_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default provider selection preserves the existing Telegram behavior."""
    monkeypatch.delenv("CHAT_CLIENT_PROVIDER", raising=False)
    _reset_chat_registry()

    selected = load_chat_provider()

    telegram_module = importlib.import_module("telegram_client_impl.client")
    assert selected == "telegram"
    assert isinstance(chat_client_api.get_client(), telegram_module.TelegramClient)


def test_load_chat_provider_selects_team9_slack_impl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slack provider selection loads Team 9's ChatClient implementation."""
    monkeypatch.setenv("CHAT_CLIENT_PROVIDER", "slack")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    _reset_chat_registry()

    selected = load_chat_provider()

    slack_module = importlib.import_module("slack_client_impl.client")
    client = chat_client_api.get_client()
    assert selected == "slack"
    assert client.__class__.__name__ == "_SlackCompatibilityClient"
    assert isinstance(
        object.__getattribute__(client, "_inner"), slack_module.SlackClient
    )


def test_load_chat_provider_rejects_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider names fail clearly when they are not supported."""
    monkeypatch.setenv("CHAT_CLIENT_PROVIDER", "discord")

    with pytest.raises(RuntimeError, match="CHAT_CLIENT_PROVIDER"):
        load_chat_provider()
