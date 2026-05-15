"""Typed Pydantic models and auto-generated tool definitions for the assistant."""

from __future__ import annotations

from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from ai_client_api.tool_schema import make_tool

_M = TypeVar("_M", bound=BaseModel)

IssueStatus = Literal["to_do", "in_progress", "completed"]


class ToolCallValidationError(ValueError):
    """Raised when tool-call arguments fail Pydantic validation."""

    tool_name: str
    cause: ValidationError

    def __init__(self, tool_name: str, cause: ValidationError) -> None:
        """Wrap a Pydantic ``ValidationError`` with the offending tool name."""
        super().__init__(f"Invalid arguments for tool '{tool_name}': {cause}")
        self.tool_name = tool_name
        self.cause = cause


def validate_tool_args(  # noqa: UP047
    tool_name: str,
    model: type[_M],
    args: dict[str, Any],
) -> _M:
    """Validate ``args`` against ``model``, raising ``ToolCallValidationError``."""
    try:
        return model.model_validate(args)
    except ValidationError as exc:
        raise ToolCallValidationError(tool_name, exc) from exc


# ── Chat tool models ────────────────────────────────────────────────────────


class GetMessagesArgs(BaseModel):
    """Arguments for the get_messages tool."""

    channel_id: str
    limit: int = 10
    cursor: str | None = None


class GetMessageArgs(BaseModel):
    """Arguments for the get_message tool."""

    message_id: str


class SendMessageArgs(BaseModel):
    """Arguments for the send_message tool."""

    text: str
    channel_id: str | None = None


class DeleteMessageArgs(BaseModel):
    """Arguments for the delete_message tool."""

    message_id: str


class GetChannelsArgs(BaseModel):
    """Arguments for the get_channels tool (no parameters required)."""


class GetChannelArgs(BaseModel):
    """Arguments for the get_channel tool."""

    channel_id: str


# ── Issue tracker tool models ───────────────────────────────────────────────


class GetBoardsArgs(BaseModel):
    """Arguments for the get_boards tool (no parameters required)."""


class GetIssuesArgs(BaseModel):
    """Arguments for the get_issues tool."""

    board_id: str


class CreateIssueArgs(BaseModel):
    """Arguments for the create_issue tool."""

    title: str
    board_id: str
    desc: str | None = None
    status: IssueStatus = "to_do"


class UpdateIssueArgs(BaseModel):
    """Arguments for the update_issue tool."""

    issue_id: str
    title: str | None = None
    desc: str | None = None
    status: IssueStatus | None = None


class DeleteIssueArgs(BaseModel):
    """Arguments for the delete_issue tool."""

    issue_id: str


class CreateBoardArgs(BaseModel):
    """Arguments for the create_board tool."""

    name: str


# ── Auto-generated tool definitions ────────────────────────────────────────

CHAT_TOOLS: list[dict[str, Any]] = [
    make_tool("get_messages", "List messages from a chat channel.", GetMessagesArgs),
    make_tool("get_message", "Get one message by its opaque id.", GetMessageArgs),
    make_tool(
        "send_message",
        "Send a message to the current Telegram chat.",
        SendMessageArgs,
    ),
    make_tool(
        "delete_message",
        "Delete a message by its opaque id.",
        DeleteMessageArgs,
    ),
    make_tool(
        "get_channels",
        "List Telegram chats available to the bot.",
        GetChannelsArgs,
    ),
    make_tool("get_channel", "Get one Telegram chat by id.", GetChannelArgs),
]

ISSUE_TRACKER_TOOLS: list[dict[str, Any]] = [
    make_tool("get_boards", "List all available issue tracker boards.", GetBoardsArgs),
    make_tool("get_issues", "List all issues on a board.", GetIssuesArgs),
    make_tool("create_issue", "Create a new issue on a board.", CreateIssueArgs),
    make_tool("update_issue", "Update fields on an existing issue.", UpdateIssueArgs),
    make_tool("delete_issue", "Delete an issue by ID.", DeleteIssueArgs),
    make_tool("create_board", "Create a new board.", CreateBoardArgs),
]

TOOLS: list[dict[str, Any]] = CHAT_TOOLS + ISSUE_TRACKER_TOOLS
