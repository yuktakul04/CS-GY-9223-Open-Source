"""SQLite storage for bot-observed Telegram chats, messages, and auth sessions."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from time import time

from chat_client_api import Channel, Message

_DEFAULT_STORE_PATH = ".data/chat_client.sqlite3"


def _store_path_from_env() -> str:
    raw = os.getenv("CHAT_CLIENT_STORE_PATH", _DEFAULT_STORE_PATH)
    stripped = (raw or "").strip()
    return stripped or _DEFAULT_STORE_PATH


@dataclass(frozen=True)
class StoredMessage:
    """Normalized message captured from or sent through the Bot API."""

    message_id: str
    sender: str
    channel_id: str
    timestamp: str
    text: str


@dataclass(frozen=True)
class StoredChannel:
    """Normalized chat captured from or sent through the Bot API."""

    channel_id: str
    name: str
    channel_type: str


@dataclass(frozen=True)
class StoredOidcState:
    """OIDC state persisted between /auth/login and /auth/callback."""

    state: str
    code_verifier: str
    nonce: str
    created_at: int
    session_id: str | None = None


@dataclass(frozen=True)
class StoredAuthSession:
    """Service auth session for adapter-style clients."""

    session_id: str
    token: str | None
    telegram_id: str | None
    username: str | None
    name: str | None
    created_at: int


class BotUpdateStore:
    """Thread-safe SQLite store for bot-scoped chat state."""

    def __init__(self, *, db_path: str | None = None) -> None:
        """Initialize storage and ensure schema exists."""
        self._db_path = db_path or _store_path_from_env()
        self._lock = RLock()
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    channel_type TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    channel_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    text TEXT NOT NULL,
                    stored_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (channel_id, message_id)
                );

                CREATE TABLE IF NOT EXISTS chat_access (
                    telegram_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    PRIMARY KEY (telegram_id, channel_id)
                );

                CREATE TABLE IF NOT EXISTS oidc_states (
                    state TEXT PRIMARY KEY,
                    code_verifier TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    session_id TEXT
                );

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    session_id TEXT PRIMARY KEY,
                    token TEXT,
                    telegram_id TEXT,
                    username TEXT,
                    name TEXT,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            try:
                self._conn.execute("ALTER TABLE oidc_states ADD COLUMN session_id TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    def clear(self) -> None:
        """Clear process-local test state."""
        with self._lock, self._conn:
            self._conn.executescript(
                """
                DELETE FROM messages;
                DELETE FROM channels;
                DELETE FROM chat_access;
                DELETE FROM oidc_states;
                DELETE FROM auth_sessions;
                DELETE FROM bot_state;
                """
            )

    def upsert_channel(self, channel: StoredChannel) -> None:
        """Create or update a known bot chat."""
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO channels (channel_id, name, channel_type)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    name = excluded.name,
                    channel_type = excluded.channel_type
                """,
                (channel.channel_id, channel.name, channel.channel_type),
            )

    def add_message(self, message: StoredMessage) -> None:
        """Store a bot-observed or bot-sent message."""
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO messages
                    (channel_id, message_id, sender, timestamp, text, stored_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.channel_id,
                    message.message_id,
                    message.sender,
                    message.timestamp,
                    message.text,
                    int(time()),
                ),
            )

    def list_channels(self) -> list[Channel]:
        """Return all known channels as shared API objects."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT channel_id, name, channel_type
                FROM channels
                ORDER BY name, channel_id
                """
            ).fetchall()
        return [_channel_from_row(row) for row in rows]

    def get_channel(self, *, channel_id: str) -> Channel | None:
        """Return one known channel by ID."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT channel_id, name, channel_type
                FROM channels
                WHERE channel_id = ?
                """,
                (channel_id,),
            ).fetchone()
        return _channel_from_row(row) if row is not None else None

    def list_messages(
        self,
        *,
        channel_id: str,
        max_results: int,
        cursor: str | None = None,
    ) -> list[Message]:
        """Return recent messages for a known bot chat."""
        cursor_channel_id, cursor_message_id = _split_message_id(cursor or "")
        if cursor_channel_id is not None and cursor_channel_id != channel_id:
            return []

        with self._lock:
            if cursor_message_id:
                rows = self._conn.execute(
                    """
                    SELECT message_id, sender, channel_id, timestamp, text
                    FROM messages
                    WHERE channel_id = ?
                      AND CAST(message_id AS INTEGER) > CAST(? AS INTEGER)
                    ORDER BY CAST(message_id AS INTEGER), stored_at
                    LIMIT ?
                    """,
                    (channel_id, cursor_message_id, max_results),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT message_id, sender, channel_id, timestamp, text
                    FROM messages
                    WHERE channel_id = ?
                    ORDER BY stored_at DESC, CAST(message_id AS INTEGER) DESC
                    LIMIT ?
                    """,
                    (channel_id, max_results),
                ).fetchall()
        return [_message_from_row(row) for row in rows]

    def get_message(self, *, message_id: str) -> Message | None:
        """Return one stored message by opaque or simple message ID."""
        channel_id, telegram_message_id = _split_message_id(message_id)
        if channel_id is not None:
            return self.get_message_in_channel(
                channel_id=channel_id,
                message_id=telegram_message_id,
            )

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT message_id, sender, channel_id, timestamp, text
                FROM messages
                WHERE message_id = ?
                ORDER BY stored_at DESC
                LIMIT 2
                """,
                (telegram_message_id,),
            ).fetchall()
        if len(rows) != 1:
            return None
        return _message_from_row(rows[0])

    def get_message_in_channel(
        self,
        *,
        channel_id: str,
        message_id: str,
    ) -> Message | None:
        """Return one stored message from one channel."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT message_id, sender, channel_id, timestamp, text
                FROM messages
                WHERE channel_id = ? AND message_id = ?
                """,
                (channel_id, message_id),
            ).fetchone()
        return _message_from_row(row) if row is not None else None

    def remove_message(self, *, channel_id: str, message_id: str) -> None:
        """Remove a message from local storage if present."""
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM messages WHERE channel_id = ? AND message_id = ?",
                (channel_id, message_id),
            )

    def grant_access(self, *, telegram_id: str, channel_id: str) -> None:
        """Allow a Telegram user to access a known bot chat."""
        if not telegram_id or not channel_id:
            return
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO chat_access (telegram_id, channel_id)
                VALUES (?, ?)
                """,
                (telegram_id, channel_id),
            )

    def revoke_channel_access(self, *, channel_id: str) -> None:
        """Remove cached user access for a chat the bot left."""
        if not channel_id:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM chat_access WHERE channel_id = ?",
                (channel_id,),
            )

    def user_can_access(self, *, telegram_id: str, channel_id: str) -> bool:
        """Return whether a Telegram user may access a known bot chat."""
        if telegram_id == channel_id:
            return True
        with self._lock:
            row = self._conn.execute(
                """
                SELECT 1 FROM chat_access
                WHERE telegram_id = ? AND channel_id = ?
                """,
                (telegram_id, channel_id),
            ).fetchone()
        return row is not None

    def save_oidc_state(self, state: StoredOidcState) -> None:
        """Persist OIDC state and PKCE verifier until callback."""
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO oidc_states
                    (state, code_verifier, nonce, created_at, session_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    state.state,
                    state.code_verifier,
                    state.nonce,
                    state.created_at,
                    state.session_id,
                ),
            )

    def consume_oidc_state(
        self,
        *,
        state: str,
        ttl_seconds: int,
        now: int,
    ) -> StoredOidcState | None:
        """Load and delete an OIDC state value."""
        with self._lock, self._conn:
            row = self._conn.execute(
                """
                SELECT state, code_verifier, nonce, created_at, session_id
                FROM oidc_states
                WHERE state = ?
                """,
                (state,),
            ).fetchone()
            self._conn.execute("DELETE FROM oidc_states WHERE state = ?", (state,))
            self._conn.execute(
                "DELETE FROM oidc_states WHERE created_at < ?",
                (now - ttl_seconds,),
            )
        if row is None or int(row["created_at"]) < now - ttl_seconds:
            return None
        return StoredOidcState(
            state=str(row["state"]),
            code_verifier=str(row["code_verifier"]),
            nonce=str(row["nonce"]),
            created_at=int(row["created_at"]),
            session_id=str(row["session_id"])
            if row["session_id"] is not None
            else None,
        )

    def create_auth_session(self, *, session_id: str, created_at: int) -> None:
        """Create a pending service auth session."""
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO auth_sessions
                    (session_id, token, telegram_id, username, name, created_at)
                VALUES (?, NULL, NULL, NULL, NULL, ?)
                """,
                (session_id, created_at),
            )

    def get_auth_session(self, *, session_id: str) -> StoredAuthSession | None:
        """Return a service auth session by ID."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT session_id, token, telegram_id, username, name, created_at
                FROM auth_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredAuthSession(
            session_id=str(row["session_id"]),
            token=str(row["token"]) if row["token"] is not None else None,
            telegram_id=(
                str(row["telegram_id"]) if row["telegram_id"] is not None else None
            ),
            username=str(row["username"]) if row["username"] is not None else None,
            name=str(row["name"]) if row["name"] is not None else None,
            created_at=int(row["created_at"]),
        )

    def authenticate_session(
        self,
        *,
        session_id: str,
        token: str,
        claims: dict[str, str],
    ) -> StoredAuthSession | None:
        """Attach local auth claims to a pending service auth session."""
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE auth_sessions
                SET token = ?, telegram_id = ?, username = ?, name = ?
                WHERE session_id = ?
                """,
                (
                    token,
                    claims.get("telegram_id"),
                    claims.get("username"),
                    claims.get("name"),
                    session_id,
                ),
            )
        return self.get_auth_session(session_id=session_id)

    def delete_auth_session(self, *, session_id: str) -> None:
        """Delete a service auth session."""
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM auth_sessions WHERE session_id = ?",
                (session_id,),
            )

    def token_for_session(self, *, session_id: str) -> str | None:
        """Return the local Bearer token stored for an authenticated session."""
        session = self.get_auth_session(session_id=session_id)
        if session is None:
            return None
        return session.token

    def get_int_state(self, *, key: str) -> int | None:
        """Return an integer bot state value."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM bot_state WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        try:
            return int(row["value"])
        except ValueError:
            return None

    def set_int_state(self, *, key: str, value: int) -> None:
        """Persist an integer bot state value."""
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO bot_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value)),
            )


_STORE: BotUpdateStore | None = None
_STORE_PATH: str | None = None


def get_store() -> BotUpdateStore:
    """Return the configured bot update store."""
    global _STORE, _STORE_PATH  # noqa: PLW0603
    path = _store_path_from_env()
    if _STORE is None or path != _STORE_PATH:
        _STORE = BotUpdateStore(db_path=path)
        _STORE_PATH = path
    return _STORE


def channel_from_chat(chat: dict[str, object]) -> StoredChannel:
    """Normalize a Bot API chat object."""
    chat_id = str(chat.get("id", ""))
    title = chat.get("title") or chat.get("username") or chat.get("first_name")
    return StoredChannel(
        channel_id=chat_id,
        name=str(title or chat_id),
        channel_type=str(chat.get("type") or "unknown"),
    )


def message_from_bot_api(raw_message: dict[str, object]) -> StoredMessage:
    """Normalize a Bot API message object."""
    chat = _as_dict(raw_message.get("chat"))
    sender = _as_dict(raw_message.get("from"))
    sender_chat = _as_dict(raw_message.get("sender_chat"))
    timestamp_raw = raw_message.get("date")
    timestamp = (
        datetime.fromtimestamp(timestamp_raw, tz=UTC).isoformat()
        if isinstance(timestamp_raw, int)
        else datetime.now(tz=UTC).isoformat()
    )
    return StoredMessage(
        message_id=str(raw_message.get("message_id", "")),
        sender=str(sender.get("id") or sender_chat.get("id") or chat.get("id") or ""),
        channel_id=str(chat.get("id", "")),
        timestamp=timestamp,
        text=str(raw_message.get("text") or raw_message.get("caption") or ""),
    )


def record_bot_api_message(raw_message: dict[str, object]) -> StoredMessage:
    """Record a raw Bot API message and return its normalized form."""
    chat = _as_dict(raw_message.get("chat"))
    channel = channel_from_chat(chat)
    message = message_from_bot_api(raw_message)
    store = get_store()
    store.upsert_channel(channel)
    store.add_message(message)
    store.grant_access(telegram_id=message.sender, channel_id=message.channel_id)
    return message


def record_update(update: dict[str, object]) -> StoredMessage | None:
    """Record supported Bot API update payloads."""
    member_update = update.get("my_chat_member")
    if isinstance(member_update, dict):
        record_chat_member_update(member_update)
        return None

    raw_message = (
        update.get("message")
        or update.get("edited_message")
        or update.get("channel_post")
        or update.get("edited_channel_post")
    )
    if not isinstance(raw_message, dict):
        return None
    return record_bot_api_message(raw_message)


def record_chat_member_update(raw_update: dict[str, object]) -> None:
    """Record a chat surfaced by a bot membership update."""
    new_member = _as_dict(raw_update.get("new_chat_member"))
    chat = _as_dict(raw_update.get("chat"))
    if new_member.get("status") in {"left", "kicked"}:
        get_store().revoke_channel_access(channel_id=str(chat.get("id") or ""))
        return

    if not chat:
        return

    actor = _as_dict(raw_update.get("from"))
    store = get_store()
    channel = channel_from_chat(chat)
    store.upsert_channel(channel)
    store.grant_access(
        telegram_id=str(actor.get("id") or ""),
        channel_id=channel.channel_id,
    )


def _channel_from_row(row: sqlite3.Row) -> Channel:
    return Channel(
        channel_id=str(row["channel_id"]),
        name=str(row["name"]),
        channel_type=str(row["channel_type"]),
    )


def _message_from_row(row: sqlite3.Row) -> Message:
    channel_id = str(row["channel_id"])
    provider_message_id = str(row["message_id"])
    return Message(
        message_id=f"{channel_id}:{provider_message_id}",
        channel=channel_id,
        text=str(row["text"]),
        sender=str(row["sender"]),
        timestamp=_parse_timestamp(row["timestamp"]),
    )


def _parse_timestamp(value: object) -> datetime:
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(tz=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _split_message_id(message_id: str) -> tuple[str | None, str]:
    if ":" not in message_id:
        return None, message_id
    channel_id, telegram_message_id = message_id.split(":", 1)
    return channel_id, telegram_message_id
