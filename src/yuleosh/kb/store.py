# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""SQLite storage for Knowledge Base — CRUD operations for kb_articles, lessons, fmea_entries."""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import KbArticle, Lesson, FmeaEntry


class KbStore:
    """SQLite-backed store for the knowledge base tables.

    Thread-safe. Uses a single connection-per-thread via threading.local.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            osh_home = Path(__file__).resolve().parent.parent.parent.parent
            db_path = str(osh_home / ".yuleosh" / "kb.db")
        self._db_path = db_path
        self._local = threading.local()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── Connection management ────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def close(self):
        """Close the thread-local connection if open."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ── Schema init ──────────────────────────────────────────────────────

    def _init_db(self):
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS kb_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                source_ref TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                problem TEXT NOT NULL DEFAULT '',
                solution TEXT NOT NULL DEFAULT '',
                root_cause TEXT NOT NULL DEFAULT '',
                project_id TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL DEFAULT 'medium',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS fmea_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item TEXT NOT NULL DEFAULT '',
                failure_mode TEXT NOT NULL DEFAULT '',
                effect TEXT NOT NULL DEFAULT '',
                cause TEXT NOT NULL DEFAULT '',
                severity INTEGER NOT NULL DEFAULT 1,
                occurence INTEGER NOT NULL DEFAULT 1,
                detection INTEGER NOT NULL DEFAULT 1,
                rpn INTEGER NOT NULL DEFAULT 0,
                recommendation TEXT NOT NULL DEFAULT '',
                created_at TEXT
            );
        """)
        conn.commit()

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

    def _row_to_article(self, row: sqlite3.Row) -> KbArticle:
        return KbArticle(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            source=row["source"],
            source_ref=row["source_ref"],
            tags=row["tags"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    def _row_to_lesson(self, row: sqlite3.Row) -> Lesson:
        return Lesson(
            id=row["id"],
            title=row["title"],
            problem=row["problem"],
            solution=row["solution"],
            root_cause=row["root_cause"],
            project_id=row["project_id"],
            severity=row["severity"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    def _row_to_fmea(self, row: sqlite3.Row) -> FmeaEntry:
        return FmeaEntry(
            id=row["id"],
            item=row["item"],
            failure_mode=row["failure_mode"],
            effect=row["effect"],
            cause=row["cause"],
            severity=row["severity"],
            occurence=row["occurence"],
            detection=row["detection"],
            rpn=row["rpn"],
            recommendation=row["recommendation"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    # ── kb_articles CRUD ─────────────────────────────────────────────────

    def create_article(self, fields: dict) -> KbArticle:
        now = self._now()
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO kb_articles (title, content, source, source_ref, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (fields.get("title", ""), fields.get("content", ""),
             fields.get("source", ""), fields.get("source_ref", ""),
             fields.get("tags", ""), now, now),
        )
        conn.commit()
        return self.get_article(cur.lastrowid)

    def get_article(self, article_id: int) -> Optional[KbArticle]:
        conn = self._get_conn()
        cur = conn.execute("SELECT * FROM kb_articles WHERE id = ?", (article_id,))
        row = cur.fetchone()
        return self._row_to_article(row) if row else None

    def list_articles(self, search: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[KbArticle]:
        conn = self._get_conn()
        if search:
            pattern = f"%{search}%"
            cur = conn.execute(
                """SELECT * FROM kb_articles
                   WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? OR source LIKE ?
                   ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
                (pattern, pattern, pattern, pattern, limit, offset),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM kb_articles ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [self._row_to_article(r) for r in cur.fetchall()]

    def count_articles(self, search: Optional[str] = None) -> int:
        conn = self._get_conn()
        if search:
            pattern = f"%{search}%"
            cur = conn.execute(
                "SELECT COUNT(*) FROM kb_articles WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? OR source LIKE ?",
                (pattern, pattern, pattern, pattern),
            )
        else:
            cur = conn.execute("SELECT COUNT(*) FROM kb_articles")
        return cur.fetchone()[0]

    def update_article(self, article_id: int, fields: dict) -> Optional[KbArticle]:
        now = self._now()
        fields["updated_at"] = now
        # Validate field names against allowed columns to prevent SQL injection
        _allowed = {"title", "content", "source", "source_ref", "tags", "updated_at"}
        safe_fields = {k: v for k, v in fields.items() if k in _allowed}
        if not safe_fields or "updated_at" not in safe_fields:
            return self.get_article(article_id)
        set_clause = ", ".join(f"{k} = ?" for k in safe_fields)
        values = list(safe_fields.values()) + [article_id]
        conn = self._get_conn()
        conn.execute(f"UPDATE kb_articles SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return self.get_article(article_id)

    def delete_article(self, article_id: int) -> bool:
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM kb_articles WHERE id = ?", (article_id,))
        conn.commit()
        return cur.rowcount > 0

    # ── lessons CRUD ─────────────────────────────────────────────────────

    def create_lesson(self, fields: dict) -> Lesson:
        now = self._now()
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO lessons (title, problem, solution, root_cause, project_id, severity, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (fields.get("title", ""), fields.get("problem", ""),
             fields.get("solution", ""), fields.get("root_cause", ""),
             fields.get("project_id", ""), fields.get("severity", "medium"), now),
        )
        conn.commit()
        return self.get_lesson(cur.lastrowid)

    def get_lesson(self, lesson_id: int) -> Optional[Lesson]:
        conn = self._get_conn()
        cur = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
        row = cur.fetchone()
        return self._row_to_lesson(row) if row else None

    def list_lessons(self, project_id: Optional[str] = None, severity: Optional[str] = None,
                     limit: int = 100, offset: int = 0) -> list[Lesson]:
        conn = self._get_conn()
        conditions = []
        params = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        cur = conn.execute(
            f"SELECT * FROM lessons {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        return [self._row_to_lesson(r) for r in cur.fetchall()]

    def count_lessons(self, project_id: Optional[str] = None, severity: Optional[str] = None) -> int:
        conn = self._get_conn()
        conditions = []
        params = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        cur = conn.execute(f"SELECT COUNT(*) FROM lessons {where}", params)
        return cur.fetchone()[0]

    def update_lesson(self, lesson_id: int, fields: dict) -> Optional[Lesson]:
        _allowed = {"title", "problem", "solution", "root_cause", "project_id", "severity"}
        safe_fields = {k: v for k, v in fields.items() if k in _allowed}
        if not safe_fields:
            return self.get_lesson(lesson_id)
        set_clause = ", ".join(f"{k} = ?" for k in safe_fields)
        values = list(safe_fields.values()) + [lesson_id]
        conn = self._get_conn()
        conn.execute(f"UPDATE lessons SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return self.get_lesson(lesson_id)

    def delete_lesson(self, lesson_id: int) -> bool:
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        conn.commit()
        return cur.rowcount > 0

    # ── fmea_entries CRUD ────────────────────────────────────────────────

    def create_fmea(self, fields: dict) -> FmeaEntry:
        now = self._now()
        sev = fields.get("severity", 1)
        occ = fields.get("occurence", 1)
        det = fields.get("detection", 1)
        rpn = sev * occ * det
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO fmea_entries (item, failure_mode, effect, cause, severity, occurence, detection, rpn, recommendation, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fields.get("item", ""), fields.get("failure_mode", ""),
             fields.get("effect", ""), fields.get("cause", ""),
             sev, occ, det, rpn,
             fields.get("recommendation", ""), now),
        )
        conn.commit()
        return self.get_fmea(cur.lastrowid)

    def get_fmea(self, fmea_id: int) -> Optional[FmeaEntry]:
        conn = self._get_conn()
        cur = conn.execute("SELECT * FROM fmea_entries WHERE id = ?", (fmea_id,))
        row = cur.fetchone()
        return self._row_to_fmea(row) if row else None

    def list_fmea(self, sort_by: str = "rpn", sort_desc: bool = True,
                  limit: int = 100, offset: int = 0) -> list[FmeaEntry]:
        conn = self._get_conn()
        allowed_sort = {"rpn", "severity", "occurence", "detection", "created_at"}
        if sort_by not in allowed_sort:
            sort_by = "rpn"
        direction = "DESC" if sort_desc else "ASC"
        cur = conn.execute(
            f"SELECT * FROM fmea_entries ORDER BY {sort_by} {direction} LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [self._row_to_fmea(r) for r in cur.fetchall()]

    def count_fmea(self) -> int:
        conn = self._get_conn()
        cur = conn.execute("SELECT COUNT(*) FROM fmea_entries")
        return cur.fetchone()[0]

    def update_fmea(self, fmea_id: int, fields: dict) -> Optional[FmeaEntry]:
        # Recompute RPN if any rating changed
        sev = fields.get("severity")
        occ = fields.get("occurence")
        det = fields.get("detection")
        if sev is not None or occ is not None or det is not None:
            existing = self.get_fmea(fmea_id)
            if existing:
                fields["severity"] = sev if sev is not None else existing.severity
                fields["occurence"] = occ if occ is not None else existing.occurence
                fields["detection"] = det if det is not None else existing.detection
                fields["rpn"] = fields["severity"] * fields["occurence"] * fields["detection"]
        # Validate field names against allowed columns
        _allowed = {"item", "failure_mode", "effect", "cause", "severity", "occurence",
                     "detection", "rpn", "recommendation"}
        safe_fields = {k: v for k, v in fields.items() if k in _allowed}
        if not safe_fields:
            return self.get_fmea(fmea_id)
        set_clause = ", ".join(f"{k} = ?" for k in safe_fields)
        values = list(safe_fields.values()) + [fmea_id]
        conn = self._get_conn()
        conn.execute(f"UPDATE fmea_entries SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return self.get_fmea(fmea_id)

    def delete_fmea(self, fmea_id: int) -> bool:
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM fmea_entries WHERE id = ?", (fmea_id,))
        conn.commit()
        return cur.rowcount > 0

    # ── MISRA de-duplication ────────────────────────────────────────────

    def deduplicate_misra_articles(self) -> dict:
        """Deduplicate MISRA analysis articles keeping only the latest entry per
        (rule_id, file, line) group.

        MISRA violations are stored as kb_articles with source='misra_analysis'.
        Multiple CI runs create duplicate entries for the same (rule_id, file, line)
        violation. This method keeps only the newest article per unique key.

        Returns a dict with counts of removed duplicates.
        """
        conn = self._get_conn()

        # Step 1: Find all articles with source='misra_analysis'
        cur = conn.execute(
            "SELECT id, title, content, source_ref, tags, created_at FROM kb_articles "
            "WHERE source='misra_analysis' ORDER BY created_at DESC"
        )
        rows = cur.fetchall()

        if not rows:
            return {"articles_before": 0, "removed": 0, "kept": 0}

        articles_before = len(rows)

        # Step 2: Extract dedup key (rule_id, file, line) from each article
        seen: dict[tuple[str, str, int], int] = {}  # key → max id
        to_delete: list[int] = []

        for row in rows:
            article_id = row["id"]
            title = row["title"] or ""
            content = row["content"] or ""
            source_ref = row["source_ref"] or ""
            tags = row["tags"] or ""

            # Extract rule_id from title: "MISRA-10.1: ..." or tags: "rule-10-1"
            rule_id = ""
            import re
            m = re.match(r'^MISRA[- ]([\d.]+)', title)
            if m:
                rule_id = m.group(1)
            if not rule_id:
                m = re.search(r'rule-(\d+)-(\d+)', tags)
                if m:
                    rule_id = f"{m.group(1)}.{m.group(2)}"

            # Extract file and line from source_ref: "path/to/file.c:142"
            file_path = ""
            line_num = 0
            if ":" in source_ref:
                parts = source_ref.rsplit(":", 1)
                file_path = parts[0]
                try:
                    line_num = int(parts[1])
                except (ValueError, IndexError):
                    pass

            # If we can't extract a meaningful key, skip (keep it)
            if not rule_id and not file_path:
                continue

            key = (rule_id, file_path, line_num)

            # Keep the one with the highest id (most recent)
            if key in seen:
                to_delete.append(article_id)
            else:
                seen[key] = article_id

        # Step 3: Delete duplicates
        removed = 0
        for del_id in to_delete:
            try:
                conn.execute("DELETE FROM kb_articles WHERE id=?", (del_id,))
                removed += 1
            except Exception:
                pass
        if removed:
            conn.commit()

        kept = articles_before - removed
        return {
            "articles_before": articles_before,
            "removed": removed,
            "kept": kept,
        }

    def list_deduped_misra_articles(
        self, limit: int = 100, offset: int = 0
    ) -> list[KbArticle]:
        """List MISRA analysis articles with client-side dedup.

        Returns unique articles keyed by (rule_id, file, line) grouped for
        the dashboard _dashboard_misra_trend() endpoint.
        """
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM kb_articles WHERE source='misra_analysis' "
            "ORDER BY created_at DESC"
        )
        all_rows = cur.fetchall()

        seen: set[tuple[str, str, int]] = set()
        deduped: list[KbArticle] = []

        import re

        for row in all_rows:
            title = row["title"] or ""
            source_ref = row["source_ref"] or ""
            tags = row["tags"] or ""

            rule_id = ""
            m = re.match(r'^MISRA[- ]([\d.]+)', title)
            if m:
                rule_id = m.group(1)
            if not rule_id:
                m = re.search(r'rule-(\d+)-(\d+)', tags)
                if m:
                    rule_id = f"{m.group(1)}.{m.group(2)}"

            file_path = ""
            line_num = 0
            if ":" in source_ref:
                parts = source_ref.rsplit(":", 1)
                file_path = parts[0]
                try:
                    line_num = int(parts[1])
                except (ValueError, IndexError):
                    pass

            key = (rule_id, file_path, line_num)

            # Skip if all empty (no dedup possible, include it)
            if rule_id or file_path:
                if key in seen:
                    continue
                seen.add(key)

            deduped.append(self._row_to_article(row))

            if len(deduped) >= limit + offset:
                break

        return deduped[offset:offset + limit]

    def count_misra_violations_by_rule(self) -> dict[str, int]:
        """Count unique MISRA violations per rule, deduplicated by (file, line).

        Returns dict mapping rule_id → count of unique (file, line) violations.
        """
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT id, title, content, source_ref, tags, created_at FROM kb_articles "
            "WHERE source='misra_analysis' ORDER BY created_at DESC"
        )
        rows = cur.fetchall()

        import re
        from collections import defaultdict

        by_rule: dict[str, set[tuple[str, int]]] = defaultdict(set)

        for row in rows:
            title = row["title"] or ""
            source_ref = row["source_ref"] or ""
            tags = row["tags"] or ""

            rule_id = ""
            m = re.match(r'^MISRA[- ]([\d.]+)', title)
            if m:
                rule_id = m.group(1)
            if not rule_id:
                m = re.search(r'rule-(\d+)-(\d+)', tags)
                if m:
                    rule_id = f"{m.group(1)}.{m.group(2)}"

            file_path = ""
            line_num = 0
            if ":" in source_ref:
                parts = source_ref.rsplit(":", 1)
                file_path = parts[0]
                try:
                    line_num = int(parts[1])
                except (ValueError, IndexError):
                    pass

            if rule_id:
                by_rule[rule_id].add((file_path, line_num))

        return {k: len(v) for k, v in sorted(by_rule.items())}
