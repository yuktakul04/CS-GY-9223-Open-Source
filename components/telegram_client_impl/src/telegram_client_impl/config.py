"""Configuration primitives for Telegram client setup."""

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class TelegramClientConfig:
    """Configuration required to initialize a Telegram client scaffold."""

    api_id: str | None
    api_hash: str | None
    bot_token: str | None
    session_name: str = "telegram_session"
    interactive: bool = False

    @classmethod
    def from_env(cls, *, interactive: bool = False) -> "TelegramClientConfig":
        """Create config from environment variables only."""
        return cls(
            api_id=getenv("TELEGRAM_API_ID"),
            api_hash=getenv("TELEGRAM_API_HASH"),
            bot_token=getenv("TELEGRAM_BOT_TOKEN"),
            session_name=getenv("TELEGRAM_SESSION_NAME", "telegram_session"),
            interactive=interactive,
        )
