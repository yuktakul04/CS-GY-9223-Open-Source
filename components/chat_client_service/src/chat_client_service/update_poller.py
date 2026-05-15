"""Background Telegram Bot API polling for deployments without webhooks."""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING, cast

from telegram_client_impl.client import TelegramClient, get_client_impl
from telegram_client_impl.errors import TelegramAuthError

if TYPE_CHECKING:
    from collections.abc import Callable

LOGGER = logging.getLogger(__name__)
DEFAULT_POLL_INTERVAL_SECONDS = 3.0


class TelegramUpdatePoller:
    """Run Bot API update polling while the web service process is alive."""

    def __init__(
        self,
        *,
        interval_seconds: float,
        on_update: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        """Create a poller with a fixed interval between update checks."""
        self._interval_seconds = interval_seconds
        self._on_update = on_update
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background polling thread once."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="telegram-update-poller",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_seconds))
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._poll_once()
            self._stop_event.wait(self._interval_seconds)

    def _poll_once(self) -> None:
        client: TelegramClient | None = None
        try:
            client = cast("TelegramClient", get_client_impl(interactive=False))
            client.sync_updates(force=True, on_update=self._on_update)
        except TelegramAuthError:
            LOGGER.warning("Telegram polling disabled because bot token is missing")
            self._stop_event.set()
        except Exception:
            LOGGER.exception("Telegram polling failed")
        finally:
            if client is not None:
                client.close()


def should_start_update_poller() -> bool:
    """Return whether service startup should run background polling."""
    return os.getenv("TELEGRAM_UPDATE_MODE", "webhook").strip().lower() == "polling"


def poll_interval_seconds() -> float:
    """Return the configured polling interval."""
    raw = os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS", "")
    if not raw:
        return DEFAULT_POLL_INTERVAL_SECONDS
    try:
        return max(0.5, float(raw))
    except ValueError:
        return DEFAULT_POLL_INTERVAL_SECONDS
