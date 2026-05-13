"""Telegram Bot API implementation of the shared ``ChatClient`` contract."""

import logging
import os
import time
from collections.abc import Callable
from typing import Any

import httpx

from chat_client_api import Channel, ChatClient, Message
from telegram_client_impl.config import TelegramClientConfig
from telegram_client_impl.errors import TelegramAuthError, TelegramClientError
from telegram_client_impl.store import (
    channel_from_chat,
    get_store,
    record_bot_api_message,
    record_update,
)

MAX_TEXT_LENGTH = 4096
TELEGRAM_CONFLICT_ERROR_CODE = 409
TELEGRAM_TOO_MANY_REQUESTS_ERROR_CODE = 429
BACKGROUND_POLL_TIMEOUT_SECONDS = 3
TELEGRAM_HTTP_TIMEOUT_SECONDS = 30.0
TELEGRAM_RETRY_AFTER_CAP_SECONDS = 5
POLLING_OFFSET_STATE_KEY = "telegram_get_updates_offset"
POLLING_ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
    "my_chat_member",
]
LOGGER = logging.getLogger(__name__)


class TelegramClient(ChatClient):
    """Telegram client backed by the official Bot API."""

    def __init__(
        self,
        *,
        config: TelegramClientConfig,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Initialize a Telegram Bot API client with static configuration."""
        self._config = config
        self._http_client = http_client
        self._owns_http_client = http_client is None
        self._connected = False
        self._polling_checked = False

    def send_message(self, channel_id: str, text: str) -> Message:
        """Send a message to a Telegram chat through the bot."""
        _require_non_empty(value=channel_id, name="channel_id")
        _require_non_empty(value=text, name="text")
        _require_max_length(value=text, name="text", max_length=MAX_TEXT_LENGTH)
        self._ensure_connected()

        result = self._request(
            "sendMessage",
            json={"chat_id": channel_id, "text": text},
        )
        raw_message = _as_dict(result.get("result"))
        stored = record_bot_api_message(raw_message)
        return get_store().list_messages(
            channel_id=stored.channel_id,
            max_results=1,
        )[0]

    def get_messages(
        self,
        channel_id: str,
        limit: int = 10,
        cursor: str | None = None,
        *,
        max_results: int | None = None,
    ) -> list[Message]:
        """Retrieve bot-observed messages from a Telegram chat."""
        _require_non_empty(value=channel_id, name="channel_id")
        requested_limit = max_results if max_results is not None else limit
        if requested_limit <= 0:
            msg = "limit must be > 0"
            raise ValueError(msg)

        self._ensure_connected()
        self._sync_updates_from_polling()
        messages = get_store().list_messages(
            channel_id=channel_id,
            max_results=requested_limit,
            cursor=cursor,
        )
        return list(messages)

    def get_message(self, message_id: str) -> Message:
        """Return a bot-observed message by simple or opaque message ID."""
        _require_non_empty(value=message_id, name="message_id")
        self._ensure_connected()

        self._sync_updates_from_polling()
        message = get_store().get_message(message_id=message_id)
        if message is None:
            msg = f"Message not found: {message_id}"
            raise ValueError(msg)
        return message

    def delete_message(self, message_id: str, channel_id: str | None = None) -> None:
        """Delete a message if the bot has Telegram permission."""
        channel_id, provider_message_id = _resolve_message_reference(
            message_id=message_id,
            channel_id=channel_id,
        )
        self._ensure_connected()

        result = self._request(
            "deleteMessage",
            json={"chat_id": channel_id, "message_id": int(provider_message_id)},
        )
        if result.get("result") is not True:
            msg = "Telegram Bot API did not confirm message deletion"
            raise TelegramClientError(msg, method="deleteMessage")
        get_store().remove_message(
            channel_id=channel_id,
            message_id=provider_message_id,
        )

    def get_channels(self) -> list[Channel]:
        """List Telegram chats known to this bot instance."""
        self._ensure_connected()
        self._sync_updates_from_polling()
        channels = get_store().list_channels()
        return list(channels)

    def get_channel(self, channel_id: str) -> Channel:
        """Return one Telegram chat, refreshing metadata from Telegram on miss."""
        _require_non_empty(value=channel_id, name="channel_id")
        self._ensure_connected()

        self._sync_updates_from_polling()
        store = get_store()
        channel = store.get_channel(channel_id=channel_id)
        if channel is not None:
            return channel

        result = self._request("getChat", json={"chat_id": channel_id})
        raw_chat = _as_dict(result.get("result"))
        store.upsert_channel(channel_from_chat(raw_chat))
        channel = store.get_channel(channel_id=channel_id)
        if channel is None:
            msg = f"Channel not found: {channel_id}"
            raise ValueError(msg)
        return channel

    def user_can_access_channel(self, *, user_id: str, channel_id: str) -> bool:
        """Return whether Telegram reports the user as a chat member."""
        _require_non_empty(value=user_id, name="user_id")
        _require_non_empty(value=channel_id, name="channel_id")
        self._ensure_connected()

        try:
            numeric_user_id = int(user_id)
        except ValueError:
            return False
        result = self._request(
            "getChatMember",
            json={"chat_id": channel_id, "user_id": numeric_user_id},
        )
        member = _as_dict(result.get("result"))
        return member.get("status") not in {"left", "kicked"}

    def get_bot_username(self) -> str | None:
        """Return the current bot username reported by Telegram, if any."""
        self._ensure_connected()
        payload = self._request(
            "getMe",
            json={},
            retry_on_rate_limit=False,
        )
        result = payload.get("result")
        if not isinstance(result, dict):
            return None
        username = result.get("username")
        return username if isinstance(username, str) and username else None

    def _ensure_connected(self) -> None:
        """Ensure required Bot API configuration is present."""
        if self._connected:
            return
        if self._config.bot_token is None:
            msg = "TELEGRAM_BOT_TOKEN is required"
            raise TelegramAuthError(msg)
        if self._http_client is None:
            self._http_client = httpx.Client(
                base_url=self._api_base_url,
                timeout=TELEGRAM_HTTP_TIMEOUT_SECONDS,
            )
        self._connected = True

    @property
    def _api_base_url(self) -> str:
        token = (self._config.bot_token or "").strip()
        base = (self._config.bot_api_base_url or "").strip().rstrip("/")
        if not base:
            base = "https://api.telegram.org"
        return f"{base}/bot{token}"

    def _request(
        self,
        method: str,
        *,
        json: dict[str, object],
        retry_on_rate_limit: bool = True,
    ) -> dict[str, Any]:
        self._ensure_connected()
        assert self._http_client is not None
        try:
            response = self._http_client.post(f"/{method}", json=json)
            payload = response.json()
        except httpx.HTTPError as exc:
            msg = f"Telegram Bot API request failed for {method}"
            raise TelegramClientError(msg, method=method) from exc
        except ValueError as exc:
            msg = f"Telegram Bot API returned invalid JSON for {method}"
            raise TelegramClientError(msg, method=method) from exc

        if not isinstance(payload, dict):
            msg = f"Telegram Bot API returned non-object payload for {method}"
            raise TelegramClientError(msg, method=method)
        if payload.get("ok") is not True:
            error_code = _as_int(payload.get("error_code"))
            parameters = payload.get("parameters")
            if (
                retry_on_rate_limit
                and error_code == TELEGRAM_TOO_MANY_REQUESTS_ERROR_CODE
                and isinstance(parameters, dict)
            ):
                retry_after = _as_int(parameters.get("retry_after"))
                if (
                    retry_after is not None
                    and 0 < retry_after <= TELEGRAM_RETRY_AFTER_CAP_SECONDS
                ):
                    time.sleep(retry_after)
                    return self._request(
                        method,
                        json=json,
                        retry_on_rate_limit=False,
                    )
            description = payload.get("description") or payload
            msg = f"Telegram Bot API returned error for {method}: {description}"
            raise TelegramClientError(
                msg,
                method=method,
                error_code=error_code,
                parameters=parameters if isinstance(parameters, dict) else None,
            )
        return payload

    def _sync_updates_from_polling(
        self,
        *,
        force: bool = False,
        on_update: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        """Pull pending updates when this bot is not configured for webhooks."""
        if self._polling_checked:
            return
        if _background_polling_enabled() and not force:
            self._polling_checked = True
            return
        self._polling_checked = True

        try:
            webhook_configured = self._webhook_is_configured()
        except TelegramClientError as exc:
            LOGGER.warning("Telegram getWebhookInfo failed: %s", exc)
            return
        if webhook_configured:
            return

        try:
            updates_payload = self._request(
                "getUpdates",
                json=self._polling_request_payload(
                    timeout_seconds=BACKGROUND_POLL_TIMEOUT_SECONDS if force else 0,
                ),
            )
        except TelegramClientError as exc:
            if exc.error_code == TELEGRAM_CONFLICT_ERROR_CODE:
                LOGGER.debug("Telegram getUpdates skipped: another poller is active")
                return
            LOGGER.warning("Telegram getUpdates failed: %s", exc)
            return

        self._record_polled_updates(updates_payload.get("result"), on_update=on_update)

    def sync_updates(
        self,
        *,
        force: bool = False,
        on_update: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        """Synchronize pending Bot API updates when polling is available."""
        if force:
            self._polling_checked = False
        self._sync_updates_from_polling(force=force, on_update=on_update)

    def _webhook_is_configured(self) -> bool:
        """Return whether Telegram reports an active webhook URL."""
        webhook_info = self._request("getWebhookInfo", json={})
        result = _as_dict(webhook_info.get("result"))
        return bool(result.get("url"))

    def _polling_request_payload(
        self,
        *,
        timeout_seconds: int = 0,
    ) -> dict[str, object]:
        """Build the getUpdates request from the persisted offset."""
        offset = get_store().get_int_state(key=POLLING_OFFSET_STATE_KEY)
        payload: dict[str, object] = {
            "limit": 100,
            "timeout": timeout_seconds,
            "allowed_updates": POLLING_ALLOWED_UPDATES,
        }
        if offset is not None:
            payload["offset"] = offset
        return payload

    def _record_polled_updates(
        self,
        updates: object,
        *,
        on_update: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        """Record polled updates and advance the persisted offset."""
        if not isinstance(updates, list):
            msg = "Telegram Bot API returned non-list updates result"
            raise TelegramClientError(msg, method="getUpdates")

        store = get_store()
        update_ids: list[int] = []
        for update in updates:
            if not isinstance(update, dict):
                continue
            record_update(update)
            if on_update is not None:
                on_update(update)
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                update_ids.append(update_id)

        if update_ids:
            store.set_int_state(
                key=POLLING_OFFSET_STATE_KEY,
                value=max(update_ids) + 1,
            )

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_http_client and self._http_client is not None:
            self._http_client.close()


def get_client_impl(*, interactive: bool = False) -> ChatClient:
    """Return the injected client factory implementation."""
    config = TelegramClientConfig.from_env(interactive=interactive)
    return TelegramClient(config=config)


def get_bot_login_target() -> tuple[str | None, str | None]:
    """Return the bot username and a Telegram deep link that shows Start."""
    env_username = os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    if env_username:
        return env_username, _bot_start_url(env_username)

    config = TelegramClientConfig.from_env(interactive=False)
    if not config.bot_token:
        return None, None

    client = TelegramClient(config=config)
    try:
        username = client.get_bot_username()
    except TelegramClientError:
        LOGGER.warning("Failed to resolve Telegram bot username from Bot API")
        return None, None
    finally:
        client.close()
    if username is None:
        return None, None
    return username, _bot_start_url(username)


def _require_non_empty(*, value: str, name: str) -> None:
    """Validate required string parameters."""
    if not value:
        msg = f"{name} must be non-empty"
        raise ValueError(msg)


def _require_max_length(*, value: str, name: str, max_length: int) -> None:
    """Validate Telegram Bot API string length limits."""
    if len(value) > max_length:
        msg = f"{name} must be <= {max_length} characters"
        raise ValueError(msg)


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = "Telegram Bot API response missing message result"
        raise TelegramClientError(msg)
    return value


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _bot_start_url(username: str) -> str:
    normalized = username.lstrip("@")
    return f"https://t.me/{normalized}?start=chatclient"


def _background_polling_enabled() -> bool:
    return os.getenv("TELEGRAM_UPDATE_MODE", "webhook").strip().lower() == "polling"


def _resolve_message_reference(
    *,
    message_id: str,
    channel_id: str | None = None,
) -> tuple[str, str]:
    _require_non_empty(value=message_id, name="message_id")
    resolved_channel_id = channel_id
    provider_message_id = message_id
    if ":" in message_id:
        embedded_channel_id, provider_message_id = message_id.split(":", 1)
        if channel_id is not None and channel_id != embedded_channel_id:
            msg = "message_id channel_id mismatch"
            raise ValueError(msg)
        resolved_channel_id = embedded_channel_id
    if resolved_channel_id is None:
        msg = "message_id must be formatted as channel_id:message_id"
        raise ValueError(msg)
    _require_non_empty(value=resolved_channel_id, name="channel_id")
    _require_non_empty(value=provider_message_id, name="message_id")
    return resolved_channel_id, provider_message_id
