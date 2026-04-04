"""Concrete interface models used by the service-backed adapter."""

from chat_client_api.channel import Channel
from chat_client_api.message import Message


class AdapterChannel(Channel):
    """Channel concrete model returned by the service-backed adapter."""

    def __init__(self, *, channel_id: str, name: str, channel_type: str) -> None:
        """Create channel model."""
        self._id = channel_id
        self._name = name
        self._channel_type = channel_type

    @property
    def id(self) -> str:
        """Return channel identifier."""
        return self._id

    @property
    def name(self) -> str:
        """Return channel display name."""
        return self._name

    @property
    def channel_type(self) -> str:
        """Return channel type string."""
        return self._channel_type


class AdapterMessage(Message):
    """Message concrete model returned by the service-backed adapter."""

    def __init__(
        self,
        *,
        message_id: str,
        sender: str,
        channel_id: str,
        timestamp: str,
        text: str,
    ) -> None:
        """Create message model."""
        self._id = message_id
        self._sender = sender
        self._channel_id = channel_id
        self._timestamp = timestamp
        self._text = text

    @property
    def id(self) -> str:
        """Return message identifier."""
        return self._id

    @property
    def sender(self) -> str:
        """Return message sender identifier."""
        return self._sender

    @property
    def channel_id(self) -> str:
        """Return message channel identifier."""
        return self._channel_id

    @property
    def timestamp(self) -> str:
        """Return message timestamp."""
        return self._timestamp

    @property
    def text(self) -> str:
        """Return message text payload."""
        return self._text
