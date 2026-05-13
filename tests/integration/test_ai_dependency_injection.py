"""Integration tests for AI client dependency injection."""

import importlib

import pytest

import ai_client_api
import ai_client_api.client as client_module
import gemini_client_impl as gemini_impl
import openai_client_impl as openai_impl
from gemini_client_impl.client import GeminiClient
from openai_client_impl.client import OpenAIClient


def test_importing_openai_impl_registers_ai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Importing the provider registers an ``AIClient`` factory."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    importlib.reload(client_module)
    importlib.reload(ai_client_api)

    with pytest.raises(RuntimeError, match="No AI client implementation"):
        ai_client_api.get_client()

    importlib.reload(openai_impl)

    injected_client = ai_client_api.get_client()
    assert isinstance(injected_client, OpenAIClient)


def test_importing_gemini_impl_registers_ai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Importing the Gemini provider also registers an ``AIClient`` factory."""
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")

    importlib.reload(client_module)
    importlib.reload(ai_client_api)

    with pytest.raises(RuntimeError, match="No AI client implementation"):
        ai_client_api.get_client()

    importlib.reload(gemini_impl)

    injected_client = ai_client_api.get_client()
    assert isinstance(injected_client, GeminiClient)
