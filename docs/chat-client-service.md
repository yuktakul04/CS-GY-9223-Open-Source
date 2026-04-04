# Chat Client Service

`chat_client_service` is the HW2 FastAPI deployment unit.

## Current Scaffold Endpoints

- `GET /health`
- `GET /auth/login`
- `GET /auth/callback`
- `POST /chat/messages`
- `GET /chat/messages`
- `DELETE /chat/messages/{message_id}`
- `GET /chat/channels`

## Notes

- OAuth endpoints are currently scaffold stubs.
- Core chat endpoints currently return `501 Not Implemented` in scaffold mode.
- OpenAPI is available at `/openapi.json`.
