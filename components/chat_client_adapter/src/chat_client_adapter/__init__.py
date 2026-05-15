"""Register the service-backed adapter as the ``chat_client_api`` implementation."""

from chat_client_adapter.client import get_client_impl
from chat_client_api import register_client

register_client(get_client_impl)
