"""Unit tests for IssueTrackerOrchestrator."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, create_autospec

from api.issue import Status

from ai_client_api import AIClient
from issue_tracker_integration.client import IssueTrackerBridge
from issue_tracker_integration.orchestrator import IssueTrackerOrchestrator


def _mock_ai() -> MagicMock:
    return cast("MagicMock", create_autospec(AIClient, instance=True))


def _mock_bridge() -> MagicMock:
    return cast("MagicMock", create_autospec(IssueTrackerBridge, instance=True))


def _mock_chat() -> MagicMock:
    return MagicMock()


def _tool_call(tool_name: str, **kwargs: object) -> dict[str, Any]:
    return {"name": tool_name, "arguments": kwargs}


def _orch(
    ai: MagicMock,
    bridge: MagicMock,
    chat: MagicMock | None = None,
) -> IssueTrackerOrchestrator:
    return IssueTrackerOrchestrator(ai, bridge, chat or _mock_chat())


def _fake_issue(
    *,
    issue_id: str = "i-1",
    title: str = "Bug",
    status: Status = Status.TO_DO,
) -> MagicMock:
    m = MagicMock()
    m.id = issue_id
    m.title = title
    m.status = status
    return m


def _fake_board(*, board_id: str = "b-1", board_name: str = "Sprint") -> MagicMock:
    m = MagicMock()
    m.id = board_id
    m.board_name = board_name
    return m


# ---------------------------------------------------------------------------
# Plain-text response (no tool call)
# ---------------------------------------------------------------------------


def test_handle_plain_text_posts_to_telegram() -> None:
    ai, bridge, chat = _mock_ai(), _mock_bridge(), _mock_chat()
    ai.send_message.return_value = "Hello!"

    reply = _orch(ai, bridge, chat).handle("chat-1", "hi")

    assert reply == "Hello!"
    chat.send_message.assert_called_once_with("chat-1", "Hello!")


# ---------------------------------------------------------------------------
# Tool call — get_boards
# ---------------------------------------------------------------------------


def test_handle_get_boards_empty() -> None:
    ai, bridge = _mock_ai(), _mock_bridge()
    ai.send_message.return_value = _tool_call("get_boards")
    bridge.get_boards.return_value = iter([])

    assert _orch(ai, bridge).handle("c", "list boards") == "No boards found."


def test_handle_get_boards_lists_boards() -> None:
    ai, bridge = _mock_ai(), _mock_bridge()
    ai.send_message.return_value = _tool_call("get_boards")
    bridge.get_boards.return_value = iter([_fake_board()])

    reply = _orch(ai, bridge).handle("c", "list boards")

    assert "Sprint" in reply
    assert "b-1" in reply


# ---------------------------------------------------------------------------
# Tool call — get_issues
# ---------------------------------------------------------------------------


def test_handle_get_issues_empty() -> None:
    ai, bridge = _mock_ai(), _mock_bridge()
    ai.send_message.return_value = _tool_call("get_issues", board_id="b-1")
    bridge.get_issues.return_value = iter([])

    assert "No issues" in _orch(ai, bridge).handle("c", "show issues")


def test_handle_get_issues_lists_issues() -> None:
    ai, bridge = _mock_ai(), _mock_bridge()
    ai.send_message.return_value = _tool_call("get_issues", board_id="b-1")
    bridge.get_issues.return_value = iter([_fake_issue(title="Bug fix")])

    assert "Bug fix" in _orch(ai, bridge).handle("c", "show issues")


# ---------------------------------------------------------------------------
# Tool call — create_issue
# ---------------------------------------------------------------------------


def test_handle_create_issue_minimal() -> None:
    ai, bridge = _mock_ai(), _mock_bridge()
    ai.send_message.return_value = _tool_call(
        "create_issue", title="New bug", board_id="b-1"
    )
    bridge.create_issue.return_value = _fake_issue(title="New bug")

    reply = _orch(ai, bridge).handle("c", "create issue")

    bridge.create_issue.assert_called_once_with(
        title="New bug", board_id="b-1", desc=None, status=Status.TO_DO
    )
    assert "New bug" in reply


def test_handle_create_issue_with_status() -> None:
    ai, bridge = _mock_ai(), _mock_bridge()
    ai.send_message.return_value = _tool_call(
        "create_issue", title="Task", board_id="b-1", status="in_progress"
    )
    bridge.create_issue.return_value = _fake_issue(status=Status.IN_PROGRESS)

    _orch(ai, bridge).handle("c", "create task")

    bridge.create_issue.assert_called_once_with(
        title="Task", board_id="b-1", desc=None, status=Status.IN_PROGRESS
    )


# ---------------------------------------------------------------------------
# Tool call — update_issue
# ---------------------------------------------------------------------------


def test_handle_update_issue() -> None:
    ai, bridge = _mock_ai(), _mock_bridge()
    ai.send_message.return_value = _tool_call(
        "update_issue", issue_id="i-1", status="completed"
    )
    bridge.update_issue.return_value = _fake_issue(status=Status.COMPLETED)

    reply = _orch(ai, bridge).handle("c", "close issue")

    bridge.update_issue.assert_called_once_with(
        "i-1", title=None, desc=None, status=Status.COMPLETED
    )
    assert "Updated" in reply


# ---------------------------------------------------------------------------
# Tool call — delete_issue
# ---------------------------------------------------------------------------


def test_handle_delete_issue() -> None:
    ai, bridge = _mock_ai(), _mock_bridge()
    ai.send_message.return_value = _tool_call("delete_issue", issue_id="i-1")

    reply = _orch(ai, bridge).handle("c", "delete issue")

    bridge.delete_issue.assert_called_once_with("i-1")
    assert "i-1" in reply


# ---------------------------------------------------------------------------
# Tool call — create_board
# ---------------------------------------------------------------------------


def test_handle_create_board() -> None:
    ai, bridge = _mock_ai(), _mock_bridge()
    ai.send_message.return_value = _tool_call("create_board", name="Q3")
    bridge.create_board.return_value = _fake_board(board_name="Q3")

    reply = _orch(ai, bridge).handle("c", "create board")

    bridge.create_board.assert_called_once_with("Q3")
    assert "Q3" in reply


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


def test_handle_unknown_tool() -> None:
    ai, bridge = _mock_ai(), _mock_bridge()
    ai.send_message.return_value = _tool_call("fly_to_moon")

    assert "Unknown tool" in _orch(ai, bridge).handle("c", "???")
