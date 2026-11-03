"""Message contract - Core message representation for chat clients."""

from abc import ABC, abstractmethod


class Message(ABC):
    """Abstract base class representing a chat message."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Return the unique identifier of the message."""
        raise NotImplementedError

    @property
    @abstractmethod
    def sender(self) -> str:
        """Return the sender's identifier."""
        raise NotImplementedError

    @property
    @abstractmethod
    def channel_id(self) -> str:
        """Return the channel or conversation ID this message belongs to."""
        raise NotImplementedError

    @property
    @abstractmethod
    def timestamp(self) -> str:
        """Return the timestamp when the message was sent."""
        raise NotImplementedError

    @property
    @abstractmethod
    def text(self) -> str:
        """Return the text content of the message."""
        raise NotImplementedError


def get_message(msg_id: str, raw_data: str) -> Message:
    """Return an instance of a Message.

    Args:
        msg_id: The unique identifier for the message.
        raw_data: The raw data used to construct the message.

    Returns:
        An instance conforming to the Message contract.

    Raises:
        NotImplementedError: If not overridden by an implementation.

    """
    raise NotImplementedError
