# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for the SQLite-backed shared rate limiter (W2, api/ratelimit_shared).

Covers the Done criteria:
  W2-1  module importable, sqlite backend usable
  W2-2  same-key over-limit rejected; window slides → recovery
  W2-3  concurrent multi-connection writes never raise "database is locked"
  W2-4  signature shape matches api/ratelimit.check_rate_limit
  W2-6  (ruff is run separately)

All db files live under pytest tmp_path — nothing is written to .osh/.
"""

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from yuleosh.api.ratelimit_shared import (
    RateLimitStore,
    check_rate_limit_shared,
    default_db_path,
    get_remaining_shared,
    reset_shared,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeClock:
    """Injectable clock for deterministic window-slide tests."""

    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def allowed_requests(store: RateLimitStore, key: str, n: int) -> int:
    """Make n requests, return how many were allowed."""
    allowed = 0
    for _ in range(n):
        ok, _ = store.check(key)
        allowed += int(ok)
    return allowed


# ---------------------------------------------------------------------------
# W2-1 / W2-4: importable, signature-compatible, sqlite backend usable
# ---------------------------------------------------------------------------


def test_module_importable_and_signature(tmp_path):
    import inspect

    sig = inspect.signature(check_rate_limit_shared)
    params = list(sig.parameters)
    assert params[:4] == ["key", "limit", "window_seconds", "db_path"]
    # Same shape as api/ratelimit.check_rate_limit: single identity arg
    # first, returns a (bool, int) tuple.
    from yuleosh.api.ratelimit import check_rate_limit

    legacy_params = list(inspect.signature(check_rate_limit).parameters)
    assert len(legacy_params) == 1  # check_rate_limit(ip)
    assert len(sig.parameters) >= 4  # shared variant is a superset


def test_sqlite_backend_creates_table(tmp_path):
    db = tmp_path / "rl.db"
    store = RateLimitStore(db_path=str(db), limit=10)
    ok, remaining = store.check("ip-1")
    assert ok is True
    assert remaining == 9
    # Schema persisted: table exists with expected columns.
    conn = sqlite3.connect(str(db))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(rate_limit)")]
    assert cols == ["key", "window_start", "count"]
    conn.close()


def test_wal_and_busy_timeout_pragmas(tmp_path):
    db = tmp_path / "rl.db"
    RateLimitStore(db_path=str(db), limit=10)
    conn = sqlite3.connect(str(db))
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    conn.close()


# ---------------------------------------------------------------------------
# W2-2: limit semantics (same key, window slide, independent keys)
# ---------------------------------------------------------------------------


def test_basic_rate_limit(tmp_path):
    store = RateLimitStore(db_path=str(tmp_path / "rl.db"), limit=3)
    assert store.check("k") == (True, 2)
    assert store.check("k") == (True, 1)
    assert store.check("k") == (True, 0)
    ok, remaining = store.check("k")  # 4th within window → rejected
    assert ok is False
    assert remaining == 0


def test_limit_defaults_to_env(tmp_path, monkeypatch):
    monkeypatch.setenv("YULEOSH_RATE_LIMIT", "5")
    store = RateLimitStore(db_path=str(tmp_path / "rl.db"))
    assert store.limit == 5
    assert allowed_requests(store, "k", 5) == 5
    assert store.check("k") == (False, 0)


def test_window_slides_after_expiry(tmp_path):
    clock = FakeClock()
    store = RateLimitStore(db_path=str(tmp_path / "rl.db"), limit=3, clock=clock)
    assert allowed_requests(store, "k", 3) == 3
    assert store.check("k") == (False, 0)  # still inside the window

    clock.advance(60.0)  # window fully elapsed
    ok, remaining = store.check("k")  # sliding window → allowed again
    assert ok is True
    assert remaining == 2


def test_window_start_reset_after_expiry(tmp_path):
    clock = FakeClock()
    db = tmp_path / "rl.db"
    store = RateLimitStore(db_path=str(db), limit=3, clock=clock)
    allowed_requests(store, "k", 3)
    clock.advance(60.0)
    assert store.check("k") == (True, 2)
    # Back inside the window again: 3 more → 4th rejected (window reset, not stale).
    assert store.check("k") == (True, 1)
    assert store.check("k") == (True, 0)
    assert store.check("k") == (False, 0)


def test_different_keys_independent(tmp_path):
    db = str(tmp_path / "rl.db")
    store_a = RateLimitStore(db_path=db, limit=2)
    store_b = RateLimitStore(db_path=db, limit=2)
    assert store_a.check("key-A") == (True, 1)
    assert store_a.check("key-A") == (True, 0)
    assert store_a.check("key-A") == (False, 0)  # key-A exhausted
    assert store_b.check("key-B") == (True, 1)  # key-B untouched


def test_get_remaining_and_reset(tmp_path):
    db = str(tmp_path / "rl.db")
    store = RateLimitStore(db_path=db, limit=10)
    assert get_remaining_shared("k", limit=10, db_path=db) == 10
    store.check("k")
    store.check("k")
    assert get_remaining_shared("k", limit=10, db_path=db) == 8
    reset_shared(db_path=db)
    assert get_remaining_shared("k", limit=10, db_path=db) == 10


# ---------------------------------------------------------------------------
# Shared-storage proof: counts survive across separate store instances
# ---------------------------------------------------------------------------


def test_count_shared_across_store_instances(tmp_path):
    """Two independent store objects on the same db share one counter —
    this is what makes the limiter work across workers."""
    db = str(tmp_path / "rl.db")
    s1 = RateLimitStore(db_path=db, limit=3)
    s2 = RateLimitStore(db_path=db, limit=3)
    s3 = RateLimitStore(db_path=db, limit=3)
    assert s1.check("ip") == (True, 2)
    assert s2.check("ip") == (True, 1)
    assert s3.check("ip") == (True, 0)
    assert s1.check("ip") == (False, 0)  # s1 sees what s2/s3 recorded


# ---------------------------------------------------------------------------
# W2-3: concurrency — many connections, no "database is locked"
# ---------------------------------------------------------------------------


def test_concurrent_threads_no_lock_error(tmp_path):
    """N threads × M requests each on the same db: busy_timeout absorbs
    contention; no sqlite3.OperationalError("database is locked"); the
    shared counter admits exactly limit requests then rejects the rest."""
    db = str(tmp_path / "rl.db")
    limit = 50
    threads = 8
    per_thread = 20
    _ = RateLimitStore(db_path=db, limit=limit)  # pre-create schema deterministically

    def worker(_):
        # Fresh store per thread → every call opens its own connection.
        local = RateLimitStore(db_path=db, limit=limit)
        return [local.check("shared-key") for _ in range(per_thread)]

    with ThreadPoolExecutor(max_workers=threads) as ex:
        results = list(ex.map(worker, range(threads)))

    flat = [r for batch in results for r in batch]
    allowed = sum(1 for ok, _ in flat if ok)
    assert allowed == limit
    assert len(flat) - allowed == threads * per_thread - limit  # rest rejected
    # No rejected call reports a bogus positive remaining.
    assert all(rem == 0 for ok, rem in flat if not ok)


def test_concurrent_threads_mixed_keys(tmp_path):
    db = str(tmp_path / "rl.db")
    keys = [f"ip-{i}" for i in range(4)]
    per_thread = 25
    threads = 8
    store = RateLimitStore(db_path=db, limit=per_thread * threads + 1)  # never hit limit

    def worker(tid):
        local = RateLimitStore(db_path=db)
        return [local.check(keys[(tid + i) % len(keys)]) for i in range(per_thread)]

    with ThreadPoolExecutor(max_workers=threads) as ex:
        results = list(ex.map(worker, range(threads)))
    assert sum(1 for batch in results for ok, _ in batch if ok) == threads * per_thread
    # All keys counted independently.
    for key in keys:
        assert get_remaining_shared(key, limit=store.limit, db_path=db) == (
            store.limit - threads * per_thread // len(keys)
        )


def test_concurrent_processes_no_lock_error(tmp_path):
    """Multi-process workers on one db (spawn, like a real deployment)."""
    import multiprocessing as mp

    db = str(tmp_path / "rl.db")
    limit = 40
    procs = 4
    per_proc = 15
    RateLimitStore(db_path=db, limit=limit)

    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=procs) as pool:
        results = pool.map(_proc_worker, [(db, limit, per_proc)] * procs)

    flat = [r for batch in results for r in batch]
    allowed = sum(1 for ok, _ in flat if ok)
    assert allowed == limit
    assert len(flat) - allowed == procs * per_proc - limit


def _proc_worker(args):
    """Module-level worker so spawn can pickle it (see test above)."""
    db, limit, per_proc = args
    from yuleosh.api.ratelimit_shared import check_rate_limit_shared

    return [
        check_rate_limit_shared("proc-key", limit=limit, db_path=db)
        for _ in range(per_proc)
    ]


# ---------------------------------------------------------------------------
# env configuration
# ---------------------------------------------------------------------------


def test_env_db_path_config(tmp_path, monkeypatch):
    db = tmp_path / "env-ratelimit.db"
    monkeypatch.setenv("YULEOSH_RATE_DB", str(db))
    assert default_db_path() == str(db)
    ok, _ = check_rate_limit_shared("k")
    assert ok is True
    assert db.exists()


def test_default_db_path_osh_home(tmp_path, monkeypatch):
    monkeypatch.delenv("YULEOSH_RATE_DB", raising=False)
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    assert default_db_path() == str(tmp_path / ".yuleosh" / "ratelimit.db")
    ok, _ = check_rate_limit_shared("k")
    assert ok is True
    assert (tmp_path / ".yuleosh" / "ratelimit.db").exists()


def test_default_db_path_fallback_temp(tmp_path, monkeypatch):
    monkeypatch.delenv("YULEOSH_RATE_DB", raising=False)
    monkeypatch.delenv("OSH_HOME", raising=False)
    import tempfile

    assert default_db_path() == str(
        Path(tempfile.gettempdir()) / "yuleosh-ratelimit.db"
    )


def test_env_limit_applies_to_module_function(tmp_path, monkeypatch):
    monkeypatch.setenv("YULEOSH_RATE_LIMIT", "3")
    db = str(tmp_path / "rl.db")
    for _ in range(3):
        ok, _ = check_rate_limit_shared("k", db_path=db)
        assert ok is True
    ok, remaining = check_rate_limit_shared("k", db_path=db)
    assert ok is False
    assert remaining == 0


# ---------------------------------------------------------------------------
# Misc: retry-visible behavior and old-window pruning
# ---------------------------------------------------------------------------


def test_window_does_not_accumulate_across_windows(tmp_path):
    """Requests from a previous window must not count against the next one."""
    clock = FakeClock()
    store = RateLimitStore(db_path=str(tmp_path / "rl.db"), limit=2, clock=clock)
    allowed_requests(store, "k", 2)
    assert store.check("k") == (False, 0)
    clock.advance(60.0)
    # New window starts clean: exactly 2 allowed again, then reject.
    assert allowed_requests(store, "k", 2) == 2
    assert store.check("k") == (False, 0)


def test_pragmas_verified_on_every_connection(tmp_path):
    """Connection-per-call: a fresh connection each time still gets WAL + timeout."""
    db = str(tmp_path / "rl.db")
    store = RateLimitStore(db_path=db, limit=5)
    for _ in range(5):
        conn = store._connect()
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        conn.close()


def test_time_is_monotonic_reasonable():
    """Sanity: default clock is time.time (matches ratelimit.py)."""
    store = RateLimitStore(db_path=":memory:", limit=1)
    assert abs(store._clock() - time.time()) < 1.0
