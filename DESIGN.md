# DESIGN

This document describes how Team 4 (Chat — Telegram) integrates an LLM
assistant, conforms to the shared chat vertical contract, integrates with
the Issue Tracker vertical, and observes itself in production.

## 1. AI Integration

The assistant talks to an LLM through a tiny provider-agnostic seam so the
backend can be swapped at runtime without touching the orchestrator.

**Abstraction.** [`AIClient`](components/ai_client_api/src/ai_client_api/client.py)
is an ABC with a single method:

```python
def send_message(prompt, context=None, tools=None) -> str | ToolCallResponse
```

`ToolCallResponse` is a `TypedDict` of `{name, arguments}` returned when the
model selects a tool instead of producing free-form text.

**Implementations.** Two packages implement `AIClient`:

- [`openai_client_impl`](components/openai_client_impl/src/openai_client_impl/) — wraps the OpenAI Chat Completions API.
- [`gemini_client_impl`](components/gemini_client_impl/src/gemini_client_impl/) — wraps the Google Gemini API.

**Registration.** Each implementation's `__init__.py` calls
`ai_client_api.register_client(get_client_impl)` at import time. The
registry holds a single factory; `ai_client_api.get_client()` retrieves it.
This means the orchestrator never imports a concrete provider — it imports
whichever module is configured and asks the registry for the client.

**Runtime selection.** [`assistant.py`](components/chat_client_service/src/chat_client_service/assistant.py)
reads `CHAT_CLIENT_ASSISTANT_PROVIDER` (`openai` or `gemini`), uses
`importlib.import_module` to load the matching impl package (triggering its
registration side effect), then calls `ai_client_api.get_client()`. If the
env var is unset it falls back to whichever provider's API key is present.

**Tool dispatch.** The assistant exposes 12 tool schemas — `_CHAT_TOOLS`
(6 chat operations: `get_messages`, `get_message`, `send_message`,
`delete_message`, `get_channels`, `get_channel`) and `_ISSUE_TRACKER_TOOLS`
(6 issue operations: `get_boards`, `get_issues`, `create_issue`,
`update_issue`, `delete_issue`, `create_board`). When the model returns a
`ToolCallResponse`, `_dispatch()` routes it to either `_dispatch_chat_tool`
(against the `ChatClient`) or `_dispatch_issue_tracker_tool` (against the
`IssueTrackerBridge`) and feeds the result back as the reply.

## 2. Shared Vertical Contract

The chat vertical (Teams 4, 8, 9) shares one API package pulled from
`git+https://github.com/HarshithKoriRaj/Shared-API.git` as
`chat-client-api`. It defines the `ChatClient` ABC — `get_messages`,
`get_message`, `send_message`, `delete_message`, `get_channels`,
`get_channel` — and the `Message` / `Channel` domain types every team
returns.

**Team 4 adaptation.** Telegram-native messages and dialogs do not match
the shared contract, so two components bridge the gap:

- [`telegram_client_impl`](components/telegram_client_impl/src/telegram_client_impl/client.py) implements `ChatClient` directly on top of the
  Telegram Bot API. It converts Telegram message/chat objects into the
  shared `Message` and `Channel` types at the boundary.
- [`chat_client_adapter`](components/chat_client_adapter/src/chat_client_adapter/client.py) provides `ServiceBackedChatClient`, a `ChatClient`
  that delegates to our own FastAPI service via the generated
  `chat_client_service_api_client`. This is what other verticals depend on
  when they call us as a service.

**Breaking change.** The pre-shared-API implementation returned
Telethon-native types directly. The migration to the shared ABC replaced
those return types with the domain `Message` and `Channel`, normalized
cursor-based pagination, and changed `delete_message` to take a message ID
rather than a Telethon `Message` object. All call sites and tests were
updated accordingly.

**Same-vertical provider swap.** Team 4 remains Telegram-first:
`CHAT_CLIENT_PROVIDER=telegram` is the default and loads Team 4's provider.
For the HW3 same-vertical swap demo, `CHAT_CLIENT_PROVIDER=slack` loads Team
9's Slack provider based on their HW3 PR #5 implementation through
[`provider.py`](components/chat_client_service/src/chat_client_service/provider.py).
The imported Slack content is Team 9's `components/slack_client_impl`, vendored
locally as `components/slack_client_impl` / `slack-client-impl` from
<https://github.com/HarshithKoriRaj/CS-GY-9223-Open-Source/pull/5>.
The generic `/chat/messages` and `/chat/channels` endpoints are unchanged; only
provider-specific channel and message IDs change. Telegram webhook/login routes
and the `me` alias remain Telegram-specific.

## 3. Cross-Vertical Integration

We integrate with the Issue Tracker vertical (Team 7 — Trello) through a
second shared ABC, `api.client.Client`, from
`git+https://github.com/tatyanacthomas/ospd_issue_tracker.git`
(`ospd-issue-tracker-api`). Team 7 ships their concrete `TrelloClient`
separately.

**Adapter pattern.** Team 7's `TrelloClient` predates the shared ABC and
has minor surface mismatches, so
[`TrelloClientAdapter`](components/issue_tracker_integration/src/issue_tracker_integration/trello_adapter.py)
wraps it and re-exposes the shared `Client`, `Board`, and `Issue`
interfaces. Missing fields (`desc`, `members`, `due_date`) degrade
gracefully; status is mapped from `is_complete`; HTTP errors are mapped to
the shared `IssueTrackerError` hierarchy.

**Bridge.**
[`IssueTrackerBridge`](components/issue_tracker_integration/src/issue_tracker_integration/client.py)
holds a `Client` and exposes the operations the assistant needs. Because
it only depends on the shared ABC, swapping Trello for Jira (or any other
tracker) means writing a new `Client` implementation — no changes to the
bridge, the assistant, or the tool schemas. `get_bridge()` validates at
construction time that the injected object is a real
`api.client.Client` subclass.

**Wiring.** `assistant.py`'s `_build_issue_tracker_bridge()` reads Trello
credentials from the environment, constructs a `TrelloClient`, wraps it in
`TrelloClientAdapter`, and passes that to `get_bridge()`. If credentials
are absent the bridge is `None` and issue-tracker tools are simply
disabled — chat tools still work.

## 4. Observability Strategy

Every HTTP request emits a structured metric event; CloudWatch parses and
graphs them with no custom collector.

**Middleware.**
[`TelemetryMiddleware`](components/chat_client_service/src/chat_client_service/middleware/telemetry.py)
wraps every FastAPI request. It measures wall-clock latency with
`perf_counter()`, classifies the response (`status_code >= 400` → failure),
and emits a single AWS Embedded Metric Format (EMF) JSON event per
request. Metric emission is wrapped in `_publish_request_metrics_safe` so
a telemetry failure can never break the HTTP response.

**Metrics.** Three metrics under namespace `OSPSD/HW3`:

| Metric          | Unit         | Meaning                              |
|-----------------|--------------|--------------------------------------|
| `RequestLatency`| Milliseconds | Per-request wall time                |
| `SuccessRate`   | Count        | 1 for `< 400`, else 0                |
| `FailureRate`   | Count        | 1 for `>= 400` or exception, else 0  |

All three are dimensioned by `Service` (constant `chat_client_service`)
and `Endpoint` (FastAPI route template, e.g. `/messages/{message_id}`,
falling back to the raw URL path).

**Transport.**
[`middleware/cloudwatch.py`](components/chat_client_service/src/chat_client_service/middleware/cloudwatch.py)
configures a `watchtower.CloudWatchLogHandler` against the log group
`chat-client-service-logs`. The middleware writes the EMF JSON to a
dedicated logger; CloudWatch extracts metrics automatically from the
`_aws` block in the payload — no `PutMetricData` calls.

**Dashboard.** [`infra/main.tf`](infra/main.tf) provisions the
`OSPSD-HW3-ChatService` dashboard plus the log group, IAM policy, and
`cloudwatch:PutMetricData` permission. Widgets use CloudWatch `SEARCH`
expressions over `{OSPSD/HW3, Service, Endpoint}` so new endpoints appear
automatically the first time they emit metrics — no Terraform change is
required to chart a newly added route.
