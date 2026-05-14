"""Provider loading for the shared chat client interface."""

from __future__ import annotations

import importlib
import os
from typing import TYPE_CHECKING, cast

from chat_client_api import register_client

if TYPE_CHECKING:
    from collections.abc import Callable

    from chat_client_api import ChatClient

_DEFAULT_PROVIDER = "telegram"
_PROVIDER_MODULES = {
    "telegram": ("telegram_client_impl.client", "get_client_impl"),
    "slack": ("slack_client_impl.client", "_create_slack_client"),
}


def configured_chat_provider() -> str:
    """Return the configured chat provider name."""
    return os.getenv("CHAT_CLIENT_PROVIDER", _DEFAULT_PROVIDER).strip().lower()


def load_chat_provider(provider: str | None = None) -> str:
    """Import the configured provider package so it registers with chat_client_api."""
    selected = (provider or configured_chat_provider()).strip().lower()
    provider_config = _PROVIDER_MODULES.get(selected)
    if provider_config is None:
        supported = ", ".join(sorted(_PROVIDER_MODULES))
        msg = f"CHAT_CLIENT_PROVIDER must be one of: {supported}"
        raise RuntimeError(msg)
    module_name, factory_name = provider_config
    module = importlib.import_module(module_name)
    factory = getattr(module, factory_name, None)
    if not callable(factory):
        msg = f"{module_name} must expose {factory_name}()"
        raise TypeError(msg)
    register_client(cast("Callable[[], ChatClient]", factory))
    return selected


def is_telegram_provider() -> bool:
    """Return whether the configured chat provider is Telegram."""
    return configured_chat_provider() == "telegram"
