"""Chat operation endpoints delegating through chat_client_api."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

import telegram_client_impl  # noqa: F401
from chat_client_api import Client, get_client
from chat_client_service.models import (
    ChannelModel,
    DeleteMessageResponse,
    MessageModel,
    SendMessageRequest,
)
from chat_client_service.routers.auth import get_current_token

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    dependencies=[Depends(get_current_token)],
)


def get_chat_client() -> Client:
    """FastAPI dependency that returns a Telegram-backed Client.

    Override via ``app.dependency_overrides[get_chat_client]`` in tests.
    """
    return get_client()


@router.post("/messages")
def send_message(
    payload: SendMessageRequest,
    client: Annotated[Client, Depends(get_chat_client)],
) -> MessageModel:
    """Send a message to a channel via telegram_client_impl."""
    try:
        msg = client.send_message(channel_id=payload.channel_id, text=payload.text)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return MessageModel(
        id=msg.id,
        sender=msg.sender,
        channel_id=msg.channel_id,
        timestamp=msg.timestamp,
        text=msg.text,
    )


@router.get("/messages")
def get_messages(
    client: Annotated[Client, Depends(get_chat_client)],
    channel_id: Annotated[str, Query(min_length=1)],
    max_results: Annotated[int, Query(gt=0)] = 10,
) -> list[MessageModel]:
    """Retrieve messages from a channel via telegram_client_impl."""
    try:
        msgs = list(client.get_messages(channel_id=channel_id, max_results=max_results))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return [
        MessageModel(
            id=m.id,
            sender=m.sender,
            channel_id=m.channel_id,
            timestamp=m.timestamp,
            text=m.text,
        )
        for m in msgs
    ]


@router.delete("/messages/{message_id}")
def delete_message(
    client: Annotated[Client, Depends(get_chat_client)],
    message_id: str,
    channel_id: Annotated[str, Query(min_length=1)],
) -> DeleteMessageResponse:
    """Delete a message via telegram_client_impl."""
    try:
        success = client.delete_message(channel_id=channel_id, message_id=message_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return DeleteMessageResponse(success=success)


@router.get("/channels")
def get_channels(
    client: Annotated[Client, Depends(get_chat_client)],
) -> list[ChannelModel]:
    """List available channels via telegram_client_impl."""
    try:
        channels = list(client.get_channels())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return [
        ChannelModel(
            id=ch.id,
            name=ch.name,
            channel_type=ch.channel_type,
        )
        for ch in channels
    ]
