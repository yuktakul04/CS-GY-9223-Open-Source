"""Private Telegram assistant/orchestration flow for chat_client_service."""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from api.issue import Status
from trello_client_impl import TrelloClient

import ai_client_api
from issue_tracker_integration.client import get_bridge
from issue_tracker_integration.trello_adapter import TrelloClientAdapter

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ai_client_api import AIClient, ToolCallResponse
    from chat_client_api import ChatClient
    from issue_tracker_integration.client import IssueTrackerBridge

_ISSUE_TRACKER_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_boards",
            "description": "List all available issue tracker boards.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_issues",
            "description": "List all issues on a board.",
            "parameters": {
                "type": "object",
                "properties": {
                    "board_id": {
                        "type": "string",
                        "description": "The board ID to fetch issues from.",
                    },
                },
                "required": ["board_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_issue",
            "description": "Create a new issue on a board.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Issue title."},
                    "board_id": {"type": "string", "description": "Target board ID."},
                    "desc": {"type": "string", "description": "Optional description."},
                    "status": {
                        "type": "string",
                        "enum": ["to_do", "in_progress", "completed"],
                        "description": "Initial status (default: to_do).",
                    },
                },
                "required": ["title", "board_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_issue",
            "description": "Update fields on an existing issue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "Issue ID to update.",
                    },
                    "title": {"type": "string", "description": "New title."},
                    "desc": {"type": "string", "description": "New description."},
                    "status": {
                        "type": "string",
                        "enum": ["to_do", "in_progress", "completed"],
                    },
                },
                "required": ["issue_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_issue",
            "description": "Delete an issue by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "Issue ID to delete.",
                    },
                },
                "required": ["issue_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_board",
            "description": "Create a new board.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Board name."},
                },
                "required": ["name"],
            },
        },
    },
]

_CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_messages",
            "description": "List messages from a chat channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string"},
                    "limit": {"type": "integer"},
                    "cursor": {"type": "string"},
                },
                "required": ["channel_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_message",
            "description": "Get one message by its opaque id.",
            "parameters": {
                "type": "object",
                "properties": {"message_id": {"type": "string"}},
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a message to the current Telegram chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_message",
            "description": "Delete a message by its opaque id.",
            "parameters": {
                "type": "object",
                "properties": {"message_id": {"type": "string"}},
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_channels",
            "description": "List Telegram chats available to the bot.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_channel",
            "description": "Get one Telegram chat by id.",
            "parameters": {
                "type": "object",
                "properties": {"channel_id": {"type": "string"}},
                "required": ["channel_id"],
            },
        },
    },
]

_TOOLS = _CHAT_TOOLS + _ISSUE_TRACKER_TOOLS

_SYSTEM_PROMPT = (
    "You are a Telegram assistant for chat and issue tracker workflows. "
    "Use the available tools to fulfil the user's request. "
    "If no tool applies, reply in plain text."
)

_STATUS_MAP = {
    "to_do": Status.TO_DO,
    "in_progress": Status.IN_PROGRESS,
    "completed": Status.COMPLETED,
}


@dataclass(frozen=True)
class _IncomingTelegramMessage:
    chat_id: str
    text: str
    is_bot: bool


class TelegramAssistantOrchestrator:
    """Process Telegram updates with AI + issue tracker + chat collaborators."""

    def __init__(
        self,
        ai_client: AIClient,
        bridge: IssueTrackerBridge | None,
        chat_client: ChatClient,
    ) -> None:
        """Store collaborators used to fulfill Telegram assistant messages."""
        self._ai = ai_client
        self._bridge = bridge
        self._chat = chat_client

    def handle_update(self, update: dict[str, object]) -> str | None:
        """Reply to a supported Telegram message update, if any."""
        message = _extract_message(update)
        if message is None or message.is_bot or not message.text.strip():
            return None
        return self.handle_message(chat_id=message.chat_id, user_message=message.text)

    def handle_message(self, *, chat_id: str, user_message: str) -> str:
        """Process one inbound Telegram message and post the reply."""
        response = self._ai.send_message(
            prompt=user_message,
            context={"system": _SYSTEM_PROMPT},
            tools=_TOOLS,
        )
        if isinstance(response, dict):
            reply = _dispatch(self._bridge, self._chat, response, chat_id)
        else:
            reply = response
        self._chat.send_message(channel_id=chat_id, text=reply)
        return reply


def build_default_orchestrator(
    chat_client: ChatClient,
) -> TelegramAssistantOrchestrator | None:
    """Build the service-owned assistant from env-backed collaborators."""
    try:
        ai_client = _build_ai_client()
    except RuntimeError:
        LOGGER.warning("AI client not configured — assistant disabled", exc_info=True)
        return None
    bridge = _build_issue_tracker_bridge()
    if bridge is None:
        LOGGER.info("Trello not configured — issue tracker tools disabled")
    LOGGER.info("Telegram assistant orchestrator started")
    return TelegramAssistantOrchestrator(ai_client, bridge, chat_client)


def _build_ai_client() -> AIClient:
    provider = os.getenv("CHAT_CLIENT_ASSISTANT_PROVIDER", "").strip().lower()
    module_name = _resolve_ai_provider_module(provider)
    importlib.import_module(module_name)
    return ai_client_api.get_client()


def _resolve_ai_provider_module(provider: str) -> str:
    if provider == "openai":
        return "openai_client_impl"
    if provider == "gemini":
        return "gemini_client_impl"
    if provider:
        msg = "CHAT_CLIENT_ASSISTANT_PROVIDER must be 'openai' or 'gemini'"
        raise RuntimeError(msg)
    if os.getenv("GEMINI_API_KEY", "").strip():
        return "gemini_client_impl"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai_client_impl"
    msg = (
        "Assistant AI client is not configured. Set CHAT_CLIENT_ASSISTANT_PROVIDER "
        "to 'openai' or 'gemini' and provide the matching API key."
    )
    raise RuntimeError(msg)


def _build_issue_tracker_bridge() -> IssueTrackerBridge | None:
    api_key = os.getenv("TRELLO_API_KEY", "").strip()
    token = os.getenv("TRELLO_TOKEN", "").strip()
    if not api_key or not token:
        return None

    board_id = os.getenv("TRELLO_BOARD_ID", "").strip() or None
    return get_bridge(
        TrelloClientAdapter(
            TrelloClient(api_key=api_key, token=token, board_id=board_id)
        )
    )


def _dispatch(
    bridge: IssueTrackerBridge | None,
    chat_client: ChatClient,
    tool_call: ToolCallResponse,
    chat_id: str,
) -> str:
    chat_reply = _dispatch_chat_tool(chat_client, tool_call, chat_id)
    if chat_reply is not None:
        return chat_reply
    return _dispatch_issue_tracker_tool(bridge, tool_call)


def _dispatch_chat_tool(  # noqa: PLR0911
    chat_client: ChatClient,
    tool_call: ToolCallResponse,
    chat_id: str,
) -> str | None:
    name = tool_call["name"]
    args = tool_call["arguments"]

    if name == "get_messages":
        request_kwargs: dict[str, str | int] = {
            "channel_id": args["channel_id"],
            "limit": int(args.get("limit", 10)),
        }
        if "cursor" in args:
            request_kwargs["cursor"] = str(args["cursor"])
        messages = chat_client.get_messages(**request_kwargs)
        if not messages:
            return f"No messages found on channel {args['channel_id']}."
        lines = [_format_message(message) for message in messages]
        return "Messages:\n" + "\n".join(lines)

    if name == "get_message":
        message = chat_client.get_message(args["message_id"])
        return "Message:\n" + _format_message(message)

    if name == "send_message":
        sent = chat_client.send_message(channel_id=chat_id, text=str(args["text"]))
        return f"Sent message {sent.message_id}."

    if name == "delete_message":
        chat_client.delete_message(args["message_id"])
        return f"Deleted message {args['message_id']}."

    if name == "get_channels":
        channels = list(chat_client.get_channels())
        if not channels:
            return "No channels found."
        lines = [_format_channel(channel) for channel in channels]
        return "Channels:\n" + "\n".join(lines)

    if name == "get_channel":
        channel = chat_client.get_channel(args["channel_id"])
        return "Channel:\n" + _format_channel(channel)

    return None


def _dispatch_issue_tracker_tool(  # noqa: PLR0911
    bridge: IssueTrackerBridge | None,
    tool_call: ToolCallResponse,
) -> str:
    name = tool_call["name"]
    args = tool_call["arguments"]

    if bridge is None:
        return "Issue tracker integration is not configured."

    if name == "get_boards":
        boards = list(bridge.get_boards())
        if not boards:
            return "No boards found."
        lines = [f"• {board.board_name} (id: {board.id})" for board in boards]
        return "Boards:\n" + "\n".join(lines)

    if name == "get_issues":
        issues = list(bridge.get_issues(args["board_id"]))
        if not issues:
            return f"No issues on board {args['board_id']}."
        lines = [
            f"• [{issue.status.value}] {issue.title} (id: {issue.id})"
            for issue in issues
        ]
        return "Issues:\n" + "\n".join(lines)

    if name == "create_issue":
        status = _STATUS_MAP.get(args.get("status", "to_do"), Status.TO_DO)
        issue = bridge.create_issue(
            title=args["title"],
            board_id=args["board_id"],
            desc=args.get("desc"),
            status=status,
        )
        return f"Created issue '{issue.title}' (id: {issue.id})."

    if name == "update_issue":
        status = _STATUS_MAP.get(args["status"]) if "status" in args else None
        issue = bridge.update_issue(
            args["issue_id"],
            title=args.get("title"),
            desc=args.get("desc"),
            status=status,
        )
        return f"Updated issue '{issue.title}' (id: {issue.id})."

    if name == "delete_issue":
        bridge.delete_issue(args["issue_id"])
        return f"Deleted issue {args['issue_id']}."

    if name == "create_board":
        board = bridge.create_board(args["name"])
        return f"Created board '{board.board_name}' (id: {board.id})."

    return f"Unknown tool: {name}"


def _extract_message(update: dict[str, object]) -> _IncomingTelegramMessage | None:
    raw_message = (
        update.get("message")
        or update.get("edited_message")
        or update.get("channel_post")
        or update.get("edited_channel_post")
    )
    if not isinstance(raw_message, dict):
        return None

    chat = raw_message.get("chat")
    sender = raw_message.get("from")
    if not isinstance(chat, dict):
        return None

    text = raw_message.get("text") or raw_message.get("caption")
    if not isinstance(text, str):
        return None

    is_bot = isinstance(sender, dict) and bool(sender.get("is_bot"))
    return _IncomingTelegramMessage(
        chat_id=str(chat.get("id", "")),
        text=text,
        is_bot=is_bot,
    )


def _format_channel(channel: object) -> str:
    return (
        f"• {getattr(channel, 'name', '')} "
        f"(id: {getattr(channel, 'channel_id', '')}, "
        f"type: {getattr(channel, 'channel_type', '')})"
    )


def _format_message(message: object) -> str:
    return (
        f"• [{getattr(message, 'timestamp', '')}] "
        f"{getattr(message, 'sender', '')}: {getattr(message, 'text', '')} "
        f"(id: {getattr(message, 'message_id', '')})"
    )
