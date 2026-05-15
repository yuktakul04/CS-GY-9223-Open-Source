"""CloudWatch logging transport for telemetry events."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from functools import lru_cache

import boto3
import watchtower
from botocore.exceptions import BotoCoreError

_LOGGER_NAME = "chat_client_service.telemetry"
_DEFAULT_LOG_GROUP = "chat-client-service-logs"


@dataclass(frozen=True)
class CloudWatchConfig:
    """Configuration for telemetry log transport."""

    enabled: bool
    log_group_name: str
    region_name: str | None
    stream_name: str | None
    use_queues: bool
    send_interval: int


def _env_flag(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def load_cloudwatch_config() -> CloudWatchConfig:
    """Load transport config from environment variables."""
    stream_name = os.getenv("CHAT_CLIENT_CLOUDWATCH_STREAM_NAME") or None
    region_name = (
        os.getenv("CHAT_CLIENT_CLOUDWATCH_REGION")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or None
    )
    return CloudWatchConfig(
        enabled=_env_flag("CHAT_CLIENT_CLOUDWATCH_ENABLED"),
        log_group_name=os.getenv(
            "CHAT_CLIENT_CLOUDWATCH_LOG_GROUP",
            _DEFAULT_LOG_GROUP,
        ),
        region_name=region_name,
        stream_name=stream_name,
        use_queues=_env_flag("CHAT_CLIENT_CLOUDWATCH_USE_QUEUES"),
        send_interval=int(os.getenv("CHAT_CLIENT_CLOUDWATCH_SEND_INTERVAL", "1")),
    )


def _build_stdout_handler() -> logging.Handler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def _build_cloudwatch_handler(config: CloudWatchConfig) -> logging.Handler:
    client = boto3.client("logs", region_name=config.region_name)
    if config.stream_name is None:
        return watchtower.CloudWatchLogHandler(
            boto3_client=client,
            log_group_name=config.log_group_name,
            use_queues=config.use_queues,
            send_interval=config.send_interval,
            create_log_group=False,
        )
    return watchtower.CloudWatchLogHandler(
        boto3_client=client,
        log_group_name=config.log_group_name,
        log_stream_name=config.stream_name,
        use_queues=config.use_queues,
        send_interval=config.send_interval,
        create_log_group=False,
    )


@lru_cache(maxsize=1)
def get_telemetry_logger() -> logging.Logger:
    """Return the shared telemetry logger.

    Initialised exactly once per process lifetime. If CloudWatch is
    unavailable at first call the logger falls back to stdout and stays
    there permanently — recovering CloudWatch connectivity requires a
    process restart.
    """
    config = load_cloudwatch_config()

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    if config.enabled:
        try:
            handler = _build_cloudwatch_handler(config)
        except (BotoCoreError, ValueError, TypeError):
            handler = _build_stdout_handler()
    else:
        handler = _build_stdout_handler()

    logger.addHandler(handler)
    return logger
