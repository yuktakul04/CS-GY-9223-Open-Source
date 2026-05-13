"""Integration test for AI tool-call → cross-vertical pipeline.

Exercises ``IssueTrackerOrchestrator`` and ``TelegramAssistantOrchestrator``
with real ABC subclasses for every collaborator — no Mocks. The point is to
prove the wiring actually creates issues end-to-end, not just that mocked
methods were called.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from ai_client_api import AIClient, ToolCallResponse
from api.board import Board
from api.client import Client
from api.exceptions import BoardNotFoundError, IssueNotFoundError
from api.issue import Issue, Status
from chat_client_api import ChatClient, Channel, Message
from chat_client_service.assistant import TelegramAssistantOrchestrator
from issue_tracker_integration.client import get_bridge
from issue_tracker_integration.orchestrator import IssueTrackerOrchestrator


# ---------------------------------------------------------------------------
# Real ABC subclasses (no Mocks)
# ---------------------------------------------------------------------------


class FakeAIClient(AIClient):
    """AIClient that emits a pre-programmed ToolCallResponse."""

    def __init__(self, response: str | ToolCallResponse) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str | ToolCallResponse:
        self.calls.append({"prompt": prompt, "context": context, "tools": tools})
        return self._response


@dataclass
class _Board(Board):
    _id: str
    _name: str

    @property
    def id(self) -> str:  # noqa: A003
        return self._id

    @property
    def board_name(self) -> str:
        return self._name


@dataclass
class _Issue(Issue):
    _id: str
    _title: str
    _board_id: str
    _desc: str = ""
    _status: Status = Status.TO_DO
    _members: list[str] | None = None
    _due_date: str | None = None

    @property
    def id(self) -> str:  # noqa: A003
        return self._id

    @property
    def title(self) -> str:
        return self._title

    @property
    def desc(self) -> str:
        return self._desc

    @property
    def members(self) -> list[str] | None:
        return self._members

    @property
    def due_date(self) -> str | None:
        return self._due_date

    @property
    def status(self) -> Status:
        return self._status

    @property
    def board_id(self) -> str:
        return self._board_id


class InMemoryIssueClient(Client):
    """In-memory ``api.client.Client`` backed by plain dicts."""

    def __init__(self) -> None:
        self.boards: dict[str, _Board] = {}
        self.issues: dict[str, _Issue] = {}
        self._next_issue = 1
        self._next_board = 1

    # boards -----------------------------------------------------------------

    def get_boards(self) -> Iterator[Board]:
        return iter(list(self.boards.values()))

    def get_board(self, board_id: str) -> Board:
        if board_id not in self.boards:
            raise BoardNotFoundError(f"board {board_id} not found")
        return self.boards[board_id]

    def create_board(self, name: str) -> Board:
        board_id = f"b-{self._next_board}"
        self._next_board += 1
        board = _Board(_id=board_id, _name=name)
        self.boards[board_id] = board
        return board

    def update_board(self, board_id: str, name: str | None = None) -> Board:
        board = self.boards.get(board_id)
        if board is None:
            raise BoardNotFoundError(f"board {board_id} not found")
        if name is not None:
            board._name = name  # noqa: SLF001
        return board

    def delete_board(self, board_id: str) -> bool:
        if board_id not in self.boards:
            raise BoardNotFoundError(f"board {board_id} not found")
        del self.boards[board_id]
        return True

    # issues -----------------------------------------------------------------

    def get_issues(self, board_id: str) -> Iterator[Issue]:
        if board_id not in self.boards:
            raise BoardNotFoundError(f"board {board_id} not found")
        return iter([i for i in self.issues.values() if i.board_id == board_id])

    def get_issue(self, issue_id: str) -> Issue:
        if issue_id not in self.issues:
            raise IssueNotFoundError(f"issue {issue_id} not found")
        return self.issues[issue_id]

    def create_issue(  # noqa: PLR0913
        self,
        title: str,
        board_id: str,
        desc: str | None = None,
        members: list[str] | None = None,
        due_date: str | None = None,
        status: Status = Status.TO_DO,
    ) -> Issue:
        if board_id not in self.boards:
            raise BoardNotFoundError(f"board {board_id} not found")
        issue_id = f"i-{self._next_issue}"
        self._next_issue += 1
        issue = _Issue(
            _id=issue_id,
            _title=title,
            _board_id=board_id,
            _desc=desc or "",
            _members=members,
            _due_date=due_date,
            _status=status,
        )
        self.issues[issue_id] = issue
        return issue

    def update_issue(  # noqa: PLR0913
        self,
        issue_id: str,
        title: str | None = None,
        desc: str | None = None,
        members: list[str] | None = None,
        due_date: str | None = None,
        status: Status | None = None,
        board_id: str | None = None,
    ) -> Issue:
        issue = self.issues.get(issue_id)
        if issue is None:
            raise IssueNotFoundError(f"issue {issue_id} not found")
        if title is not None:
            issue._title = title  # noqa: SLF001
        if desc is not None:
            issue._desc = desc  # noqa: SLF001
        if members is not None:
            issue._members = members  # noqa: SLF001
        if due_date is not None:
            issue._due_date = due_date  # noqa: SLF001
        if status is not None:
            issue._status = status  # noqa: SLF001
        if board_id is not None:
            if board_id not in self.boards:
                raise BoardNotFoundError(f"board {board_id} not found")
            issue._board_id = board_id  # noqa: SLF001
        return issue

    def delete_issue(self, issue_id: str) -> bool:
        if issue_id not in self.issues:
            raise IssueNotFoundError(f"issue {issue_id} not found")
        del self.issues[issue_id]
        return True


class RecordingChatClient(ChatClient):
    """ChatClient that records every send_message in a list."""

    def __init__(self) -> None:
        self.sent: list[Message] = []
        self._next = 1

    def send_message(self, channel_id: str, text: str) -> Message:
        message = Message(
            message_id=f"m-{self._next}",
            channel=channel_id,
            text=text,
            sender="bot",
            timestamp="2026-05-13T00:00:00Z",
        )
        self._next += 1
        self.sent.append(message)
        return message

    def get_channels(self) -> list[Channel]:
        return [Channel(channel_id="chat-1", name="Test", channel_type="private")]

    def get_channel(self, channel_id: str) -> Channel:
        for c in self.get_channels():
            if c.channel_id == channel_id:
                return c
        msg = f"Channel not found: {channel_id}"
        raise ValueError(msg)

    def get_messages(
        self,
        channel_id: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        del limit, cursor
        return [m for m in self.sent if m.channel == channel_id]

    def get_message(self, message_id: str) -> Message:
        for m in self.sent:
            if m.message_id == message_id:
                return m
        msg = f"Message not found: {message_id}"
        raise ValueError(msg)

    def delete_message(self, message_id: str) -> None:
        for i, m in enumerate(self.sent):
            if m.message_id == message_id:
                del self.sent[i]
                return
        msg = f"Message not found: {message_id}"
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_issue_tracker_orchestrator_creates_issue_end_to_end() -> None:
    """AI tool-call drives a real bridge against a real in-memory store."""
    issue_client = InMemoryIssueClient()
    issue_client.create_board("Engineering")  # seed b-1

    ai = FakeAIClient(
        ToolCallResponse(
            name="create_issue",
            arguments={"title": "Test Bug", "board_id": "b-1"},
        )
    )
    chat = RecordingChatClient()
    bridge = get_bridge(issue_client)

    orchestrator = IssueTrackerOrchestrator(ai, bridge, chat)
    reply = orchestrator.handle("chat-1", "create a bug ticket")

    # 1. Issue actually landed in the store.
    assert len(issue_client.issues) == 1
    created = next(iter(issue_client.issues.values()))
    assert created.title == "Test Bug"
    assert created.board_id == "b-1"
    assert created.status is Status.TO_DO

    # 2. Chat client received exactly one reply on the right channel.
    assert len(chat.sent) == 1
    assert chat.sent[0].channel == "chat-1"

    # 3. Reply text references the created issue.
    assert "Test Bug" in reply
    assert created.id in reply
    assert reply == chat.sent[0].text


def test_telegram_assistant_orchestrator_routes_create_issue_tool() -> None:
    """Combined chat+issue-tracker dispatcher routes ``create_issue`` correctly."""
    issue_client = InMemoryIssueClient()
    issue_client.create_board("Engineering")  # seed b-1

    ai = FakeAIClient(
        ToolCallResponse(
            name="create_issue",
            arguments={
                "title": "Telegram-side Bug",
                "board_id": "b-1",
                "status": "in_progress",
            },
        )
    )
    chat = RecordingChatClient()
    bridge = get_bridge(issue_client)

    orchestrator = TelegramAssistantOrchestrator(ai, bridge, chat)
    reply = orchestrator.handle_message(
        chat_id="chat-1",
        user_message="open a bug ticket on b-1",
    )

    # Issue persisted with the requested status.
    assert len(issue_client.issues) == 1
    created = next(iter(issue_client.issues.values()))
    assert created.title == "Telegram-side Bug"
    assert created.status is Status.IN_PROGRESS

    # AI was given combined chat + issue tracker tool schemas.
    tool_names = {t["function"]["name"] for t in ai.calls[0]["tools"]}
    assert {"create_issue", "send_message", "get_channels"} <= tool_names

    # Chat client received the reply on chat-1, and it names the new issue.
    assert len(chat.sent) == 1
    assert chat.sent[0].channel == "chat-1"
    assert "Telegram-side Bug" in reply
    assert created.id in reply
