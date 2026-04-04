"""Telegram Login Widget authentication flow.

Flow
----
1. GET /auth/login
   Generates CSRF state, stores it in an httpOnly cookie, redirects to Telegram.

2. Telegram authenticates the user and redirects to:
   GET /auth/callback#tgAuthResult=<base64-json>
   The hash fragment is client-side only — the server returns an HTML page whose
   JavaScript decodes it and POSTs the data to /auth/verify.

3. POST /auth/verify
   Reads the CSRF cookie, verifies Telegram's HMAC-SHA256 hash, issues a signed
   Bearer token that encodes the user's Telegram identity.  No server-side session
   store is required — the token is self-contained and survives service restarts.
"""

import base64
import hashlib
import hmac
import json
import secrets
from os import getenv
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from chat_client_service.models import OAuthCallbackResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_TELEGRAM_OAUTH_URL = "https://oauth.telegram.org/auth"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bot_token() -> str:
    return getenv("TELEGRAM_BOT_TOKEN", "")


def _bot_id() -> str:
    return _bot_token().split(":")[0]


def _service_base_url(request: Request) -> str:
    override = getenv("SERVICE_BASE_URL", "")
    if override:
        return override.rstrip("/")
    return str(request.base_url).rstrip("/")


def _verify_telegram_hash(data: dict[str, str]) -> bool:
    """Verify the HMAC-SHA256 hash Telegram signs its auth results with."""
    bot_tok = _bot_token()
    received_hash = data.get("hash", "")
    check_data = {k: v for k, v in data.items() if k != "hash"}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(check_data.items()))
    secret_key = hashlib.sha256(bot_tok.encode()).digest()
    computed = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, received_hash)


def _issue_token(telegram_id: int, first_name: str, username: str) -> str:
    """Return a self-contained HMAC-signed Bearer token (no server-side state)."""
    body = {"telegram_id": telegram_id, "first_name": first_name, "username": username}
    payload = (
        base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode())
        .rstrip(b"=")
        .decode()
    )
    sig = hmac.new(_bot_token().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _decode_token(token: str) -> dict[str, str] | None:
    """Verify signature and decode a Bearer token.  Returns None if invalid."""
    try:
        payload, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    expected = hmac.new(
        _bot_token().encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + "=="))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return {str(k): str(v) for k, v in data.items()}


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


def get_current_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> str:
    """Return the validated Bearer token or raise 401."""
    if credentials is None or _decode_token(credentials.credentials) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Start at /auth/login.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

_CALLBACK_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Completing login</title></head>
<body>
<p id="status">Decoding Telegram result...</p>
<script>
(function () {
  var out = document.getElementById("status");
  var hash = window.location.hash.slice(1);
  var params = new URLSearchParams(hash);
  var raw = params.get("tgAuthResult");
  if (!raw) {
    out.textContent = "Error: no tgAuthResult found. Try /auth/login again.";
    return;
  }
  var data;
  try { data = JSON.parse(atob(raw)); }
  catch (e) {
    out.textContent = "Error decoding tgAuthResult: " + e;
    return;
  }
  out.textContent = "Verifying with server...";
  fetch("/auth/verify", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  })
  .then(function(r) {
    out.textContent = "Server responded " + r.status + ". Parsing...";
    var status = r.status;
    return r.json().then(function(body) {
      return { status: status, body: body };
    });
  })
  .then(function(res) {
    document.body.innerHTML = "<pre>" + JSON.stringify(res.body, null, 2) + "</pre>";
  })
  .catch(function(e) {
    out.textContent = "Error: " + e + ". Check console for details.";
    console.error(e);
  });
})();
</script>
</body>
</html>
"""


@router.get("/login")
def auth_login(request: Request) -> RedirectResponse:
    """Redirect to Telegram Login Widget; store CSRF state in an httpOnly cookie."""
    state = secrets.token_urlsafe(32)
    base = _service_base_url(request)
    callback_url = f"{base}/auth/callback"
    url = (
        f"{_TELEGRAM_OAUTH_URL}"
        f"?bot_id={_bot_id()}"
        f"&origin={base}"
        f"&return_to={callback_url}"
    )
    redirect = RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        "oauth_state", state, httponly=True, samesite="lax", max_age=300
    )
    return redirect


@router.get("/callback")
def auth_callback() -> HTMLResponse:
    """Serve the HTML bridge page that decodes #tgAuthResult and posts to /auth/verify.

    The hash fragment is never sent to the server, so JS must extract and forward it.
    """
    return HTMLResponse(content=_CALLBACK_HTML)


class _TelegramUser(BaseModel):
    """Data Telegram sends in the tgAuthResult JSON blob.

    ``extra="allow"`` ensures any field Telegram adds (e.g. last_name) is
    preserved so it can be included in the data-check string for HMAC
    verification — omitting any field Telegram signed will cause a hash
    mismatch.
    """

    model_config = ConfigDict(extra="allow")

    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


@router.post("/verify")
def auth_verify(
    user: _TelegramUser,
    request: Request,
    response: Response,
) -> OAuthCallbackResponse:
    """Verify Telegram auth data from the callback page and issue a session token."""
    state = request.cookies.get("oauth_state")
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing CSRF state cookie. Start the flow at /auth/login.",
        )

    telegram_data = {
        k: str(v)
        for k, v in user.model_dump(exclude_none=True).items()
        if v is not None
    }
    if not _verify_telegram_hash(telegram_data):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram hash verification failed.",
        )

    session_token = _issue_token(user.id, user.first_name, user.username or "")
    response.delete_cookie("oauth_state")
    return OAuthCallbackResponse(
        detail="Authenticated successfully.",
        state=state,
        access_token=session_token,
        token_type="bearer",  # noqa: S106
    )


@router.get("/me")
def auth_me(token: Annotated[str, Depends(get_current_token)]) -> dict[str, str]:
    """Return session info for the authenticated caller."""
    return {"token": token, **((_decode_token(token)) or {})}
