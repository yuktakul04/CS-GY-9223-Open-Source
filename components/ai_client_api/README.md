# AI Client API

This package defines the abstract **`AIClient`** contract for prompt-based LLM calls.

## Interface

Subclasses implement `send_message(prompt, context=None) -> str`.

No concrete providers live here; see `openai_client_impl` for an OpenAI-backed implementation.
