"""End-to-end orchestrator: user prompt → AI → IssueTrackerBridge → Telegram reply."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from api.issue import Status

if TYPE_CHECKING:
    from ai_client_api import AIClient, ToolCallResponse
    from chat_client_api import ChatClient
    from issue_tracker_integration.client import IssueTrackerBridge

# ---------------------------------------------------------------------------
# Tool schema definitions exposed to the LLM
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, Any]] = [
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

# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

_STATUS_MAP = {
    "to_do": Status.TO_DO,
    "in_progress": Status.IN_PROGRESS,
    "completed": Status.COMPLETED,
}


def _dispatch(bridge: IssueTrackerBridge, tool_call: ToolCallResponse) -> str:  # noqa: PLR0911
    """Execute the tool call against the bridge and return a human-readable result."""
    name = tool_call["name"]
    args = tool_call["arguments"]

    if name == "get_boards":
        boards = list(bridge.get_boards())
        if not boards:
            return "No boards found."
        lines = [f"• {b.board_name} (id: {b.id})" for b in boards]
        return "Boards:\n" + "\n".join(lines)

    if name == "get_issues":
        issues = list(bridge.get_issues(args["board_id"]))
        if not issues:
            return f"No issues on board {args['board_id']}."
        lines = [f"• [{i.status.value}] {i.title} (id: {i.id})" for i in issues]
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


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an issue tracker assistant. "
    "Use the available tools to fulfil the user's request. "
    "If no tool applies, reply in plain text."
)


class IssueTrackerOrchestrator:
    """Wires AIClient + IssueTrackerBridge + ChatClient into a single handler.

    Call ``handle(chat_id, user_message)`` to process a prompt and post the
    result back to the originating chat via the Telegram client.
    """

    def __init__(
        self,
        ai_client: AIClient,
        bridge: IssueTrackerBridge,
        chat_client: ChatClient,
    ) -> None:
        """Store collaborators."""
        self._ai = ai_client
        self._bridge = bridge
        self._chat = chat_client

    def handle(self, chat_id: str, user_message: str) -> str:
        """Process ``user_message``, act on the bridge, post reply to ``chat_id``.

        Returns the reply text that was posted.
        """
        response = self._ai.send_message(
            prompt=user_message,
            context={"system": _SYSTEM_PROMPT},
            tools=_TOOLS,
        )

        if isinstance(response, dict):
            reply = _dispatch(self._bridge, response)
        else:
            reply = response

        self._chat.send_message(chat_id, reply)
        return reply
