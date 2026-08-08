# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Simple in-memory rate limiter for API requests.

Per-IP rate limiting using a sliding time window.
Configurable via YULEOSH_RATE_LIMIT env var (default 100 requests per minute).

NOTE (D-3 / 2026-08-08): This module is TEST/COMPATIBILITY-ONLY — production
code does not import it (verified: zero references under src/). The live
rate limiters are:
  - ui/server.check_rate_limit    — static/API entry (60 req/min/IP)
  - ui/auth_extended rate limiting — login lockout (10 failed / 5 min per email)
Keep this module for tests and historical compat, but do NOT wire new
production call sites into it. Removing it entirely is deferred to v3.13.

NOTE (S-P2-02): The in-memory rate limiter does NOT work across multiple
processes or workers. For production deployments with >1 worker, replace
with a shared store (Redis/Memcached) or database-backed rate limiter.
"""

import os
import time
from collections import defaultdict


_requests: dict[str, list[float]] = defaultdict(list)

_RATE_LIMIT = int(os.environ.get("YULEOSH_RATE_LIMIT", "100"))
_WINDOW_SECONDS = 60


def check_rate_limit(ip: str) -> tuple[bool, int]:
    """Check if the given IP has exceeded the rate limit.

    Returns:
        (allowed: bool, retry_after_seconds: int)
    """
    now = time.time()
    window_start = now - _WINDOW_SECONDS

    # Prune timestamps outside the window
    timestamps = _requests[ip]
    _requests[ip] = [t for t in timestamps if t > window_start]

    timestamps = _requests[ip]

    if len(timestamps) >= _RATE_LIMIT:
        # Compute retry-after: when the oldest entry in this window expires
        oldest = min(timestamps)
        retry_after = int(_WINDOW_SECONDS - (now - oldest)) + 1
        return False, max(retry_after, 1)

    timestamps.append(now)
    return True, 0


def get_remaining(ip: str) -> int:
    """Return how many requests the IP can still make in the current window."""
    now = time.time()
    window_start = now - _WINDOW_SECONDS
    timestamps = [t for t in _requests[ip] if t > window_start]
    _requests[ip] = timestamps
    return max(0, _RATE_LIMIT - len(timestamps))


def reset():
    """Clear all rate-limit state (useful in tests)."""
    _requests.clear()
