"""Telegram Bot API webhook routes."""

import hmac
from os import getenv
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict

from chat_client_api import ChatClient
from chat_client_service.assistant import (
    TelegramAssistantOrchestrator,
    build_default_orchestrator,
)
from chat_client_service.routers.chat import get_chat_client
from telegram_client_impl.store import record_update

router = APIRouter(prefix="/telegram", tags=["telegram"])


class TelegramUpdate(BaseModel):
    """Permissive model for Telegram Bot API webhook updates."""

    model_config = ConfigDict(extra="allow")

    update_id: int


def get_telegram_assistant(
    chat_client: Annotated[ChatClient, Depends(get_chat_client)],
) -> TelegramAssistantOrchestrator | None:
    """Return the env-configured Telegram assistant when available."""
    return build_default_orchestrator(chat_client)


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
def telegram_webhook(
    update: TelegramUpdate,
    assistant: Annotated[
        TelegramAssistantOrchestrator | None,
        Depends(get_telegram_assistant),
    ],
    secret_token: Annotated[
        str | None,
        Header(alias="X-Telegram-Bot-Api-Secret-Token"),
    ] = None,
) -> None:
    """Record supported Telegram Bot API updates for later read endpoints."""
    raw_expected = getenv("TELEGRAM_WEBHOOK_SECRET")
    expected_secret = raw_expected.strip() if raw_expected else ""
    if expected_secret and not hmac.compare_digest(
        expected_secret, (secret_token or "").strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram webhook secret",
        )
    raw_update = update.model_dump()
    record_update(raw_update)
    if assistant is not None:
        assistant.handle_update(raw_update)
