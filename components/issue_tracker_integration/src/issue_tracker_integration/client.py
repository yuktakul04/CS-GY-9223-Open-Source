"""IssueTrackerBridge — thin wrapper around the ospd-issue-tracker-api Client."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.client import Client
from api.exceptions import IssueTrackerError
from api.issue import Issue, Status

if TYPE_CHECKING:
    from collections.abc import Iterator

    from api.board import Board


class IssueTrackerBridge:
    """Wraps an ``api.client.Client`` and exposes issue-tracker operations.

    All ``IssueTrackerError`` subclasses from the upstream API propagate
    unchanged so callers can handle them directly.
    """

    def __init__(self, client: Client) -> None:
        """Store the upstream client."""
        self._client = client

    # ------------------------------------------------------------------
    # Boards
    # ------------------------------------------------------------------

    def get_boards(self) -> Iterator[Board]:
        """Return an iterator of all boards."""
        return self._client.get_boards()

    def get_board(self, board_id: str) -> Board:
        """Return the board with the given ID."""
        return self._client.get_board(board_id)

    def create_board(self, name: str) -> Board:
        """Create a new board and return it."""
        return self._client.create_board(name)

    def update_board(self, board_id: str, *, name: str | None = None) -> Board:
        """Update a board's name."""
        return self._client.update_board(board_id, name=name)

    def delete_board(self, board_id: str) -> bool:
        """Delete a board by ID. Returns True on success."""
        return self._client.delete_board(board_id)

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    def get_issues(self, board_id: str) -> Iterator[Issue]:
        """Return an iterator of all issues on the given board."""
        return self._client.get_issues(board_id)

    def get_issue(self, issue_id: str) -> Issue:
        """Return the issue with the given ID."""
        return self._client.get_issue(issue_id)

    def create_issue(  # noqa: PLR0913
        self,
        title: str,
        board_id: str,
        desc: str | None = None,
        members: list[str] | None = None,
        due_date: str | None = None,
        status: Status = Status.TO_DO,
    ) -> Issue:
        """Create a new issue on the given board."""
        return self._client.create_issue(
            title,
            board_id,
            desc=desc,
            members=members,
            due_date=due_date,
            status=status,
        )

    def update_issue(  # noqa: PLR0913
        self,
        issue_id: str,
        *,
        title: str | None = None,
        desc: str | None = None,
        members: list[str] | None = None,
        due_date: str | None = None,
        status: Status | None = None,
        board_id: str | None = None,
    ) -> Issue:
        """Update fields on an existing issue."""
        return self._client.update_issue(
            issue_id,
            title=title,
            desc=desc,
            members=members,
            due_date=due_date,
            status=status,
            board_id=board_id,
        )

    def delete_issue(self, issue_id: str) -> bool:
        """Delete an issue by ID. Returns True on success."""
        return self._client.delete_issue(issue_id)


def get_bridge(client: Client) -> IssueTrackerBridge:
    """Wrap an existing ``Client`` in an ``IssueTrackerBridge``.

    Raises:
        IssueTrackerError: if ``client`` is not a valid ``Client`` instance.

    """
    if not isinstance(client, Client):
        msg = "client must be an instance of api.client.Client"
        raise IssueTrackerError(msg)
    return IssueTrackerBridge(client)
