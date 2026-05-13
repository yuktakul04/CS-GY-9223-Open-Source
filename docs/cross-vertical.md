# Cross-Vertical Integration

Team 4 (Chat) integrates with Team 7 (Issue Tracker — Trello) through a
shared ABC. The assistant calls into the issue tracker the same way it
calls into chat: as a tool dispatched on a `ToolCallResponse`.

## Shared ABC

[`ospd-issue-tracker-api`](https://github.com/tatyanacthomas/ospd_issue_tracker)
defines:

- `api.client.Client` — operations over `get_boards`, `get_issues`,
  `create_issue`, `update_issue`, `delete_issue`, `create_board`, etc.
- `api.board.Board`, `api.issue.Issue` — domain types.
- `api.exceptions.IssueTrackerError` and subclasses (`AuthenticationError`,
  `AuthorizationError`, `BoardNotFoundError`, `IssueNotFoundError`,
  `RequestError`).

The `issue_tracker_integration` component depends only on this ABC — no
Trello-specific code lives in the assistant.

## Adapter Pattern

Team 7 ships a concrete `TrelloClient` whose surface predates the shared
ABC.
[`TrelloClientAdapter`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/blob/main/components/issue_tracker_integration/src/issue_tracker_integration/trello_adapter.py)
wraps it and re-exposes `Client`, `Board`, and `Issue`:

- Missing fields (`desc`, `members`, `due_date`) degrade gracefully
  (empty string or `None`).
- `Status` is mapped from Team 7's `is_complete` bool (`True` →
  `COMPLETED`, `False` → `TO_DO`).
- `requests.HTTPError`s are normalized to the shared
  `IssueTrackerError` hierarchy by status code (404 → `BoardNotFoundError`
  / `IssueNotFoundError`, 401 → `AuthenticationError`, 403 →
  `AuthorizationError`).

## Bridge

[`IssueTrackerBridge`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/blob/main/components/issue_tracker_integration/src/issue_tracker_integration/client.py)
holds a `Client` and exposes the methods the assistant needs. Because it
only depends on the shared ABC, swapping Trello for Jira (or any other
tracker) means writing a new `Client` implementation — no changes to the
bridge, the assistant, or the tool schemas.

`get_bridge(client)` validates at construction time that the injected
object is a real `api.client.Client` subclass, raising
`IssueTrackerError` otherwise.

## Dependency Injection

In [`assistant.py`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/blob/main/components/chat_client_service/src/chat_client_service/assistant.py),
`_build_issue_tracker_bridge()` reads Trello credentials from the
environment:

| Env var          | Purpose                                |
|------------------|----------------------------------------|
| `TRELLO_API_KEY` | Required to enable the bridge          |
| `TRELLO_TOKEN`   | Required to enable the bridge          |
| `TRELLO_BOARD_ID`| Optional scoping for the default board |

It constructs `TrelloClient(...)`, wraps it in `TrelloClientAdapter`, and
passes the adapter to `get_bridge()`. The result is injected into the
`TelegramAssistantOrchestrator` alongside the `AIClient` and `ChatClient`.

If credentials are missing, the bridge is `None` and issue-tracker tools
are disabled at runtime — chat tools still work. The orchestrator logs
`"Trello not configured — issue tracker tools disabled"` and continues.
