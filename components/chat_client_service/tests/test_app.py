"""Tests for chat_client_service FastAPI endpoints."""

import base64
import hashlib
import hmac
import json
import os
import time
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from chat_client_api import Channel, Message
from chat_client_service import oidc
from chat_client_service.app import app
from chat_client_service.config import load_environment
from chat_client_service.middleware.cloudwatch import (
    _build_cloudwatch_handler,
    load_cloudwatch_config,
)
from chat_client_service.middleware.telemetry import _build_request_metrics_event
from chat_client_service.oidc import (
    OidcConfig,
    begin_login,
    begin_login_library,
    complete_login,
    complete_login_library,
    decode_app_token,
    issue_app_token,
)
from chat_client_service.routers.auth import (
    get_current_claims,
    get_current_token,
    get_oidc_config,
)
from chat_client_service.routers.chat import get_chat_client
from chat_client_service.update_poller import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    poll_interval_seconds,
    should_start_update_poller,
)
from telegram_client_impl.errors import TelegramClientError
from telegram_client_impl.store import StoredChannel, StoredMessage, get_store

client = TestClient(app, follow_redirects=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _message_dto(*, message_id: str = "m-1") -> Message:
    return Message(
        message_id=message_id,
        sender="alice",
        channel="ch-1",
        timestamp=datetime(2026, 3, 20, tzinfo=UTC),
        text="hello",
    )


def _awaited_call_kwargs(mock_obj: Mock) -> dict[str, Any]:
    await_args = mock_obj.await_args
    assert await_args is not None
    return dict(await_args.kwargs)


def _allow_auth() -> dict[str, str]:
    return {"telegram_id": "42", "username": "alice", "name": "Alice"}


def _telegram_auth_result(*, bot_token: str, telegram_id: int = 42) -> str:
    payload = _telegram_auth_payload(bot_token=bot_token, telegram_id=telegram_id)
    return (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode(),
        )
        .rstrip(b"=")
        .decode()
    )


def _telegram_auth_payload(
    *, bot_token: str, telegram_id: int = 42
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": telegram_id,
        "first_name": "Alice",
        "username": "alice",
        "auth_date": int(time.time()),
    }
    data_check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    payload["hash"] = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    return payload


class _MembershipClient:
    """Test double with the Bot API membership-check method."""

    checked = False

    def user_can_access_channel(self, *, user_id: str, channel_id: str) -> bool:
        """Grant access only for the test user's known group."""
        self.checked = True
        return user_id == "42" and channel_id == "123"

    def get_messages(
        self,
        channel_id: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Mock]:
        """Return a message after the access check succeeds."""
        del cursor
        assert channel_id == "123"
        assert limit == 10
        msg = Mock()
        msg.id = "5"
        msg.sender = "42"
        msg.channel_id = "123"
        msg.timestamp = "2026-04-21T00:00:00Z"
        msg.text = "hello"
        return [msg]


@pytest.fixture(autouse=True)
def auth_test_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Set deterministic auth/store env for service tests."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "osshwbot")
    monkeypatch.setenv("APP_SESSION_SECRET", "app-secret")
    monkeypatch.setenv("CHAT_CLIENT_STORE_PATH", ":memory:")
    monkeypatch.delenv("TELEGRAM_UPDATE_MODE", raising=False)
    monkeypatch.delenv("CHAT_CLIENT_PROVIDER", raising=False)
    monkeypatch.delenv("CHAT_CLIENT_DEMO_API_KEY", raising=False)
    app.openapi_schema = None
    client.cookies.clear()
    get_store().clear()
    yield
    app.dependency_overrides.clear()
    app.openapi_schema = None
    client.cookies.clear()
    get_store().clear()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_endpoint() -> None:
    """Health endpoint returns 200 with expected payload."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_serves_dark_themed_swagger_ui() -> None:
    """GET /docs renders Swagger UI with the dark CSS layered on top of base."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "swagger-ui-dist@5/swagger-ui.css" in body
    assert "/static/swagger-dark.css" in body
    assert body.index("swagger-ui-dist@5/swagger-ui.css") < body.index(
        "/static/swagger-dark.css"
    ), "Dark overlay must come after base swagger-ui.css so overrides apply."
    assert "swagger-ui-bundle.js" in body
    assert 'id="swagger-ui"' in body


def test_static_swagger_dark_css_is_served() -> None:
    """The vendored Universal Dark theme CSS is reachable under /static."""
    response = client.get("/static/swagger-dark.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "--all-bg-color" in response.text
    # Upstream wraps rules in @media (prefers-color-scheme: dark), which would
    # make the theme silently disabled for users whose OS is in light mode.
    # We strip that wrapper so dark mode applies unconditionally.
    assert "@media (prefers-color-scheme: dark)" not in response.text


def test_redoc_and_openapi_schema_still_available() -> None:
    """Disabling the default /docs must not break ReDoc or the OpenAPI schema."""
    redoc_response = client.get("/redoc")
    schema_response = client.get("/openapi.json")
    assert redoc_response.status_code == 200
    assert schema_response.status_code == 200
    assert schema_response.json()["info"]["title"] == "Chat Client Service"


def test_openapi_hides_html_pages_and_declares_all_auth_schemes() -> None:
    """HTML-only routes stay out of /docs; every supported auth path is advertised."""
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"].keys())
    # HTML pages serve browser UI, not API endpoints; hide them from Swagger.
    assert "/" not in paths
    assert "/auth/login" not in paths
    # Real API endpoints remain listed.
    assert "/chat/messages" in paths
    assert "/auth/me" in paths
    # All three credential sources accepted by get_current_token must be
    # declared so Swagger UI's Authorize dialog offers each of them.
    schemes = schema["components"]["securitySchemes"]
    assert schemes["HTTPBearer"] == {"type": "http", "scheme": "bearer"}
    assert schemes["APIKeyHeader"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Session-ID",
    }
    assert schemes["DemoAPIKeyHeader"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Demo-API-Key",
    }
    assert schemes["APIKeyCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "chat_client_session",
    }
    # Protected chat routes must advertise every scheme so Try-It-Out
    # works regardless of which credential the user pastes into Authorize.
    chat_security = schema["paths"]["/chat/messages"]["get"]["security"]
    scheme_names = {next(iter(entry.keys())) for entry in chat_security}
    assert scheme_names == {
        "HTTPBearer",
        "APIKeyHeader",
        "DemoAPIKeyHeader",
        "APIKeyCookie",
    }


def test_slack_openapi_prefers_demo_key_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slack provider mode presents the demo key path instead of Telegram sessions."""
    monkeypatch.setenv("CHAT_CLIENT_PROVIDER", "slack")
    monkeypatch.setenv("CHAT_CLIENT_DEMO_API_KEY", "demo-secret")
    app.openapi_schema = None

    schema = client.get("/openapi.json").json()

    assert schema["components"]["securitySchemes"] == {
        "DemoAPIKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Demo-API-Key",
        }
    }
    assert schema["paths"]["/chat/messages"]["get"]["security"] == [
        {"DemoAPIKeyHeader": []}
    ]
    assert schema["paths"]["/auth/me"]["get"]["security"] == [{"DemoAPIKeyHeader": []}]


def test_health_request_emits_success_telemetry() -> None:
    """GET /health records latency and marks the request as successful."""
    with patch(
        "chat_client_service.middleware.telemetry._publish_request_metrics"
    ) as publish_metrics:
        response = client.get("/health")

    assert response.status_code == 200
    publish_metrics.assert_called_once()
    kwargs = _awaited_call_kwargs(publish_metrics)
    assert kwargs["service"] == "chat_client_service"
    assert kwargs["endpoint"] == "/health"
    assert kwargs["status_code"] == 200
    assert kwargs["success"] == 1
    assert kwargs["failure"] == 0
    assert kwargs["latency_ms"] >= 0


def test_parameterized_route_uses_template_endpoint_dimension(
    mock_chat_client: Mock,
) -> None:
    """Telemetry uses the FastAPI route template instead of the raw request path."""
    mock_chat_client.get_message.return_value = _message_dto(message_id="m-1")

    with patch(
        "chat_client_service.middleware.telemetry._publish_request_metrics"
    ) as publish_metrics:
        response = client.get("/chat/messages/m-1")

    assert response.status_code == 200
    kwargs = _awaited_call_kwargs(publish_metrics)
    assert kwargs["endpoint"] == "/chat/messages/{message_id}"
    assert kwargs["status_code"] == 200
    assert kwargs["success"] == 1
    assert kwargs["failure"] == 0


def test_failure_response_emits_failure_telemetry(mock_chat_client: Mock) -> None:
    """HTTP responses with status >= 400 are recorded as failures."""
    mock_chat_client.get_channels.side_effect = RuntimeError("Telegram error")

    with patch(
        "chat_client_service.middleware.telemetry._publish_request_metrics"
    ) as publish_metrics:
        response = client.get("/chat/channels")

    assert response.status_code == 500
    kwargs = _awaited_call_kwargs(publish_metrics)
    assert kwargs["endpoint"] == "/chat/channels"
    assert kwargs["status_code"] == 500
    assert kwargs["success"] == 0
    assert kwargs["failure"] == 1


def test_unhandled_exception_still_emits_failure_telemetry() -> None:
    """Unhandled exceptions still publish telemetry before FastAPI returns 500."""
    router = APIRouter()

    @router.get("/telemetry-boom")
    def telemetry_boom() -> None:
        message = "boom"
        raise RuntimeError(message)

    app.include_router(router)
    try:
        boom_client = TestClient(
            app,
            follow_redirects=False,
            raise_server_exceptions=False,
        )
        with patch(
            "chat_client_service.middleware.telemetry._publish_request_metrics"
        ) as publish_metrics:
            response = boom_client.get("/telemetry-boom")
    finally:
        app.router.routes.pop()

    assert response.status_code == 500
    kwargs = _awaited_call_kwargs(publish_metrics)
    assert kwargs["endpoint"] == "/telemetry-boom"
    assert kwargs["status_code"] == 500
    assert kwargs["success"] == 0
    assert kwargs["failure"] == 1


def test_build_request_metrics_event_uses_emf_shape() -> None:
    """Telemetry events keep the EMF structure CloudWatch metric extraction expects."""
    event = _build_request_metrics_event(
        service="chat_client_service",
        endpoint="/health",
        latency_ms=12.5,
        status_code=200,
        success=1,
        failure=0,
    )

    assert event["Service"] == "chat_client_service"
    assert event["Endpoint"] == "/health"
    assert event["RequestLatency"] == 12.5
    assert event["SuccessRate"] == 1
    assert event["FailureRate"] == 0

    metadata = cast("dict[str, object]", event["_aws"])
    cloudwatch_metrics = cast(
        "list[dict[str, object]]",
        metadata["CloudWatchMetrics"],
    )
    assert metadata["CloudWatchMetrics"] == [
        {
            "Dimensions": [["Service", "Endpoint"]],
            "Metrics": [
                {"Name": "RequestLatency", "Unit": "Milliseconds"},
                {"Name": "SuccessRate", "Unit": "Count"},
                {"Name": "FailureRate", "Unit": "Count"},
            ],
            "Namespace": "OSPSD/HW3",
        }
    ]
    assert cloudwatch_metrics[0]["Namespace"] == "OSPSD/HW3"
    assert isinstance(metadata["Timestamp"], int)


def test_cloudwatch_config_defaults_to_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """CloudWatch is disabled unless explicitly enabled by env var."""
    monkeypatch.delenv("CHAT_CLIENT_CLOUDWATCH_ENABLED", raising=False)
    monkeypatch.delenv("CHAT_CLIENT_CLOUDWATCH_LOG_GROUP", raising=False)
    monkeypatch.delenv("CHAT_CLIENT_CLOUDWATCH_STREAM_NAME", raising=False)
    monkeypatch.delenv("CHAT_CLIENT_CLOUDWATCH_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    config = load_cloudwatch_config()

    assert config.enabled is False
    assert config.log_group_name == "chat-client-service-logs"
    assert config.region_name is None
    assert config.stream_name is None


def test_cloudwatch_config_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """CloudWatch config should resolve the explicit toggle and region settings."""
    monkeypatch.setenv("CHAT_CLIENT_CLOUDWATCH_ENABLED", "true")
    monkeypatch.setenv("CHAT_CLIENT_CLOUDWATCH_LOG_GROUP", "chat-client-service-logs")
    monkeypatch.setenv("CHAT_CLIENT_CLOUDWATCH_STREAM_NAME", "local-dev")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    config = load_cloudwatch_config()

    assert config.enabled is True
    assert config.log_group_name == "chat-client-service-logs"
    assert config.stream_name == "local-dev"
    assert config.region_name == "us-east-1"
    assert config.use_queues is False
    assert config.send_interval == 1


def test_build_cloudwatch_handler_disables_buffering_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local CloudWatch publishing should not wait on the default 60s queue flush."""
    monkeypatch.setenv("CHAT_CLIENT_CLOUDWATCH_ENABLED", "true")
    monkeypatch.setenv("CHAT_CLIENT_CLOUDWATCH_LOG_GROUP", "chat-client-service-logs")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    captured: dict[str, Any] = {}

    class DummyClient:
        pass

    def fake_boto3_client(
        service_name: str,
        region_name: str | None = None,
    ) -> DummyClient:
        assert service_name == "logs"
        assert region_name == "us-east-1"
        return DummyClient()

    class DummyHandler:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        "chat_client_service.middleware.cloudwatch.boto3.client",
        fake_boto3_client,
    )
    monkeypatch.setattr(
        "chat_client_service.middleware.cloudwatch.watchtower.CloudWatchLogHandler",
        DummyHandler,
    )

    handler = _build_cloudwatch_handler(load_cloudwatch_config())

    assert isinstance(handler, DummyHandler)
    assert captured["use_queues"] is False
    assert captured["send_interval"] == 1


def test_load_environment_reads_dotenv_without_overriding_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local env loading should populate missing values but preserve exported ones."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        (
            "CHAT_CLIENT_CLOUDWATCH_ENABLED=true\n"
            "CHAT_CLIENT_CLOUDWATCH_LOG_GROUP=chat-client-service-logs\n"
            "AWS_DEFAULT_REGION=us-east-1\n"
            "AWS_ACCESS_KEY_ID=file-key\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("CHAT_CLIENT_CLOUDWATCH_ENABLED", raising=False)
    monkeypatch.delenv("CHAT_CLIENT_CLOUDWATCH_LOG_GROUP", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "exported-key")

    load_environment(env_file)

    assert os.getenv("CHAT_CLIENT_CLOUDWATCH_ENABLED") == "true"
    assert os.getenv("CHAT_CLIENT_CLOUDWATCH_LOG_GROUP") == "chat-client-service-logs"
    assert os.getenv("AWS_DEFAULT_REGION") == "us-east-1"
    assert os.getenv("AWS_ACCESS_KEY_ID") == "exported-key"


# ---------------------------------------------------------------------------
# Auth — Telegram OIDC + session flow
# ---------------------------------------------------------------------------


_FAKE_USER = {
    "id": 123456,
    "first_name": "Alice",
    "auth_date": 1700000000,
    "hash": "fakehash",
}


def test_update_poller_env_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Polling mode is explicit and has a safe interval fallback."""
    monkeypatch.delenv("TELEGRAM_UPDATE_MODE", raising=False)
    monkeypatch.delenv("TELEGRAM_POLL_INTERVAL_SECONDS", raising=False)
    assert should_start_update_poller() is False
    assert poll_interval_seconds() == DEFAULT_POLL_INTERVAL_SECONDS

    monkeypatch.setenv("TELEGRAM_UPDATE_MODE", "polling")
    monkeypatch.setenv("TELEGRAM_POLL_INTERVAL_SECONDS", "0")
    assert should_start_update_poller() is True
    assert poll_interval_seconds() == 0.5

    monkeypatch.setenv("TELEGRAM_POLL_INTERVAL_SECONDS", "bad")
    assert poll_interval_seconds() == DEFAULT_POLL_INTERVAL_SECONDS


def test_auth_login_serves_telegram_login_page() -> None:
    """Login page fallback works when no OIDC client secret is configured."""
    config = OidcConfig(
        client_id="123",
        client_secret=None,
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    app.dependency_overrides[get_oidc_config] = lambda: config

    response = client.get("/auth/login")

    assert response.status_code == 200
    assert "https://oauth.telegram.org/js/telegram-login.js?3" in response.text
    assert "Telegram.Login.init" in response.text
    assert "authUrl.searchParams.set" in response.text
    assert "sessionStorage.setItem" in response.text
    assert "localStorage.setItem" in response.text
    assert "/auth/telegram-login" in response.text
    assert "telegramAuthUrl" in response.text
    assert 'data.error === "missing id_token"' in response.text
    assert 'authUrl.searchParams.set("redirect_uri", origin + "/")' in response.text
    assert 'const origin = "https://example.com";' in response.text
    assert 'request_access: ["write"]' in response.text
    assert 'window.addEventListener("message"' in response.text
    assert "telegram-auth-complete" in response.text
    assert "Browser session authenticated. Return to your API client." in response.text
    assert "https://t.me/osshwbot?start=chatclient" in response.text
    assert "Open @osshwbot in Telegram" in response.text
    assert "If this is your first time using this bot, open" in response.text
    assert "press Start before sending messages." in response.text
    assert 'id="telegram-login"' in response.text
    assert "window.close()" not in response.text
    assert 'sessionStorage.removeItem("telegram_auth_session_id")' in response.text
    assert "async function responseBody(response)" in response.text
    assert "Login failed. Please retry." in response.text


def test_auth_login_prefers_oidc_code_flow_when_secret_configured() -> None:
    """Default login uses Telegram OIDC Authorization Code Flow when available."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    app.dependency_overrides[get_oidc_config] = lambda: config

    response = client.get("/auth/login")

    assert response.status_code == 200
    assert "sessionStorage.setItem" in response.text
    assert "localStorage.setItem" in response.text
    assert "window.location.replace" in response.text
    assert "https://oauth.telegram.org/auth?" in response.text
    assert "response_type=code" in response.text
    assert "origin=https%3A%2F%2Fexample.com" in response.text


def test_auth_login_code_flow_redirects_to_telegram_oidc() -> None:
    """Explicit code flow starts the Telegram OIDC Authorization Code Flow."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    app.dependency_overrides[get_oidc_config] = lambda: config

    response = client.get(
        "/auth/login",
        params={"flow": "code"},
    )

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://oauth.telegram.org/auth?")
    assert "response_type=code" in location
    assert "origin=https%3A%2F%2Fexample.com" in location
    assert "code_challenge_method=S256" in location


def test_auth_login_config_supports_telegram_login_library() -> None:
    """Login config returns the client_id and nonce used by Telegram.Login.init."""
    config = OidcConfig(
        client_id="123",
        client_secret=None,
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    app.dependency_overrides[get_oidc_config] = lambda: config

    response = client.get("/auth/login/config")

    assert response.status_code == 200
    assert response.json()["client_id"] == "123"
    assert response.json()["origin"] == "https://example.com"
    assert response.json()["nonce"]
    assert response.json()["bot_username"] == "osshwbot"
    assert response.json()["bot_start_url"] == (
        "https://t.me/osshwbot?start=chatclient"
    )


def test_auth_callback_requires_code_and_state() -> None:
    """GET /auth/callback requires the OIDC code and state query parameters."""
    response = client.get("/auth/callback")
    assert response.status_code == 422


def test_root_serves_telegram_fragment_handler() -> None:
    """Root page handles tgAuthResult fragments returned by Telegram."""
    response = client.get("/")

    assert response.status_code == 200
    assert "tgAuthResult" in response.text
    assert "/auth/telegram-login" in response.text
    assert "sessionStorage.getItem" in response.text
    assert "localStorage.getItem" in response.text
    assert "window.opener.postMessage" in response.text
    assert 'type: "telegram-auth-complete"' in response.text
    assert "You can close this tab and return to your API client." in response.text
    assert "https://t.me/osshwbot?start=chatclient" in response.text
    assert "Open @osshwbot in Telegram" in response.text
    assert "If this is your first time using this bot, open" in response.text
    assert "press Start before sending messages." in response.text
    assert "window.close()" not in response.text
    assert "async function responseBody(response)" in response.text
    assert "Login failed. Please retry." in response.text


def test_telegram_hash_login_authenticates_session() -> None:
    """Hash login result verifies Telegram payload and authenticates session."""
    bot_token = "123456:bot-secret"
    config = OidcConfig(
        client_id="123456",
        client_secret="bot-secret",
        service_base_url="http://testserver",
        app_session_secret="app-secret",
        bot_token=bot_token,
    )
    app.dependency_overrides[get_oidc_config] = lambda: config

    session_response = client.post("/auth/sessions")
    session_payload = session_response.json()
    session_id = session_payload["session_id"]
    login_response = client.get(
        "/auth/login",
        params={"session_id": session_id},
    )
    state = login_response.text.split(
        'sessionStorage.setItem("telegram_auth_state", "',
        1,
    )[1].split('"', 1)[0]
    client.cookies.clear()
    auth_result = _telegram_auth_result(bot_token=bot_token)
    callback_response = client.post(
        "/auth/telegram-login",
        json={
            "auth_result": auth_result,
            "state": state,
            "session_id": session_id,
        },
    )
    status_response = client.get(f"/auth/sessions/{session_id}")

    assert login_response.status_code == 200
    assert session_payload["bot_username"] == "osshwbot"
    assert session_payload["bot_start_url"] == (
        "https://t.me/osshwbot?start=chatclient"
    )
    assert "telegram_auth_session_id" in login_response.text
    assert "telegram_auth_state" in login_response.headers["set-cookie"]
    assert "telegram_auth_session_id" in login_response.headers["set-cookie"]
    assert callback_response.status_code == 200
    assert status_response.json()["authenticated"] is True
    assert status_response.json()["telegram_id"] == "42"


def test_auth_verify_legacy_callback_issues_local_token() -> None:
    """Legacy /auth/verify remains available for parent-branch compatibility."""
    bot_token = "123456:bot-secret"
    config = OidcConfig(
        client_id="123456",
        client_secret="bot-secret",
        service_base_url="http://testserver",
        app_session_secret="app-secret",
        bot_token=bot_token,
    )
    app.dependency_overrides[get_oidc_config] = lambda: config

    _client_id, state = begin_login_library(config)
    client.cookies.set("telegram_auth_state", state)

    response = client.post(
        "/auth/verify",
        json=_telegram_auth_payload(bot_token=bot_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["detail"] == "Authenticated successfully."
    assert body["state"] == state
    assert body["access_token"] is not None
    assert body["token_type"] == "bearer"


def test_auth_verify_legacy_rejects_missing_cookie() -> None:
    """Legacy /auth/verify still requires the state cookie."""
    bot_token = "123456:bot-secret"
    config = OidcConfig(
        client_id="123456",
        client_secret="bot-secret",
        service_base_url="http://testserver",
        app_session_secret="app-secret",
        bot_token=bot_token,
    )
    app.dependency_overrides[get_oidc_config] = lambda: config
    client.cookies.clear()

    response = client.post(
        "/auth/verify",
        json=_telegram_auth_payload(bot_token=bot_token),
    )

    assert response.status_code == 400
    assert "cookie" in response.json()["detail"].lower()


def test_auth_callback_issues_local_token() -> None:
    """Callback exchanges the OIDC code and returns a service Bearer token."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    app.dependency_overrides[get_oidc_config] = lambda: config
    token = issue_app_token(
        config=config,
        claims={
            "id": 42,
            "sub": "oidc-sub",
            "preferred_username": "alice",
            "name": "Alice",
        },
    )

    with patch(
        "chat_client_service.routers.auth.complete_login",
        return_value=(token, None),
    ):
        response = client.get("/auth/callback", params={"code": "c", "state": "s"})

    assert response.status_code == 200
    assert response.json() == {"access_token": token, "token_type": "bearer"}
    assert get_store().user_can_access(telegram_id="42", channel_id="42") is True


def test_auth_callback_rejects_partial_oidc_query() -> None:
    """OIDC callback requires both code and state when query params are present."""
    response = client.get("/auth/callback", params={"code": "c"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "missing"


def test_auth_login_library_callback_issues_local_token() -> None:
    """POST callback verifies Telegram.Login id_token and returns a Bearer token."""
    config = OidcConfig(
        client_id="123",
        client_secret=None,
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    app.dependency_overrides[get_oidc_config] = lambda: config
    _client_id, nonce = begin_login_library(config)

    with patch(
        "chat_client_service.oidc.verify_id_token",
        return_value={
            "id": 42,
            "sub": "oidc-sub",
            "preferred_username": "alice",
            "name": "Alice",
        },
    ):
        response = client.post(
            "/auth/callback",
            json={"id_token": "telegram-id-token", "nonce": nonce},
        )

    assert response.status_code == 200
    claims = decode_app_token(
        config=config,
        token=response.json()["access_token"],
    )
    assert claims is not None
    assert claims["telegram_id"] == "42"


def test_auth_session_flow_authenticates_chat_with_session_header() -> None:
    """Adapter-style session auth works without changing chat endpoints."""
    config = OidcConfig(
        client_id="123",
        client_secret=None,
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    app.dependency_overrides[get_oidc_config] = lambda: config
    service_client = Mock()
    service_client.send_message.return_value = Message(
        message_id="42:5",
        sender="42",
        channel="42",
        timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        text="hello",
    )
    app.dependency_overrides[get_chat_client] = lambda: service_client

    session_response = client.post("/auth/sessions")
    session_payload = session_response.json()
    session_id = session_payload["session_id"]

    config_response = client.get(
        "/auth/login/config",
        params={"session_id": session_id},
    )
    nonce = config_response.json()["nonce"]

    with patch(
        "chat_client_service.oidc.verify_id_token",
        return_value={
            "id": 42,
            "sub": "oidc-sub",
            "preferred_username": "alice",
            "name": "Alice",
        },
    ):
        callback_response = client.post(
            "/auth/callback",
            json={"id_token": "telegram-id-token", "nonce": nonce},
        )

    status_response = client.get(f"/auth/sessions/{session_id}")
    chat_response = client.post(
        "/chat/messages",
        headers={"X-Session-ID": session_id},
        json={"channel_id": "me", "text": "hello"},
    )

    assert session_response.status_code == 201
    assert session_payload["authenticated"] is False
    assert session_payload["bot_username"] == "osshwbot"
    assert session_payload["bot_start_url"] == (
        "https://t.me/osshwbot?start=chatclient"
    )
    assert config_response.json()["bot_username"] == "osshwbot"
    assert config_response.json()["bot_start_url"] == (
        "https://t.me/osshwbot?start=chatclient"
    )
    assert session_payload["login_url"].endswith(
        f"/auth/login?session_id={session_id}&flow=page"
    )
    assert callback_response.status_code == 200
    assert "access_token" in callback_response.json()
    assert status_response.json()["authenticated"] is True
    assert status_response.json()["telegram_id"] == "42"
    assert chat_response.status_code == 200
    service_client.send_message.assert_called_once_with(channel_id="42", text="hello")


def test_auth_callback_cookie_authenticates_chat_routes() -> None:
    """Browser cookie and X-Session-ID use the same service session."""
    config = OidcConfig(
        client_id="123",
        client_secret=None,
        service_base_url="http://testserver",
        app_session_secret="app-secret",
    )
    app.dependency_overrides[get_oidc_config] = lambda: config
    service_client = Mock()
    service_client.send_message.return_value = Message(
        message_id="42:5",
        sender="42",
        channel="42",
        timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        text="hello",
    )
    app.dependency_overrides[get_chat_client] = lambda: service_client
    _client_id, nonce = begin_login_library(config)

    with patch(
        "chat_client_service.oidc.verify_id_token",
        return_value={
            "id": 42,
            "sub": "oidc-sub",
            "preferred_username": "alice",
            "name": "Alice",
        },
    ):
        callback_response = client.post(
            "/auth/callback",
            json={"id_token": "telegram-id-token", "nonce": nonce},
        )

    chat_response = client.post(
        "/chat/messages",
        json={"channel_id": "me", "text": "hello"},
    )
    session_id = client.cookies.get("chat_client_session")
    assert session_id is not None
    client.cookies.clear()
    header_response = client.post(
        "/chat/messages",
        headers={"X-Session-ID": session_id},
        json={"channel_id": "me", "text": "again"},
    )

    assert callback_response.status_code == 200
    assert "chat_client_session" in callback_response.headers["set-cookie"]
    assert chat_response.status_code == 200
    assert header_response.status_code == 200
    service_client.send_message.assert_any_call(channel_id="42", text="hello")
    service_client.send_message.assert_any_call(channel_id="42", text="again")


def test_auth_session_logout_rejects_session_header() -> None:
    """Deleting a service auth session invalidates X-Session-ID auth."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    token = issue_app_token(
        config=config,
        claims={"id": 42, "sub": "oidc-sub", "preferred_username": "alice"},
    )
    app.dependency_overrides[get_oidc_config] = lambda: config
    get_store().create_auth_session(session_id="session-1", created_at=1)
    claims = decode_app_token(config=config, token=token)
    assert claims is not None
    get_store().authenticate_session(
        session_id="session-1",
        token=token,
        claims=claims,
    )

    delete_response = client.delete("/auth/sessions/session-1")
    chat_response = client.get(
        "/chat/channels",
        headers={"X-Session-ID": "session-1"},
    )

    assert delete_response.status_code == 200
    assert delete_response.json() == {"success": True}
    assert chat_response.status_code == 401


def test_auth_me_requires_valid_token() -> None:
    """GET /auth/me returns 401 without a valid Bearer token."""
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_slack_mode_unauthorized_points_to_demo_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slack provider mode does not tell callers to start Telegram login."""
    monkeypatch.setenv("CHAT_CLIENT_PROVIDER", "slack")

    response = client.get("/chat/channels")

    assert response.status_code == 401
    assert "X-Demo-API-Key" in response.json()["detail"]
    assert "/auth/login" not in response.json()["detail"]


def test_auth_me_decodes_local_token() -> None:
    """Issued local tokens authenticate /auth/me."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    token = issue_app_token(
        config=config,
        claims={
            "id": 42,
            "sub": "oidc-sub",
            "preferred_username": "alice",
            "name": "Alice",
        },
    )
    app.dependency_overrides[get_oidc_config] = lambda: config

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["telegram_id"] == "42"


def test_demo_api_key_authenticates_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Render demo API key can authenticate Swagger without Telegram login."""
    monkeypatch.setenv("CHAT_CLIENT_DEMO_API_KEY", "demo-secret")

    response = client.get("/auth/me", headers={"X-Demo-API-Key": "demo-secret"})

    assert response.status_code == 200
    assert response.json() == {
        "telegram_id": "demo",
        "username": "demo",
        "name": "Demo User",
    }


def test_demo_api_key_is_disabled_when_unconfigured() -> None:
    """The demo key header has no effect unless the env var is set."""
    response = client.get("/auth/me", headers={"X-Demo-API-Key": "demo-secret"})

    assert response.status_code == 401


def test_telegram_auth_sessions_are_disabled_in_slack_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slack provider mode does not expose Telegram session auth as the demo path."""
    monkeypatch.setenv("CHAT_CLIENT_PROVIDER", "slack")

    response = client.post("/auth/sessions")

    assert response.status_code == 400
    assert "X-Demo-API-Key" in response.json()["detail"]


def test_telegram_webhook_is_disabled_in_slack_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telegram webhooks are not processed while the chat provider is Slack."""
    monkeypatch.setenv("CHAT_CLIENT_PROVIDER", "slack")

    response = client.post("/telegram/webhook", json={"update_id": 1})

    assert response.status_code == 404
    assert "disabled" in response.json()["detail"]


def test_decode_app_token_omits_null_optional_claims() -> None:
    """Telegram tokens without username/name do not expose literal 'None' values."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    token = issue_app_token(
        config=config,
        claims={
            "id": 42,
            "sub": "oidc-sub",
            "preferred_username": None,
            "name": None,
        },
    )

    claims = decode_app_token(config=config, token=token)

    assert claims is not None
    assert claims["telegram_id"] == "42"
    assert "username" not in claims
    assert "name" not in claims


def test_issue_app_token_rejects_missing_telegram_identity() -> None:
    """Local service tokens require a non-empty Telegram user id."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )

    with pytest.raises(ValueError, match="Telegram user id is required"):
        issue_app_token(config=config, claims={"preferred_username": "alice"})


def test_auth_me_rejects_tampered_token() -> None:
    """Invalid local Bearer tokens are rejected."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    app.dependency_overrides[get_oidc_config] = lambda: config

    response = client.get("/auth/me", headers={"Authorization": "Bearer bad.token"})

    assert response.status_code == 401


def test_auth_me_rejects_expired_token() -> None:
    """Expired local Bearer tokens are rejected."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
        app_session_ttl_seconds=-1,
    )
    token = issue_app_token(config=config, claims={"sub": "42"})
    app.dependency_overrides[get_oidc_config] = lambda: config

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_begin_login_requires_oidc_config() -> None:
    """OIDC startup fails loudly without service-owned Telegram credentials."""
    config = OidcConfig(
        client_id=None,
        client_secret=None,
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )

    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        begin_login(config)


def test_oidc_config_derives_login_client_id_from_bot_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telegram Login can derive the client id from the bot token prefix."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:bot-secret")
    monkeypatch.delenv("TELEGRAM_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_OIDC_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("APP_SESSION_SECRET", raising=False)

    config = OidcConfig.from_env()

    assert config.client_id == "123456"
    assert config.client_secret is None
    assert config.app_session_secret == "123456:bot-secret"


def test_oidc_config_allows_explicit_login_credential_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit Telegram Login credentials override bot token derivation."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:bot-secret")
    monkeypatch.setenv("TELEGRAM_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("TELEGRAM_OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.delenv("APP_SESSION_SECRET", raising=False)

    config = OidcConfig.from_env()

    assert config.client_id == "client-id"
    assert config.client_secret == "client-secret"
    assert config.app_session_secret == "123456:bot-secret"


def test_oidc_config_strips_whitespace_from_pasted_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strip pasted whitespace to avoid invalid service URLs."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "\n123456:bot-secret\t")
    monkeypatch.setenv("SERVICE_BASE_URL", " https://svc.example/app \n")
    monkeypatch.delenv("TELEGRAM_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_OIDC_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("APP_SESSION_SECRET", raising=False)

    config = OidcConfig.from_env()

    assert config.bot_token == "123456:bot-secret"
    assert config.service_base_url == "https://svc.example/app"


def test_complete_login_exchanges_code_and_issues_token() -> None:
    """OIDC callback exchanges code, verifies id_token, and signs local token."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    _url, state = begin_login(config)

    with (
        patch(
            "chat_client_service.oidc._exchange_code",
            return_value={"id_token": "telegram-id-token"},
        ) as exchange_code,
        patch(
            "chat_client_service.oidc.verify_id_token",
            return_value={
                "id": 42,
                "sub": "oidc-sub",
                "preferred_username": "alice",
                "name": "Alice",
            },
        ) as verify_id_token,
    ):
        token, session_id = complete_login(config=config, code="code", state=state)

    claims = decode_app_token(config=config, token=token)
    assert claims is not None
    assert claims["telegram_id"] == "42"
    assert session_id is None
    exchange_code.assert_called_once()
    verify_id_token.assert_called_once()
    assert verify_id_token.call_args.kwargs["nonce"]


def test_complete_login_library_rejects_bad_nonce() -> None:
    """Telegram.Login callback rejects missing server-generated nonce."""
    config = OidcConfig(
        client_id="client-id",
        client_secret=None,
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )

    with pytest.raises(ValueError, match="Invalid or expired Telegram Login nonce"):
        complete_login_library(
            config=config,
            id_token="telegram-id-token",
            nonce="missing",
        )


def test_oidc_code_exchange_uses_basic_auth() -> None:
    """Token exchange follows Telegram OIDC client-auth requirements."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )
    response = Mock()
    response.json.return_value = {"id_token": "telegram-id-token"}
    response.raise_for_status.return_value = None

    with patch("chat_client_service.oidc.httpx.post", return_value=response) as post:
        payload = oidc._exchange_code(
            config=config,
            code="code",
            code_verifier="verifier",
        )

    assert payload == {"id_token": "telegram-id-token"}
    assert post.call_args.kwargs["auth"] == ("client-id", "secret")
    assert "client_secret" not in post.call_args.kwargs["data"]


def test_complete_login_rejects_bad_state() -> None:
    """OIDC callback rejects missing or expired state values."""
    config = OidcConfig(
        client_id="client-id",
        client_secret="secret",
        service_base_url="https://example.com",
        app_session_secret="app-secret",
    )

    with pytest.raises(ValueError, match="Invalid or expired"):
        complete_login(config=config, code="code", state="missing")


# ---------------------------------------------------------------------------
# Chat — delegate to impl via DI override
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_chat_client() -> Generator[Mock, None, None]:
    """Provide a mock Client wired into the FastAPI dependency system."""
    mock = Mock()
    app.dependency_overrides[get_chat_client] = lambda: mock
    app.dependency_overrides[get_current_token] = lambda: "test-token"
    app.dependency_overrides[get_current_claims] = lambda: {
        "telegram_id": "42",
        "username": "alice",
        "name": "Alice",
    }
    get_store().grant_access(telegram_id="42", channel_id="ch-1")
    yield mock
    app.dependency_overrides.pop(get_chat_client, None)
    app.dependency_overrides.pop(get_current_token, None)
    app.dependency_overrides.pop(get_current_claims, None)


def test_send_message_delegates_to_client(mock_chat_client: Mock) -> None:
    """POST /chat/messages delegates to the injected client."""
    mock_chat_client.send_message.return_value = _message_dto()

    response = client.post(
        "/chat/messages", json={"channel_id": "ch-1", "text": "hello"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "m-1"
    assert body["text"] == "hello"
    mock_chat_client.send_message.assert_called_once_with(
        channel_id="ch-1", text="hello"
    )


def test_send_message_uses_configured_slack_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /chat/messages can swap from Telegram to the Slack ChatClient."""
    from slack_client_impl import client as slack_client_module

    class FakeSlackWebClient:
        def __init__(self, *, token: str) -> None:
            self.token = token
            self.sent: dict[str, str] | None = None

        def chat_postMessage(  # noqa: N802
            self,
            *,
            channel: str,
            text: str,
        ) -> dict[str, object]:
            self.sent = {"channel": channel, "text": text}
            return {"ok": True, "channel": channel, "ts": "1715200000.000100"}

        def conversations_info(self, *, channel: str) -> dict[str, object]:
            return {
                "ok": True,
                "channel": {
                    "id": channel,
                    "name": "demo",
                    "is_private": False,
                    "is_member": True,
                },
            }

    fake_slack = FakeSlackWebClient(token="xoxb-test")
    monkeypatch.setenv("CHAT_CLIENT_PROVIDER", "slack")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")

    def build_fake_web_client(*, token: str) -> FakeSlackWebClient:
        assert token == "xoxb-test"
        return fake_slack

    monkeypatch.setattr(
        slack_client_module,
        "WebClient",
        build_fake_web_client,
    )
    app.dependency_overrides[get_current_token] = lambda: "test-token"
    app.dependency_overrides[get_current_claims] = _allow_auth
    try:
        response = client.post(
            "/chat/messages",
            json={"channel_id": "C1234567890", "text": "hello from Slack provider"},
        )
    finally:
        app.dependency_overrides.pop(get_current_token, None)
        app.dependency_overrides.pop(get_current_claims, None)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "C1234567890:1715200000.000100"
    assert body["timestamp"] == "2024-05-08T20:26:40.000100+00:00"
    assert fake_slack.sent == {
        "channel": "C1234567890",
        "text": "hello from Slack provider",
    }


def test_get_messages_delegates_to_client(mock_chat_client: Mock) -> None:
    """GET /chat/messages delegates to the injected client."""
    mock_chat_client.get_messages.return_value = [
        _message_dto(message_id="m-1"),
        _message_dto(message_id="m-2"),
    ]

    response = client.get("/chat/messages?channel_id=ch-1&limit=2")

    assert response.status_code == 200
    ids = [m["id"] for m in response.json()]
    assert ids == ["m-1", "m-2"]
    mock_chat_client.get_messages.assert_called_once_with(channel_id="ch-1", limit=2)


def test_get_messages_accepts_openapi_client_max_results(
    mock_chat_client: Mock,
) -> None:
    """GET /chat/messages keeps compatibility with OpenAPI clients."""
    mock_chat_client.get_messages.return_value = [_message_dto(message_id="m-1")]

    response = client.get("/chat/messages?channel_id=ch-1&max_results=3")

    assert response.status_code == 200
    assert response.json()[0]["id"] == "m-1"
    mock_chat_client.get_messages.assert_called_once_with(channel_id="ch-1", limit=3)


def test_delete_message_delegates_to_client(mock_chat_client: Mock) -> None:
    """DELETE /chat/messages/{id} delegates to the injected client."""
    response = client.delete("/chat/messages/ch-1:m-1")

    assert response.status_code == 200
    assert response.json() == {"success": True}
    mock_chat_client.delete_message.assert_called_once_with(message_id="ch-1:m-1")


def test_me_channel_requires_telegram_identity(mock_chat_client: Mock) -> None:
    """The explicit 'me' alias fails clearly if auth state lacks Telegram identity."""

    def empty_claims() -> dict[str, str]:
        return {}

    app.dependency_overrides[get_current_claims] = empty_claims
    try:
        response = client.post(
            "/chat/messages",
            json={"channel_id": "me", "text": "hello"},
        )
    finally:
        app.dependency_overrides.pop(get_current_claims, None)

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Authenticated session has no Telegram identity."
    )
    mock_chat_client.send_message.assert_not_called()


def test_me_channel_alias_is_telegram_only(
    mock_chat_client: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Telegram 'me' shortcut is not reused for Slack provider swaps."""
    monkeypatch.setenv("CHAT_CLIENT_PROVIDER", "slack")

    response = client.post(
        "/chat/messages",
        json={"channel_id": "me", "text": "hello"},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "'me' is only supported by the Telegram provider."
    )
    mock_chat_client.send_message.assert_not_called()


def test_delete_message_resolves_simple_id_from_store(mock_chat_client: Mock) -> None:
    """DELETE /chat/messages/{id} still accepts unique simple ids from stored state."""
    get_store().upsert_channel(
        StoredChannel(channel_id="ch-1", name="general", channel_type="group")
    )
    get_store().add_message(
        StoredMessage(
            message_id="m-1",
            sender="alice",
            channel_id="ch-1",
            timestamp="2026-03-20T00:00:00",
            text="hello",
        )
    )
    get_store().grant_access(telegram_id="42", channel_id="ch-1")

    response = client.delete("/chat/messages/m-1")

    assert response.status_code == 200
    assert response.json() == {"success": True}
    mock_chat_client.delete_message.assert_called_once_with(message_id="ch-1:m-1")


def test_delete_message_requires_opaque_id_or_channel_context(
    mock_chat_client: Mock,
) -> None:
    """DELETE /chat/messages/{id} returns 400 without channel context."""
    response = client.delete("/chat/messages/m-1")

    assert response.status_code == 400
    assert "opaque message id" in response.json()["detail"].lower()
    mock_chat_client.delete_message.assert_not_called()


def test_get_message_delegates_to_client(mock_chat_client: Mock) -> None:
    """GET /chat/messages/{id} delegates to the injected client."""
    mock_chat_client.get_message.return_value = _message_dto(message_id="m-1")

    response = client.get("/chat/messages/m-1")

    assert response.status_code == 200
    assert response.json()["id"] == "m-1"
    mock_chat_client.get_message.assert_called_once_with(message_id="m-1")


def test_get_channels_delegates_to_client(mock_chat_client: Mock) -> None:
    """GET /chat/channels delegates to the injected client."""
    ch = Channel(
        channel_id="ch-1",
        name="general",
        is_private=False,
        channel_type="group",
    )
    mock_chat_client.get_channels.return_value = [ch]

    response = client.get("/chat/channels")

    assert response.status_code == 200
    channels = response.json()
    assert channels[0]["id"] == "ch-1"
    assert channels[0]["name"] == "general"


def test_send_message_returns_500_on_client_error(mock_chat_client: Mock) -> None:
    """POST /chat/messages returns 500 when the client raises an exception."""
    mock_chat_client.send_message.side_effect = RuntimeError("Telegram error")

    response = client.post(
        "/chat/messages", json={"channel_id": "ch-1", "text": "hello"}
    )

    assert response.status_code == 500


def test_send_message_me_chat_not_found_returns_start_guidance(
    mock_chat_client: Mock,
) -> None:
    """Sending to 'me' explains how to establish the bot DM before retrying."""
    mock_chat_client.send_message.side_effect = TelegramClientError(
        "Telegram Bot API returned error for sendMessage: Bad Request: chat not found",
        method="sendMessage",
        error_code=400,
    )

    response = client.post(
        "/chat/messages",
        json={"channel_id": "me", "text": "hello"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "This bot cannot message your private chat yet. Open "
        "@osshwbot (https://t.me/osshwbot?start=chatclient), press Start, then "
        "retry. If you already did that, log in again and make sure you "
        "authenticated against the same bot."
    )


def test_get_messages_returns_500_on_client_error(mock_chat_client: Mock) -> None:
    """GET /chat/messages returns 500 when the client raises an exception."""
    mock_chat_client.get_messages.side_effect = RuntimeError("Telegram error")

    response = client.get("/chat/messages?channel_id=ch-1")

    assert response.status_code == 500


def test_delete_message_returns_500_on_client_error(mock_chat_client: Mock) -> None:
    """DELETE /chat/messages/{id} returns 500 when the client raises an exception."""
    mock_chat_client.delete_message.side_effect = RuntimeError("Telegram error")

    response = client.delete("/chat/messages/ch-1:m-1")

    assert response.status_code == 500


def test_get_message_returns_500_on_client_error(mock_chat_client: Mock) -> None:
    """GET /chat/messages/{id} returns 500 when the client raises an exception."""
    mock_chat_client.get_message.side_effect = RuntimeError("Telegram error")

    response = client.get("/chat/messages/m-1")

    assert response.status_code == 500


def test_get_channels_returns_500_on_client_error(mock_chat_client: Mock) -> None:
    """GET /chat/channels returns 500 when the client raises an exception."""
    mock_chat_client.get_channels.side_effect = RuntimeError("Telegram error")

    response = client.get("/chat/channels")

    assert response.status_code == 500
