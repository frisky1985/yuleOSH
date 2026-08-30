#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH Persistent Storage — auto-selects SQLite or PostgreSQL backend.

Usage:
    YULEOSH_DB_URL=postgresql://user:pass@host:5432/dbname  → PostgreSQL
    YULEOSH_DB=/path/to/store.db or unset                  → SQLite (default)
"""
import json, os, re, sqlite3, threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.store_interface import AbstractStore


def _session_token_hash(token: str) -> str:
    """Return the sha256 hexdigest of a session token (P1-6).

    The raw JWT is never persisted — only this hash, so a database leak
    does not yield usable bearer tokens.
    """
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Store(AbstractStore):
    """SQLite-backed persistent store. Thread-safe, testable.

    Falls back to PostgresStore when YULEOSH_DB_URL starts with postgresql://
    """

    _instances = {}
    _lock = threading.Lock()

    def __new__(cls, db_path: Optional[str] = None):
        db_url = os.environ.get("YULEOSH_DB_URL", "")
        if db_url.startswith("postgresql://"):
            from yuleosh.store_pg import PostgresStore
            return PostgresStore.__new__(PostgresStore, db_url)

        key = db_path or "default"
        with cls._lock:
            if key not in cls._instances:
                instance = super().__new__(cls)
                db = db_path or os.environ.get(
                    "YULEOSH_DB",
                    str(Path(os.environ.get("OSH_HOME", ".")) / ".yuleosh" / "store.db"),
                )
                Path(db).parent.mkdir(parents=True, exist_ok=True)
                instance.db_path = db
                instance.conn = sqlite3.connect(db, check_same_thread=False)
                instance.conn.row_factory = sqlite3.Row
                instance._migrate()
                cls._instances[key] = instance
            return cls._instances[key]

    @classmethod
    def reset(cls):
        """Clear all instances (for testing)."""
        cls._instances = {}

    # Current migration version — bump to trigger new table creation
    _MIGRATION_VERSION = 8  # v0.9.0: usage/subscription tables + org tier; v8: usage_log user attribution

    def _migrate(self):
        # Create or update meta table for tracking migration version
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS pipelines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                spec_path TEXT, status TEXT DEFAULT 'created',
                created_at TEXT, updated_at TEXT,
                artifacts TEXT DEFAULT '{}', steps TEXT DEFAULT '[]', errors TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS ci_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                layer INTEGER NOT NULL, commit_hash TEXT, status TEXT DEFAULT 'running',
                started_at TEXT, completed_at TEXT,
                stages TEXT DEFAULT '[]', coverage TEXT, errors TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_name TEXT NOT NULL, decision TEXT, status TEXT DEFAULT 'running',
                created_at TEXT, data TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, type TEXT, path TEXT, size INTEGER, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL, description TEXT, spec_path TEXT,
                created_at TEXT, updated_at TEXT
            );
        """)
        self.conn.commit()

        # Multi-tenant auth tables (migration v2+)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS _meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                password_hash TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (org_id) REFERENCES organizations(id),
                UNIQUE(org_id, email)
            );
            CREATE TABLE IF NOT EXISTS org_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (org_id) REFERENCES organizations(id),
                UNIQUE(org_id, slug)
            );
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                project_id INTEGER,
                resource TEXT NOT NULL,
                amount INTEGER NOT NULL DEFAULT 1,
                recorded_at TEXT NOT NULL,
                FOREIGN KEY (org_id) REFERENCES organizations(id)
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL UNIQUE,
                stripe_subscription_id TEXT,
                stripe_customer_id TEXT,
                tier TEXT NOT NULL DEFAULT 'community',
                status TEXT NOT NULL DEFAULT 'active',
                current_period_end TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (org_id) REFERENCES organizations(id)
            );
        """)
        self.conn.commit()

        # Session token hashing (P1-6 / S-P1-02): legacy plaintext JWT rows
        # (sha256 hexdigests are always exactly 64 chars) are migrated to
        # their sha256 hash so the DB never stores usable bearer tokens.
        #
        # W-4 (COR-W3 / Fix 7): the old ``WHERE length(token) != 64``
        # predicate assumed "64 chars == already hashed", but a plaintext JWT
        # whose payload happens to be exactly 64 characters (e.g. base64url
        # with ``-``/``_``) slipped through untouched.  Migration now checks
        # the token is a real sha256 hexdigest (``[0-9a-f]{64}``) and only
        # skips those; Python-side filtering avoids SQLite GLOB quirks and is
        # idempotent (already-hashed rows are untouched).
        legacy = self.conn.execute(
            "SELECT id, token FROM user_sessions"
        ).fetchall()
        _TOKEN_HEX64 = re.compile(r"[0-9a-f]{64}")
        for row in legacy:
            token = row["token"]
            # NULL/empty tokens: skip safely (W-4.4) — nothing to migrate.
            if not token or _TOKEN_HEX64.fullmatch(token):
                continue
            self.conn.execute(
                "UPDATE user_sessions SET token=? WHERE id=?",
                (_session_token_hash(token), row["id"]),
            )
        self.conn.commit()

        # API keys table (v4)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL,
                prefix TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked INTEGER NOT NULL DEFAULT 0
            );
        """)
        self.conn.commit()

        # Spec parsing cache table (v5)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS spec_cache (
                spec_path TEXT NOT NULL,
                mtime TEXT NOT NULL,
                result_json TEXT NOT NULL,
                cached_at TEXT NOT NULL,
                PRIMARY KEY (spec_path, mtime)
            );
        """)
        self.conn.commit()

        # Migration v3 — add stat tracking columns
        version = self.get_migration_version()
        if version < 3:
            self._run_migration_v3()
        if version < 6:
            self._run_migration_v6()
        if version < 7:
            self._run_migration_v7()
        if version < 8:
            self._run_migration_v8()

        # Record migration version
        self.conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('migration_version', ?)",
            (str(self._MIGRATION_VERSION),)
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Migration helpers
    # ------------------------------------------------------------------

    def _run_migration_v3(self):
        """Migration v3: add pipeline_run_count and last_active_at to projects."""
        from sqlite3 import OperationalError
        try:
            self.conn.execute(
                "ALTER TABLE projects ADD COLUMN pipeline_run_count INTEGER DEFAULT 0"
            )
        except OperationalError:
            pass
        try:
            self.conn.execute(
                "ALTER TABLE projects ADD COLUMN last_active_at TEXT"
            )
        except OperationalError:
            pass
        self.conn.commit()

    def _run_migration_v6(self):
        """Migration v6: add password_hash column to users (v0.8.0)."""
        from sqlite3 import OperationalError
        try:
            self.conn.execute(
                "ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT NULL"
            )
        except OperationalError:
            pass
        self.conn.commit()

    def _run_migration_v7(self):
        """Migration v7: add tier to organizations (v0.9.0)."""
        from sqlite3 import OperationalError
        try:
            self.conn.execute(
                "ALTER TABLE organizations ADD COLUMN tier TEXT DEFAULT 'pro'"
            )
        except OperationalError:
            pass
        self.conn.commit()

    def _run_migration_v8(self):
        """Migration v8: usage_log user attribution (Portal billing, 2026-08-10).

        Adds user_id / run_id / user_email columns so LLM token consumption
        can be attributed to the triggering user (audit / per-user split)
        without affecting historical rows (NULL).
        """
        from sqlite3 import OperationalError
        for sql in (
            "ALTER TABLE usage_log ADD COLUMN user_id INTEGER",
            "ALTER TABLE usage_log ADD COLUMN run_id TEXT",
            "ALTER TABLE usage_log ADD COLUMN user_email TEXT",
        ):
            try:
                self.conn.execute(sql)
            except OperationalError:
                pass
        self.conn.commit()

    # ------------------------------------------------------------------
    # Usage Statistics
    # ------------------------------------------------------------------

    def record_activity(self, project_name: str):
        """Increment pipeline_run_count and update last_active_at for a project."""
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE projects SET pipeline_run_count = COALESCE(pipeline_run_count, 0) + 1, last_active_at = ? WHERE name = ?",
            (now, project_name)
        )
        self.conn.commit()

    def get_total_users(self) -> int:
        """Return total users across all organizations."""
        cur = self.conn.execute("SELECT COUNT(*) as c FROM users")
        return cur.fetchone()["c"]

    def get_total_projects(self) -> int:
        """Return total projects (both legacy and org-scoped)."""
        legacy = self.conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()["c"]
        org = self.conn.execute("SELECT COUNT(*) as c FROM org_projects").fetchone()["c"]
        return legacy + org

    def get_usage_stats(self) -> dict:
        """Return aggregated usage statistics."""
        conn = self.conn
        pipe_count = conn.execute("SELECT COUNT(*) as c FROM pipelines").fetchone()["c"]
        ci_count = conn.execute("SELECT COUNT(*) as c FROM ci_runs").fetchone()["c"]
        review_count = conn.execute("SELECT COUNT(*) as c FROM reviews").fetchone()["c"]
        ev_count = conn.execute("SELECT COUNT(*) as c FROM evidence").fetchone()["c"]
        proj_count = conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()["c"]
        org_count = conn.execute("SELECT COUNT(*) as c FROM organizations").fetchone()["c"]
        user_count = self.get_total_users()

        # Aggregate pipeline statuses
        pipe_statuses = conn.execute(
            "SELECT status, COUNT(*) as c FROM pipelines GROUP BY status"
        ).fetchall()

        # Aggregate CI layer statistics
        ci_layers = conn.execute(
            "SELECT layer, COUNT(*) as c FROM ci_runs GROUP BY layer"
        ).fetchall()

        return {
            "total_pipelines": pipe_count,
            "total_ci_runs": ci_count,
            "total_reviews": review_count,
            "total_evidence": ev_count,
            "total_projects": proj_count,
            "total_organizations": org_count,
            "total_users": user_count,
            "pipeline_statuses": {r["status"]: r["c"] for r in pipe_statuses},
            "ci_by_layer": {str(r["layer"]): r["c"] for r in ci_layers},
        }

    # A4 (v3.8.0): Store interface methods — eliminate bare conn.execute
    # in api/project.py / api/stats.py (SHALL-A4.1/4.2).

    def list_projects(self) -> list:
        """SELECT * FROM projects ORDER BY created_at DESC (A4)."""
        cur = self.conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def update_project_spec_path(self, name: str, spec_path: str):
        """UPDATE projects SET spec_path=? WHERE name=? (A4)."""
        self.conn.execute(
            "UPDATE projects SET spec_path=? WHERE name=?", (spec_path, name))
        self.conn.commit()

    def get_project_stats(self) -> dict:
        """Aggregate project statistics across all store tables (A4).

        Mirrors the v3.7.0 api/project.py _project_stats query exactly
        (SHALL-A4.4): counts + pipeline status distribution.
        """
        conn = self.conn
        pipe_count = conn.execute("SELECT COUNT(*) as c FROM pipelines").fetchone()["c"]
        ci_count = conn.execute("SELECT COUNT(*) as c FROM ci_runs").fetchone()["c"]
        review_count = conn.execute("SELECT COUNT(*) as c FROM reviews").fetchone()["c"]
        ev_count = conn.execute("SELECT COUNT(*) as c FROM evidence").fetchone()["c"]
        proj_count = conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()["c"]
        pipe_statuses = conn.execute(
            "SELECT status, COUNT(*) as c FROM pipelines GROUP BY status"
        ).fetchall()
        return {
            "projects": proj_count,
            "pipelines": pipe_count,
            "pipeline_statuses": {r["status"]: r["c"] for r in pipe_statuses},
            "ci_runs": ci_count,
            "reviews": review_count,
            "evidence_files": ev_count,
        }

    def count_ci_passed(self) -> int:
        """SELECT COUNT(*) FROM ci_runs WHERE status='passed' (A4)."""
        try:
            cur = self.conn.execute(
                "SELECT COUNT(*) as c FROM ci_runs WHERE status='passed'")
            return cur.fetchone()["c"]
        except Exception:
            return 0

    def get_pipeline_trend_rows(self, start_iso: str) -> list:
        """Pipeline rows since a start timestamp (A4 — stats trends)."""
        cur = self.conn.execute(
            "SELECT created_at, status FROM pipelines WHERE created_at >= ? "
            "ORDER BY created_at", (start_iso,))
        return [dict(r) for r in cur.fetchall()]

    def get_ci_trend_rows(self, start_iso: str) -> list:
        """CI run rows since a start timestamp (A4 — stats trends)."""
        cur = self.conn.execute(
            "SELECT started_at, status FROM ci_runs WHERE started_at >= ? "
            "ORDER BY started_at", (start_iso,))
        return [dict(r) for r in cur.fetchall()]

    def get_review_trend_rows(self, start_iso: str) -> list:
        """Review rows since a start timestamp (A4 — stats trends)."""
        cur = self.conn.execute(
            "SELECT created_at FROM reviews WHERE created_at >= ? "
            "ORDER BY created_at", (start_iso,))
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Multi-tenant: Organizations
    # ------------------------------------------------------------------

    def create_organization(self, name: str, slug: str) -> dict:
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
            (name, slug, now)
        )
        self.conn.commit()
        return {"id": cur.lastrowid, "name": name, "slug": slug, "created_at": now}

    def get_organization(self, slug: str) -> Optional[dict]:
        cur = self.conn.execute("SELECT * FROM organizations WHERE slug=?", (slug,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_organization_by_id(self, org_id: int) -> Optional[dict]:
        cur = self.conn.execute("SELECT * FROM organizations WHERE id=?", (org_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def count_org_users(self, org_id: int) -> int:
        """Count users belonging to an org (Phase 9, billing usage)."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM users WHERE org_id=?", (org_id,)
        ).fetchone()
        return row[0] if row else 0

    def list_organizations(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM organizations ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Multi-tenant: Users
    # ------------------------------------------------------------------

    def create_user(self, org_id: int, email: str, role: str = "member", password_hash: str = None) -> dict:
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            "INSERT INTO users (org_id, email, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (org_id, email, role, password_hash, now)
        )
        self.conn.commit()
        return {"id": cur.lastrowid, "org_id": org_id, "email": email, "role": role, "password_hash": password_hash, "created_at": now}

    def get_user(self, org_id: int, email: str) -> Optional[dict]:
        cur = self.conn.execute(
            "SELECT * FROM users WHERE org_id=? AND email=?", (org_id, email)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        cur = self.conn.execute("SELECT * FROM users WHERE id=?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_users(self, org_id: int) -> list[dict]:
        cur = self.conn.execute(
            "SELECT id, email, role, created_at FROM users WHERE org_id=? ORDER BY created_at",
            (org_id,)
        )
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Multi-tenant: Org-scoped Projects
    # ------------------------------------------------------------------

    def create_org_project(self, org_id: int, name: str, slug: str, description: str = "") -> dict:
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            "INSERT INTO org_projects (org_id, name, slug, description, created_at) VALUES (?, ?, ?, ?, ?)",
            (org_id, name, slug, description, now)
        )
        self.conn.commit()
        return {"id": cur.lastrowid, "org_id": org_id, "name": name, "slug": slug,
                "description": description, "created_at": now}

    def get_org_project(self, org_id: int, slug: str) -> Optional[dict]:
        cur = self.conn.execute(
            "SELECT * FROM org_projects WHERE org_id=? AND slug=?", (org_id, slug)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_org_project_by_id(self, project_id: int) -> Optional[dict]:
        cur = self.conn.execute("SELECT * FROM org_projects WHERE id=?", (project_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_org_projects(self, org_id: int) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM org_projects WHERE org_id=? ORDER BY created_at DESC", (org_id,)
        )
        return [dict(r) for r in cur.fetchall()]

    def update_org_project(self, org_id: int, slug: str, name: str = None,
                           new_slug: str = None, description: str = None):
        """UPDATE org_projects SET ... WHERE org_id=? AND slug=? (A4).

        Used to promote/rename a demo project in place without creating a
        duplicate row (the Dashboard lists projects by org_id + slug).
        """
        fields, params = [], []
        if name is not None:
            fields.append("name=?"); params.append(name)
        if new_slug is not None:
            fields.append("slug=?"); params.append(new_slug)
        if description is not None:
            fields.append("description=?"); params.append(description)
        if not fields:
            return
        params += [org_id, slug]
        self.conn.execute(
            "UPDATE org_projects SET " + ", ".join(fields) + " WHERE org_id=? AND slug=?",
            params,
        )
        self.conn.commit()

    def rename_project(self, old_name: str, new_name: str, new_description: str = None):
        """UPDATE projects SET name=?[, description=?] WHERE name=? (A4).

        Keeps the spec/pipeline chain (which resolves projects by name) pointing
        at the renamed project; spec_path is re-linked by the caller afterwards.
        """
        if new_description is not None:
            self.conn.execute(
                "UPDATE projects SET name=?, description=? WHERE name=?",
                (new_name, new_description, old_name),
            )
        else:
            self.conn.execute(
                "UPDATE projects SET name=? WHERE name=?", (new_name, old_name)
            )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Multi-tenant: Sessions
    # ------------------------------------------------------------------

    def create_session(self, user_id: int, token: str, ttl_hours: int = 24) -> dict:
        now = datetime.now()
        expires = datetime.fromtimestamp(now.timestamp() + ttl_hours * 3600)
        # Use space separator (SQLite-compatible format) so that
        # comparisons against datetime('now') work correctly.
        # isoformat() with 'T' separator sorts differently from SQLite's space.
        now_str = now.isoformat(sep=" ")
        exp_str = expires.isoformat(sep=" ")
        # P1-6 (S-P1-02): store only sha256(token) — the raw JWT (which
        # embeds user identity and stays valid for the TTL) must never be
        # persisted in the DB where a leak would enable session hijacking.
        token_hash = _session_token_hash(token)
        self.conn.execute(
            "INSERT OR REPLACE INTO user_sessions (user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, token_hash, now_str, exp_str)
        )
        self.conn.commit()
        return {"user_id": user_id, "token": token_hash, "created_at": now_str, "expires_at": exp_str}

    def get_session(self, token: str) -> Optional[dict]:
        token_hash = _session_token_hash(token)
        cur = self.conn.execute(
            "SELECT * FROM user_sessions WHERE token=? AND expires_at > datetime('now')",
            (token_hash,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def delete_session(self, token: str):
        token_hash = _session_token_hash(token)
        self.conn.execute("DELETE FROM user_sessions WHERE token=?", (token_hash,))
        self.conn.commit()

    def cleanup_expired_sessions(self):
        self.conn.execute(
            "DELETE FROM user_sessions WHERE expires_at <= datetime('now')"
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Spec parsing cache
    # ------------------------------------------------------------------

    def cache_spec_parse(self, spec_path: str, mtime: float, result: dict):
        """Cache spec parsing results keyed by path + mtime."""
        self.conn.execute(
            "INSERT OR REPLACE INTO spec_cache (spec_path, mtime, result_json, cached_at) VALUES (?, ?, ?, ?)",
            (spec_path, str(mtime), json.dumps(result), datetime.now().isoformat())
        )
        self.conn.commit()

    def get_cached_spec_parse(self, spec_path: str, mtime: float) -> Optional[dict]:
        """Return cached parse result if spec hasn't changed, else None."""
        cur = self.conn.execute(
            "SELECT result_json FROM spec_cache WHERE spec_path=? AND mtime=?",
            (spec_path, str(mtime))
        )
        row = cur.fetchone()
        if row:
            return json.loads(row["result_json"])
        return None

    def create_api_key(self, key_hash: str, label: str, prefix: str) -> dict:
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            "INSERT INTO api_keys (key_hash, label, prefix, created_at) VALUES (?, ?, ?, ?)",
            (key_hash, label, prefix, now)
        )
        self.conn.commit()
        return {"id": cur.lastrowid, "label": label, "prefix": prefix, "created_at": now, "revoked": 0}

    def get_api_key_by_hash(self, key_hash: str):
        cur = self.conn.execute(
            "SELECT * FROM api_keys WHERE key_hash=?", (key_hash,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_api_keys(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT id, label, prefix, created_at, last_used_at, revoked FROM api_keys ORDER BY created_at DESC"
        )
        return [dict(r) for r in cur.fetchall()]

    def revoke_api_key(self, key_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE api_keys SET revoked=1 WHERE id=? AND revoked=0", (key_id,)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def update_api_key_last_used(self, key_id: int):
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE api_keys SET last_used_at=? WHERE id=?", (now, key_id)
        )
        self.conn.commit()

    def get_migration_version(self) -> int:
        cur = self.conn.execute("SELECT value FROM _meta WHERE key='migration_version'")
        row = cur.fetchone()
        return int(row["value"]) if row else 0

    # ------------------------------------------------------------------
    # First-run Wizard
    # ------------------------------------------------------------------

    def is_wizard_completed(self) -> bool:
        """Check if the first-run wizard has been completed."""
        cur = self.conn.execute("SELECT value FROM _meta WHERE key='wizard_completed'")
        row = cur.fetchone()
        return row is not None and row["value"] == "1"

    def complete_wizard(self, org_id: int = 0):
        """Mark the first-run wizard as completed.

        Args:
            org_id: Organization ID for audit trail (default 0).
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('wizard_completed', '1')"
        )
        self.conn.commit()

    def save_pipeline(self, name: str, data: dict):
        self.conn.execute("""INSERT OR REPLACE INTO pipelines 
            (name, spec_path, status, created_at, updated_at, artifacts, steps, errors)
            VALUES (?,?,?,?,?,?,?,?)""", (
            name, data.get("spec_path",""), data.get("status","created"),
            data.get("created_at",datetime.now().isoformat()),
            data.get("updated_at",datetime.now().isoformat()),
            json.dumps(data.get("artifacts",{})), json.dumps(data.get("steps",[])),
            json.dumps(data.get("errors",[])),
        ))
        self.conn.commit()

    def get_pipeline(self, name: str) -> Optional[dict]:
        cur = self.conn.execute("SELECT * FROM pipelines WHERE name=?", (name,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_pipelines(self) -> list[dict]:
        cur = self.conn.execute("SELECT name,status,created_at,updated_at FROM pipelines ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def save_ci(self, data: dict):
        self.conn.execute("""INSERT INTO ci_runs 
            (layer, commit_hash, status, started_at, completed_at, stages, coverage, errors)
            VALUES (?,?,?,?,?,?,?,?)""", (
            data.get("layer",0), data.get("commit",""), data.get("status","running"),
            data.get("started_at",datetime.now().isoformat()), data.get("completed_at"),
            json.dumps(data.get("stages",[])), json.dumps(data.get("coverage")),
            json.dumps(data.get("errors",[])),
        ))
        self.conn.commit()

    def list_ci(self, limit: int = 10) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM ci_runs ORDER BY started_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def save_review(self, task_name: str, data: dict):
        self.conn.execute("""INSERT OR REPLACE INTO reviews
            (task_name, decision, status, created_at, data) VALUES (?,?,?,?,?)""",
            (task_name, data.get("decision"), data.get("status","running"),
             data.get("created_at",datetime.now().isoformat()), json.dumps(data)))
        self.conn.commit()

    def list_reviews(self, limit: int = 10) -> list[dict]:
        cur = self.conn.execute(
            "SELECT task_name,decision,status,created_at FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def log_evidence(self, name: str, type_: str, path: str, size: int = 0):
        self.conn.execute("INSERT INTO evidence (name,type,path,size,created_at) VALUES (?,?,?,?,?)",
            (name, type_, path, size, datetime.now().isoformat()))
        self.conn.commit()

    def list_evidence(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM evidence ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def init_project(self, name: str, description: str = ""):
        now = datetime.now().isoformat()
        self.conn.execute("INSERT OR IGNORE INTO projects (name,description,created_at,updated_at) VALUES (?,?,?,?)",
            (name, description, now, now))
        self.conn.commit()

    def get_project(self, name: str) -> Optional[dict]:
        cur = self.conn.execute("SELECT * FROM projects WHERE name=?", (name,))
        row = cur.fetchone()
        return dict(row) if row else None

    def setup(self):
        """Explicit initialization — runs migrations."""
        self._migrate()
        return self

    def close(self):
        self.conn.close()

    # ── v0.9.0: Usage & Subscription ─────────────────────────────────────────

    def record_usage(self, org_id: int, project_id: int, resource: str, amount: int,
                     user_id: int | None = None, run_id: str | None = None,
                     user_email: str | None = None):
        """Record a usage event.

        user_id / run_id / user_email (v8, 2026-08-10): optional user
        attribution so LLM token consumption can be split per user.
        Historical callers omit them → NULL columns, fully backward compatible.
        """
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO usage_log (org_id, project_id, resource, amount, recorded_at,"
            " user_id, run_id, user_email) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (org_id, project_id, resource, amount, now, user_id, run_id, user_email)
        )
        self.conn.commit()

    def get_monthly_usage(self, org_id: int) -> dict:
        """Get aggregated usage for the current month."""
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        rows = self.conn.execute(
            "SELECT resource, SUM(amount) FROM usage_log WHERE org_id=? AND recorded_at >= ? GROUP BY resource",
            (org_id, month_start)
        ).fetchall()
        usage = {"project_count": 0, "pipeline_runs": 0, "llm_tokens": 0, "storage_mb": 0}
        for resource, total in rows:
            usage[resource] = total
        # Count projects for this org
        proj_count = self.conn.execute(
            "SELECT COUNT(*) FROM org_projects WHERE org_id=?", (org_id,)
        ).fetchone()[0]
        usage["project_count"] = proj_count
        return usage

    def get_monthly_usage_by_user(self, org_id: int) -> list[dict]:
        """Per-user usage breakdown for the current month (v8, Portal billing).

        Returns rows: {user_id, user_email, llm_tokens, pipeline_runs}
        — only rows carrying user attribution (user_id NOT NULL); historical
        NULL rows are excluded from the per-user split (still counted in the
        org total via get_monthly_usage).
        """
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        rows = self.conn.execute(
            "SELECT user_id, user_email,"
            " SUM(CASE WHEN resource='llm_tokens' THEN amount ELSE 0 END) AS llm_tokens,"
            " SUM(CASE WHEN resource='pipeline_runs' THEN amount ELSE 0 END) AS pipeline_runs"
            " FROM usage_log"
            " WHERE org_id=? AND recorded_at >= ? AND user_id IS NOT NULL"
            " GROUP BY user_id, user_email"
            " ORDER BY llm_tokens DESC",
            (org_id, month_start)
        ).fetchall()
        return [{
            "user_id": r["user_id"],
            "user_email": r["user_email"] or "",
            "llm_tokens": r["llm_tokens"] or 0,
            "pipeline_runs": r["pipeline_runs"] or 0,
        } for r in rows]

    def get_subscription(self, org_id: int):
        """Get subscription info for an org."""
        row = self.conn.execute(
            "SELECT * FROM subscriptions WHERE org_id=?", (org_id,)
        ).fetchone()
        return dict(row) if row else None

    def upsert_subscription(self, org_id: int, data: dict):
        """Create or update subscription."""
        existing = self.get_subscription(org_id)
        now = datetime.now().isoformat()
        if existing:
            # Static parameterized UPDATE — all column names are hardcoded
            self.conn.execute(
                """UPDATE subscriptions SET
                    stripe_subscription_id = COALESCE(?, stripe_subscription_id),
                    stripe_customer_id = COALESCE(?, stripe_customer_id),
                    tier = COALESCE(?, tier),
                    status = COALESCE(?, status),
                    current_period_end = COALESCE(?, current_period_end)
                WHERE org_id = ?""",
                (data.get("stripe_subscription_id"), data.get("stripe_customer_id"),
                 data.get("tier"), data.get("status"),
                 data.get("current_period_end"), org_id)
            )
        else:
            self.conn.execute(
                "INSERT INTO subscriptions (org_id, stripe_subscription_id, stripe_customer_id, tier, status, current_period_end, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (org_id, data.get("stripe_subscription_id", ""), data.get("stripe_customer_id", ""),
                 data.get("tier", "pro"), data.get("status", "active"),
                 data.get("current_period_end", ""), now)
            )
        self.conn.commit()

    def update_org_tier(self, org_id: int, tier: str):
        """Update organization tier."""
        self.conn.execute("UPDATE organizations SET tier=? WHERE id=?", (tier, org_id))
        self.conn.commit()

    def get_org_by_stripe_subscription(self, sub_id: str):
        """Find organization by Stripe subscription ID."""
        row = self.conn.execute(
            "SELECT org_id FROM subscriptions WHERE stripe_subscription_id=?", (sub_id,)
        ).fetchone()
        if row:
            return self.get_organization_by_id(row["org_id"])
        return None
