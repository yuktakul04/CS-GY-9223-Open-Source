# AI Integration

The assistant talks to an LLM through a small provider-agnostic seam so
the backend can be swapped at runtime without touching the orchestrator.

## Abstraction

[`ai_client_api`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/tree/main/components/ai_client_api)
defines a single ABC:

```python
class AIClient(ABC):
    @abstractmethod
    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str | ToolCallResponse: ...
```

`ToolCallResponse` is a `TypedDict` of `{name, arguments}` returned when
the model chooses a tool instead of producing free-form text.

The package also exposes a registry:

- `register_client(factory)` — store a zero-arg `AIClient` factory.
- `get_client()` — return an instance from the registered factory, or
  raise if none has been registered.

## Implementations

Two packages implement `AIClient`:

| Package | Backend | Env vars |
|---------|---------|----------|
| [`openai_client_impl`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/tree/main/components/openai_client_impl) | OpenAI Chat Completions | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| [`gemini_client_impl`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/tree/main/components/gemini_client_impl) | Google Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL` |

Each implementation's `__init__.py` calls `register_client(get_client_impl)`
at import time — importing the package is the registration.

## Runtime Provider Selection

[`assistant.py`](https://github.com/yuktakul04/CS-GY-9223-Open-Source/blob/main/components/chat_client_service/src/chat_client_service/assistant.py)
reads `CHAT_CLIENT_ASSISTANT_PROVIDER` (`openai` or `gemini`),
`importlib.import_module`s the matching package, then calls
`ai_client_api.get_client()`. If the env var is unset it falls back to
whichever provider's API key is present in the environment. The
orchestrator never imports a concrete provider directly.

## Tool Calling

The assistant exposes 12 tool schemas in `assistant.py`:

- `_CHAT_TOOLS` — `get_messages`, `get_message`, `send_message`,
  `delete_message`, `get_channels`, `get_channel`.
- `_ISSUE_TRACKER_TOOLS` — `get_boards`, `get_issues`, `create_issue`,
  `update_issue`, `delete_issue`, `create_board`.

When the model returns a `ToolCallResponse`, `_dispatch()` routes it to
`_dispatch_chat_tool` (against the shared `ChatClient`) or
`_dispatch_issue_tracker_tool` (against the `IssueTrackerBridge`). The
tool result is fed back as the user-visible reply.

## Swapping Providers

Adding a third provider requires only:

1. A new package implementing `AIClient.send_message`.
2. A `register_client(get_client_impl)` call in its `__init__.py`.
3. A new branch in `_resolve_ai_provider_module()` in `assistant.py`.

No changes to tool schemas, orchestrator wiring, or the chat/issue-tracker
adapters are needed.
