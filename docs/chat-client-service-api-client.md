# Chat Client Service API Client

`chat_client_service_api_client` is the component reserved for OpenAPI-generated
client code from `chat_client_service`.

## Generation Workflow

1. Start the FastAPI service.
2. Generate client code from `/openapi.json`.
3. Keep the stable wrapper module (`chat_client_service_api_client.client`) as the
   adapter-facing surface.

## Scaffold Status

- Wrapper class exists with typed method signatures.
- Runtime endpoint wiring is intentionally deferred to implementation phase.
