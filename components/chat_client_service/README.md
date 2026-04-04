# Chat Client Service

`chat_client_service` is the HW2 FastAPI deployment unit for the chat client.

## Endpoints (Scaffold)

- `GET /health`
- `GET /auth/login`
- `GET /auth/callback`
- `POST /chat/messages`
- `GET /chat/messages`
- `DELETE /chat/messages/{message_id}`
- `GET /chat/channels`

## Local Run

```bash
uv run uvicorn chat_client_service.app:app --reload
```

OpenAPI schema is available at `/openapi.json`.
