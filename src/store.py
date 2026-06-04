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

    def _migrate(self):
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
