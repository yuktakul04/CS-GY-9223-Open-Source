"""Register the service-backed adapter as the ``chat_client_api`` implementation."""

import chat_client_api
from chat_client_adapter.client import get_client_impl

chat_client_api.register(get_client_impl)
