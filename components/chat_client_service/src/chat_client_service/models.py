"""Shared API models for the chat client service scaffold."""

from pydantic import BaseModel, Field


class ChannelModel(BaseModel):
    """Transport model for a channel."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    channel_type: str = Field(min_length=1)


class MessageModel(BaseModel):
    """Transport model for a message."""

    id: str = Field(min_length=1)
    sender: str
    channel_id: str = Field(min_length=1)
    timestamp: str
    text: str


class SendMessageRequest(BaseModel):
    """Request payload for sending a message."""

    channel_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class DeleteMessageResponse(BaseModel):
    """Response payload for delete message operations."""

    success: bool


class OAuthLoginResponse(BaseModel):
    """Compatibility model for Telegram login initiation responses."""

    authorization_url: str
    state: str


class OAuthCallbackResponse(BaseModel):
    """Compatibility model for Telegram login callback responses."""

    detail: str
    code: str | None = None
    state: str | None = None
    access_token: str | None = None
    token_type: str | None = None


class OAuthTokenResponse(BaseModel):
    """Compatibility model for issued bearer session tokens."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
