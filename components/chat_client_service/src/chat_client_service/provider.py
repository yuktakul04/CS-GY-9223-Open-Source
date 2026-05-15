"""Provider loading for the shared chat client interface."""

from __future__ import annotations

import importlib
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from slack_sdk.errors import SlackApiError

from chat_client_api import ChatClient, Message, register_client

if TYPE_CHECKING:
    from collections.abc import Callable

    from chat_client_api import Channel

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
    provider_factory = cast("Callable[[], ChatClient]", factory)
    if selected == "slack":
        register_client(lambda: _SlackCompatibilityClient(provider_factory()))
    else:
        register_client(provider_factory)
    return selected


def is_telegram_provider() -> bool:
    """Return whether the configured chat provider is Telegram."""
    return configured_chat_provider() == "telegram"


class _SlackCompatibilityClient(ChatClient):
    """Normalize Team 9's Slack package to the canonical shared API contract."""

    def __init__(self, inner: ChatClient) -> None:
        self._inner = inner

    def send_message(self, channel_id: str, text: str) -> Message:
        return _normalize_message(self._inner.send_message(channel_id, text))

    def get_channels(self) -> list[Channel]:
        return list(self._inner.get_channels())

    def get_channel(self, channel_id: str) -> Channel:
        return self._inner.get_channel(channel_id)

    def get_messages(
        self,
        channel_id: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        return [
            _normalize_message(message)
            for message in self._inner.get_messages(channel_id, limit, cursor)
        ]

    def get_message(self, message_id: str) -> Message:
        return _normalize_message(self._inner.get_message(message_id))

    def delete_message(self, message_id: str) -> None:
        self._inner.delete_message(message_id)

    def user_can_access_channel(self, user_id: str, channel_id: str) -> bool:  # noqa: ARG002
        """Return whether the Slack bot can operate in the requested channel."""
        slack_web_client = getattr(self._inner, "client", None)
        conversations_info = getattr(slack_web_client, "conversations_info", None)
        if callable(conversations_info):
            try:
                response = conversations_info(channel=channel_id)
            except (SlackApiError, TypeError, ValueError):
                return False
            channel = _response_channel(response)
            if "is_member" in channel:
                return bool(channel["is_member"])
        try:
            self._inner.get_channel(channel_id)
        except ValueError:
            return False
        return True


def _normalize_message(message: Message) -> Message:
    if isinstance(message.timestamp, datetime):
        return message
    return Message(
        message_id=message.message_id,
        channel=message.channel,
        text=message.text,
        sender=message.sender,
        timestamp=_parse_timestamp(message.timestamp),
    )


def _response_channel(response: object) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    channel = response.get("channel")
    return channel if isinstance(channel, dict) else {}


def _parse_timestamp(value: object) -> datetime:
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromtimestamp(float(text), tz=UTC)
        except (OverflowError, ValueError):
            return datetime.now(tz=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
