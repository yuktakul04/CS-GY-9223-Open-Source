# Chat Client Adapter

`chat_client_adapter` implements the `ChatClient` ABC from `chat-client-api`
(the shared external git dependency) by delegating to `chat_client_service`
through the service API client component. Note: this is distinct from
`ai_client_api`, which defines the `AIClient` ABC for LLM integrations.

Importing this package injects a service-backed `get_client()` factory into
`chat_client_api`.
