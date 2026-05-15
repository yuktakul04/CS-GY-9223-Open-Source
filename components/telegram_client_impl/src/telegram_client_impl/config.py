"""Configuration primitives for Telegram client setup."""

from dataclasses import dataclass
from os import getenv


def _env_strip(name: str) -> str | None:
    raw = getenv(name)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def _env_strip_default(name: str, default: str) -> str:
    raw = getenv(name)
    if raw is None:
        return default
    stripped = raw.strip()
    return stripped or default


@dataclass(frozen=True)
class TelegramClientConfig:
    """Configuration required to initialize a Telegram Bot API client."""

    bot_token: str | None
    bot_api_base_url: str = "https://api.telegram.org"
    interactive: bool = False

    @classmethod
    def from_env(cls, *, interactive: bool = False) -> "TelegramClientConfig":
        """Create config from environment variables only."""
        return cls(
            bot_token=_env_strip("TELEGRAM_BOT_TOKEN"),
            bot_api_base_url=_env_strip_default(
                "TELEGRAM_BOT_API_BASE_URL",
                "https://api.telegram.org",
            ),
            interactive=interactive,
        )
