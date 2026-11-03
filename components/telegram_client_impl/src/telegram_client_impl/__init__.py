"""Inject Telegram factory functions into ``chat_client_api``."""

import chat_client_api
import chat_client_api.client as client_module
import chat_client_api.message as message_module
from telegram_client_impl.client import get_client_impl
from telegram_client_impl.message import get_message_impl

# Rebind module-level factory hooks.
client_module.get_client = get_client_impl
message_module.get_message = get_message_impl

# Keep package exports aligned for `from chat_client_api import get_client` use-cases.
chat_client_api.get_client = get_client_impl
chat_client_api.get_message = get_message_impl
