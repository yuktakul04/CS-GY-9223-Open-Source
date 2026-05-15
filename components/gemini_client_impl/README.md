# Gemini Client Implementation

This package provides **`GeminiClient`**, a concrete [`AIClient`](../ai_client_api) backed by the official Google Gen AI Python SDK.

## Environment

- `GEMINI_API_KEY` - required unless you construct `GeminiClient` with an injected `google.genai.Client` instance (e.g. tests).
- `GEMINI_MODEL` - optional; defaults to `gemini-2.5-flash`.

## Usage

```python
from gemini_client_impl import GeminiClient

client = GeminiClient()
reply = client.send_message("Say hello in one word.")
```

Optional `context` is JSON-serialized and prepended to the user message for the model.
