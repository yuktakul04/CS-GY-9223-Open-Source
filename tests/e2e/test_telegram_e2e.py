"""E2E wiring test for Telegram client implementation.

This test is env-gated because real provider credentials are external.
"""

import importlib
from os import getenv

import pytest

from chat_client_api import Channel


@pytest.mark.e2e
def test_telegram_wiring_e2e() -> None:
    """Validate interface -> implementation wiring in an E2E-style path."""
    if getenv("TELEGRAM_E2E_ENABLED") != "1":
        pytest.skip("Set TELEGRAM_E2E_ENABLED=1 to run Telegram E2E test")
    if not getenv("TELEGRAM_BOT_TOKEN"):
        pytest.skip("Set TELEGRAM_BOT_TOKEN in CI settings to run Telegram E2E")

    importlib.import_module("telegram_client_impl")
    get_client = importlib.import_module("chat_client_api").get_client

    client = get_client()

    channels = client.get_channels()
    assert isinstance(channels, list)
    for channel in channels:
        assert isinstance(channel, Channel)
