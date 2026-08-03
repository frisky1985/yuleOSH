# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""T1 (v3.9.0) — tenant auth cookie policy: single source of truth.

Dual-cookie scheme (裁决 B1/B3):
  - ``yuleosh_at`` : short-lived access token (HttpOnly; SameSite=Lax; Path=/)
  - ``yuleosh_rt`` : long-lived refresh token (same attributes)

Cookie names deliberately avoid the legacy ``osh_session`` key so the two
mechanisms never collide (SHALL-T1.8 / T-T1-18).  The ``Secure`` attribute
is applied unless running in development mode (SHALL-T1.1: production HTTPS
requires Secure; dev over plain HTTP is not forced).

Every Set-Cookie emitted by the tenant auth flow goes through the builders
in this module — one place for names/attributes (SHALL-T1.1, T-T1-22).
"""

from typing import Optional

import http.cookies

# Cookie names (裁决 B1) — never collide with legacy ``osh_session`` (T1.8).
ACCESS_COOKIE_NAME = "yuleosh_at"
REFRESH_COOKIE_NAME = "yuleosh_rt"

# Token lifetimes (SHALL-T1.2 / T-T1-15): access is significantly shorter
# than the legacy 72h (≤30min recommended), refresh ≥ access (7d).
ACCESS_TTL_HOURS = 0.5     # 30 minutes
REFRESH_TTL_HOURS = 168    # 7 days

_COOKIE_PATH = "/"
_COOKIE_SAMESITE = "Lax"


def _secure_enabled() -> bool:
    """True when the Secure attribute should be set.

    Production (default) requires Secure (HTTPS); development mode
    (YULEOSH_ENV=development) omits it so local http:// works.
    """
    try:
        from yuleosh.api.cors import is_development
        return not is_development()
    except Exception:
        # Fail closed: unknown environment → require Secure.
        return True


def make_auth_cookie(name: str, value: str, max_age: Optional[int] = None) -> str:
    """Build a tenant auth Set-Cookie header value.

    Attributes are the single source for the whole tenant auth flow
    (T1.1 / T-T1-22): ``HttpOnly`` + ``SameSite=Lax`` + ``Path=/`` +
    ``Secure`` (production).  ``max_age`` in seconds; pass 0 to delete.
    """
    parts = [f"{name}={value}"]
    parts.append("HttpOnly")
    parts.append(f"SameSite={_COOKIE_SAMESITE}")
    parts.append(f"Path={_COOKIE_PATH}")
    if max_age is not None:
        parts.append(f"Max-Age={int(max_age)}")
    if _secure_enabled():
        parts.append("Secure")
    return "; ".join(parts)


def token_cookie_headers(access: str, refresh: str) -> list:
    """Set-Cookie header values for a fresh access+refresh pair (T1.1)."""
    return [
        make_auth_cookie(ACCESS_COOKIE_NAME, access,
                         int(ACCESS_TTL_HOURS * 3600)),
        make_auth_cookie(REFRESH_COOKIE_NAME, refresh,
                         int(REFRESH_TTL_HOURS * 3600)),
    ]


def clear_cookie_headers() -> list:
    """Set-Cookie header values that delete both tenant cookies (T1.6)."""
    return [
        make_auth_cookie(ACCESS_COOKIE_NAME, "", 0),
        make_auth_cookie(REFRESH_COOKIE_NAME, "", 0),
    ]


def read_cookie_value(headers, name: str) -> Optional[str]:
    """Extract a cookie value from request headers (dict or object).

    T1 (v3.9.0, SHALL-T1.4): the cookie fallback reader used by the
    middleware and the auth routes.  Accepts both a plain dict
    (``{"Cookie": ...}``) and an object with ``.get`` (real
    ``BaseHTTPRequestHandler.headers`` is case-insensitive).  Returns None
    when the cookie is absent or unparseable — never raises.
    """
    if callable(getattr(headers, "get", None)):
        cookie_raw = headers.get("Cookie", "") or headers.get("cookie", "")
    elif isinstance(headers, dict):
        cookie_raw = headers.get("Cookie", "") or headers.get("cookie", "")
    else:
        return None
    if not cookie_raw:
        return None
    try:
        parsed = http.cookies.SimpleCookie(cookie_raw)
    except Exception:
        return None
    morsel = parsed.get(name)
    return morsel.value if morsel is not None else None
