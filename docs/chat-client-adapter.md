# Chat Client Adapter

`chat_client_adapter` implements `chat_client_api.Client` by delegating to the
service API client.

## Dependency Injection Behavior

Importing `chat_client_adapter` rebinds:

- `chat_client_api.client.get_client`
- `chat_client_api.get_client`

This allows consumer code to keep using:

```python
from chat_client_api import get_client
```

while changing only the injected backend component.
