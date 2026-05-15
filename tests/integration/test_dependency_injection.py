"""Integration tests for dependency injection between shared API and implementation."""

import importlib

import pytest

import chat_client_api
import chat_client_api.client as client_module
import telegram_client_impl as telegram_impl
from telegram_client_impl.client import TelegramClient


def test_importing_telegram_impl_registers_chat_client() -> None:
    """Importing (or reloading) telegram_client_impl registers a ChatClient factory."""
    importlib.reload(client_module)
    importlib.reload(chat_client_api)

    with pytest.raises(RuntimeError, match="No chat client implementation"):
        chat_client_api.get_client()

    importlib.reload(telegram_impl)

    injected_client = chat_client_api.get_client()
    assert isinstance(injected_client, TelegramClient)
