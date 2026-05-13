"""Telegram OpenID Connect helpers."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from os import getenv
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from telegram_client_impl.store import StoredOidcState, get_store


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
class OidcConfig:
    """Configuration for Telegram OIDC and local app sessions."""

    client_id: str | None
    client_secret: str | None
    service_base_url: str
    app_session_secret: str | None
    bot_token: str | None = None
    app_session_ttl_seconds: int = 3600
    authorization_endpoint: str = "https://oauth.telegram.org/auth"
    token_endpoint: str = "https://oauth.telegram.org/token"  # noqa: S105
    jwks_uri: str = "https://oauth.telegram.org/.well-known/jwks.json"
    issuer: str = "https://oauth.telegram.org"

    @classmethod
    def from_env(cls) -> OidcConfig:
        """Create config from environment variables."""
        bot_token = _env_strip("TELEGRAM_BOT_TOKEN")
        return cls(
            client_id=_env_strip("TELEGRAM_OIDC_CLIENT_ID")
            or _client_id_from_bot_token(bot_token),
            client_secret=_env_strip("TELEGRAM_OIDC_CLIENT_SECRET"),
            service_base_url=_env_strip_default(
                "SERVICE_BASE_URL",
                "http://localhost:8000",
            ),
            app_session_secret=_env_strip("APP_SESSION_SECRET") or bot_token,
            bot_token=bot_token,
            app_session_ttl_seconds=int(getenv("APP_SESSION_TTL_SECONDS", "3600")),
            authorization_endpoint=_env_strip_default(
                "TELEGRAM_OIDC_AUTHORIZATION_ENDPOINT",
                "https://oauth.telegram.org/auth",
            ),
            token_endpoint=_env_strip_default(
                "TELEGRAM_OIDC_TOKEN_ENDPOINT",
                "https://oauth.telegram.org/token",
            ),
            jwks_uri=_env_strip_default(
                "TELEGRAM_OIDC_JWKS_URI",
                "https://oauth.telegram.org/.well-known/jwks.json",
            ),
            issuer=_env_strip_default(
                "TELEGRAM_OIDC_ISSUER",
                "https://oauth.telegram.org",
            ),
        )


_STATE_TTL_SECONDS = 300
_LOGIN_LIBRARY_VERIFIER = "telegram-login-library"


def begin_login(
    config: OidcConfig,
    *,
    session_id: str | None = None,
) -> tuple[str, str]:
    """Create a Telegram OIDC authorization URL and CSRF state."""
    _require_oidc_config(config)
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    get_store().save_oidc_state(
        StoredOidcState(
            state=state,
            code_verifier=code_verifier,
            nonce=nonce,
            created_at=int(time.time()),
            session_id=session_id,
        )
    )
    challenge = _pkce_challenge(code_verifier)
    params = {
        "client_id": config.client_id,
        "redirect_uri": _callback_url(config),
        "origin": config.service_base_url.rstrip("/"),
        "response_type": "code",
        "scope": "openid profile telegram:bot_access",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{config.authorization_endpoint}?{urlencode(params)}", state


def begin_login_library(
    config: OidcConfig,
    *,
    session_id: str | None = None,
) -> tuple[str, str]:
    """Create nonce data for Telegram.Login JavaScript library auth."""
    _require_client_id(config)
    nonce = secrets.token_urlsafe(32)
    get_store().save_oidc_state(
        StoredOidcState(
            state=nonce,
            code_verifier=_LOGIN_LIBRARY_VERIFIER,
            nonce=nonce,
            created_at=int(time.time()),
            session_id=session_id,
        )
    )
    return str(config.client_id), nonce


def complete_login_library(
    *,
    config: OidcConfig,
    id_token: str,
    nonce: str,
) -> tuple[str, str | None]:
    """Verify a Telegram.Login id_token and issue a local Bearer token."""
    _require_client_id(config)
    pending = get_store().consume_oidc_state(
        state=nonce,
        ttl_seconds=_STATE_TTL_SECONDS,
        now=int(time.time()),
    )
    if pending is None:
        msg = "Invalid or expired Telegram Login nonce"
        raise ValueError(msg)
    claims = verify_id_token(config=config, id_token=id_token, nonce=pending.nonce)
    return issue_app_token(config=config, claims=claims), pending.session_id


def complete_login(
    *, config: OidcConfig, code: str, state: str
) -> tuple[str, str | None]:
    """Exchange the OIDC code and issue a local app Bearer token."""
    _require_oidc_config(config)
    pending = get_store().consume_oidc_state(
        state=state,
        ttl_seconds=_STATE_TTL_SECONDS,
        now=int(time.time()),
    )
    if pending is None:
        msg = "Invalid or expired OAuth state"
        raise ValueError(msg)

    token_payload = _exchange_code(
        config=config,
        code=code,
        code_verifier=pending.code_verifier,
    )
    id_token = token_payload.get("id_token")
    if not isinstance(id_token, str):
        msg = "Telegram token response did not include id_token"
        raise TypeError(msg)
    claims = verify_id_token(config=config, id_token=id_token, nonce=pending.nonce)
    return issue_app_token(config=config, claims=claims), pending.session_id


def complete_telegram_hash_login(
    *,
    config: OidcConfig,
    auth_result: str,
    state: str | None,
    fallback_session_id: str | None = None,
) -> tuple[str, str | None]:
    """Verify Telegram's hash-based login result and issue a local token."""
    if not state:
        msg = "Missing Telegram login state"
        raise ValueError(msg)
    pending = get_store().consume_oidc_state(
        state=state,
        ttl_seconds=_STATE_TTL_SECONDS,
        now=int(time.time()),
    )
    if pending is None:
        msg = "Invalid or expired Telegram login state"
        raise ValueError(msg)
    claims = verify_telegram_hash_login(config=config, auth_result=auth_result)
    session_id = pending.session_id or _known_session_id(fallback_session_id)
    return issue_app_token(config=config, claims=claims), session_id


def verify_telegram_hash_login(
    *,
    config: OidcConfig,
    auth_result: str,
) -> dict[str, Any]:
    """Validate signed Telegram Login Widget data from tgAuthResult."""
    if not config.bot_token:
        msg = "TELEGRAM_BOT_TOKEN is required"
        raise ValueError(msg)
    raw_payload = _decode_b64(auth_result)
    payload = json.loads(raw_payload)
    if not isinstance(payload, dict):
        msg = "Telegram login payload is not an object"
        raise TypeError(msg)

    received_hash = payload.get("hash")
    if not isinstance(received_hash, str):
        msg = "Telegram login payload is missing hash"
        raise TypeError(msg)
    data_check_string = "\n".join(
        f"{key}={payload[key]}"
        for key in sorted(payload)
        if key != "hash" and payload[key] is not None
    )
    secret_key = hashlib.sha256(config.bot_token.encode()).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        msg = "Telegram login hash mismatch"
        raise ValueError(msg)

    auth_date = payload.get("auth_date")
    if not isinstance(auth_date, int) or auth_date < int(time.time()) - 86400:
        msg = "Telegram login payload is expired"
        raise ValueError(msg)

    telegram_id = payload.get("id")
    if not isinstance(telegram_id, int):
        msg = "Telegram login payload is missing user id"
        raise TypeError(msg)
    first_name = str(payload.get("first_name") or "")
    last_name = str(payload.get("last_name") or "")
    return {
        "id": telegram_id,
        "sub": str(telegram_id),
        "preferred_username": payload.get("username"),
        "name": " ".join(part for part in (first_name, last_name) if part),
        "picture": payload.get("photo_url"),
    }


def _known_session_id(session_id: str | None) -> str | None:
    if session_id is None:
        return None
    if get_store().get_auth_session(session_id=session_id) is None:
        return None
    return session_id


def verify_id_token(
    *,
    config: OidcConfig,
    id_token: str,
    nonce: str,
) -> dict[str, Any]:
    """Validate a Telegram OIDC id_token and return claims."""
    jwk_client = jwt.PyJWKClient(config.jwks_uri)
    signing_key = jwk_client.get_signing_key_from_jwt(id_token)
    decoded = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=config.client_id,
        issuer=config.issuer,
    )
    if not isinstance(decoded, dict):
        msg = "Telegram id_token decoded to a non-object payload"
        raise TypeError(msg)
    if decoded.get("nonce") != nonce:
        msg = "Telegram id_token nonce mismatch"
        raise ValueError(msg)
    return decoded


def issue_app_token(*, config: OidcConfig, claims: dict[str, Any]) -> str:
    """Issue a compact HMAC-signed token for this service."""
    if not config.app_session_secret:
        msg = "APP_SESSION_SECRET is required"
        raise ValueError(msg)
    now = int(time.time())
    telegram_id = claims.get("id") or claims.get("sub")
    if not telegram_id:
        msg = "Telegram user id is required"
        raise ValueError(msg)
    body = {
        "telegram_id": str(telegram_id),
        "telegram_sub": str(claims.get("sub", "")),
        "username": claims.get("preferred_username"),
        "name": claims.get("name"),
        "iat": now,
        "exp": now + config.app_session_ttl_seconds,
    }
    payload = _b64(json.dumps(body, separators=(",", ":")).encode())
    signature = hmac.new(
        config.app_session_secret.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def decode_app_token(*, config: OidcConfig, token: str) -> dict[str, str] | None:
    """Validate and decode a local app Bearer token."""
    if not config.app_session_secret:
        return None
    try:
        decoded = _decode_signed_token_body(
            secret=config.app_session_secret,
            token=token,
        )
    except (binascii.Error, json.JSONDecodeError, TypeError, ValueError):
        return None
    return {str(key): str(value) for key, value in decoded.items() if value is not None}


def _decode_signed_token_body(*, secret: str, token: str) -> dict[str, Any]:
    payload, signature = token.rsplit(".", 1)
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        msg = "Bad token signature"
        raise ValueError(msg)
    decoded = json.loads(_decode_b64(payload))
    if not isinstance(decoded, dict):
        msg = "Token payload is not an object"
        raise TypeError(msg)
    exp = decoded.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        msg = "Token is expired"
        raise ValueError(msg)
    return decoded


def _exchange_code(
    *,
    config: OidcConfig,
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    if config.client_id is None or config.client_secret is None:
        msg = "TELEGRAM_OIDC_CLIENT_ID and TELEGRAM_OIDC_CLIENT_SECRET are required"
        raise ValueError(msg)
    response = httpx.post(
        config.token_endpoint,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _callback_url(config),
            "client_id": config.client_id,
            "code_verifier": code_verifier,
        },
        auth=(config.client_id, config.client_secret),
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        msg = "Telegram token endpoint returned a non-object payload"
        raise TypeError(msg)
    return payload


def _callback_url(config: OidcConfig) -> str:
    return f"{config.service_base_url.rstrip('/')}/auth/callback"


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return _b64(digest)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode_b64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _require_oidc_config(config: OidcConfig) -> None:
    _require_client_id(config)
    if not config.client_secret:
        msg = "TELEGRAM_OIDC_CLIENT_ID and TELEGRAM_OIDC_CLIENT_SECRET are required"
        raise ValueError(msg)


def _require_client_id(config: OidcConfig) -> None:
    if not config.client_id:
        msg = (
            "TELEGRAM_BOT_TOKEN with numeric bot id or "
            "TELEGRAM_OIDC_CLIENT_ID is required"
        )
        raise ValueError(msg)


def _client_id_from_bot_token(bot_token: str | None) -> str | None:
    if not bot_token:
        return None
    bot_id, separator, _secret = bot_token.partition(":")
    if not separator or not bot_id.isdecimal():
        return None
    return bot_id
