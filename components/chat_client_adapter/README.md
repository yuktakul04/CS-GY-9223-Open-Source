# Chat Client Adapter

`chat_client_adapter` implements `chat_client_api.Client` by delegating to
`chat_client_service` through the service API client component.

Importing this package can inject a service-backed `get_client()` factory into
`chat_client_api`.
