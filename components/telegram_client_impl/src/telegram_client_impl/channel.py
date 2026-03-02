"""Telegram Channel scaffold model implementing the Channel contract."""

from chat_client_api.channel import Channel


class TelegramChannel(Channel):
    """Concrete channel model for Telegram-backed channels/chats."""

    def __init__(self, *, channel_id: str, name: str, channel_type: str) -> None:
        """Initialize a Telegram channel scaffold model."""
        self._id = channel_id
        self._name = name
        self._channel_type = channel_type

    @property
    def id(self) -> str:
        """Return the unique identifier of the channel."""
        return self._id

    @property
    def name(self) -> str:
        """Return the display name of the channel."""
        return self._name

    @property
    def channel_type(self) -> str:
        """Return the type of channel (e.g. group/private/channel)."""
        return self._channel_type
