"""DTOs used by the stable service-client wrapper."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelDTO:
    """Channel DTO returned by the service client wrapper."""

    id: str
    name: str
    channel_type: str


@dataclass(frozen=True)
class MessageDTO:
    """Message DTO returned by the service client wrapper."""

    id: str
    sender: str
    channel_id: str
    timestamp: str
    text: str
