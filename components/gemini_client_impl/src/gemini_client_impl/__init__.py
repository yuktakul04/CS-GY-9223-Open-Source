"""Gemini-backed :class:`ai_client_api.AIClient` implementation."""

from ai_client_api import register_client
from gemini_client_impl.client import GeminiClient as GeminiClient
from gemini_client_impl.client import get_client_impl as get_client_impl

register_client(get_client_impl)
