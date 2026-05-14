"""Tests for the Team 9 Slack ChatClient implementation."""

from __future__ import annotations

import pytest

from slack_client_impl.client import SlackClient


class _FakeWebClient:
    """Minimal Slack SDK test double."""

    def __init__(self) -> None:
        self.sent: dict[str, str] | None = None
        self.deleted: dict[str, str] | None = None

    def chat_postMessage(  # noqa: N802
        self,
        *,
        channel: str,
        text: str,
    ) -> dict[str, object]:
        self.sent = {"channel": channel, "text": text}
        return {
            "ok": True,
            "channel": channel,
            "ts": "1715200000.000100",
        }

    def conversations_list(self) -> dict[str, object]:
        return {
            "ok": True,
            "channels": [
                {"id": "C123", "name": "general", "is_private": False},
            ],
        }

    def conversations_info(self, *, channel: str) -> dict[str, object]:
        return {
            "ok": True,
            "channel": {"id": channel, "name": "general", "is_private": False},
        }

    def conversations_history(  # noqa: PLR0913
        self,
        *,
        channel: str,
        limit: int,
        cursor: str | None = None,
        latest: str | None = None,
        oldest: str | None = None,
        inclusive: bool | None = None,
    ) -> dict[str, object]:
        del limit, cursor, oldest, inclusive
        ts = latest or "1715200000.000100"
        return {
            "ok": True,
            "messages": [
                {"ts": ts, "text": "hello", "user": "U123"},
            ],
        }

    def chat_delete(self, *, channel: str, ts: str) -> dict[str, object]:
        self.deleted = {"channel": channel, "ts": ts}
        return {"ok": True}


def _client() -> tuple[SlackClient, _FakeWebClient]:
    slack = SlackClient("xoxb-test")
    fake = _FakeWebClient()
    slack.client = fake  # type: ignore[assignment]
    return slack, fake


def test_send_message_uses_slack_channel_id() -> None:
    """send_message maps Slack post response to the shared Message type."""
    slack, fake = _client()

    message = slack.send_message("C123", "hello")

    assert fake.sent == {"channel": "C123", "text": "hello"}
    assert message.message_id == "C123:1715200000.000100"
    assert message.channel == "C123"
    assert message.text == "hello"


def test_channels_map_to_shared_channel_type() -> None:
    """get_channels returns provider-neutral Channel objects."""
    slack, _fake = _client()

    channels = slack.get_channels()

    assert len(channels) == 1
    assert channels[0].channel_id == "C123"
    assert channels[0].name == "general"


def test_get_channel_maps_to_shared_channel_type() -> None:
    """get_channel returns provider-neutral Channel objects."""
    slack, _fake = _client()

    channel = slack.get_channel("C123")

    assert channel.channel_id == "C123"
    assert channel.name == "general"
    assert channel.is_private is False


def test_get_messages_maps_to_shared_message_type() -> None:
    """get_messages returns provider-neutral Message objects."""
    slack, _fake = _client()

    messages = slack.get_messages("C123")

    assert len(messages) == 1
    assert messages[0].message_id == "C123:1715200000.000100"
    assert messages[0].channel == "C123"
    assert messages[0].text == "hello"
    assert messages[0].sender == "U123"


def test_get_message_decodes_opaque_id() -> None:
    """get_message accepts the shared opaque channel_id:timestamp id."""
    slack, _fake = _client()

    message = slack.get_message("C123:1715200000.000100")

    assert message.message_id == "C123:1715200000.000100"
    assert message.channel == "C123"
    assert message.text == "hello"


def test_delete_message_decodes_opaque_id() -> None:
    """delete_message accepts the shared opaque channel_id:timestamp id."""
    slack, fake = _client()

    slack.delete_message("C123:1715200000.000100")

    assert fake.deleted == {"channel": "C123", "ts": "1715200000.000100"}


def test_invalid_message_id_fails_before_slack_call() -> None:
    """Opaque message IDs must include channel and Slack timestamp."""
    slack, _fake = _client()

    with pytest.raises(ValueError, match="Invalid message_id format"):
        slack.delete_message("1715200000.000100")


def test_create_slack_client_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory reads the Slack bot token from the environment."""
    from slack_client_impl.client import _create_slack_client

    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-env")

    slack = _create_slack_client()

    assert slack.token == "xoxb-env"


def test_create_slack_client_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory fails clearly when Slack credentials are absent."""
    from slack_client_impl.client import _create_slack_client

    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)

    with pytest.raises(ValueError, match="SLACK_BOT_TOKEN"):
        _create_slack_client()
