"""Simple API key authentication for OSH Dashboard.

Features:
- When YULEOSH_API_KEY env var is set, all API routes require X-API-Key header
- Web UI gets served a minimal login page for unauthenticated browser access
- Session-based auth via a simple token cookie for browser UX
- No external dependencies — pure stdlib
"""

import hashlib
import hmac
import html
import http.cookies
import os
import secrets
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("YULEOSH_API_KEY", "")
AUTH_ENABLED = bool(API_KEY)

# In-memory session store: token -> timestamp
_sessions: dict[str, float] = {}
SESSION_TTL = 86400  # 24 hours


def _generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def _session_sig(token: str) -> str:
    """HMAC-sign a session token with the API key so sessions can't be forged."""
    key = API_KEY.encode("utf-8")
    return hmac.new(key, token.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def create_session() -> tuple[str, str]:
    """Create a new session. Returns (token, cookie_value)."""
    token = _generate_session_token()
    _sessions[token] = time.time()
    sig = _session_sig(token)
    return token, f"{token}.{sig}"


def validate_session(cookie_val: str) -> bool:
    """Validate a signed session cookie. Returns True if valid."""
    try:
        parts = cookie_val.split(".")
        if len(parts) != 2:
            return False
        token, sig = parts
        expected_sig = _session_sig(token)
        if not hmac.compare_digest(sig, expected_sig):
            return False
        created = _sessions.get(token)
        if created is None:
            return False
        if time.time() - created > SESSION_TTL:
            del _sessions[token]
            return False
        return True
    except Exception:
        return False


def cleanup_sessions():
    """Remove expired sessions from memory."""
    now = time.time()
    stale = [t for t, c in _sessions.items() if now - c > SESSION_TTL]
    for t in stale:
        _sessions.pop(t, None)


# ---------------------------------------------------------------------------
# Login page HTML (dark theme matching dashboard)
# ---------------------------------------------------------------------------

LOGIN_PAGE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OSH-Fusion — Login</title>
<style>
:root {{
  --bg: #0a0e17;
  --surface: #111827;
  --surface2: #1a2332;
  --border: #1e293b;
  --text: #e2e8f0;
  --text2: #94a3b8;
  --green: #10b981;
  --red: #ef4444;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'Inter', -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}}
.login-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 40px;
  width: 380px;
  max-width: 90vw;
  text-align: center;
}}
.login-card h1 {{ font-size: 24px; font-weight: 800; margin-bottom: 4px; }}
.login-card h1 .green {{ color: var(--green); }}
.login-card h1 .blue {{ color: #3b82f6; }}
.login-card p {{ color: var(--text2); font-size: 14px; margin: 8px 0 24px; }}
.login-card .error {{ color: var(--red); font-size: 13px; margin-bottom: 12px; min-height: 20px; }}
.login-card input {{
  width: 100%;
  padding: 12px 16px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-size: 14px;
  outline: none;
  transition: border-color .15s;
}}
.login-card input:focus {{ border-color: var(--green); }}
.login-card input::placeholder {{ color: var(--text2); }}
.login-card button {{
  width: 100%;
  margin-top: 16px;
  padding: 12px;
  background: var(--green);
  border: none;
  border-radius: 8px;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: opacity .15s;
}}
.login-card button:hover {{ opacity: .85; }}
.login-card .hint {{ font-size: 11px; color: var(--text2); margin-top: 16px; }}
</style>
</head>
<body>
<div class="login-card">
  <h1><span class="green">🔱 OSH</span><span class="blue">-Fusion</span></h1>
  <p>Enter API key to access the dashboard</p>
  <div class="error" id="error">{error}</div>
  <form method="POST" action="/_auth/login">
    <input type="password" name="api_key" placeholder="API Key" autofocus required>
    <button type="submit">→ Unlock</button>
  </form>
  <div class="hint">Configured via YULEOSH_API_KEY environment variable</div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Auth check helpers
# ---------------------------------------------------------------------------

def is_authenticated(headers: dict) -> bool:
    """Check if the request carries a valid API key or session cookie.

    Returns True when auth is disabled (no API key set).
    """
    if not AUTH_ENABLED:
        return True

    # 1. Check X-API-Key header
    api_key = headers.get("x-api-key", "")
    if api_key and hmac.compare_digest(api_key, API_KEY):
        return True

    # 2. Check session cookie
    cookie_raw = headers.get("cookie", "")
    cookies = http.cookies.SimpleCookie(cookie_raw) if cookie_raw else {}
    if "osh_session" in cookies:
        if validate_session(cookies["osh_session"].value):
            return True

    return False


def get_login_page(error: str = "") -> str:
    """Return the login page HTML with optional error message."""
    return LOGIN_PAGE.format(
        error=html.escape(error) if error else ""
    )
