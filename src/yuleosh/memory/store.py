# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Memory — structured fact store + session search.

Implements the Hermes-style memory capability for yuleOSH:

- **Fact Store**: cross-session structured facts with entity resolution,
  trust scoring, and relationship reasoning. Facts are remembered once and
  recalled by entity/category/content — the foundation for "the tool learns
  your project" behavior.
- **Session Search**: FTS5 full-text index over recorded session/decision
  logs, so past work is queryable from the CLI.

The store is SQLite-backed (thread-safe, WAL mode) at `.yuleosh/memory.db`.
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    """ISO-8601 UTC timestamp for records."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MemoryStore:
    """SQLite-backed fact + session memory store.

    Thread-safe (connection-per-thread). Uses WAL journaling. Schema is
    created idempotently — repeated setup never errors.
    """

    # ── Constants ────────────────────────────────────────────────────────

    DEFAULT_TRUST = 0.5          # neutral starting trust
    TRUST_DELTA = 0.1            # increment on each recall hit
    TRUST_MAX = 1.0
    TRUST_MIN = 0.0

    # ── Construction ─────────────────────────────────────────────────────

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            env_db = os.environ.get("YULEOSH_MEMORY_DB")
            if env_db:
                db_path = env_db
            else:
                # Repo-local default: <repo>/.yuleosh/memory.db
                osh_home = Path(__file__).resolve().parent.parent.parent.parent
                db_path = str(osh_home / ".yuleosh" / "memory.db")
        self._db_path = db_path
        self._local = threading.local()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── Connection management ────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ── Schema init (idempotent) ─────────────────────────────────────────

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'general',
                content TEXT NOT NULL,
                trust REAL NOT NULL DEFAULT 0.5,
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                recall_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_memory_facts_entity
                ON memory_facts(entity);
            CREATE INDEX IF NOT EXISTS idx_memory_facts_category
                ON memory_facts(category);
            CREATE INDEX IF NOT EXISTS idx_memory_facts_trust
                ON memory_facts(trust);

            CREATE TABLE IF NOT EXISTS session_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'note',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_session_logs_key
                ON session_logs(session_key);

            -- FTS5 virtual table for full-text session search.
            -- External content table over session_logs. NOTE: external
            -- content tables do NOT auto-index — triggers keep the FTS
            -- index in sync on INSERT/DELETE.
            CREATE VIRTUAL TABLE IF NOT EXISTS session_logs_fts USING fts5(
                content,
                content='session_logs',
                content_rowid='id'
            );
            CREATE TRIGGER IF NOT EXISTS session_logs_ai AFTER INSERT ON session_logs BEGIN
                INSERT INTO session_logs_fts(rowid, content) VALUES (new.id, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS session_logs_ad AFTER DELETE ON session_logs BEGIN
                INSERT INTO session_logs_fts(session_logs_fts, rowid, content)
                VALUES ('delete', old.id, old.content);
            END;
        """)
        conn.commit()

        # Backfill FTS index for any pre-existing rows (idempotent).
        conn.execute("INSERT INTO session_logs_fts(session_logs_fts) VALUES ('rebuild')")
        conn.commit()

    # ── Fact CRUD ────────────────────────────────────────────────────────

    def remember(self, content: str, entity: str = "",
                 category: str = "general", tags: str = "",
                 trust: float | None = None) -> dict:
        """Store a new fact. Returns the created row dict."""
        conn = self._get_conn()
        now = _now()
        t = self.DEFAULT_TRUST if trust is None else max(self.TRUST_MIN,
                                                         min(self.TRUST_MAX,
                                                             float(trust)))
        cur = conn.execute(
            "INSERT INTO memory_facts "
            "(entity, category, content, trust, tags, created_at, updated_at, recall_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (entity, category, content, t, tags, now, now),
        )
        conn.commit()
        fid = cur.lastrowid
        if fid is None:
            # Extremely defensive — INSERT just succeeded, lastrowid is set.
            raise RuntimeError("memory fact insert did not return an id")
        return self.get_fact(fid)

    def get_fact(self, fact_id: int) -> dict | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM memory_facts WHERE id = ?",
                           (fact_id,)).fetchone()
        return dict(row) if row else None

    def list_facts(self, category: str | None = None,
                   entity: str | None = None,
                   limit: int = 50, offset: int = 0) -> list[dict]:
        """List facts with optional filters. Ordered by trust DESC, newest first."""
        conn = self._get_conn()
        clauses, params = [], []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if entity:
            clauses.append("entity = ?")
            params.append(entity)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([limit, offset])
        rows = conn.execute(
            f"SELECT * FROM memory_facts {where} "
            "ORDER BY trust DESC, updated_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def recall(self, query: str, entity: str | None = None,
               category: str | None = None, limit: int = 20) -> list[dict]:
        """Recall facts matching query text (LIKE over content/tags) with
        optional entity/category filters. Matching facts get a small trust
        bump (use-based reinforcement)."""
        conn = self._get_conn()
        clauses = ["(content LIKE ? OR tags LIKE ? OR entity LIKE ?)"]
        params = [f"%{query}%", f"%{query}%", f"%{query}%"]
        if entity:
            clauses.append("entity = ?")
            params.append(entity)
        if category:
            clauses.append("category = ?")
            params.append(category)
        where = " AND ".join(clauses)
        rows = conn.execute(
            f"SELECT * FROM memory_facts WHERE {where} "
            "ORDER BY trust DESC, updated_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        results = [dict(r) for r in rows]

        # Trust reinforcement: each hit increments recall_count + trust,
        # capped at TRUST_MAX. Facts used often become more trusted.
        for r in results:
            new_count = r["recall_count"] + 1
            new_trust = min(self.TRUST_MAX, r["trust"] + self.TRUST_DELTA)
            conn.execute(
                "UPDATE memory_facts SET recall_count = ?, trust = ?, "
                "updated_at = ? WHERE id = ?",
                (new_count, new_trust, _now(), r["id"]),
            )
        conn.commit()
        return results

    def forget(self, fact_id: int) -> bool:
        """Delete a fact by id. Returns True if a row was removed."""
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM memory_facts WHERE id = ?", (fact_id,))
        conn.commit()
        return cur.rowcount > 0

    def update_trust(self, fact_id: int, trust: float) -> dict | None:
        """Explicitly set trust for a fact."""
        conn = self._get_conn()
        t = max(self.TRUST_MIN, min(self.TRUST_MAX, float(trust)))
        cur = conn.execute(
            "UPDATE memory_facts SET trust = ?, updated_at = ? WHERE id = ?",
            (t, _now(), fact_id),
        )
        conn.commit()
        return self.get_fact(fact_id) if cur.rowcount > 0 else None

    def stats(self) -> dict:
        """Return memory statistics."""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
        sessions = conn.execute("SELECT COUNT(*) FROM session_logs").fetchone()[0]
        by_category = {
            r["category"]: r["n"]
            for r in conn.execute(
                "SELECT category, COUNT(*) AS n FROM memory_facts "
                "GROUP BY category ORDER BY n DESC"
            )
        }
        return {
            "facts": total,
            "sessions": sessions,
            "by_category": by_category,
        }

    # ── Session log CRUD ─────────────────────────────────────────────────

    def log_session(self, content: str, session_key: str = "",
                    kind: str = "note") -> dict:
        """Record a session/decision log entry (searchable via FTS5)."""
        conn = self._get_conn()
        now = _now()
        cur = conn.execute(
            "INSERT INTO session_logs (session_key, content, kind, created_at) "
            "VALUES (?, ?, ?, ?)",
            (session_key, content, kind, now),
        )
        conn.commit()
        return {"id": cur.lastrowid, "session_key": session_key,
                "content": content, "kind": kind, "created_at": now}

    def search_sessions(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search over session logs using FTS5."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT sl.id, sl.session_key, sl.content, sl.kind, sl.created_at, "
                "       snippet(session_logs_fts, 0, '[', ']', '…', 12) AS snippet "
                "FROM session_logs_fts "
                "JOIN session_logs sl ON sl.id = session_logs_fts.rowid "
                "WHERE session_logs_fts MATCH ? "
                "ORDER BY sl.created_at DESC LIMIT ?",
                (query, limit),
            ).fetchall()
            results = [dict(r) for r in rows]
            for r in results:
                r["snippet"] = r["snippet"] or r["content"][:120]
            return results
        except sqlite3.OperationalError:
            # Malformed FTS query (e.g. stray quote) — fall back to LIKE.
            rows = conn.execute(
                "SELECT id, session_key, content, kind, created_at, "
                "       substr(content, 1, 120) AS snippet "
                "FROM session_logs WHERE content LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]
