# CS-GY-9223 Open Source

A chat client interface and a Telegram implementation scaffold.

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

## Prerequisites

- Python 3.10 or higher
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
├── components/      # Interface + implementation components
│   ├── chat_client_api/         # chat_client_api interface component
│   └── telegram_client_impl/    # Telegram implementation component (scaffold)
├── tests/           # Test suite
├── docs/            # MkDocs documentation
├── .circleci/       # CircleCI CI/CD configuration
├── pyproject.toml   # Project configuration
└── README.md
```

## Dependency Injection Usage

```python
import telegram_client_impl  # injects factory hooks into chat_client_api
from chat_client_api import get_client

client = get_client(interactive=False)
```

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
