# CS-GY-9223 Open Source

A chat client interface, Telegram implementation, and a deployed FastAPI microservice with OAuth authentication.

## Team

**Team name:** Team 4

**Members:**

- Yukta Kulkarni — yk3213 (yuktakul04)
- Sumanth Subramanian Ramesh — sr7420
- Karthik Subramanian — ks7886
- Pranav Raj N K — pn2330
- Mohamed Yaseen Mohamed Shuaib — mm14451

**Course staff (collaborators to add):**

- adithyab-20
- ivanearisty
- AranyaAryaman

## Live Deployment

The service is deployed on Render:

| Endpoint | URL |
|---|---|
| Health | https://chat-client-service.onrender.com/health |
| Swagger UI | https://chat-client-service.onrender.com/docs |
| OpenAPI spec | https://chat-client-service.onrender.com/openapi.json |
| Login | https://chat-client-service.onrender.com/auth/login |

### Required environment variables (Render)

| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot credentials for Telegram Login Widget HMAC verification |
| `TELEGRAM_API_ID` | Telegram API credentials |
| `TELEGRAM_API_HASH` | Telegram API credentials |
| `TELEGRAM_SESSION_STRING` | Persistent Telethon session string |
| `SERVICE_BASE_URL` | Public HTTPS base URL (`https://chat-client-service.onrender.com`) |

### CI/CD

CircleCI runs on every push: lint (`ruff`) → format check → type check (`mypy`) → tests + coverage (≥85%). On push to the deployment branch, a Render deploy hook is triggered automatically (`RENDER_DEPLOY_HOOK_URL` env var in CircleCI project settings).

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
# Clone the repository
git clone https://github.com/yuktakul04/CS-GY-9223-Open-Source.git
cd CS-GY-9223-Open-Source

# Install dependencies
uv sync

# Install with all dependencies (dev + docs)
uv sync --all-extras
```

## Development

```bash
# Run tests
uv run pytest

# Run linting
uv run ruff check .

# Run type checking
uv run mypy components tests
```

## Documentation

```bash
uv run mkdocs serve
```

## Project Structure

```
.
├── components/
│   ├── chat_client_api/                 # Abstract interface (Client, Message, Channel)
│   ├── telegram_client_impl/            # Telegram implementation of chat_client_api
│   ├── chat_client_service/             # FastAPI microservice (Telegram OAuth + chat)
│   ├── chat_client_service_api_client/  # Auto-generated OpenAPI client + stable wrapper
│   └── chat_client_adapter/             # Adapter: implements chat_client_api over HTTP
├── tests/           # E2E + integration tests
├── docs/            # MkDocs documentation
├── .circleci/       # CircleCI CI/CD configuration
├── render.yaml      # Render deployment configuration
├── pyproject.toml   # Project configuration
└── README.md
```

## Usage

**Direct library (HW1 style):**
```python
import telegram_client_impl  # registers Telegram implementation
from chat_client_api import get_client

client = get_client()
for msg in client.get_messages(channel_id="my_channel"):
    print(msg.text)
```

**Via deployed service (HW2 — same consumer code):**
```python
import chat_client_adapter  # registers service-backed implementation
from chat_client_api import get_client

client = get_client()  # now backed by the HTTP service
for msg in client.get_messages(channel_id="my_channel"):
    print(msg.text)  # identical call, different backend
```

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
