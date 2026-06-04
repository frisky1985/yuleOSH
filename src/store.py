#!/usr/bin/env python3
"""yuleOSH Persistent Storage — SQLite-backed runtime data store."""
import json, os, sqlite3, threading
from datetime import datetime
from pathlib import Path
from typing import Optional


class Store:
    """SQLite-backed persistent store. Thread-safe, testable."""

    _instances = {}
    _lock = threading.Lock()

    def __new__(cls, db_path: Optional[str] = None):
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
    _MIGRATION_VERSION = 4

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
        """)
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

        # Migration v3 — add stat tracking columns
        version = self.get_migration_version()
        if version < 3:
            self._run_migration_v3()

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

    def list_organizations(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM organizations ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Multi-tenant: Users
    # ------------------------------------------------------------------

    def create_user(self, org_id: int, email: str, role: str = "member") -> dict:
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            "INSERT INTO users (org_id, email, role, created_at) VALUES (?, ?, ?, ?)",
            (org_id, email, role, now)
        )
        self.conn.commit()
        return {"id": cur.lastrowid, "org_id": org_id, "email": email, "role": role, "created_at": now}

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

    # ------------------------------------------------------------------
    # Multi-tenant: Sessions
    # ------------------------------------------------------------------

    def create_session(self, user_id: int, token: str, ttl_hours: int = 24) -> dict:
        now = datetime.now()
        expires = datetime.fromtimestamp(now.timestamp() + ttl_hours * 3600)
        now_str = now.isoformat()
        exp_str = expires.isoformat()
        self.conn.execute(
            "INSERT INTO user_sessions (user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, token, now_str, exp_str)
        )
        self.conn.commit()
        return {"user_id": user_id, "token": token, "created_at": now_str, "expires_at": exp_str}

    def get_session(self, token: str) -> Optional[dict]:
        cur = self.conn.execute(
            "SELECT * FROM user_sessions WHERE token=? AND expires_at > datetime('now')",
            (token,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def delete_session(self, token: str):
        self.conn.execute("DELETE FROM user_sessions WHERE token=?", (token,))
        self.conn.commit()

    def cleanup_expired_sessions(self):
        self.conn.execute(
            "DELETE FROM user_sessions WHERE expires_at <= datetime('now')"
        )
        self.conn.commit()

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

    def complete_wizard(self):
        """Mark the first-run wizard as completed."""
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

    def close(self):
        self.conn.close()
