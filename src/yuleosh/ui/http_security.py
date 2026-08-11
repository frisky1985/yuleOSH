# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH Dashboard — HTTP security controls (TD-004, split from server.py).

Domain: HTTP-layer security for the OSHHandler server — rate limiting
(429 / Retry-After), Content-Security-Policy construction with per-request
nonce injection, and security response headers.  Moved verbatim from
yuleosh/ui/server.py (pure relocation, zero logic change).

The rate-limit bucket state lives here; server.py re-exports the same
objects so ``mock.patch("yuleosh.ui.server.check_rate_limit")`` and the
shared ``_rate_limit_buckets`` dict semantics keep working.
"""

import logging
import re
import secrets
import sqlite3
import time
from collections import defaultdict

log = logging.getLogger("ui.http_security")


# ── T2 (v3.9.0): CSP — single source for every HTML response ────────────
#   script-src uses a per-request nonce (裁决 B5 ①): _serve_static/
#   _serve_file rewrite inline RSC <script> tags and inject the matching
#   nonce into the policy — no build coupling, per-response randomness.
#   'unsafe-inline' is allowed in style-src / style-src-attr: the static
#   export has 31 inline style= attributes AND the React runtime injects
#   <style> elements dynamically (hash-impossible) — style injection is
#   not an XSS vector, so script-src stays strict while styles keep
#   'unsafe-inline' (verified by browser test T-T2-08).
#   'unsafe-eval' is REMOVED (裁决 B6): the only Function( in the bundle is
#   core-js's global-detection fallback
#   (frontend/out/_next/static/chunks/0cz1d0mv5g_q7.js:
#   ``Function("return this")``) — short-circuited dead code wherever
#   globalThis exists (all modern browsers), so it is never executed.
#   nginx (deploy/nginx/nginx.conf) intentionally does NOT set its own
#   CSP — a static nginx CSP would AND with this per-request nonce policy
#   and block the inline RSC scripts (single source, T-T2-10).
def _format_csp(directives: dict) -> str:
    """Serialize a {directive: [sources]} dict into a CSP header value."""
    return "; ".join(
        f"{k} {' '.join(v)}" for k, v in directives.items()
    ) + ";"


def _base_csp_directives(nonce: str) -> dict:
    """The strict base policy — single source for every HTML response.

    - script-src: per-request nonce ONLY (裁决 B5 ①) — no 'unsafe-inline',
      no 'unsafe-eval' (B6: core-js Function("return this") fallback is
      short-circuited dead code wherever globalThis exists).
    - style-src 'unsafe-inline': static export's inline style= attributes
      AND the React runtime's dynamically injected <style> elements
      (hash-impossible; style injection is not an XSS vector).
    """
    return {
        "default-src": ["'self'"],
        "script-src": ["'self'", f"'nonce-{nonce}'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "style-src-attr": ["'unsafe-inline'"],
        "font-src": ["'self'"],
        "img-src": ["'self'", "data:", "blob:"],
        "connect-src": ["'self'"],
        "frame-src": ["'self'"],  # defensive: nothing uses frames today
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "frame-ancestors": ["'self'"],
        "form-action": ["'self'"],
    }


# ── T2.2 exception (注明用途) ──────────────────────────────────────────────
#   The legacy Python templates (ui/pages/*, ui/marketing/*) genuinely
#   load a few external resources at runtime (verified by byte-scan of
#   each template + Chrome console).  The contract's "产物零引用" premise
#   holds for frontend/out/ (Next.js export) but NOT for these served
#   templates — so the origins they actually reference are appended to
#   the policy, per T2.2's own exception clause ("实际在用，注明用途").
#   The scan is by template bytes, so the allowlist can never drift from
#   the templates themselves.  js.stripe.com is listed here only if a
#   template starts referencing it — none do today.
_LEGACY_EXTERNAL = [
    # (marker_bytes, directive, origin)
    (b"fonts.googleapis.com", "style-src", "https://fonts.googleapis.com"),
    (b"fonts.googleapis.com", "font-src", "https://fonts.gstatic.com"),
    (b"cdn.tailwindcss.com", "script-src", "https://cdn.tailwindcss.com"),
    (b"js.stripe.com", "script-src", "https://js.stripe.com"),
    (b"js.stripe.com", "frame-src", "https://js.stripe.com"),
    (b"js.stripe.com", "connect-src", "https://api.stripe.com"),
]


def _csp_for_html(nonce: str, html: bytes) -> str:
    """Build the CSP for one HTML response.

    Starts from the strict base and appends the external origins the
    template actually references (legacy templates only — frontend/out
    pages reference nothing external, so they stay strict).
    """
    directives = _base_csp_directives(nonce)
    for marker, directive, origin in _LEGACY_EXTERNAL:
        if marker in html and origin not in directives[directive]:
            directives[directive].append(origin)
    return _format_csp(directives)


# Strict-form template (no legacy extras) — kept for tests/comments.
CSP_POLICY_TEMPLATE = _format_csp(_base_csp_directives("{nonce}"))

# Inline <script> without a src attribute (RSC flight data + legacy page
# inline JS).  External scripts are never touched.
_INLINE_SCRIPT_RE = re.compile(rb"<script(?![^>]*\bsrc=)([^>]*)>", re.IGNORECASE)


def _inject_csp_nonce(html: bytes):
    """Rewrite inline <script> tags with a per-request nonce (B5 ①).

    Returns ``(rewritten_html, nonce)``.  The nonce is random per
    response; the caller must pair it with the CSP header built from
    ``CSP_POLICY_TEMPLATE``.
    """
    nonce = secrets.token_urlsafe(16)
    rewritten = _INLINE_SCRIPT_RE.sub(
        lambda m: b'<script nonce="' + nonce.encode() + b'"' + m.group(1) + b">",
        html,
    )
    return rewritten, nonce


# ── Rate limiting ───────────────────────────────────────────────────────────

_rate_limit_buckets: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX = 60          # requests per window
RATE_LIMIT_WINDOW = 60.0     # seconds


def check_rate_limit_memory(client_ip: str, max_requests: int = RATE_LIMIT_MAX,
                            window: float = RATE_LIMIT_WINDOW) -> tuple[bool, float]:
    """In-memory rate limit check — kept for tests / single-process fallback.

    Multi-worker deployments must use :func:`check_rate_limit` (shared SQLite).
    """
    now = time.time()
    bucket = _rate_limit_buckets[client_ip]
    # Prune old entries
    while bucket and bucket[0] < now - window:
        bucket.pop(0)
    if len(bucket) >= max_requests:
        retry_after = window - (now - bucket[0])
        return False, round(retry_after, 1)
    bucket.append(now)
    return True, 0.0


def check_rate_limit(client_ip: str, max_requests: int = RATE_LIMIT_MAX,
                     window: float = RATE_LIMIT_WINDOW) -> tuple[bool, float]:
    """Check if client_ip is within rate limits.  Returns (allowed, retry_after).

    W2 (2026-08-11): backed by the shared SQLite store
    (``api.ratelimit_shared.RateLimitStore``) so multiple workers share one
    budget.  db path resolves via ``YULEOSH_RATE_DB`` → ``$OSH_HOME/.yuleosh`` →
    temp dir; fall back to the in-memory limiter when the shared store is
    unavailable so a storage hiccup cannot take the API down.
    """
    try:
        from yuleosh.api.ratelimit_shared import RateLimitStore, default_db_path
        store = RateLimitStore(db_path=default_db_path())
        allowed, _remaining = store.check(
            client_ip, limit=max_requests, window_seconds=int(window))
        if allowed:
            return True, 0.0
        retry_after = store.window_remaining_seconds(client_ip, int(window))
        return False, round(retry_after, 1)
    except (sqlite3.Error, OSError) as e:
        # 仅存储层故障（SQLite/文件系统）降级内存限流；编程错误向上抛，
        # 避免降级掩盖真实 bug（如参数/契约变更）。
        log.warning(
            "Rate-limit store unavailable (%s: %s); falling back to in-memory "
            "limiter — multi-worker shared budget is NOT enforced",
            type(e).__name__, e,
        )
        return check_rate_limit_memory(client_ip, max_requests, window)

# ── Security response headers (OSHHandler._add_security_headers) ──────────

def _add_security_headers(self) -> None:
    self.send_header("X-Content-Type-Options", "nosniff")
    self.send_header("X-Frame-Options", "DENY")
    self.send_header("X-XSS-Protection", "1; mode=block")
    self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
