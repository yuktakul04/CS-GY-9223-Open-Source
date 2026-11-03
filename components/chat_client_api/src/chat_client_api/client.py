"""Core chat client contract definitions and factory placeholder."""

from abc import ABC, abstractmethod
from collections.abc import Iterator

from chat_client_api.channel import Channel
from chat_client_api.message import Message


class Client(ABC):
    """Abstract base class representing a chat client."""

    @abstractmethod
    def send_message(self, channel_id: str, text: str) -> Message:
        """Send a message to a channel.

        Args:
            channel_id: The target channel or conversation ID.
            text: The message content to send.

        Returns:
            The sent Message object.

        """
        raise NotImplementedError

    @abstractmethod
    def get_messages(self, channel_id: str, max_results: int = 10) -> Iterator[Message]:
        """Return an iterator of messages from a channel.

        Args:
            channel_id: The channel or conversation to fetch messages from.
            max_results: Maximum number of messages to return.

        Returns:
            An iterator of Message objects. Results are not paginated;
            at most max_results messages are returned. Errors during
            iteration may raise implementation-specific exceptions.


        """
        raise NotImplementedError

    @abstractmethod
    def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Delete a message by its ID.

        Args:
            channel_id: The channel containing the message.
            message_id: The unique identifier of the message to delete.

        Raises:
            MessageNotFoundError: If the message does not exist.
            PermissionError: If the client lacks permission to delete.

        """
        raise NotImplementedError

    @abstractmethod
    def get_channels(self) -> Iterator[Channel]:
        """Return an iterator of available channels or conversations.

        Returns:
            An iterator of Channel objects.

        """
        raise NotImplementedError


def get_client(*, interactive: bool = False) -> Client:
    """Return an instance of a Chat Client.

    Args:
        interactive: If True, allow interactive authentication prompts.

    Returns:
        A Client instance.

    Raises:
        NotImplementedError: If no implementation has been injected.

    """
    raise NotImplementedError
