# Chat Client Service API Client

This package contains two layers:

1. **`chat_client_service_client/`** — auto-generated OpenAPI client produced by
   `openapi-python-client` from the service's `/openapi.json` spec.

2. **`chat_client_service_api_client/`** — a stable hand-written wrapper
   (`ChatServiceApiClient`) that decouples the adapter from the generated client's
   surface area, so API regeneration does not break downstream consumers.

## Regenerating the client

Run this against a live (or locally running) instance of `chat_client_service`:

```bash
openapi-python-client generate \
  --url https://chat-client-service.onrender.com/openapi.json \
  --output-path components/chat_client_service_api_client
```

Or locally:

```bash
uvicorn chat_client_service.app:app --port 8000 &
openapi-python-client generate \
  --url http://localhost:8000/openapi.json \
  --output-path components/chat_client_service_api_client
```
