"""Telegram Message model implementing the Message contract."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from chat_client_api.message import Message
from telegram_client_impl.errors import TelegramMappingError


class TelegramMessage(Message):
    """Concrete message model for Telegram-backed messages."""

    def __init__(
        self,
        *,
        message_id: str,
        sender: str,
        channel_id: str,
        timestamp: str,
        text: str,
    ) -> None:
        """Initialize a Telegram message model."""
        self._id = message_id
        self._sender = sender
        self._channel_id = channel_id
        self._timestamp = timestamp
        self._text = text

    @property
    def id(self) -> str:
        """Return the unique identifier of the message."""
        return self._id

    @property
    def sender(self) -> str:
        """Return the sender identifier."""
        return self._sender

    @property
    def channel_id(self) -> str:
        """Return the channel identifier."""
        return self._channel_id

    @property
    def timestamp(self) -> str:
        """Return an ISO timestamp for when the message was sent."""
        return self._timestamp

    @property
    def text(self) -> str:
        """Return the message body."""
        return self._text


def get_message_impl(msg_id: str, raw_data: str) -> Message:
    """Build a message instance from serialized provider data."""
    if not msg_id:
        msg = "msg_id must be non-empty"
        raise ValueError(msg)
    if not raw_data:
        msg = "raw_data must be non-empty"
        raise ValueError(msg)

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        msg = f"raw_data is not valid JSON: {exc}"
        raise TelegramMappingError(msg) from exc

    if not isinstance(data, dict):
        msg = "raw_data must decode to a JSON object"
        raise TelegramMappingError(msg)

    sender_value = data.get("sender") or data.get("from_id") or ""
    sender = str(sender_value)

    channel_raw = data.get("channel_id") or data.get("chat_id")
    if channel_raw is None:
        msg = "raw_data missing required field 'channel_id' or 'chat_id'"
        raise TelegramMappingError(msg)
    channel_id = str(channel_raw)

    timestamp_raw = data.get("timestamp") or data.get("date")
    if timestamp_raw is None:
        msg = "raw_data missing required field 'timestamp' or 'date'"
        raise TelegramMappingError(msg)

    if isinstance(timestamp_raw, (int, float)):
        dt = datetime.fromtimestamp(timestamp_raw, tz=timezone.utc)
        timestamp = dt.isoformat()
    else:
        timestamp = str(timestamp_raw)

    text = str(data.get("text") or data.get("message") or "")

    return TelegramMessage(
        message_id=msg_id,
        sender=sender,
        channel_id=channel_id,
        timestamp=timestamp,
        text=text,
    )
