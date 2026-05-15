# OpenAI Client Implementation

This package provides **`OpenAIClient`**, a concrete [`AIClient`](../ai_client_api) backed by the official OpenAI Python SDK.

## Environment

- `OPENAI_API_KEY` — required unless you construct `OpenAIClient` with an injected `OpenAI` instance (e.g. tests).
- `OPENAI_MODEL` — optional; defaults to `gpt-4o-mini`.

## Usage

```python
from openai_client_impl import OpenAIClient

client = OpenAIClient()
reply = client.send_message("Say hello in one word.")
```

Optional `context` is JSON-serialized and prepended to the user message for the model.
