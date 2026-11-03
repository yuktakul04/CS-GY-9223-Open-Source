"""Telegram Client implementation for the chat_client_api.Client contract."""

from collections.abc import Iterator

from telethon.sync import TelegramClient as _TeleClient

from chat_client_api.channel import Channel
from chat_client_api.client import Client
from chat_client_api.message import Message
from telegram_client_impl.config import TelegramClientConfig
from telegram_client_impl.errors import TelegramAuthError, TelegramClientError
from telegram_client_impl.mappers import to_channel, to_message


class TelegramClient(Client):
    """Telegram client backed by Telethon."""

    def __init__(self, *, config: TelegramClientConfig) -> None:
        """Initialize a Telegram client with static configuration."""
        self._config = config
        self._client: _TeleClient | None = None
        self._connected = False

    def _get_client(self) -> _TeleClient:
        """Return the underlying Telethon client (must be connected)."""
        assert self._client is not None
        return self._client

    def send_message(self, channel_id: str, text: str) -> Message:
        """Send a message to a Telegram channel/chat."""
        _require_non_empty(value=channel_id, name="channel_id")
        _require_non_empty(value=text, name="text")
        self._ensure_connected()

        try:
            raw = self._get_client().send_message(int(channel_id), text)
        except Exception as exc:  # pragma: no cover - Telethon-specific error types
            msg = f"Failed to send message: {exc}"
            raise TelegramClientError(msg) from exc

        return to_message(raw)

    def get_messages(
        self,
        channel_id: str,
        max_results: int = 10,
    ) -> Iterator[Message]:
        """Retrieve messages from a Telegram channel/chat."""
        _require_non_empty(value=channel_id, name="channel_id")
        if max_results <= 0:
            msg = "max_results must be > 0"
            raise ValueError(msg)

        self._ensure_connected()

        try:
            iterator = self._get_client().iter_messages(
                int(channel_id), limit=max_results
            )
        except Exception as exc:  # pragma: no cover - Telethon-specific error types
            msg = f"Failed to get messages: {exc}"
            raise TelegramClientError(msg) from exc

        for raw in iterator:
            yield to_message(raw)

    def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Delete a message in a Telegram channel/chat."""
        _require_non_empty(value=channel_id, name="channel_id")
        _require_non_empty(value=message_id, name="message_id")

        self._ensure_connected()

        try:
            self._get_client().delete_messages(int(channel_id), int(message_id))
        except Exception as exc:  # pragma: no cover - Telethon-specific error types
            msg = f"Failed to delete message: {exc}"
            raise TelegramClientError(msg) from exc

        return True

    def get_channels(self) -> Iterator[Channel]:
        """List available Telegram channels/chats."""
        self._ensure_connected()

        try:
            dialogs = self._get_client().get_dialogs()
        except Exception as exc:  # pragma: no cover - Telethon-specific error types
            msg = f"Failed to retrieve channels: {exc}"
            raise TelegramClientError(msg) from exc

        for dialog in dialogs:
            yield to_channel(dialog)

    def _ensure_connected(self) -> None:
        """Ensure the underlying Telethon client is authenticated and connected."""
        if self._connected:
            return

        if (
            self._config.api_id is None
            or self._config.api_hash is None
            or self._config.bot_token is None
        ):
            msg = (
                "TELEGRAM_API_ID, TELEGRAM_API_HASH, and "
                "TELEGRAM_BOT_TOKEN are required"
            )
            raise TelegramAuthError(msg)

        if self._client is None:
            self._client = _TeleClient(
                self._config.session_name,
                int(self._config.api_id),
                self._config.api_hash,
            )

        try:
            self._get_client().start(bot_token=self._config.bot_token)
        except Exception as exc:  # pragma: no cover - Telethon-specific error types
            msg = f"Failed to authenticate Telegram client: {exc}"
            raise TelegramAuthError(msg) from exc

        self._connected = True


def get_client_impl(*, interactive: bool = False) -> Client:
    """Return the injected client factory implementation."""
    config = TelegramClientConfig.from_env(interactive=interactive)
    return TelegramClient(config=config)


def _require_non_empty(*, value: str, name: str) -> None:
    """Validate required string parameters."""
    if not value:
        msg = f"{name} must be non-empty"
        raise ValueError(msg)
