"""Register the Telegram ``ChatClient`` with the shared vertical API."""

from chat_client_api import register_client
from telegram_client_impl.client import get_client_impl

register_client(get_client_impl)
