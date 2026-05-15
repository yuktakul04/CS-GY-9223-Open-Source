"""Telegram OIDC authentication routes."""

import base64
import html
import json
import secrets
import time
from typing import Annotated
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import (
    APIKeyCookie,
    APIKeyHeader,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from chat_client_service.models import (
    AuthSessionResponse,
    AuthSessionStatusResponse,
    LegacyTelegramVerifyRequest,
    LogoutResponse,
    MeResponse,
    OAuthCallbackResponse,
    TelegramHashLoginCallbackRequest,
    TelegramLoginCallbackRequest,
    TelegramLoginConfigResponse,
    TokenResponse,
)
from chat_client_service.oidc import (
    OidcConfig,
    begin_login,
    begin_login_library,
    complete_login,
    complete_login_library,
    complete_telegram_hash_login,
    decode_app_token,
)
from telegram_client_impl.client import get_bot_login_target
from telegram_client_impl.store import StoredChannel, get_store

router = APIRouter(prefix="/auth", tags=["auth"])
_APP_SESSION_COOKIE = "chat_client_session"
_STATE_COOKIE = "telegram_auth_state"
_PENDING_SESSION_COOKIE = "telegram_auth_session_id"
_TOKEN_TYPE_BEARER = "bearer"  # noqa: S105

# Security schemes surfaced in the OpenAPI spec so Swagger UI's Authorize
# dialog exposes every supported credential source. auto_error=False keeps
# each scheme optional — get_current_token performs the cross-source check
# and raises 401 only if none of them yield a valid token.
_bearer = HTTPBearer(auto_error=False)
_session_header = APIKeyHeader(name="X-Session-ID", auto_error=False)
_session_cookie = APIKeyCookie(name=_APP_SESSION_COOKIE, auto_error=False)


def get_oidc_config() -> OidcConfig:
    """Return OIDC config from environment."""
    return OidcConfig.from_env()


def get_current_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
    config: Annotated[OidcConfig, Depends(get_oidc_config)],
    x_session_id: Annotated[str | None, Depends(_session_header)] = None,
    chat_client_session: Annotated[str | None, Depends(_session_cookie)] = None,
) -> str:
    """Return the validated Bearer token or raise 401."""
    token: str | None = None
    if credentials is None:
        session_id = x_session_id or chat_client_session
        if session_id is not None:
            token = get_store().token_for_session(session_id=session_id)
    else:
        token = credentials.credentials
    if token is None:
        raise _unauthorized()
    if decode_app_token(config=config, token=token) is None:
        raise _unauthorized()
    return token


def get_current_claims(
    token: Annotated[str, Depends(get_current_token)],
    config: Annotated[OidcConfig, Depends(get_oidc_config)],
) -> dict[str, str]:
    """Return validated local session claims or raise 401."""
    claims = decode_app_token(config=config, token=token)
    if claims is None or not claims.get("telegram_id"):
        raise _unauthorized()
    return claims


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
)
def create_auth_session(
    config: Annotated[OidcConfig, Depends(get_oidc_config)],
) -> AuthSessionResponse:
    """Create a pending service auth session for adapter clients."""
    session_id = secrets.token_urlsafe(24)
    bot_username, bot_start_url = _bot_login_target()
    get_store().create_auth_session(
        session_id=session_id,
        created_at=int(time.time()),
    )
    return AuthSessionResponse(
        session_id=session_id,
        authenticated=False,
        login_url=_session_login_url(config=config, session_id=session_id),
        status_url=_session_status_url(config=config, session_id=session_id),
        bot_username=bot_username,
        bot_start_url=bot_start_url,
    )


@router.get("/login", response_model=None, include_in_schema=False)
def auth_login(
    config: Annotated[OidcConfig, Depends(get_oidc_config)],
    session_id: Annotated[str | None, Query(min_length=1)] = None,
    flow: Annotated[str, Query(pattern="^(auto|page|code)$")] = "auto",
) -> HTMLResponse | RedirectResponse:
    """Start Telegram Login with OIDC code flow or the hosted page fallback."""
    _require_known_session(session_id)
    if flow == "code":
        return _auth_code_redirect(config=config, session_id=session_id)
    if flow == "auto" and config.client_secret:
        return _auth_code_launch_page(config=config, session_id=session_id)

    try:
        client_id, nonce = begin_login_library(config, session_id=session_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    bot_username, bot_start_url = _bot_login_target()
    response = HTMLResponse(
        content=_login_page_html(
            client_id=client_id,
            nonce=nonce,
            origin=config.service_base_url.rstrip("/"),
            session_id=session_id,
            bot_login_target=(bot_username, bot_start_url),
        )
    )
    _set_auth_cookies(
        response=response,
        config=config,
        state=nonce,
        session_id=session_id,
    )
    return response


def _auth_code_redirect(
    *,
    config: OidcConfig,
    session_id: str | None,
) -> RedirectResponse:
    try:
        url, state = begin_login(config, session_id=session_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    response = RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
    _set_auth_cookies(
        response=response,
        config=config,
        state=state,
        session_id=session_id,
    )
    return response


def _auth_code_launch_page(
    *,
    config: OidcConfig,
    session_id: str | None,
) -> HTMLResponse:
    try:
        url, state = begin_login(config, session_id=session_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    response = HTMLResponse(
        content=_login_redirect_html(
            url=url,
            state=state,
            session_id=session_id,
        )
    )
    _set_auth_cookies(
        response=response,
        config=config,
        state=state,
        session_id=session_id,
    )
    return response


def _set_auth_cookies(
    *,
    response: HTMLResponse | RedirectResponse,
    config: OidcConfig,
    state: str,
    session_id: str | None,
) -> None:
    response.set_cookie(
        _STATE_COOKIE,
        state,
        httponly=True,
        max_age=300,
        samesite="lax",
        secure=config.service_base_url.startswith("https://"),
    )
    if session_id is not None:
        response.set_cookie(
            _PENDING_SESSION_COOKIE,
            session_id,
            httponly=True,
            max_age=300,
            samesite="lax",
            secure=config.service_base_url.startswith("https://"),
        )
    else:
        response.delete_cookie(_PENDING_SESSION_COOKIE)


@router.get("/login/config")
def auth_login_config(
    config: Annotated[OidcConfig, Depends(get_oidc_config)],
    session_id: Annotated[str | None, Query(min_length=1)] = None,
) -> TelegramLoginConfigResponse:
    """Return init data for Telegram.Login JavaScript library."""
    _require_known_session(session_id)
    try:
        client_id, nonce = begin_login_library(config, session_id=session_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    bot_username, bot_start_url = _bot_login_target()
    return TelegramLoginConfigResponse(
        client_id=client_id,
        nonce=nonce,
        origin=config.service_base_url.rstrip("/"),
        bot_username=bot_username,
        bot_start_url=bot_start_url,
    )


@router.get("/callback")
def auth_callback(
    code: str,
    state: str,
    response: Response,
    config: Annotated[OidcConfig, Depends(get_oidc_config)],
) -> TokenResponse:
    """Complete Telegram OIDC login and issue a local Bearer token."""
    try:
        token, session_id = complete_login(config=config, code=code, state=state)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _issue_token_response(
        config=config,
        token=token,
        response=response,
        session_id=session_id,
    )


@router.post("/callback")
def auth_login_library_callback(
    request: TelegramLoginCallbackRequest,
    response: Response,
    config: Annotated[OidcConfig, Depends(get_oidc_config)],
) -> TokenResponse:
    """Complete Telegram.Login JavaScript id_token callback."""
    try:
        token, session_id = complete_login_library(
            config=config,
            id_token=request.id_token,
            nonce=request.nonce,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _issue_token_response(
        config=config,
        token=token,
        response=response,
        session_id=session_id,
    )


@router.post("/telegram-login")
def auth_telegram_hash_callback(
    request: TelegramHashLoginCallbackRequest,
    response: Response,
    config: Annotated[OidcConfig, Depends(get_oidc_config)],
    telegram_auth_state: Annotated[str | None, Cookie(alias=_STATE_COOKIE)] = None,
    telegram_auth_session_id: Annotated[
        str | None,
        Cookie(alias=_PENDING_SESSION_COOKIE),
    ] = None,
) -> TokenResponse:
    """Complete Telegram hash login returned as a URL fragment."""
    try:
        token, session_id = complete_telegram_hash_login(
            config=config,
            auth_result=request.auth_result,
            state=request.state or telegram_auth_state,
            fallback_session_id=request.session_id or telegram_auth_session_id,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _issue_token_response(
        config=config,
        token=token,
        response=response,
        session_id=session_id,
    )


@router.post("/verify")
def auth_verify_legacy(
    payload: LegacyTelegramVerifyRequest,
    response: Response,
    request: Request,
    config: Annotated[OidcConfig, Depends(get_oidc_config)],
) -> OAuthCallbackResponse:
    """Compatibility shim for the parent-branch /auth/verify endpoint."""
    state = request.cookies.get(_STATE_COOKIE) or request.cookies.get("oauth_state")
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing CSRF state cookie. Start the flow at /auth/login.",
        )
    pending_session_id = request.cookies.get(_PENDING_SESSION_COOKIE)

    raw_payload = json.dumps(
        payload.model_dump(exclude_none=True),
        separators=(",", ":"),
    ).encode()
    auth_result = base64.urlsafe_b64encode(raw_payload).rstrip(b"=").decode()
    try:
        token, session_id = complete_telegram_hash_login(
            config=config,
            auth_result=auth_result,
            state=state,
            fallback_session_id=pending_session_id,
        )
    except ValueError as exc:
        status_code = status.HTTP_401_UNAUTHORIZED
        if "hash mismatch" not in str(exc).lower():
            status_code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=status_code,
            detail=str(exc),
        ) from exc
    except TypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    claims = decode_app_token(config=config, token=token)
    if claims is not None:
        _grant_self_chat_access(claims)
        if session_id is not None:
            get_store().authenticate_session(
                session_id=session_id,
                token=token,
                claims=claims,
            )
            _set_app_session_cookie(
                response=response,
                config=config,
                session_id=session_id,
            )

    response.delete_cookie(_STATE_COOKIE)
    response.delete_cookie("oauth_state")
    response.delete_cookie(_PENDING_SESSION_COOKIE)
    return OAuthCallbackResponse(
        detail="Authenticated successfully.",
        state=state,
        access_token=token,
        token_type=_TOKEN_TYPE_BEARER,
    )


@router.get("/me")
def auth_me(
    claims: Annotated[dict[str, str], Depends(get_current_claims)],
) -> MeResponse:
    """Return identity from the authenticated local session."""
    return MeResponse(
        telegram_id=claims.get("telegram_id", ""),
        username=claims.get("username"),
        name=claims.get("name"),
    )


@router.get("/sessions/{session_id}")
def get_auth_session(
    session_id: str,
    config: Annotated[OidcConfig, Depends(get_oidc_config)],
) -> AuthSessionStatusResponse:
    """Return the current auth state for a service session."""
    session = get_store().get_auth_session(session_id=session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown auth session.",
        )
    authenticated = (
        session.token is not None
        and decode_app_token(config=config, token=session.token) is not None
    )
    return AuthSessionStatusResponse(
        session_id=session.session_id,
        authenticated=authenticated,
        telegram_id=session.telegram_id,
        username=session.username,
        name=session.name,
    )


@router.delete("/sessions/{session_id}")
def delete_auth_session(
    session_id: str,
    response: Response,
    config: Annotated[OidcConfig, Depends(get_oidc_config)],
) -> LogoutResponse:
    """Delete a service auth session."""
    get_store().delete_auth_session(session_id=session_id)
    _clear_app_session_cookie(response=response, config=config)
    response.delete_cookie(_PENDING_SESSION_COOKIE)
    return LogoutResponse(success=True)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Start at /auth/login.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _issue_token_response(
    *,
    config: OidcConfig,
    token: str,
    response: Response,
    session_id: str | None = None,
) -> TokenResponse:
    claims = decode_app_token(config=config, token=token)
    if claims is not None:
        _grant_self_chat_access(claims)
        session_id = session_id or secrets.token_urlsafe(24)
        if get_store().get_auth_session(session_id=session_id) is None:
            get_store().create_auth_session(
                session_id=session_id,
                created_at=int(time.time()),
            )
        get_store().authenticate_session(
            session_id=session_id,
            token=token,
            claims=claims,
        )
        _set_app_session_cookie(
            response=response,
            config=config,
            session_id=session_id,
        )
    return TokenResponse(access_token=token)


def _set_app_session_cookie(
    *,
    response: Response,
    config: OidcConfig,
    session_id: str,
) -> None:
    response.set_cookie(
        _APP_SESSION_COOKIE,
        session_id,
        httponly=True,
        max_age=config.app_session_ttl_seconds,
        samesite="lax",
        secure=config.service_base_url.startswith("https://"),
    )


def _clear_app_session_cookie(
    *,
    response: Response,
    config: OidcConfig,
) -> None:
    response.delete_cookie(
        _APP_SESSION_COOKIE,
        httponly=True,
        samesite="lax",
        secure=config.service_base_url.startswith("https://"),
    )


def _grant_self_chat_access(claims: dict[str, str]) -> None:
    telegram_id = claims.get("telegram_id", "")
    if not telegram_id:
        return
    name = claims.get("username") or claims.get("name") or telegram_id
    store = get_store()
    store.upsert_channel(
        StoredChannel(
            channel_id=telegram_id,
            name=name,
            channel_type="private",
        )
    )
    store.grant_access(telegram_id=telegram_id, channel_id=telegram_id)


def _require_known_session(session_id: str | None) -> None:
    if session_id is None:
        return
    if get_store().get_auth_session(session_id=session_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown auth session.",
        )


def _session_login_url(*, config: OidcConfig, session_id: str) -> str:
    return (
        f"{config.service_base_url.rstrip('/')}/auth/login?"
        f"{urlencode({'session_id': session_id, 'flow': 'page'})}"
    )


def _session_status_url(*, config: OidcConfig, session_id: str) -> str:
    return f"{config.service_base_url.rstrip('/')}/auth/sessions/{session_id}"


def _bot_login_target() -> tuple[str | None, str | None]:
    """Return bot identity data for login/start instructions."""
    return get_bot_login_target()


def _login_redirect_html(
    *,
    url: str,
    state: str,
    session_id: str | None,
) -> str:
    url_json = json.dumps(url)
    state_json = json.dumps(state)
    session_id_json = json.dumps(session_id)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Telegram Login</title>
</head>
<body>
  <pre>Redirecting to Telegram...</pre>
  <script>
    sessionStorage.setItem("telegram_auth_state", {state_json});
    localStorage.setItem("telegram_auth_state", {state_json});
    if ({session_id_json} !== null) {{
      sessionStorage.setItem("telegram_auth_session_id", {session_id_json});
      localStorage.setItem("telegram_auth_session_id", {session_id_json});
    }} else {{
      sessionStorage.removeItem("telegram_auth_session_id");
      localStorage.removeItem("telegram_auth_session_id");
    }}
    window.location.replace({url_json});
  </script>
</body>
</html>
"""


_TELEGRAM_LOGO_PATH = (
    "M9.78 18.65"
    "l.28-4.23 7.68-6.92"
    "c.34-.31-.07-.46-.52-.19"
    "L7.74 13.3 3.64 12"
    "c-.88-.27-.89-.86.2-1.3"
    "l15.97-6.16"
    "c.73-.27 1.43.18 1.15 1.3"
    "l-2.72 12.81"
    "c-.19.91-.74 1.13-1.5.71"
    "L12.6 16.3"
    "l-1.99 1.93"
    "c-.23.23-.42.42-.83.42z"
)


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


def _login_page_html(
    *,
    client_id: str,
    nonce: str,
    origin: str,
    session_id: str | None,
    bot_login_target: tuple[str | None, str | None],
) -> str:
    session_hint = (
        f"Use X-Session-ID: {session_id} on /chat/*."
        if session_id is not None
        else "Browser session authenticated. Return to your API client."
    )
    client_id_json = json.dumps(client_id)
    nonce_json = json.dumps(nonce)
    origin_json = json.dumps(origin)
    session_id_json = json.dumps(session_id)
    session_hint_json = json.dumps(session_hint)
    bot_username, bot_start_url = bot_login_target
    bot_start_markup = _bot_start_markup(
        bot_username=bot_username,
        bot_start_url=bot_start_url,
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Telegram Login</title>
  <style>
    body {{
      margin: 0; min-height: 100vh;
      display: flex; flex-direction: column; align-items: center;
      padding: 14vh 1.5rem 2rem;
      background: #1a1a1a; color: #f5f5f5;
      font-family: ui-sans-serif, system-ui, sans-serif;
    }}
    main {{ width: 100%; max-width: 26rem; text-align: center; }}
    h1 {{
      margin: 0 0 0.5rem;
      font-size: 1.5rem; font-weight: 600;
    }}
    .lead {{
      margin: 0 auto 1.75rem;
      color: #9a9a9a; line-height: 1.5;
    }}
    .button {{
      display: inline-flex;
      align-items: center; justify-content: center;
      gap: 0.5rem;
      min-width: 14rem; padding: 0.65rem 1.4rem;
      border: 0; border-radius: 999px;
      background: #54a9eb; color: #fff;
      font: inherit; font-weight: 500;
      text-decoration: none; cursor: pointer;
      transition: background 0.15s ease;
    }}
    .button:hover {{ background: #3d99d6; }}
    .tg-icon {{ width: 1.15em; height: 1.15em; flex-shrink: 0; }}
    #status {{
      margin: 1rem 0 0; min-height: 1.25em;
      color: #9a9a9a; font-size: 0.9rem;
      white-space: pre-wrap; word-break: break-word;
    }}
    .bot-start {{
      margin-top: 2.5rem;
      color: #8a8a8a; font-size: 0.85rem; line-height: 1.55;
    }}
    .bot-start p {{ margin: 0 0 0.4rem; }}
    .bot-start a {{ color: #e5e5e5; word-break: break-word; }}
  </style>
</head>
  <body>
    <main>
      <h1>Sign in with Telegram</h1>
      <p class="lead">
        Authenticate this API session with your Telegram account.
      </p>
      <button id="telegram-login" class="button" type="button">
        <svg class="tg-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="{_TELEGRAM_LOGO_PATH}" fill="currentColor"/>
        </svg>
        Log in with Telegram
      </button>
      <pre id="status" aria-live="polite"></pre>
      {bot_start_markup}
    </main>
    <script src="https://oauth.telegram.org/js/telegram-login.js?3"></script>
    <script>
      const clientId = Number({client_id_json});
      const nonce = {nonce_json};
      const origin = {origin_json};
      const launchedSessionId = {session_id_json};
      const sessionHint = {session_hint_json};
      const statusBox = document.getElementById("status");
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const authResult = fragment.get("tgAuthResult");
    const storedState = sessionStorage.getItem("telegram_auth_state") ||
      localStorage.getItem("telegram_auth_state");
    const storedSessionId = sessionStorage.getItem("telegram_auth_session_id") ||
      localStorage.getItem("telegram_auth_session_id");
    const state = authResult ? storedState : nonce;
    const sessionId = authResult ? storedSessionId : launchedSessionId;
    if (!authResult) {{
      sessionStorage.setItem("telegram_auth_state", nonce);
      localStorage.setItem("telegram_auth_state", nonce);
      if (launchedSessionId !== null) {{
        sessionStorage.setItem("telegram_auth_session_id", launchedSessionId);
        localStorage.setItem("telegram_auth_session_id", launchedSessionId);
      }} else {{
        sessionStorage.removeItem("telegram_auth_session_id");
        localStorage.removeItem("telegram_auth_session_id");
      }}
    }}
      function show(message) {{
        statusBox.textContent = message;
      }}
      window.addEventListener("message", (event) => {{
      if (event.origin !== origin) {{
        return;
      }}
      const data = event.data;
      if (!data || data.type !== "telegram-auth-complete") {{
        return;
      }}
      show("Login complete. " + sessionHint);
    }});
    function telegramAuthUrl() {{
      const params = new URLSearchParams({{
        response_type: "post_message",
        client_id: String(clientId),
        redirect_uri: origin + "/",
        scope: "openid profile telegram:bot_access",
        nonce,
        origin,
      }});
      return "https://oauth.telegram.org/auth?" + params.toString();
    }}
    function authResultFrom(data) {{
      const bytes = new TextEncoder().encode(JSON.stringify(data));
      let raw = "";
      bytes.forEach((byte) => {{
        raw += String.fromCharCode(byte);
      }});
      return btoa(raw).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
    }}
    async function responseBody(response) {{
      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {{
        return {{
          detail: "Login failed. Please retry.",
        }};
      }}
      try {{
        return await response.json();
      }} catch {{
        return {{
          detail: "Login failed. Please retry.",
        }};
      }}
    }}
    async function postJson(url, data) {{
      let response;
      try {{
        response = await fetch(url, {{
          method: "POST",
          headers: {{"content-type": "application/json"}},
          body: JSON.stringify(data),
        }});
      }} catch {{
        show("Login failed. Please retry.");
        return false;
      }}
      const body = await responseBody(response);
      if (!response.ok) {{
        show(body.detail || "Login failed. Please retry.");
        return false;
      }}
      sessionStorage.removeItem("telegram_auth_state");
      sessionStorage.removeItem("telegram_auth_session_id");
      localStorage.removeItem("telegram_auth_state");
      localStorage.removeItem("telegram_auth_session_id");
      show("Login complete. " + sessionHint);
      return true;
    }}
    async function finishLogin(data) {{
      if (!data || data.error) {{
        if (data && data.error === "missing id_token") {{
          window.location.assign(telegramAuthUrl());
          return;
        }}
        show(data && data.error ? data.error : "Telegram login was cancelled.");
        return;
      }}
      if (data.id_token) {{
        await postJson("/auth/callback", {{id_token: data.id_token, nonce}});
        return;
      }}
      if (data.hash) {{
        await postJson("/auth/telegram-login", {{
          auth_result: authResultFrom(data),
          state,
          session_id: sessionId,
        }});
        return;
      }}
      show("Telegram did not return an id_token or signed login payload.");
    }}
    if (authResult) {{
      postJson("/auth/telegram-login", {{
        auth_result: authResult,
        state,
        session_id: sessionId,
      }}).then((completed) => {{
        if (completed && window.opener && !window.opener.closed) {{
          window.opener.postMessage(
            {{
              type: "telegram-auth-complete",
              sessionId: sessionId,
            }},
            origin
          );
        }}
      }});
    }} else {{
      Telegram.Login.init({{
        client_id: clientId,
        request_access: ["write"],
        nonce,
      }}, finishLogin);
      document.getElementById("telegram-login").addEventListener("click", () => {{
      const openPopup = window.open;
      window.open = function(url, target, features) {{
        if (
          typeof url === "string" &&
          url.startsWith("https://oauth.telegram.org/auth?")
        ) {{
          const authUrl = new URL(url);
          authUrl.searchParams.set("origin", origin);
          authUrl.searchParams.set("redirect_uri", origin + "/");
          url = authUrl.toString();
          target = "telegram_auth_popup";
        }}
        return openPopup.call(window, url, target, features);
      }};
      try {{
        Telegram.Login.open(finishLogin);
      }} finally {{
        window.open = openPopup;
      }}
      }});
    }}
  </script>
</body>
</html>
"""
