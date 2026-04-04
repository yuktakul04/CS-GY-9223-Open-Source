# DESIGN.md — Chat Client Service (HW2)

---

## Architecture Overview

### What Changed from HW1

In HW1, the Telegram implementation was imported directly as a library — wired in at import time via dependency injection. Every consumer of `chat_client_api` had to have the Telegram credentials and implementation installed locally.

HW2 introduces a **service-oriented architecture**: the implementation is wrapped in a standalone FastAPI process that exposes chat operations over HTTP. Consumers talk to the service through a generated API client and an adapter — and crucially, their calling code does not change.

```
[User Code]
    │  calls chat_client_api.get_client() — same as HW1
    ▼
[chat_client_adapter]             ← NEW: implements chat_client_api.Client
    │  delegates to →
[chat_client_service_api_client]  ← NEW: stable wrapper around generated HTTP client
    │  HTTP requests →
[chat_client_service]             ← NEW: FastAPI service (runs as independent process)
    │  delegates to →
[telegram_client_impl]            ← HW1: unchanged Telegram implementation
```

### Components

| Component | Role |
|---|---|
| `chat_client_api` | Unchanged HW1 interface (`Client`, `Message`, `Channel`) |
| `telegram_client_impl` | Unchanged HW1 Telegram implementation |
| `chat_client_service` | FastAPI service — delegates to `telegram_client_impl`, exposes HTTP endpoints + Telegram OAuth |
| `chat_client_service_api_client` | Stable wrapper around the auto-generated OpenAPI client |
| `chat_client_adapter` | Implements `chat_client_api.Client` by delegating to the service client |

---

## Request Flow

A complete `send_message` call travels through all three bridges:

```
User Code
  │
  │  client = chat_client_api.get_client()
  │  # chat_client_adapter.register() rebinds get_client at import time
  │  # so this returns a ServiceBackedChatClient
  │
  ▼
chat_client_adapter.ServiceBackedChatClient.send_message(channel_id, text)
  │
  │  calls → self._service_client.send_message(channel_id=..., text=...)
  │
  ▼
chat_client_service_api_client.ChatServiceApiClient.send_message(...)
  │
  │  HTTP POST → /chat/messages
  │
  ▼
chat_client_service  (FastAPI)
  │  POST /chat/messages
  │  injects telegram_client_impl.Client via get_chat_client()
  │  delegates → client.send_message(channel_id, text)
  │
  ▼
HTTP Response (JSON)
  │
  ▼
chat_client_service_api_client  (parses response → DTO)
  │
  ▼
chat_client_adapter  (maps DTO → AdapterMessage implementing chat_client_api.Message)
  │
  ▼
User Code receives a Message object — identical interface to HW1
```

---

## API Design

### Endpoints

#### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns service liveness status |

**Response:**
```json
{ "status": "ok" }
```

#### Auth — Telegram Login Widget

| Method | Path | Description |
|---|---|---|
| `GET` | `/auth/login` | Generates CSRF state cookie, redirects to Telegram OAuth |
| `GET` | `/auth/callback` | Serves JS bridge page that decodes `#tgAuthResult` and POSTs to `/auth/verify` |
| `POST` | `/auth/verify` | Verifies Telegram HMAC, issues signed Bearer session token |
| `GET` | `/auth/me` | Returns session info for authenticated caller |

**`GET /auth/login`** — Sets `oauth_state` httpOnly cookie, returns `302` to:
```
https://oauth.telegram.org/auth?bot_id=<id>&origin=<base>&return_to=<base>/auth/callback
```

**`POST /auth/verify`** request body (from Telegram's `tgAuthResult`):
```json
{
  "id": 123456789,
  "first_name": "Alice",
  "last_name": "Smith",
  "username": "alice",
  "auth_date": 1700000000,
  "hash": "<telegram-hmac>"
}
```

**`POST /auth/verify`** success response:
```json
{
  "detail": "Authenticated successfully.",
  "state": "<csrf-state>",
  "access_token": "<signed-bearer-token>",
  "token_type": "bearer"
}
```

The Bearer token is self-contained and HMAC-signed with the bot token — no server-side session store required. Tokens survive service restarts and scale across instances.

#### Chat

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat/messages` | Send a message to a channel |
| `GET` | `/chat/messages` | List messages from a channel |
| `DELETE` | `/chat/messages/{message_id}` | Delete a specific message |
| `GET` | `/chat/channels` | List available channels |

**Request model for `POST /chat/messages`:**
```json
{
  "channel_id": "string (min_length=1)",
  "text": "string (min_length=1)"
}
```

**Response model for messages:**
```json
{
  "id": "string",
  "sender": "string",
  "channel_id": "string",
  "timestamp": "string (ISO 8601)",
  "text": "string"
}
```

**Response model for `DELETE /chat/messages/{message_id}`:**
```json
{ "success": true }
```

### Error Handling

| Scenario | HTTP Status | Response |
|---|---|---|
| Missing CSRF cookie on `/auth/verify` | `400 Bad Request` | `{"detail": "Missing CSRF state cookie. Start the flow at /auth/login."}` |
| Telegram HMAC mismatch | `401 Unauthorized` | `{"detail": "Telegram hash verification failed."}` |
| Invalid/missing Bearer token | `401 Unauthorized` | `{"detail": "Not authenticated. Start at /auth/login."}` |
| Telegram API error in chat endpoint | `500 Internal Server Error` | `{"detail": "<exception message>"}` |
| Invalid request body | `422 Unprocessable Entity` | FastAPI default validation error |

---

## The Adapter Pattern

### Why the Generated Client Doesn't Match the Interface

`chat_client_api.Client` defines an interface using domain types: `Message` and `Channel` are abstract classes with specific properties. The OpenAPI-generated client returns raw DTOs — plain data containers shaped by the HTTP response schema, not by the `chat_client_api` contract.

Without the adapter, user code would have to know it's talking to a service and deal with DTOs directly. The adapter closes this gap.

### How It Works

**Library usage (HW1) — no changes required to user code:**
```python
from chat_client_api import get_client

client = get_client()
# client is telegram_client_impl.TelegramClient

for msg in client.get_messages(channel_id="my_channel"):
    print(msg.text)
```

**Service usage (HW2) — same user code, different wiring:**
```python
import chat_client_adapter  # registers ServiceBackedChatClient as the implementation
from chat_client_api import get_client

client = get_client()
# client is now chat_client_adapter.ServiceBackedChatClient
# get_messages calls the HTTP service, maps DTOs to AdapterMessage

for msg in client.get_messages(channel_id="my_channel"):
    print(msg.text)  # identical call — user code is unchanged
```

**The adapter's mapping logic:**
```python
class ServiceBackedChatClient(Client):
    def send_message(self, channel_id: str, text: str) -> Message:
        dto = self._service_client.send_message(channel_id=channel_id, text=text)
        return AdapterMessage(
            message_id=dto.id,
            sender=dto.sender,
            channel_id=dto.channel_id,
            timestamp=dto.timestamp,
            text=dto.text,
        )
```

**The DI registration (in `chat_client_adapter/__init__.py`):**
```python
import chat_client_api
from chat_client_adapter.client import get_client_impl

chat_client_api.register(get_client_impl)
# Uses chat_client_api's register() hook — no fragile monkey-patching
```

---

## Authentication Flow and Deviation from Standard OAuth 2.0

The assignment specifies an OAuth 2.0 Authorization Code Flow (redirect → callback with `code` → server-side code-for-token exchange). This service implements the **Telegram Login Widget** instead, which is a documented deviation.

**Why the deviation:** Telegram and Telethon do not provide a standard OAuth 2.0 authorization-code flow for end-user web authentication. The Login Widget (`oauth.telegram.org/auth`) is the closest provider-supported web authentication flow available for Telegram. There is no backchannel token endpoint to exchange a code — Telegram sends signed user data directly.

**What the flow does instead:**
1. `/auth/login` redirects to `oauth.telegram.org/auth` — the authorization redirect step is present.
2. Telegram redirects to `/auth/callback` with user data in the URL fragment (`#tgAuthResult`). Because fragments are never sent to the server, a JS bridge page decodes it client-side and POSTs to `/auth/verify` — this is the callback step.
3. `/auth/verify` validates Telegram's HMAC-SHA256 signature (using the bot token as the secret key) and issues a signed Bearer token — this is the token issuance step.

All three logical steps are present. The deviation is that step 3 uses Telegram's HMAC verification instead of a backchannel code exchange, because Telegram does not offer one. Chat endpoints require a valid Bearer token issued by this flow.

## OpenAPI Client Generation

The `chat_client_service_api_client` package contains a client generated from the service's `/openapi.json` using `openapi-python-client`, plus a stable hand-written wrapper (`ChatServiceApiClient`) that decouples the adapter from the generated code's surface area.

To regenerate after API changes:
```bash
openapi-python-client generate \
  --url http://localhost:8000/openapi.json \
  --output-path components/chat_client_service_api_client
```

---

## Testing Strategy

### Test Types

| Test | Location | Type | What It Validates |
|---|---|---|---|
| `test_health_endpoint` | `chat_client_service/tests/test_app.py` | Unit | `GET /health` returns `200 {"status": "ok"}` |
| `test_auth_login_redirects_to_provider` | `chat_client_service/tests/test_app.py` | Unit | `/auth/login` returns `302` to Telegram with CSRF cookie |
| `test_auth_callback_returns_html_bridge` | `chat_client_service/tests/test_app.py` | Unit | `/auth/callback` returns HTML page containing JS bridge |
| `test_auth_full_flow_returns_access_token` | `chat_client_service/tests/test_app.py` | Unit | Full login → verify → token flow |
| `test_auth_cookie_is_cleared_after_verify` | `chat_client_service/tests/test_app.py` | Unit | CSRF cookie deleted after successful verify |
| `test_auth_verify_rejects_invalid_hash` | `chat_client_service/tests/test_app.py` | Unit | Bad Telegram HMAC returns 401 |
| `test_auth_me_*` | `chat_client_service/tests/test_app.py` | Unit | Bearer token auth on `/auth/me` |
| Chat endpoint tests | `chat_client_service/tests/test_app.py` | Unit | All 4 chat endpoints delegate via DI, return correct models, return 500 on client errors |
| Transport-level tests | `chat_client_service_api_client/tests/test_transport_client.py` | Unit | `ChatServiceApiClient` wrapper sends correct HTTP requests and maps responses |
| Location transparency | `tests/e2e/test_location_transparency.py` | E2E | Same consumer workflow runs identically with local mock and service-adapter backends |

### Mocking Strategy

| What Was Mocked | Why |
|---|---|
| `ChatServiceApiClient` | Adapter unit tests mock the service client so tests don't require a running service |
| `_verify_telegram_hash` | Auth tests patch Telegram HMAC to test flow logic without real bot credentials |
| `get_chat_client` dependency | FastAPI `dependency_overrides` injects mock client for chat endpoint tests |
| `httpx.BaseTransport` | Transport-level tests intercept HTTP at the wire level to verify request construction |

### Interface Compliance

The adapter's compliance with `chat_client_api.Client` is enforced at two levels:

**Static:** `ServiceBackedChatClient` inherits directly from `chat_client_api.Client`. `mypy` strict mode checks the full component graph and fails if any method signature diverges.

**Runtime:** `test_consumer_workflow_with_service_adapter_backend` runs the complete consumer workflow through `ServiceBackedChatClient` with a mocked HTTP layer, proving location transparency end-to-end.

---

## Deployment

The service is deployed to Render at:
**`https://chat-client-service.onrender.com`**

| Endpoint | URL |
|---|---|
| Health | `https://chat-client-service.onrender.com/health` |
| OpenAPI spec | `https://chat-client-service.onrender.com/openapi.json` |
| Swagger UI | `https://chat-client-service.onrender.com/docs` |
| Login | `https://chat-client-service.onrender.com/auth/login` |

Required environment variables on Render:

| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram bot credentials (HMAC verification + login widget) |
| `TELEGRAM_API_ID` | Telegram API credentials |
| `TELEGRAM_API_HASH` | Telegram API credentials |
| `TELEGRAM_SESSION_STRING` | Persistent Telethon session (avoids interactive auth on ephemeral filesystem) |
| `SERVICE_BASE_URL` | Public HTTPS URL (`https://chat-client-service.onrender.com`) |

CircleCI automatically deploys on push to the branch via a Render deploy hook (`RENDER_DEPLOY_HOOK_URL` env var in CircleCI project settings).
