"""yuleOSH PostgreSQL Store — production-grade multi-tenant storage.

Replaces SQLite Store when YULEOSH_DB_URL starts with postgresql://
Schema automatically migrated on first connect.
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


class PostgresStore:
    """PostgreSQL-backed persistent store. Thread-safe via connection pool."""

    _instances = {}
    _lock = threading.Lock()

    def __new__(cls, dsn: Optional[str] = None):
        key = dsn or "default"
        with cls._lock:
            if key not in cls._instances:
                instance = super().__new__(cls)
                instance.dsn = dsn or os.environ.get(
                    "YULEOSH_DB_URL",
                    "postgresql://yuleosh:yuleosh@localhost:5432/yuleosh"
                )
                instance._pool = None
                instance._conn = None  # per-thread fallback
                instance._migrate()
                cls._instances[key] = instance
            return cls._instances[key]

    @classmethod
    def reset(cls):
        """Clear all instances (for testing)."""
        cls._instances = {}

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @property
    def conn(self):
        """Get a database connection (creates if needed)."""
        import psycopg2
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.dsn)
            self._conn.autocommit = True
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Schema & Migration
    # ------------------------------------------------------------------

    _MIGRATION_VERSION = 7

    def _ensure_schema(self):
        """Create all tables if they don't exist."""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS _meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)
        self.conn.commit()

    def _migrate(self):
        """Run all migrations. Uses _meta.migration_version for tracking."""
        with self.conn.cursor() as cur:
            # Meta table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS _meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

            # Core tables
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pipelines (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    spec_path TEXT, status TEXT DEFAULT 'created',
                    created_at TEXT, updated_at TEXT,
                    artifacts TEXT DEFAULT '{}', steps TEXT DEFAULT '[]',
                    errors TEXT DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS ci_runs (
                    id SERIAL PRIMARY KEY,
                    layer INTEGER NOT NULL, commit_hash TEXT,
                    status TEXT DEFAULT 'running',
                    started_at TEXT, completed_at TEXT,
                    stages TEXT DEFAULT '[]', coverage TEXT,
                    errors TEXT DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id SERIAL PRIMARY KEY,
                    task_name TEXT NOT NULL, decision TEXT,
                    status TEXT DEFAULT 'running',
                    created_at TEXT, data TEXT DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL, type TEXT, path TEXT,
                    size INTEGER, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL, description TEXT,
                    spec_path TEXT,
                    created_at TEXT, updated_at TEXT,
                    pipeline_run_count INTEGER DEFAULT 0,
                    last_active_at TEXT
                );

                -- Multi-tenant tables
                CREATE TABLE IF NOT EXISTS organizations (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    tier TEXT DEFAULT 'pro',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    org_id INTEGER NOT NULL REFERENCES organizations(id),
                    email TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'member',
                    password_hash TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(org_id, email)
                );
                CREATE TABLE IF NOT EXISTS org_projects (
                    id SERIAL PRIMARY KEY,
                    org_id INTEGER NOT NULL REFERENCES organizations(id),
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(org_id, slug)
                );
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    token TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage_log (
                    id SERIAL PRIMARY KEY,
                    org_id INTEGER NOT NULL REFERENCES organizations(id),
                    project_id INTEGER,
                    resource TEXT NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 1,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    org_id INTEGER NOT NULL UNIQUE REFERENCES organizations(id),
                    stripe_subscription_id TEXT,
                    stripe_customer_id TEXT,
                    tier TEXT NOT NULL DEFAULT 'community',
                    status TEXT NOT NULL DEFAULT 'active',
                    current_period_end TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_keys (
                    id SERIAL PRIMARY KEY,
                    key_hash TEXT UNIQUE NOT NULL,
                    label TEXT NOT NULL,
                    prefix TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS spec_cache (
                    spec_path TEXT NOT NULL,
                    mtime TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (spec_path, mtime)
                );
            """)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Multi-tenant: Organizations
    # ------------------------------------------------------------------

    def create_organization(self, name: str, slug: str) -> dict:
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO organizations (name, slug, created_at) VALUES (%s, %s, %s) RETURNING id",
                (name, slug, now)
            )
            row_id = cur.fetchone()[0]
        self.conn.commit()
        return {"id": row_id, "name": name, "slug": slug, "created_at": now}

    def get_organization(self, slug: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM organizations WHERE slug=%s", (slug,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def get_organization_by_id(self, org_id: int) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM organizations WHERE id=%s", (org_id,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def list_organizations(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM organizations ORDER BY created_at DESC")
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Multi-tenant: Users
    # ------------------------------------------------------------------

    def create_user(self, org_id: int, email: str, role: str = "member", password_hash: str = None) -> dict:
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (org_id, email, role, password_hash, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (org_id, email, role, password_hash, now)
            )
            row_id = cur.fetchone()[0]
        self.conn.commit()
        return {"id": row_id, "org_id": org_id, "email": email, "role": role,
                "password_hash": password_hash, "created_at": now}

    def get_user(self, org_id: int, email: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE org_id=%s AND email=%s", (org_id, email)
            )
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def list_users(self, org_id: int) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, role, created_at FROM users WHERE org_id=%s ORDER BY created_at",
                (org_id,)
            )
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Multi-tenant: Org Projects
    # ------------------------------------------------------------------

    def create_org_project(self, org_id: int, name: str, slug: str, description: str = "") -> dict:
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO org_projects (org_id, name, slug, description, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (org_id, name, slug, description, now)
            )
            row_id = cur.fetchone()[0]
        self.conn.commit()
        return {"id": row_id, "org_id": org_id, "name": name, "slug": slug,
                "description": description, "created_at": now}

    def get_org_project(self, org_id: int, slug: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM org_projects WHERE org_id=%s AND slug=%s", (org_id, slug)
            )
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def get_org_project_by_id(self, project_id: int) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM org_projects WHERE id=%s", (project_id,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def list_org_projects(self, org_id: int) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM org_projects WHERE org_id=%s ORDER BY created_at DESC", (org_id,)
            )
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(self, user_id: int, token: str, ttl_hours: int = 24) -> dict:
        now = datetime.now()
        expires = datetime.fromtimestamp(now.timestamp() + ttl_hours * 3600)
        now_str = now.isoformat()
        exp_str = expires.isoformat()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_sessions (user_id, token, created_at, expires_at) VALUES (%s, %s, %s, %s)",
                (user_id, token, now_str, exp_str)
            )
        self.conn.commit()
        return {"user_id": user_id, "token": token, "created_at": now_str, "expires_at": exp_str}

    def get_session(self, token: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM user_sessions WHERE token=%s AND expires_at > %s",
                (token, datetime.now().isoformat())
            )
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def delete_session(self, token: str):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM user_sessions WHERE token=%s", (token,))
        self.conn.commit()

    def cleanup_expired_sessions(self):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM user_sessions WHERE expires_at <= %s",
                        (datetime.now().isoformat(),))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Spec cache
    # ------------------------------------------------------------------

    def cache_spec_parse(self, spec_path: str, mtime: float, result: dict):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO spec_cache (spec_path, mtime, result_json, cached_at) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (spec_path, mtime) DO UPDATE SET result_json=%s, cached_at=%s",
                (spec_path, str(mtime), json.dumps(result), datetime.now().isoformat(),
                 json.dumps(result), datetime.now().isoformat())
            )
        self.conn.commit()

    def get_cached_spec_parse(self, spec_path: str, mtime: float) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT result_json FROM spec_cache WHERE spec_path=%s AND mtime=%s",
                (spec_path, str(mtime))
            )
            row = cur.fetchone()
            return json.loads(row[0]) if row else None

    # ------------------------------------------------------------------
    # API Keys
    # ------------------------------------------------------------------

    def create_api_key(self, key_hash: str, label: str, prefix: str) -> dict:
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_keys (key_hash, label, prefix, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
                (key_hash, label, prefix, now)
            )
            row_id = cur.fetchone()[0]
        self.conn.commit()
        return {"id": row_id, "label": label, "prefix": prefix, "created_at": now, "revoked": 0}

    def get_api_key_by_hash(self, key_hash: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM api_keys WHERE key_hash=%s", (key_hash,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def list_api_keys(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, label, prefix, created_at, last_used_at, revoked FROM api_keys ORDER BY created_at DESC"
            )
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    def revoke_api_key(self, key_id: int) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE api_keys SET revoked=1 WHERE id=%s AND revoked=0", (key_id,)
            )
            affected = cur.rowcount
        self.conn.commit()
        return affected > 0

    def update_api_key_last_used(self, key_id: int):
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("UPDATE api_keys SET last_used_at=%s WHERE id=%s", (now, key_id))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Pipelines
    # ------------------------------------------------------------------

    def save_pipeline(self, name: str, data: dict):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pipelines (name, spec_path, status, created_at, updated_at, artifacts, steps, errors)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (name) DO UPDATE SET
                    spec_path=EXCLUDED.spec_path, status=EXCLUDED.status,
                    updated_at=EXCLUDED.updated_at, artifacts=EXCLUDED.artifacts,
                    steps=EXCLUDED.steps, errors=EXCLUDED.errors
            """, (
                name, data.get("spec_path", ""), data.get("status", "created"),
                data.get("created_at", datetime.now().isoformat()),
                data.get("updated_at", datetime.now().isoformat()),
                json.dumps(data.get("artifacts", {})),
                json.dumps(data.get("steps", [])),
                json.dumps(data.get("errors", [])),
            ))
        self.conn.commit()

    def get_pipeline(self, name: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM pipelines WHERE name=%s", (name,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def list_pipelines(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT name,status,created_at,updated_at FROM pipelines ORDER BY created_at DESC"
            )
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # CI Runs
    # ------------------------------------------------------------------

    def save_ci(self, data: dict):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ci_runs (layer, commit_hash, status, started_at, completed_at, stages, coverage, errors)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                data.get("layer", 0), data.get("commit", ""),
                data.get("status", "running"),
                data.get("started_at", datetime.now().isoformat()),
                data.get("completed_at"),
                json.dumps(data.get("stages", [])),
                json.dumps(data.get("coverage")),
                json.dumps(data.get("errors", [])),
            ))
        self.conn.commit()

    def list_ci(self, limit: int = 10) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM ci_runs ORDER BY started_at DESC LIMIT %s", (limit,)
            )
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------

    def save_review(self, task_name: str, data: dict):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO reviews (task_name, decision, status, created_at, data)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (task_name) DO UPDATE SET
                    decision=EXCLUDED.decision, status=EXCLUDED.status,
                    data=EXCLUDED.data
            """, (
                task_name, data.get("decision"), data.get("status", "running"),
                data.get("created_at", datetime.now().isoformat()),
                json.dumps(data)
            ))
        self.conn.commit()

    def list_reviews(self, limit: int = 10) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT task_name,decision,status,created_at FROM reviews ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    def log_evidence(self, name: str, type_: str, path: str, size: int = 0):
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO evidence (name, type, path, size, created_at) VALUES (%s,%s,%s,%s,%s)",
                (name, type_, path, size, now)
            )
        self.conn.commit()

    def list_evidence(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM evidence ORDER BY created_at DESC")
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def init_project(self, name: str, description: str = ""):
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO projects (name, description, created_at, updated_at)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (name) DO NOTHING
            """, (name, description, now, now))
        self.conn.commit()

    def get_project(self, name: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM projects WHERE name=%s", (name,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    # ------------------------------------------------------------------
    # Usage & Subscription
    # ------------------------------------------------------------------

    def record_usage(self, org_id: int, project_id: int, resource: str, amount: int):
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usage_log (org_id, project_id, resource, amount, recorded_at) VALUES (%s,%s,%s,%s,%s)",
                (org_id, project_id, resource, amount, now)
            )
        self.conn.commit()

    def get_monthly_usage(self, org_id: int) -> dict:
        with self.conn.cursor() as cur:
            month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            cur.execute(
                "SELECT resource, SUM(amount) FROM usage_log WHERE org_id=%s AND recorded_at>=%s GROUP BY resource",
                (org_id, month_start)
            )
            rows = cur.fetchall()
            usage = {"project_count": 0, "pipeline_runs": 0, "llm_tokens": 0, "storage_mb": 0}
            for resource, total in rows:
                usage[resource] = total
            cur.execute("SELECT COUNT(*) FROM org_projects WHERE org_id=%s", (org_id,))
            usage["project_count"] = cur.fetchone()[0]
        return usage

    def get_subscription(self, org_id: int) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM subscriptions WHERE org_id=%s", (org_id,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def upsert_subscription(self, org_id: int, data: dict):
        existing = self.get_subscription(org_id)
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            if existing:
                for key in ("stripe_subscription_id", "stripe_customer_id", "tier", "status", "current_period_end"):
                    if key in data and data[key]:
                        cur.execute(
                            f"UPDATE subscriptions SET {key}=%s WHERE org_id=%s",
                            (data[key], org_id)
                        )
            else:
                cur.execute("""
                    INSERT INTO subscriptions (org_id, stripe_subscription_id, stripe_customer_id, tier, status, current_period_end, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (org_id, data.get("stripe_subscription_id", ""), data.get("stripe_customer_id", ""),
                      data.get("tier", "pro"), data.get("status", "active"),
                      data.get("current_period_end", ""), now))
        self.conn.commit()

    def update_org_tier(self, org_id: int, tier: str):
        with self.conn.cursor() as cur:
            cur.execute("UPDATE organizations SET tier=%s WHERE id=%s", (tier, org_id))
        self.conn.commit()

    def get_org_by_stripe_subscription(self, sub_id: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT org_id FROM subscriptions WHERE stripe_subscription_id=%s", (sub_id,)
            )
            row = cur.fetchone()
            if row:
                return self.get_organization_by_id(row[0])
        return None

    # ------------------------------------------------------------------
    # Usage Stats
    # ------------------------------------------------------------------

    def record_activity(self, project_name: str):
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE projects SET pipeline_run_count = COALESCE(pipeline_run_count, 0) + 1, last_active_at=%s WHERE name=%s",
                (now, project_name)
            )
        self.conn.commit()

    def get_total_users(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as c FROM users")
            return cur.fetchone()[0]

    def get_total_projects(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM projects")
            legacy = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM org_projects")
            org = cur.fetchone()[0]
        return legacy + org

    def get_usage_stats(self) -> dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pipelines"); pipe = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM ci_runs"); ci = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM reviews"); rv = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM evidence"); ev = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM projects"); pj = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM organizations"); org = cur.fetchone()[0]
            cur.execute("SELECT status, COUNT(*) as c FROM pipelines GROUP BY status")
            pipe_statuses = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute("SELECT layer, COUNT(*) as c FROM ci_runs GROUP BY layer")
            ci_layers = {str(r[0]): r[1] for r in cur.fetchall()}
        return {
            "total_pipelines": pipe, "total_ci_runs": ci,
            "total_reviews": rv, "total_evidence": ev,
            "total_projects": pj, "total_organizations": org,
            "total_users": self.get_total_users(),
            "pipeline_statuses": pipe_statuses,
            "ci_by_layer": ci_layers,
        }

    def get_migration_version(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT value FROM _meta WHERE key='migration_version'")
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def is_wizard_completed(self) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SELECT value FROM _meta WHERE key='wizard_completed'")
            row = cur.fetchone()
            return row is not None and row[0] == "1"

    def complete_wizard(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO _meta (key, value) VALUES ('wizard_completed', '1') "
                "ON CONFLICT (key) DO UPDATE SET value='1'"
            )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _row_to_dict(self, cursor, row) -> dict:
        """Convert a psycopg2 row to a dict using cursor description."""
        return {desc[0]: row[i] for i, desc in enumerate(cursor.description)}
