"""Unit tests for TrelloClientAdapter — all Trello API calls are mocked."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, create_autospec, patch

import pytest
import requests
from api.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BoardNotFoundError,
    IssueNotFoundError,
    RequestError,
)
from api.issue import Status

from issue_tracker_integration.trello_adapter import (
    TrelloClientAdapter,
    _BoardAdapter,
    _IssueAdapter,
    _map_http_error,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _http_error(status: int) -> requests.HTTPError:
    resp = MagicMock()
    resp.status_code = status
    return requests.HTTPError(response=resp)


def _fake_t7_issue(
    *,
    issue_id: str = "card-1",
    title: str = "Fix bug",
    is_complete: bool = False,
    board_id: str | None = "board-1",
    list_id: str = "list-1",
) -> MagicMock:
    issue = MagicMock()
    issue.id = issue_id
    issue.title = title
    issue.is_complete = is_complete
    issue.board_id = board_id
    issue.list_id = list_id
    return issue


def _fake_t7_board(*, board_id: str = "board-1", name: str = "Sprint") -> MagicMock:
    board = MagicMock()
    board.id = board_id
    board.name = name
    return board


def _fake_t7_list(*, list_id: str = "list-1", name: str = "To Do") -> MagicMock:
    lst = MagicMock()
    lst.id = list_id
    lst.name = name
    return lst


def _mock_trello() -> MagicMock:
    from trello_client_impl import TrelloClient

    return cast("MagicMock", create_autospec(TrelloClient, instance=True))


# ---------------------------------------------------------------------------
# _map_http_error
# ---------------------------------------------------------------------------


def test_map_404_issue() -> None:
    err = _map_http_error(_http_error(404), resource="issue")
    assert isinstance(err, IssueNotFoundError)


def test_map_404_board() -> None:
    err = _map_http_error(_http_error(404), resource="board")
    assert isinstance(err, BoardNotFoundError)


def test_map_401() -> None:
    assert isinstance(_map_http_error(_http_error(401)), AuthenticationError)


def test_map_403() -> None:
    assert isinstance(_map_http_error(_http_error(403)), AuthorizationError)


def test_map_500() -> None:
    assert isinstance(_map_http_error(_http_error(500)), RequestError)


# ---------------------------------------------------------------------------
# _IssueAdapter
# ---------------------------------------------------------------------------


def test_issue_adapter_properties() -> None:
    wrapped = _fake_t7_issue(is_complete=False)
    adapter = _IssueAdapter(wrapped)
    assert adapter.id == "card-1"
    assert adapter.title == "Fix bug"
    assert adapter.desc == ""
    assert adapter.members is None
    assert adapter.due_date is None
    assert adapter.status == Status.TO_DO
    assert adapter.board_id == "board-1"


def test_issue_adapter_completed_status() -> None:
    adapter = _IssueAdapter(_fake_t7_issue(is_complete=True))
    assert adapter.status == Status.COMPLETED


def test_issue_adapter_board_id_none() -> None:
    adapter = _IssueAdapter(_fake_t7_issue(board_id=None))
    assert adapter.board_id == ""


# ---------------------------------------------------------------------------
# _BoardAdapter
# ---------------------------------------------------------------------------


def test_board_adapter_properties() -> None:
    adapter = _BoardAdapter(_fake_t7_board(board_id="b-1", name="My Board"))
    assert adapter.id == "b-1"
    assert adapter.board_name == "My Board"


# ---------------------------------------------------------------------------
# TrelloClientAdapter — issues
# ---------------------------------------------------------------------------


def test_get_issue_returns_adapter() -> None:
    trello = _mock_trello()
    trello.get_issue.return_value = _fake_t7_issue()
    result = TrelloClientAdapter(trello).get_issue("card-1")
    assert isinstance(result, _IssueAdapter)
    trello.get_issue.assert_called_once_with("card-1")


def test_get_issue_maps_404() -> None:
    trello = _mock_trello()
    trello.get_issue.side_effect = _http_error(404)
    with pytest.raises(IssueNotFoundError):
        TrelloClientAdapter(trello).get_issue("missing")


def test_get_issues_iterates_lists() -> None:
    trello = _mock_trello()
    lst = _fake_t7_list()
    issue = _fake_t7_issue()
    trello.get_lists.return_value = iter([lst])
    trello.get_issues_in_list.return_value = iter([issue])

    results = list(TrelloClientAdapter(trello).get_issues("board-1"))

    assert len(results) == 1
    trello.get_lists.assert_called_once_with("board-1")
    trello.get_issues_in_list.assert_called_once_with("list-1")


def test_create_issue_uses_first_list() -> None:
    trello = _mock_trello()
    lst = _fake_t7_list()
    issue = _fake_t7_issue()
    trello.get_lists.return_value = iter([lst])
    trello.create_issue.return_value = issue

    result = TrelloClientAdapter(trello).create_issue(
        "New task", "board-1", desc="details"
    )

    trello.create_issue.assert_called_once_with(
        "New task", "list-1", description="details"
    )
    assert isinstance(result, _IssueAdapter)


def test_create_issue_creates_list_when_none_exist() -> None:
    trello = _mock_trello()
    new_list = _fake_t7_list(list_id="list-new")
    issue = _fake_t7_issue()
    trello.get_lists.return_value = iter([])
    trello.create_list.return_value = new_list
    trello.create_issue.return_value = issue

    TrelloClientAdapter(trello).create_issue("Task", "board-1")

    trello.create_list.assert_called_once_with("board-1", "To Do")
    trello.create_issue.assert_called_once_with("Task", "list-new", description=None)


def test_update_issue_title_and_status() -> None:
    trello = _mock_trello()
    trello.get_issue.return_value = _fake_t7_issue(title="Updated")

    with patch(
        "issue_tracker_integration.trello_adapter.TrelloClientAdapter._put"
    ) as mock_put:
        TrelloClientAdapter(trello).update_issue(
            "card-1", title="Updated", status=Status.COMPLETED
        )
        mock_put.assert_called_once_with("/cards/card-1", {"name": "Updated"})

    trello.update_status.assert_called_once_with("card-1", "completed")


def test_delete_issue_delegates() -> None:
    trello = _mock_trello()
    trello.delete_issue.return_value = True
    assert TrelloClientAdapter(trello).delete_issue("card-1") is True


# ---------------------------------------------------------------------------
# TrelloClientAdapter — boards
# ---------------------------------------------------------------------------


def test_get_board_returns_adapter() -> None:
    trello = _mock_trello()
    trello.get_board.return_value = _fake_t7_board()
    result = TrelloClientAdapter(trello).get_board("board-1")
    assert isinstance(result, _BoardAdapter)


def test_get_board_maps_404() -> None:
    trello = _mock_trello()
    trello.get_board.side_effect = _http_error(404)
    with pytest.raises(BoardNotFoundError):
        TrelloClientAdapter(trello).get_board("missing")


def test_get_boards_wraps_all() -> None:
    trello = _mock_trello()
    boards = [_fake_t7_board(), _fake_t7_board(board_id="b2")]
    trello.get_boards.return_value = iter(boards)
    results = list(TrelloClientAdapter(trello).get_boards())
    assert len(results) == 2
    assert all(isinstance(b, _BoardAdapter) for b in results)


def test_create_board_returns_adapter() -> None:
    trello = _mock_trello()
    trello.create_board.return_value = _fake_t7_board(name="New")
    result = TrelloClientAdapter(trello).create_board("New")
    assert isinstance(result, _BoardAdapter)
    trello.create_board.assert_called_once_with("New")


def test_update_board_calls_put() -> None:
    trello = _mock_trello()
    trello.get_board.return_value = _fake_t7_board(name="Renamed")

    with patch(
        "issue_tracker_integration.trello_adapter.TrelloClientAdapter._put"
    ) as mock_put:
        result = TrelloClientAdapter(trello).update_board("board-1", name="Renamed")
        mock_put.assert_called_once_with("/boards/board-1", {"name": "Renamed"})

    assert isinstance(result, _BoardAdapter)


def test_delete_board_calls_delete() -> None:
    with patch(
        "issue_tracker_integration.trello_adapter.TrelloClientAdapter._delete"
    ) as mock_del:
        result = TrelloClientAdapter(_mock_trello()).delete_board("board-1")
        mock_del.assert_called_once_with("/boards/board-1")

    assert result is True
