"""Chat operation endpoints delegating through chat_client_api."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from chat_client_api import Channel, ChatClient, Message, get_client
from chat_client_service.models import (
    ChannelModel,
    DeleteMessageResponse,
    MessageModel,
    SendMessageRequest,
)
from chat_client_service.provider import configured_chat_provider, load_chat_provider
from chat_client_service.routers.auth import (
    get_current_claims,
    get_current_token,
)
from telegram_client_impl.client import get_bot_login_target
from telegram_client_impl.errors import TelegramClientError
from telegram_client_impl.store import get_store

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    dependencies=[Depends(get_current_token)],
)


def get_chat_client() -> ChatClient:
    """FastAPI dependency that returns the configured ChatClient provider."""
    load_chat_provider()
    return get_client()


class MessageListQuery:
    """Query parameters for listing messages."""

    def __init__(
        self,
        limit: Annotated[int | None, Query(gt=0)] = None,
        max_results: Annotated[int | None, Query(gt=0)] = None,
        cursor: str | None = None,
    ) -> None:
        """Capture message list query values."""
        self.limit = limit
        self.max_results = max_results
        self.cursor = cursor

    @property
    def requested_limit(self) -> int:
        """Return the effective shared API limit value."""
        return self.limit if self.limit is not None else (self.max_results or 10)


@router.post("/messages")
def send_message(
    payload: SendMessageRequest,
    claims: Annotated[dict[str, str], Depends(get_current_claims)],
    client: Annotated[ChatClient, Depends(get_chat_client)],
) -> MessageModel:
    """Send a message through the configured ChatClient provider."""
    requested_self_chat = payload.channel_id == "me"
    channel_id = _resolve_channel_id(claims=claims, channel_id=payload.channel_id)
    _require_channel_access(claims=claims, channel_id=channel_id, client=client)
    try:
        msg = client.send_message(channel_id=channel_id, text=payload.text)
        get_store().grant_access(
            telegram_id=claims.get("telegram_id", ""),
            channel_id=channel_id,
        )
    except Exception as exc:
        if _is_missing_bot_start(exc=exc, requested_self_chat=requested_self_chat):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_missing_bot_start_detail(),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return _message_model(msg)


@router.get("/messages")
def get_messages(
    channel_id: str,
    claims: Annotated[dict[str, str], Depends(get_current_claims)],
    client: Annotated[ChatClient, Depends(get_chat_client)],
    query: Annotated[MessageListQuery, Depends()],
) -> list[MessageModel]:
    """Retrieve messages from a channel through the configured provider."""
    resolved_channel_id = _resolve_channel_id(claims=claims, channel_id=channel_id)
    _require_channel_access(
        claims=claims,
        channel_id=resolved_channel_id,
        client=client,
    )
    try:
        if query.cursor is None:
            msgs = client.get_messages(
                channel_id=resolved_channel_id,
                limit=query.requested_limit,
            )
        else:
            msgs = client.get_messages(
                channel_id=resolved_channel_id,
                limit=query.requested_limit,
                cursor=query.cursor,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return [_message_model(message) for message in msgs]


@router.get("/messages/{message_id}")
def get_message(
    message_id: str,
    claims: Annotated[dict[str, str], Depends(get_current_claims)],
    client: Annotated[ChatClient, Depends(get_chat_client)],
) -> MessageModel:
    """Retrieve a single message by opaque id."""
    try:
        msg = client.get_message(message_id=message_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    _require_channel_access(claims=claims, channel_id=msg.channel, client=client)
    return _message_model(msg)


@router.delete("/messages/{message_id}")
def delete_message(
    message_id: str,
    claims: Annotated[dict[str, str], Depends(get_current_claims)],
    client: Annotated[ChatClient, Depends(get_chat_client)],
    channel_id: str | None = None,
) -> DeleteMessageResponse:
    """Delete a message through the configured ChatClient provider."""
    resolved_channel_id, provider_message_id = _resolve_delete_reference(
        claims=claims,
        message_id=message_id,
        channel_id=channel_id,
    )
    _require_channel_access(
        claims=claims,
        channel_id=resolved_channel_id,
        client=client,
    )
    try:
        client.delete_message(message_id=f"{resolved_channel_id}:{provider_message_id}")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return DeleteMessageResponse(success=True)


@router.get("/channels")
def get_channels(
    claims: Annotated[dict[str, str], Depends(get_current_claims)],
    client: Annotated[ChatClient, Depends(get_chat_client)],
) -> list[ChannelModel]:
    """List available channels through the configured ChatClient provider."""
    try:
        channels = list(client.get_channels())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return [
        _channel_model(channel)
        for channel in channels
        if _can_access_channel(
            claims=claims,
            channel_id=channel.channel_id,
            client=client,
        )
    ]


@router.get("/channels/{channel_id}")
def get_channel(
    channel_id: str,
    claims: Annotated[dict[str, str], Depends(get_current_claims)],
    client: Annotated[ChatClient, Depends(get_chat_client)],
) -> ChannelModel:
    """Retrieve a single known channel by id."""
    resolved_channel_id = _resolve_channel_id(claims=claims, channel_id=channel_id)
    _require_channel_access(
        claims=claims,
        channel_id=resolved_channel_id,
        client=client,
    )
    try:
        channel = client.get_channel(channel_id=resolved_channel_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return _channel_model(channel)


def _resolve_channel_id(*, claims: dict[str, str], channel_id: str) -> str:
    if channel_id == "me":
        if configured_chat_provider() != "telegram":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'me' is only supported by the Telegram provider.",
            )
        telegram_id = claims.get("telegram_id")
        if not telegram_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authenticated session has no Telegram identity.",
            )
        return telegram_id
    return channel_id


def _require_channel_access(
    *,
    claims: dict[str, str],
    channel_id: str,
    client: ChatClient,
) -> None:
    if _can_access_channel(claims=claims, channel_id=channel_id, client=client):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to that channel.",
    )


def _can_access_channel(
    *,
    claims: dict[str, str],
    channel_id: str,
    client: ChatClient,
) -> bool:
    telegram_id = claims.get("telegram_id", "")
    if get_store().user_can_access(telegram_id=telegram_id, channel_id=channel_id):
        return True

    membership_checker = getattr(client, "user_can_access_channel", None)
    if not callable(membership_checker):
        return False
    try:
        allowed = membership_checker(user_id=telegram_id, channel_id=channel_id)
    except (TypeError, ValueError, RuntimeError):
        return False
    if not isinstance(allowed, bool):
        return False
    if allowed:
        get_store().grant_access(telegram_id=telegram_id, channel_id=channel_id)
    return allowed


def _resolve_delete_reference(
    *,
    claims: dict[str, str],
    message_id: str,
    channel_id: str | None,
) -> tuple[str, str]:
    if channel_id is not None:
        resolved_channel_id = _resolve_channel_id(claims=claims, channel_id=channel_id)
        if ":" in message_id:
            embedded_channel_id, provider_message_id = message_id.split(":", 1)
            embedded_channel_id = _resolve_channel_id(
                claims=claims,
                channel_id=embedded_channel_id,
            )
            if embedded_channel_id != resolved_channel_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="message_id channel does not match channel_id",
                )
            return resolved_channel_id, provider_message_id
        return resolved_channel_id, message_id

    if ":" in message_id:
        resolved_channel_id, provider_message_id = message_id.split(":", 1)
        return (
            _resolve_channel_id(claims=claims, channel_id=resolved_channel_id),
            provider_message_id,
        )

    stored = get_store().get_message(message_id=message_id)
    if stored is not None:
        _, provider_message_id = stored.message_id.split(":", 1)
        return stored.channel, provider_message_id

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Use the returned opaque message id or include channel_id",
    )


def _message_model(message: Message) -> MessageModel:
    return MessageModel(
        id=message.message_id,
        sender=message.sender,
        channel_id=message.channel,
        timestamp=_format_timestamp(message.timestamp),
        text=message.text,
    )


def _channel_model(channel: Channel) -> ChannelModel:
    return ChannelModel(
        id=channel.channel_id,
        name=channel.name,
        channel_type=channel.channel_type or "unknown",
    )


def _format_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _is_missing_bot_start(
    *,
    exc: Exception,
    requested_self_chat: bool,
) -> bool:
    if not requested_self_chat:
        return False
    if not _is_telegram_send_message_error(exc):
        return False
    return "chat not found" in str(exc).lower()


def _missing_bot_start_detail() -> str:
    bot_username, bot_start_url = get_bot_login_target()
    if bot_username and bot_start_url:
        return (
            "This bot cannot message your private chat yet. Open "
            f"@{bot_username} ({bot_start_url}), press Start, then retry. "
            "If you already did that, log in again and make sure you authenticated "
            "against the same bot."
        )
    return (
        "This bot cannot message your private chat yet. Open the bot in Telegram, "
        "press Start, then retry. If you already did that, log in again and make "
        "sure you authenticated against the same bot."
    )


def _is_telegram_send_message_error(exc: Exception) -> bool:
    return isinstance(exc, TelegramClientError) and exc.method == "sendMessage"
