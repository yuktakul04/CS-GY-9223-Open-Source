"""FastAPI application for Telegram OIDC and Bot API chat operations."""

import html
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from chat_client_api import ChatClient, get_client
from chat_client_service.assistant import build_default_orchestrator
from chat_client_service.config import load_environment
from chat_client_service.middleware.telemetry import TelemetryMiddleware
from chat_client_service.models import HealthResponse
from chat_client_service.routers.auth import router as auth_router
from chat_client_service.routers.chat import router as chat_router
from chat_client_service.routers.telegram import router as telegram_router
from chat_client_service.update_poller import (
    TelegramUpdatePoller,
    poll_interval_seconds,
    should_start_update_poller,
)
from telegram_client_impl.client import get_bot_login_target

LOGGER = logging.getLogger(__name__)

load_environment()
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start optional background services for the FastAPI app."""
    poller: TelegramUpdatePoller | None = None
    poller_chat_client: ChatClient | None = None
    if should_start_update_poller():
        poller_chat_client = get_client()
        assistant = build_default_orchestrator(poller_chat_client)
        on_update = None
        if assistant is not None:

            def _on_update(update: dict[str, object]) -> None:
                assistant.handle_update(update)

            on_update = _on_update
        poller = TelegramUpdatePoller(
            interval_seconds=poll_interval_seconds(),
            on_update=on_update,
        )
        poller.start()
    try:
        yield
    finally:
        if poller is not None:
            poller.stop()
        if poller_chat_client is not None:
            close = getattr(poller_chat_client, "close", None)
            if callable(close):
                close()


_STATIC_DIR = Path(__file__).parent / "static"
_SWAGGER_UI_DIST = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5"
_SWAGGER_UI_BASE_CSS = f"{_SWAGGER_UI_DIST}/swagger-ui.css"
_SWAGGER_UI_BUNDLE_JS = f"{_SWAGGER_UI_DIST}/swagger-ui-bundle.js"
_SWAGGER_UI_FAVICON = "https://fastapi.tiangolo.com/img/favicon.png"

app = FastAPI(
    title="Chat Client Service",
    description="Telegram OIDC login with bot-scoped chat operations.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
)
app.add_middleware(TelemetryMiddleware)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/docs", include_in_schema=False)
async def swagger_ui_dark() -> HTMLResponse:
    """Serve Swagger UI with the vendored Universal Dark theme overlaid.

    The vendored CSS only carries dark-mode overrides for swagger-ui-dist,
    so the base swagger-ui.css must be loaded first; the override stylesheet
    is then layered on top of it.
    """
    title = html.escape(f"{app.title} \u2013 Swagger UI", quote=True)
    openapi_url = app.openapi_url or "/openapi.json"
    redirect_url = app.swagger_ui_oauth2_redirect_url or "/docs/oauth2-redirect"
    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="shortcut icon" href="{_SWAGGER_UI_FAVICON}">
  <link rel="stylesheet" href="{_SWAGGER_UI_BASE_CSS}">
  <link rel="stylesheet" href="/static/swagger-dark.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="{_SWAGGER_UI_BUNDLE_JS}"></script>
  <script>
    window.ui = SwaggerUIBundle({{
      url: "{openapi_url}",
      dom_id: "#swagger-ui",
      deepLinking: true,
      showExtensions: true,
      showCommonExtensions: true,
      presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIBundle.SwaggerUIStandalonePreset,
      ],
      layout: "BaseLayout",
      oauth2RedirectUrl: window.location.origin + "{redirect_url}",
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(content=body)


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, _exc: Exception
) -> JSONResponse:
    """Return a JSON 500 response for any unhandled exception."""
    LOGGER.exception(
        "Unhandled exception in %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


@app.get("/health")
def health() -> HealthResponse:
    """Return service health status."""
    return HealthResponse(status="ok")


@app.get("/", response_model=None, include_in_schema=False)
def root() -> HTMLResponse:
    """Handle Telegram auth fragments that browsers do not send to the server."""
    bot_username, bot_start_url = get_bot_login_target()
    return HTMLResponse(
        _root_fragment_handler_html(
            bot_username=bot_username,
            bot_start_url=bot_start_url,
        )
    )


def _root_fragment_handler_html(
    *,
    bot_username: str | None,
    bot_start_url: str | None,
) -> str:
    bot_start_markup = _bot_start_markup(
        bot_username=bot_username,
        bot_start_url=bot_start_url,
    )
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Telegram Login</title>
  <style>
    body {
      margin: 0; min-height: 100vh;
      display: flex; flex-direction: column; align-items: center;
      padding: 14vh 1.5rem 2rem;
      background: #1a1a1a; color: #f5f5f5;
      font-family: ui-sans-serif, system-ui, sans-serif;
    }
    main { width: 100%; max-width: 26rem; text-align: center; }
    h1 {
      margin: 0 0 0.5rem;
      font-size: 1.5rem; font-weight: 600;
    }
    #status {
      margin: 0; color: #9a9a9a; font-size: 0.95rem;
      line-height: 1.5;
      white-space: pre-wrap; word-break: break-word;
    }
    .bot-start {
      margin-top: 2.5rem;
      color: #8a8a8a; font-size: 0.85rem; line-height: 1.55;
    }
    .bot-start p { margin: 0 0 0.4rem; }
    .bot-start a { color: #e5e5e5; word-break: break-word; }
  </style>
</head>
<body>
  <main>
    <h1>Telegram login</h1>
    <pre id="status" aria-live="polite">Completing Telegram login...</pre>
    __BOT_START_MARKUP__
  </main>
  <script>
    const statusBox = document.getElementById("status");
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const authResult = fragment.get("tgAuthResult");
    const state = sessionStorage.getItem("telegram_auth_state") ||
      localStorage.getItem("telegram_auth_state");
    const sessionId = sessionStorage.getItem("telegram_auth_session_id") ||
      localStorage.getItem("telegram_auth_session_id");
    if (!authResult) {
      statusBox.textContent = "Chat Client Service";
    } else {
      async function responseBody(response) {
        const contentType = response.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
          return {detail: "Login failed. Please retry."};
        }
        try {
          return await response.json();
        } catch {
          return {detail: "Login failed. Please retry."};
        }
      }
      fetch("/auth/telegram-login", {
        method: "POST",
        credentials: "same-origin",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({
          auth_result: authResult,
          state,
          session_id: sessionId,
        }),
      }).then(async (response) => {
        const body = await responseBody(response);
        if (!response.ok) {
          statusBox.textContent = body.detail || "Login failed. Please retry.";
          return;
        }
        sessionStorage.removeItem("telegram_auth_state");
        sessionStorage.removeItem("telegram_auth_session_id");
        localStorage.removeItem("telegram_auth_state");
        localStorage.removeItem("telegram_auth_session_id");
        window.history.replaceState(null, "", "/");
        statusBox.textContent =
          "Login complete. You can close this tab and return to your API client.";
        if (window.opener && !window.opener.closed) {
          window.opener.postMessage(
            {
              type: "telegram-auth-complete",
              sessionId: sessionId,
            },
            window.location.origin
          );
        }
      }).catch(() => {
        statusBox.textContent = "Login failed. Please retry.";
      });
    }
  </script>
</body>
</html>
""".replace("__BOT_START_MARKUP__", bot_start_markup)


def _bot_start_markup(
    *,
    bot_username: str | None,
    bot_start_url: str | None,
) -> str:
    if not bot_username or not bot_start_url:
        return ""
    username = html.escape(bot_username, quote=True)
    url = html.escape(bot_start_url, quote=True)
    return f"""
    <section class="bot-start">
      <p>
        If this is your first time using this bot, open @{username} in Telegram
        and press Start before sending messages.
      </p>
      <p>
        <a href="{url}" target="_blank" rel="noreferrer">
          Open @{username} in Telegram
        </a>
      </p>
    </section>
"""


app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(telegram_router)
