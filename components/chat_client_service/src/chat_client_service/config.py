"""Configuration helpers for local environment loading."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from dotenv import dotenv_values

if TYPE_CHECKING:
    from pathlib import Path


def load_environment(env_file: str | Path = ".env") -> bool:
    """Load non-empty local environment variables without overriding exported values."""
    values = dotenv_values(env_file)
    loaded = False

    for key, value in values.items():
        if value in (None, "") or key in os.environ:
            continue
        assert value is not None
        os.environ[key] = value
        loaded = True

    return loaded
