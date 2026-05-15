"""Adapter mapping Team 7's TrelloClient to the shared api.client.Client ABC."""

from __future__ import annotations

from typing import TYPE_CHECKING

import requests
from api.board import Board as SharedBoard
from api.client import Client as SharedClient
from api.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BoardNotFoundError,
    IssueNotFoundError,
    RequestError,
)
from api.issue import Issue as SharedIssue
from api.issue import Status

if TYPE_CHECKING:
    from collections.abc import Iterator

    from issue_tracker_client_api import Board as T7Board
    from issue_tracker_client_api import Issue as T7Issue
    from trello_client_impl import TrelloClient

_TRELLO_BASE = "https://api.trello.com/1"
_HTTP_NOT_FOUND = 404
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403


def _map_http_error(
    exc: requests.HTTPError,
    *,
    resource: str = "resource",
) -> RequestError:
    """Map an HTTPError to the closest IssueTrackerError subclass."""
    status = exc.response.status_code if exc.response is not None else 0
    if status == _HTTP_NOT_FOUND:
        return (
            IssueNotFoundError(str(exc), cause=exc)
            if resource == "issue"
            else BoardNotFoundError(str(exc), cause=exc)
        )
    if status == _HTTP_UNAUTHORIZED:
        return AuthenticationError(str(exc), cause=exc)
    if status == _HTTP_FORBIDDEN:
        return AuthorizationError(str(exc), cause=exc)
    return RequestError(str(exc), cause=exc)


class _IssueAdapter(SharedIssue):
    """Wraps Team 7's Issue to satisfy the shared api.issue.Issue interface.

    Limitations vs the full shared ABC:
      - ``desc``: not exposed by Team 7's Issue ABC → always returns ``""``
      - ``members``: not exposed → always returns ``None``
      - ``due_date``: not exposed → always returns ``None``
      - ``status``: mapped from ``is_complete`` (True → COMPLETED, False → TO_DO)
    """

    def __init__(self, wrapped: T7Issue) -> None:
        """Store the wrapped Team 7 issue."""
        self._wrapped = wrapped

    @property
    def id(self) -> str:
        """Return the issue ID."""
        return self._wrapped.id

    @property
    def title(self) -> str:
        """Return the issue title."""
        return self._wrapped.title

    @property
    def desc(self) -> str:
        """Return description (not exposed by Team 7 ABC; always empty)."""
        return ""

    @property
    def members(self) -> list[str] | None:
        """Return assignees (not exposed by Team 7 ABC; always None)."""
        return None

    @property
    def due_date(self) -> str | None:
        """Return due date (not exposed by Team 7 ABC; always None)."""
        return None

    @property
    def status(self) -> Status:
        """Map Team 7 is_complete flag to Status enum."""
        return Status.COMPLETED if self._wrapped.is_complete else Status.TO_DO

    @property
    def board_id(self) -> str:
        """Return the board ID, falling back to empty string if unknown."""
        return self._wrapped.board_id or ""


class _BoardAdapter(SharedBoard):
    """Wraps Team 7's Board to satisfy the shared api.board.Board interface."""

    def __init__(self, wrapped: T7Board) -> None:
        """Store the wrapped Team 7 board."""
        self._wrapped = wrapped

    @property
    def id(self) -> str:
        """Return the board ID."""
        return self._wrapped.id

    @property
    def board_name(self) -> str:
        """Return the board name (Team 7 uses .name; shared ABC uses .board_name)."""
        return self._wrapped.name


class TrelloClientAdapter(SharedClient):
    """Adapts Team 7's TrelloClient to the shared api.client.Client ABC.

    Method-mapping notes
    --------------------
    get_issues(board_id):
        Fetches all Trello lists on the board, then yields cards from each.
    create_issue(title, board_id, ...):
        Uses the first existing list on the board; creates a "To Do" list if none exist.
        members, due_date, status are accepted but silently ignored by Trello.
    update_issue:
        title/desc/due_date → PUT /cards via Trello REST directly.
        status → TrelloClient.update_status (moves card between lists).
        members / board_id → not supported by Team 7's API; silently ignored.
    update_board / delete_board:
        Not in TrelloClient; called via Trello REST using the public api_key + token.
    """

    def __init__(self, trello: TrelloClient) -> None:
        """Wrap a TrelloClient instance."""
        self._t = trello

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _put(self, path: str, payload: dict[str, str]) -> None:
        """Issue an authenticated PUT to the Trello REST API."""
        resp = requests.put(
            f"{_TRELLO_BASE}{path}",
            params={"key": self._t.api_key, "token": self._t.token},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()

    def _delete(self, path: str) -> None:
        """Issue an authenticated DELETE to the Trello REST API."""
        resp = requests.delete(
            f"{_TRELLO_BASE}{path}",
            params={"key": self._t.api_key, "token": self._t.token},
            timeout=30,
        )
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    def get_issue(self, issue_id: str) -> SharedIssue:
        """Return a single issue by ID."""
        try:
            return _IssueAdapter(self._t.get_issue(issue_id))
        except requests.HTTPError as exc:
            raise _map_http_error(exc, resource="issue") from exc

    def get_issues(self, board_id: str) -> Iterator[SharedIssue]:
        """Yield all issues across every list on the board."""
        try:
            for lst in self._t.get_lists(board_id):
                yield from (
                    _IssueAdapter(issue) for issue in self._t.get_issues_in_list(lst.id)
                )
        except requests.HTTPError as exc:
            raise _map_http_error(exc, resource="board") from exc

    def create_issue(  # noqa: PLR0913
        self,
        title: str,
        board_id: str,
        desc: str | None = None,
        members: list[str] | None = None,  # noqa: ARG002
        due_date: str | None = None,  # noqa: ARG002
        status: Status = Status.TO_DO,  # noqa: ARG002
    ) -> SharedIssue:
        """Create a card on the first list of the board (creates list if none exist)."""
        try:
            lists = list(self._t.get_lists(board_id))
            if lists:
                list_id = lists[0].id
            else:
                list_id = self._t.create_list(board_id, "To Do").id
            return _IssueAdapter(self._t.create_issue(title, list_id, description=desc))
        except requests.HTTPError as exc:
            raise _map_http_error(exc, resource="issue") from exc

    def update_issue(  # noqa: PLR0913
        self,
        issue_id: str,
        title: str | None = None,
        desc: str | None = None,
        members: list[str] | None = None,  # noqa: ARG002
        due_date: str | None = None,
        status: Status | None = None,
        board_id: str | None = None,  # noqa: ARG002
    ) -> SharedIssue:
        """Update a card. members and board_id are silently ignored (unsupported)."""
        try:
            payload: dict[str, str] = {}
            if title is not None:
                payload["name"] = title
            if desc is not None:
                payload["desc"] = desc
            if due_date is not None:
                payload["due"] = due_date
            if payload:
                self._put(f"/cards/{issue_id}", payload)
            if status is not None:
                self._t.update_status(issue_id, status.value)
            return self.get_issue(issue_id)
        except requests.HTTPError as exc:
            raise _map_http_error(exc, resource="issue") from exc

    def delete_issue(self, issue_id: str) -> bool:
        """Delete an issue by ID."""
        try:
            return self._t.delete_issue(issue_id)
        except requests.HTTPError as exc:
            raise _map_http_error(exc, resource="issue") from exc

    # ------------------------------------------------------------------
    # Boards
    # ------------------------------------------------------------------

    def get_board(self, board_id: str) -> SharedBoard:
        """Return a single board by ID."""
        try:
            return _BoardAdapter(self._t.get_board(board_id))
        except requests.HTTPError as exc:
            raise _map_http_error(exc, resource="board") from exc

    def get_boards(self) -> Iterator[SharedBoard]:
        """Yield all boards visible to the authenticated user."""
        try:
            yield from (_BoardAdapter(b) for b in self._t.get_boards())
        except requests.HTTPError as exc:
            raise _map_http_error(exc, resource="board") from exc

    def create_board(self, name: str) -> SharedBoard:
        """Create a new board."""
        try:
            return _BoardAdapter(self._t.create_board(name))
        except requests.HTTPError as exc:
            raise _map_http_error(exc, resource="board") from exc

    def update_board(self, board_id: str, name: str | None = None) -> SharedBoard:
        """Rename a board via Trello REST (not exposed by TrelloClient directly)."""
        try:
            if name is not None:
                self._put(f"/boards/{board_id}", {"name": name})
            return self.get_board(board_id)
        except requests.HTTPError as exc:
            raise _map_http_error(exc, resource="board") from exc

    def delete_board(self, board_id: str) -> bool:
        """Delete a board via Trello REST (not exposed by TrelloClient directly)."""
        try:
            self._delete(f"/boards/{board_id}")
        except requests.HTTPError as exc:
            raise _map_http_error(exc, resource="board") from exc
        else:
            return True
