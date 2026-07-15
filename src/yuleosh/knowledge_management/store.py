#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Management Store — SQLite-backed persistent store for articles.

Maintains its own SQLite database at .yuleosh/knowledge_management.db.
Design follows KGStore patterns (singleton, migration, CRUD).

Tables:
  km_articles       — knowledge articles (one row = one article)
  km_versions       — version snapshots (KB-03 foundation, P0 stub)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.knowledge_management.models import (
    KnowledgeArticle,
    ARTICLE_STATUSES,
    VALID_TRANSITIONS,
)

log = logging.getLogger("yuleosh.knowledge_management.store")

_SCHEMA_VERSION = 1


def _now() -> str:
    """ISO-8601 timestamp for record keeping."""
    return datetime.now().isoformat()


def _new_id() -> str:
    """UUID v4 string."""
    return str(uuid.uuid4())


def _bump_version(current: str) -> str:
    """Increment patch segment of semantic version (major.minor.patch)."""
    parts = current.split(".")
    if len(parts) != 3:
        return "1.0.0"
    try:
        patch = int(parts[2]) + 1
        return f"{parts[0]}.{parts[1]}.{patch}"
    except (ValueError, IndexError):
        return "1.0.0"


def _translate_status_transition(current: str, target: str) -> Optional[str]:
    """Validate status transition, return None if invalid, else target."""
    allowed = VALID_TRANSITIONS.get(current, set())
    if target in allowed:
        return target
    return None


class KBStore:
    """SQLite-backed knowledge base store. Thread-safe singleton per db_path."""

    _instances = {}
    _lock = threading.Lock()

    def __new__(cls, db_path: Optional[str] = None):
        key = db_path or "default"
        with cls._lock:
            if key not in cls._instances:
                instance = super().__new__(cls)
                resolved = db_path or os.environ.get(
                    "YULEOSH_KB_DB",
                    str(Path(os.environ.get("OSH_HOME", "."))
                        / ".yuleosh" / "knowledge_management.db"),
                )
                Path(resolved).parent.mkdir(parents=True, exist_ok=True)
                instance.db_path = resolved
                instance.conn = sqlite3.connect(resolved, check_same_thread=False)
                instance.conn.row_factory = sqlite3.Row
                instance._migrate()
                cls._instances[key] = instance
            return cls._instances[key]

    @classmethod
    def reset(cls):
        """Clear all instances (for testing). Recreates new instances on next access."""
        for inst in cls._instances.values():
            try:
                inst.conn.close()
            except Exception:
                pass
        cls._instances = {}

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _migrate(self):
        """Create tables and apply any pending schema changes."""
        self.conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS km_articles (
                id                     TEXT PRIMARY KEY,
                title                  TEXT NOT NULL DEFAULT '',
                content                TEXT NOT NULL DEFAULT '',
                status                 TEXT NOT NULL DEFAULT 'draft',
                safety_level           TEXT NOT NULL DEFAULT 'QM',
                created_by             TEXT NOT NULL DEFAULT '',
                updated_by             TEXT NOT NULL DEFAULT '',
                created_at             TEXT NOT NULL,
                updated_at             TEXT NOT NULL,
                version                TEXT NOT NULL DEFAULT '1.0.0',
                confidence             INTEGER NOT NULL DEFAULT 100,
                confidence_decay_policy TEXT NOT NULL DEFAULT 'usage_based',
                is_deleted             INTEGER NOT NULL DEFAULT 0,
                deleted_at             TEXT,
                tags                   TEXT NOT NULL DEFAULT '[]',
                ota_binding            TEXT,
                tcl_doc_slot           TEXT,
                hw_bom                 TEXT,
                dtc_codes              TEXT NOT NULL DEFAULT '[]',
                autosar_layers         TEXT NOT NULL DEFAULT '[]',
                code_paths             TEXT NOT NULL DEFAULT '[]',
                spec_refs              TEXT NOT NULL DEFAULT '[]',
                safety_goals           TEXT NOT NULL DEFAULT '[]',
                test_refs              TEXT NOT NULL DEFAULT '[]',
                change_reason          TEXT,
                review_notes           TEXT
            );

            CREATE TABLE IF NOT EXISTS km_versions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id  TEXT NOT NULL REFERENCES km_articles(id),
                version     TEXT NOT NULL,
                snapshot    TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                change_reason TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_km_versions_article_id
                ON km_versions(article_id);

            CREATE INDEX IF NOT EXISTS idx_km_articles_status
                ON km_articles(status);
            CREATE INDEX IF NOT EXISTS idx_km_articles_is_deleted
                ON km_articles(is_deleted);
            CREATE INDEX IF NOT EXISTS idx_km_articles_created_by
                ON km_articles(created_by);

            CREATE TABLE IF NOT EXISTS km_meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        self.conn.execute(
            "INSERT OR REPLACE INTO km_meta (key, value) VALUES ('schema_version', ?)",
            (str(_SCHEMA_VERSION),)
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Internal: row ↔ article
    # ------------------------------------------------------------------

    def _row_to_article(self, row: sqlite3.Row) -> KnowledgeArticle:
        """Convert a SQLite row to a KnowledgeArticle dataclass."""
        return KnowledgeArticle(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            status=row["status"],
            safety_level=row["safety_level"],
            created_by=row["created_by"],
            updated_by=row["updated_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=row["version"],
            confidence=row["confidence"],
            confidence_decay_policy=row["confidence_decay_policy"],
            is_deleted=bool(row["is_deleted"]),
            deleted_at=row["deleted_at"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            ota_binding=json.loads(row["ota_binding"]) if row["ota_binding"] else None,
            tcl_doc_slot=json.loads(row["tcl_doc_slot"]) if row["tcl_doc_slot"] else None,
            hw_bom=json.loads(row["hw_bom"]) if row["hw_bom"] else None,
            dtc_codes=json.loads(row["dtc_codes"]) if row["dtc_codes"] else [],
            autosar_layers=json.loads(row["autosar_layers"]) if row["autosar_layers"] else [],
            code_paths=json.loads(row["code_paths"]) if row["code_paths"] else [],
            spec_refs=json.loads(row["spec_refs"]) if row["spec_refs"] else [],
            safety_goals=json.loads(row["safety_goals"]) if row["safety_goals"] else [],
            test_refs=json.loads(row["test_refs"]) if row["test_refs"] else [],
            change_reason=row["change_reason"],
            review_notes=row["review_notes"],
        )

    def _article_to_row(self, article: KnowledgeArticle) -> dict:
        """Convert a KnowledgeArticle to a dict for SQL INSERT/UPDATE."""
        d = article.to_dict()
        # Serialize JSON fields
        for json_field in ("tags", "dtc_codes", "autosar_layers", "code_paths",
                           "spec_refs", "safety_goals", "test_refs"):
            d[json_field] = json.dumps(d.get(json_field, []))
        for json_opt in ("ota_binding", "tcl_doc_slot", "hw_bom"):
            val = d.get(json_opt)
            d[json_opt] = json.dumps(val) if val is not None else None
        d["is_deleted"] = 1 if d.get("is_deleted") else 0
        return d

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, article: KnowledgeArticle) -> KnowledgeArticle:
        """Insert a new article. Generates UUID and timestamps if missing."""
        now = _now()
        if not article.id:
            article.id = _new_id()
        if not article.created_at:
            article.created_at = now
        if not article.updated_at:
            article.updated_at = now
        article.version = article.version or "1.0.0"

        row = self._article_to_row(article)
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        self.conn.execute(
            f"INSERT INTO km_articles ({columns}) VALUES ({placeholders})",
            list(row.values()),
        )
        self.conn.commit()

        # Create initial version snapshot
        self._create_version_snapshot(article.id, article.version, article.change_reason)

        return self.get(article.id)

    def get(self, article_id: str, include_deleted: bool = False) -> Optional[KnowledgeArticle]:
        """Get a single article by ID."""
        if include_deleted:
            cur = self.conn.execute(
                "SELECT * FROM km_articles WHERE id = ?", (article_id,)
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM km_articles WHERE id = ? AND is_deleted = 0",
                (article_id,),
            )
        row = cur.fetchone()
        return self._row_to_article(row) if row else None

    def update(self, article_id: str, updates: dict,
               updated_by: str = "") -> Optional[KnowledgeArticle]:
        """Update a non-deleted article. Auto-bumps version patch.

        Args:
            article_id: UUID of the article.
            updates: Dict of fields to update. Use status=None to validate
                     and apply status transitions.
            updated_by: User identifier for the update.

        Returns:
            Updated KnowledgeArticle, or None if not found / soft-deleted.
        """
        existing = self.get(article_id)
        if existing is None:
            return None

        now = _now()

        # Handle status transition validation
        if "status" in updates and updates["status"] is not None:
            target = _translate_status_transition(existing.status, updates["status"])
            if target is None:
                log.warning(
                    "Invalid status transition: %s → %s (article %s)",
                    existing.status, updates["status"], article_id,
                )
                return None
            updates["status"] = target

        # Auto-bump patch version on content/title changes
        for_bump = {"title", "content", "status", "safety_level", "tags",
                     "code_paths", "hw_bom", "ota_binding", "dtc_codes",
                     "autosar_layers", "spec_refs", "safety_goals", "test_refs",
                     "confidence", "confidence_decay_policy"}
        should_bump = bool(set(updates.keys()) & for_bump)

        if should_bump:
            updates["version"] = _bump_version(existing.version)

        updates["updated_at"] = now
        if updated_by:
            updates["updated_by"] = updated_by

        # Build SET clause
        set_clauses = []
        params = []
        for key, value in updates.items():
            if key in ("tags", "dtc_codes", "autosar_layers", "code_paths",
                       "spec_refs", "safety_goals", "test_refs"):
                set_clauses.append(f"{key} = ?")
                params.append(json.dumps(value if value else []))
            elif key in ("ota_binding", "tcl_doc_slot", "hw_bom"):
                set_clauses.append(f"{key} = ?")
                params.append(json.dumps(value) if value is not None else None)
            elif key == "is_deleted":
                set_clauses.append(f"{key} = ?")
                params.append(1 if value else 0)
            else:
                set_clauses.append(f"{key} = ?")
                params.append(value)

        params.append(article_id)
        sql = f"UPDATE km_articles SET {', '.join(set_clauses)} WHERE id = ? AND is_deleted = 0"
        self.conn.execute(sql, params)
        self.conn.commit()

        # Create version snapshot if content changed
        if should_bump:
            self._create_version_snapshot(
                article_id,
                updates.get("version", existing.version),
                updates.get("change_reason", existing.change_reason),
            )

        return self.get(article_id)

    def soft_delete(self, article_id: str, updated_by: str = "") -> bool:
        """Soft-delete an article. Returns True if affected."""
        existing = self.get(article_id)
        if existing is None:
            return False

        now = _now()
        self.conn.execute(
            "UPDATE km_articles SET is_deleted = 1, deleted_at = ?, updated_at = ?, updated_by = ? WHERE id = ?",
            (now, now, updated_by or existing.updated_by, article_id),
        )
        self.conn.commit()
        return True

    def restore(self, article_id: str, updated_by: str = "") -> bool:
        """Restore a soft-deleted article. Returns True if affected."""
        now = _now()
        cur = self.conn.execute(
            "UPDATE km_articles SET is_deleted = 0, deleted_at = NULL, updated_at = ?, updated_by = ? WHERE id = ? AND is_deleted = 1",
            (now, updated_by, article_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Listing & Search
    # ------------------------------------------------------------------

    def list(self, status: Optional[str] = None,
             include_deleted: bool = False,
             offset: int = 0,
             limit: int = 50) -> tuple[list[KnowledgeArticle], int]:
        """List articles, optionally filtered by status.

        Returns (articles, total_count).
        """
        conditions = []
        params = []

        if not include_deleted:
            conditions.append("is_deleted = 0")
        if status and status in ARTICLE_STATUSES:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions) if conditions else "1=1"

        # Total count
        count_cur = self.conn.execute(
            f"SELECT COUNT(*) FROM km_articles WHERE {where}", params
        )
        total = count_cur.fetchone()[0]

        # Paginated list
        cur = self.conn.execute(
            f"SELECT * FROM km_articles WHERE {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        articles = [self._row_to_article(r) for r in cur.fetchall()]
        return articles, total

    def search(self, query: str, status: Optional[str] = None,
               include_deleted: bool = False,
               offset: int = 0, limit: int = 50) -> tuple[list[KnowledgeArticle], int]:
        """Full-text LIKE search on title and content.

        Returns (articles, total_count).
        """
        conditions = ["(title LIKE ? OR content LIKE ?)"]
        like_pattern = f"%{query}%"
        params = [like_pattern, like_pattern]

        if not include_deleted:
            conditions.append("is_deleted = 0")
        if status and status in ARTICLE_STATUSES:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions)

        count_cur = self.conn.execute(
            f"SELECT COUNT(*) FROM km_articles WHERE {where}", params
        )
        total = count_cur.fetchone()[0]

        cur = self.conn.execute(
            f"SELECT * FROM km_articles WHERE {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        articles = [self._row_to_article(r) for r in cur.fetchall()]
        return articles, total

    def search_by_tags(self, tags: list[str],
                       match_all: bool = False,
                       include_deleted: bool = False,
                       offset: int = 0,
                       limit: int = 50) -> tuple[list[KnowledgeArticle], int]:
        """Search articles by tags (stored as JSON array).

        Args:
            tags: List of tag strings to search for.
            match_all: If True, article must have ALL tags; if False, ANY.
            include_deleted: Whether to include soft-deleted articles.
            offset: Pagination offset.
            limit: Page size.

        Returns:
            (articles, total_count)
        """
        if not tags:
            return [], 0

        conditions = ["is_deleted = 0"] if not include_deleted else []
        tag_conditions = []

        for tag in tags:
            tag_conditions.append("tags LIKE ?")
        join_op = " AND " if match_all else " OR "
        conditions.append(f"({join_op.join(tag_conditions)})")
        params = [f"%{t}%" for t in tags]

        where = " AND ".join(conditions)

        count_cur = self.conn.execute(
            f"SELECT COUNT(*) FROM km_articles WHERE {where}", params
        )
        total = count_cur.fetchone()[0]

        cur = self.conn.execute(
            f"SELECT * FROM km_articles WHERE {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        articles = [self._row_to_article(r) for r in cur.fetchall()]
        return articles, total

    # ------------------------------------------------------------------
    # Version management (KB-03 foundation)
    # ------------------------------------------------------------------

    def _create_version_snapshot(self, article_id: str, version: str,
                                 change_reason: Optional[str] = None):
        """Internal: save a full content snapshot on update."""
        article = self.get(article_id, include_deleted=True)
        if article is None:
            return
        now = _now()
        snapshot_json = json.dumps(article.to_dict())
        self.conn.execute(
            "INSERT INTO km_versions (article_id, version, snapshot, created_at, change_reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (article_id, version, snapshot_json, now, change_reason),
        )
        self.conn.commit()

    def list_versions(self, article_id: str,
                      limit: int = 50) -> tuple[list[dict], int]:
        """List version snapshots for an article.

        Returns (version_metadata, total_count).
        """
        cur = self.conn.execute(
            "SELECT id, article_id, version, created_at, change_reason "
            "FROM km_versions WHERE article_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (article_id, limit),
        )
        versions = [dict(r) for r in cur.fetchall()]

        count_cur = self.conn.execute(
            "SELECT COUNT(*) FROM km_versions WHERE article_id = ?",
            (article_id,),
        )
        total = count_cur.fetchone()[0]
        return versions, total

    def get_version_snapshot(self, article_id: str,
                             version: str) -> Optional[KnowledgeArticle]:
        """Restore a full article from a specific version snapshot."""
        cur = self.conn.execute(
            "SELECT snapshot FROM km_versions WHERE article_id = ? AND version = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (article_id, version),
        )
        row = cur.fetchone()
        if not row:
            return None
        data = json.loads(row["snapshot"])
        return KnowledgeArticle.from_dict(data)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total = self.conn.execute(
            "SELECT COUNT(*) FROM km_articles WHERE is_deleted = 0"
        ).fetchone()[0]

        by_status = {}
        for row in self.conn.execute(
            "SELECT status, COUNT(*) as c FROM km_articles WHERE is_deleted = 0 GROUP BY status"
        ).fetchall():
            by_status[row["status"]] = row["c"]

        by_safety = {}
        for row in self.conn.execute(
            "SELECT safety_level, COUNT(*) as c FROM km_articles WHERE is_deleted = 0 GROUP BY safety_level"
        ).fetchall():
            by_safety[row["safety_level"]] = row["c"]

        low_confidence = self.conn.execute(
            "SELECT COUNT(*) FROM km_articles WHERE is_deleted = 0 AND confidence < 30"
        ).fetchone()[0]

        avg_confidence = self.conn.execute(
            "SELECT AVG(confidence) FROM km_articles WHERE is_deleted = 0"
        ).fetchone()[0] or 0.0

        pending_review = self.conn.execute(
            "SELECT COUNT(*) FROM km_articles WHERE is_deleted = 0 AND status = 'review_pending'"
        ).fetchone()[0]

        return {
            "total_articles": total,
            "by_status": by_status,
            "by_safety_level": by_safety,
            "avg_confidence": round(avg_confidence, 1),
            "low_confidence_count": low_confidence,
            "pending_review_count": pending_review,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Close the database connection."""
        self.conn.close()
