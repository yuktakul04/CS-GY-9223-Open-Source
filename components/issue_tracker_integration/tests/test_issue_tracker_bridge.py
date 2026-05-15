"""Unit tests for IssueTrackerBridge — all API calls are mocked."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, create_autospec

import pytest
from api.board import Board
from api.client import Client
from api.exceptions import BoardNotFoundError, IssueNotFoundError, IssueTrackerError
from api.issue import Issue, Status

from issue_tracker_integration.client import IssueTrackerBridge, get_bridge

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_client() -> MagicMock:
    return cast("MagicMock", create_autospec(Client, instance=True))


def _mock_issue(
    issue_id: str = "issue-1",
    title: str = "Test issue",
    status: Status = Status.TO_DO,
    board_id: str = "board-1",
) -> MagicMock:
    issue = cast("MagicMock", create_autospec(Issue, instance=True))
    issue.id = issue_id
    issue.title = title
    issue.status = status
    issue.board_id = board_id
    issue.desc = ""
    issue.members = None
    issue.due_date = None
    return issue


def _mock_board(board_id: str = "board-1", board_name: str = "Sprint 1") -> MagicMock:
    board = cast("MagicMock", create_autospec(Board, instance=True))
    board.id = board_id
    board.board_name = board_name
    return board


# ---------------------------------------------------------------------------
# get_boards / get_board
# ---------------------------------------------------------------------------


def test_get_boards_delegates_to_client() -> None:
    client = _mock_client()
    board = _mock_board()
    client.get_boards.return_value = iter([board])

    bridge = IssueTrackerBridge(client)
    boards = list(bridge.get_boards())

    client.get_boards.assert_called_once()
    assert boards == [board]


def test_get_board_returns_board() -> None:
    client = _mock_client()
    board = _mock_board()
    client.get_board.return_value = board

    bridge = IssueTrackerBridge(client)
    result = bridge.get_board("board-1")

    client.get_board.assert_called_once_with("board-1")
    assert result is board


def test_get_board_propagates_not_found() -> None:
    client = _mock_client()
    client.get_board.side_effect = BoardNotFoundError("not found")

    bridge = IssueTrackerBridge(client)
    with pytest.raises(BoardNotFoundError):
        bridge.get_board("missing")


# ---------------------------------------------------------------------------
# create_board / update_board / delete_board
# ---------------------------------------------------------------------------


def test_create_board_returns_new_board() -> None:
    client = _mock_client()
    board = _mock_board(board_name="New Board")
    client.create_board.return_value = board

    bridge = IssueTrackerBridge(client)
    result = bridge.create_board("New Board")

    client.create_board.assert_called_once_with("New Board")
    assert result is board


def test_update_board_passes_name() -> None:
    client = _mock_client()
    board = _mock_board(board_name="Renamed")
    client.update_board.return_value = board

    bridge = IssueTrackerBridge(client)
    result = bridge.update_board("board-1", name="Renamed")

    client.update_board.assert_called_once_with("board-1", name="Renamed")
    assert result is board


def test_delete_board_returns_true() -> None:
    client = _mock_client()
    client.delete_board.return_value = True

    bridge = IssueTrackerBridge(client)
    assert bridge.delete_board("board-1") is True
    client.delete_board.assert_called_once_with("board-1")


# ---------------------------------------------------------------------------
# get_issues / get_issue
# ---------------------------------------------------------------------------


def test_get_issues_returns_iterator() -> None:
    client = _mock_client()
    issue = _mock_issue()
    client.get_issues.return_value = iter([issue])

    bridge = IssueTrackerBridge(client)
    issues = list(bridge.get_issues("board-1"))

    client.get_issues.assert_called_once_with("board-1")
    assert issues == [issue]


def test_get_issue_returns_issue() -> None:
    client = _mock_client()
    issue = _mock_issue()
    client.get_issue.return_value = issue

    bridge = IssueTrackerBridge(client)
    result = bridge.get_issue("issue-1")

    client.get_issue.assert_called_once_with("issue-1")
    assert result is issue


def test_get_issue_propagates_not_found() -> None:
    client = _mock_client()
    client.get_issue.side_effect = IssueNotFoundError("not found")

    bridge = IssueTrackerBridge(client)
    with pytest.raises(IssueNotFoundError):
        bridge.get_issue("missing")


# ---------------------------------------------------------------------------
# create_issue
# ---------------------------------------------------------------------------


def test_create_issue_minimal() -> None:
    client = _mock_client()
    issue = _mock_issue()
    client.create_issue.return_value = issue

    bridge = IssueTrackerBridge(client)
    result = bridge.create_issue("Test issue", "board-1")

    client.create_issue.assert_called_once_with(
        "Test issue",
        "board-1",
        desc=None,
        members=None,
        due_date=None,
        status=Status.TO_DO,
    )
    assert result is issue


def test_create_issue_full_args() -> None:
    client = _mock_client()
    issue = _mock_issue(status=Status.IN_PROGRESS)
    client.create_issue.return_value = issue

    bridge = IssueTrackerBridge(client)
    result = bridge.create_issue(
        "Full issue",
        "board-1",
        desc="Some desc",
        members=["alice@example.com"],
        due_date="2026-05-01",
        status=Status.IN_PROGRESS,
    )

    client.create_issue.assert_called_once_with(
        "Full issue",
        "board-1",
        desc="Some desc",
        members=["alice@example.com"],
        due_date="2026-05-01",
        status=Status.IN_PROGRESS,
    )
    assert result is issue


# ---------------------------------------------------------------------------
# update_issue / delete_issue
# ---------------------------------------------------------------------------


def test_update_issue_passes_kwargs() -> None:
    client = _mock_client()
    updated = _mock_issue(title="Updated", status=Status.COMPLETED)
    client.update_issue.return_value = updated

    bridge = IssueTrackerBridge(client)
    result = bridge.update_issue("issue-1", title="Updated", status=Status.COMPLETED)

    client.update_issue.assert_called_once_with(
        "issue-1",
        title="Updated",
        desc=None,
        members=None,
        due_date=None,
        status=Status.COMPLETED,
        board_id=None,
    )
    assert result is updated


def test_delete_issue_returns_true() -> None:
    client = _mock_client()
    client.delete_issue.return_value = True

    bridge = IssueTrackerBridge(client)
    assert bridge.delete_issue("issue-1") is True
    client.delete_issue.assert_called_once_with("issue-1")


# ---------------------------------------------------------------------------
# get_bridge factory
# ---------------------------------------------------------------------------


def test_get_bridge_returns_bridge() -> None:
    client = _mock_client()
    bridge = get_bridge(client)
    assert isinstance(bridge, IssueTrackerBridge)


def test_get_bridge_rejects_non_client() -> None:
    with pytest.raises(IssueTrackerError):
        get_bridge("not-a-client")
