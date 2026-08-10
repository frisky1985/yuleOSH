# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""SQLite-backed shared rate limiter for multi-worker deployments.

Resolves S-P2-02: the in-memory limiter in ``api/ratelimit.py`` counts per
process, so a deployment with >1 worker each maintains its own budget.  This
module replaces that with a shared SQLite store: every worker writes to the
same ``rate_limit`` table, so the count is global across processes.

Semantics match ``api/ratelimit.py`` (sliding window):

  - same key: ``count >= limit`` inside the window → rejected
  - window slides: once ``now - window_start >= window_seconds`` the window
    is (lazily) reset and requests are allowed again
  - limit default: env ``YULEOSH_RATE_LIMIT`` (default 100 / minute)

Concurrency follows the project sqlite precedent
(``engine/checkpoint.py`` state_backend=sqlite):

  - ``PRAGMA journal_mode=WAL``
  - ``PRAGMA busy_timeout=10000``
  - connection-per-call (each method opens a fresh connection, so no
    cross-call state and no process lock-out)
  - the check() read-modify-write runs inside ``BEGIN IMMEDIATE`` so
    concurrent workers serialize on the write lock instead of losing counts.

DB location resolution order (``db_path`` argument wins over everything):

  1. env ``YULEOSH_RATE_DB``
  2. ``$OSH_HOME/.yuleosh/ratelimit.db``
  3. OS temp dir ``yuleosh-ratelimit.db``

NOTE (W2 / 2026-08-10): do NOT wire this into ``ui/server.py`` — that file
is being split in TD-004 and the integration belongs to the follow-up task.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

_DEFAULT_LIMIT = 100
_DEFAULT_WINDOW_SECONDS = 60
_TABLE = "rate_limit"


def _env_limit() -> int:
    """Read the rate limit from env, falling back to the default."""
    return int(os.environ.get("YULEOSH_RATE_LIMIT", str(_DEFAULT_LIMIT)))


def default_db_path() -> str:
    """Resolve the default SQLite db path (env YULEOSH_RATE_DB → OSH_HOME → temp)."""
    env_db = os.environ.get("YULEOSH_RATE_DB")
    if env_db:
        return env_db
    osh_home = os.environ.get("OSH_HOME")
    if osh_home:
        return str(Path(osh_home) / ".yuleosh" / "ratelimit.db")
    return str(Path(tempfile.gettempdir()) / "yuleosh-ratelimit.db")


class RateLimitStore:
    """Shared sliding-window rate-limit store backed by a single SQLite db.

    Table schema::

        rate_limit (
            key          TEXT PRIMARY KEY,   -- IP / caller identity
            window_start REAL NOT NULL,      -- start of the current window
            count        INTEGER NOT NULL    -- requests admitted in window
        )

    Safe for concurrent access from many workers: WAL + busy_timeout + a
    fresh connection per call, with check() serialized via BEGIN IMMEDIATE.
    """

    def __init__(
        self,
        db_path: str | None = None,
        limit: int | None = None,
        window_seconds: int | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.db_path = db_path or default_db_path()
        self.limit = _env_limit() if limit is None else int(limit)
        self.window_seconds = (
            _DEFAULT_WINDOW_SECONDS if window_seconds is None else int(window_seconds)
        )
        self._clock = clock or time.time
        self._init_schema()

    # -- connection ---------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a fresh connection: WAL + busy_timeout + connection-per-call."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_schema(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {_TABLE} ("
                "key TEXT PRIMARY KEY, window_start REAL NOT NULL,"
                " count INTEGER NOT NULL)"
            )
            conn.commit()
        finally:
            conn.close()

    # -- public API ---------------------------------------------------

    def check(
        self,
        key: str,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> tuple[bool, int]:
        """Record one request for ``key``; return (allowed, remaining).

        Mirrors ``api/ratelimit.check_rate_limit`` semantics: a request is
        allowed while ``count < limit`` inside the current window; once the
        window expires the counter lazily resets.  The read-modify-write is
        wrapped in ``BEGIN IMMEDIATE`` so concurrent workers serialize and no
        count is lost (busy_timeout absorbs lock contention instead of
        raising "database is locked").
        """
        limit = self.limit if limit is None else int(limit)
        window = self.window_seconds if window_seconds is None else int(window_seconds)
        now = self._clock()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                f"SELECT window_start, count FROM {_TABLE} WHERE key=?", (key,)
            ).fetchone()
            if row is None:
                conn.execute(
                    f"INSERT INTO {_TABLE} (key, window_start, count) VALUES (?, ?, 1)",
                    (key, now),
                )
                conn.commit()
                return True, max(0, limit - 1)
            window_start, count = row
            if now - window_start >= window:
                # Window expired → slide: open a fresh window with this request.
                conn.execute(
                    f"UPDATE {_TABLE} SET window_start=?, count=1 WHERE key=?",
                    (now, key),
                )
                conn.commit()
                return True, max(0, limit - 1)
            if count >= limit:
                conn.rollback()
                return False, 0
            conn.execute(
                f"UPDATE {_TABLE} SET count=? WHERE key=?", (count + 1, key)
            )
            conn.commit()
            return True, max(0, limit - count - 1)
        finally:
            conn.close()

    def get_remaining(
        self,
        key: str,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> int:
        """Return how many requests ``key`` can still make in the window."""
        limit = self.limit if limit is None else int(limit)
        window = self.window_seconds if window_seconds is None else int(window_seconds)
        now = self._clock()
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT window_start, count FROM {_TABLE} WHERE key=?", (key,)
            ).fetchone()
            if row is None:
                return limit
            window_start, count = row
            if now - window_start >= window:
                return limit
            return max(0, limit - count)
        finally:
            conn.close()

    def window_remaining_seconds(self, key: str, window_seconds: int) -> float:
        """Seconds until the current window slides for ``key`` (0 when absent/expired).

        Used by callers that need a ``Retry-After`` value matching the old
        in-memory limiter's semantics (window - time since window start).
        """
        now = self._clock()
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT window_start FROM {_TABLE} WHERE key=?", (key,)
            ).fetchone()
            if row is None:
                return 0.0
            return max(0.0, window_seconds - (now - row[0]))
        finally:
            conn.close()

    def reset(self) -> None:
        """Clear all rate-limit state (useful in tests)."""
        conn = self._connect()
        try:
            conn.execute(f"DELETE FROM {_TABLE}")
            conn.commit()
        finally:
            conn.close()


def check_rate_limit_shared(
    key: str,
    limit: int | None = None,
    window_seconds: int = _DEFAULT_WINDOW_SECONDS,
    db_path: str | None = None,
) -> tuple[bool, int]:
    """Shared-store counterpart of ``api/ratelimit.check_rate_limit``.

    Args:
        key: caller identity (e.g. client IP).
        limit: max requests per window (default: env ``YULEOSH_RATE_LIMIT``).
        window_seconds: sliding window length (default 60).
        db_path: SQLite db path (default: env ``YULEOSH_RATE_DB`` →
            ``$OSH_HOME/.yuleosh/ratelimit.db`` → temp dir).

    Returns:
        (allowed: bool, remaining: int) — remaining requests left in the
        current window (0 when rejected).
    """
    store = RateLimitStore(db_path=db_path)
    return store.check(key, limit=limit, window_seconds=window_seconds)


def get_remaining_shared(
    key: str,
    limit: int | None = None,
    window_seconds: int = _DEFAULT_WINDOW_SECONDS,
    db_path: str | None = None,
) -> int:
    """Shared-store counterpart of ``api/ratelimit.get_remaining``."""
    store = RateLimitStore(db_path=db_path)
    return store.get_remaining(key, limit=limit, window_seconds=window_seconds)


def reset_shared(db_path: str | None = None) -> None:
    """Clear all shared rate-limit state (useful in tests)."""
    RateLimitStore(db_path=db_path).reset()
