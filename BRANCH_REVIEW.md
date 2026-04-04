This branch adds the HW2 first-draft scaffolding for a service-oriented architecture while preserving the existing HW1 interface and Telegram implementation.

Added Components

chat_client_service:

FastAPI deployment scaffold

This sets up the service foundation so we can implement full functionality in the next iteration.

Added the deployable web service structure and app entrypoint.
The service can now be started and hosted.
/health endpoint implemented

Added a health check endpoint to confirm the service is up and responding.
OAuth route scaffolding

Added placeholder auth flow endpoints:
GET /auth/login
GET /auth/callback
Route structure is in place, but full OAuth logic is not implemented yet.
Core chat route scaffolding

Added chat API routes for send/get/delete/list operations.
These currently return 501 Not Implemented to indicate intentional placeholders.
Typed models + tests

Added typed request/response models for API contracts.
Added unit tests to validate scaffold behavior and endpoint structure.

chat_client_service_api_client:

This adds the initial scaffold for the service API client component.

OpenAPI client shell package

Created the package structure where generated client code will live.
This establishes a clear place for future openapi-python-client output.
Stable wrapper (ChatServiceApiClient)

Added a wrapper interface that the adapter can call directly.
This decouples adapter code from generated-file structure, so client regeneration won’t break adapter imports/usages.
Typed DTO models

Added DTOs to define typed data exchanged between adapter and service client layer.
Placeholder generation test

Added a scaffold test that marks generated-client wiring as a planned step.
This keeps the current scaffold explicit while signaling the next implementation milestone.

chat_client_adapter:

This adds the adapter layer that bridges the existing interface contract to the new service-client stack.

ServiceBackedChatClient implementation

Added a concrete client class that implements chat_client_api.Client.
Delegation to service client wrapper

Adapter methods forward operations to ChatServiceApiClient.
This preserves interface compatibility while moving execution toward service-backed behavior.
Factory + dependency injection wiring

Added get_client_impl(...) factory for adapter-backed client construction.
Added import-time rebinding so chat_client_api.get_client can resolve to this adapter implementation.
Unit test coverage

Added tests validating forwarding and mapping behavior between adapter and service-client DTO/model layers.

Repo/Docs/Config Updates

Root pyproject.toml updated for:
new workspace members
test discovery paths
first-party import config
dev dependencies needed by scaffold
mkdocs.yml nav updated with HW2 pages

New docs pages:
docs/chat-client-service.md
docs/chat-client-service-api-client.md
docs/chat-client-adapter.md
Root README.md updated with HW2 scaffold architecture section

Test Plan
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run mypy components tests
uv run mkdocs build

Expected results:

tests pass with expected skips for env-gated e2e / placeholder generation
ruff passes
mypy passes
docs build succeeds

Follow-ups (Final Submission Scope)
Implement real OAuth 2.0/OIDC flow in chat_client_service
Replace 501 chat handlers with real delegation to Telegram implementation
Generate and wire concrete OpenAPI client in chat_client_service_api_client
Complete adapter end-to-end service calls (remove placeholder behavior)
Deploy service publicly and document URL/env/secrets/deploy pipeline
Add final e2e coverage for deployed service flow
