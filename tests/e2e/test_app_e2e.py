"""Black-box E2E tests against the fully-wired FastAPI app.

These run with FastAPI's ``TestClient`` against the real ``app`` object —
real middleware, real routers, real dependency wiring. The only thing
stubbed is the AI assistant (so the test doesn't need provider creds).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from chat_client_service.app import app
from chat_client_service.routers.telegram import get_telegram_assistant
from telegram_client_impl.store import get_store


@pytest.fixture(autouse=True)
def app_e2e_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Run the app with deterministic env and a clean in-memory store."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "osshwbot")
    monkeypatch.setenv("APP_SESSION_SECRET", "app-secret")
    monkeypatch.setenv("CHAT_CLIENT_STORE_PATH", ":memory:")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    get_store().clear()
    app.dependency_overrides.clear()
    yield
    get_store().clear()
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    """TestClient against the real ``app`` (no redirect follow)."""
    return TestClient(app, follow_redirects=False)


def test_health_endpoint_returns_ok(client: TestClient) -> None:
    """``GET /health`` returns 200 with ``{"status": "ok"}``."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_endpoint_serves_html(client: TestClient) -> None:
    """``GET /docs`` serves a Swagger UI HTML page."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"].lower()
    body = response.text
    assert "swagger-ui" in body.lower()


def test_telegram_webhook_records_message_and_returns_204(
    client: TestClient,
) -> None:
    """``POST /telegram/webhook`` returns 204 and persists the inbound message."""
    # Stub the assistant out so the webhook does not need AI credentials.
    app.dependency_overrides[get_telegram_assistant] = lambda: None

    update = {
        "update_id": 42,
        "message": {
            "message_id": 7,
            "date": 1_715_200_000,
            "text": "hello bot",
            "chat": {"id": 555, "type": "private", "first_name": "Alice"},
            "from": {
                "id": 100,
                "is_bot": False,
                "first_name": "Alice",
                "username": "alice",
            },
        },
    }

    response = client.post("/telegram/webhook", json=update)

    assert response.status_code == 204
    assert response.content == b""

    stored = get_store().list_messages(channel_id="555", max_results=10)
    assert len(stored) == 1
    assert stored[0].text == "hello bot"
    assert stored[0].channel == "555"
