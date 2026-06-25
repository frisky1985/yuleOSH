# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Knowledge Base (KB) — PostgreSQL store layer.

Follows the existing store_pg.py patterns:
- psycopg2 connection via store_pg.PostgresStore
- dict-based row results via _row_to_dict
- JSONB stored as Python dict/list, serialized via json.dumps/json.loads
- Soft delete via is_deleted flag + deleted_at timestamp
- UUID primary keys, generated server-side via gen_random_uuid()
"""

import json
import uuid
from datetime import datetime
from typing import Optional


class KnowledgeBaseStore:
    """KB article CRUD + soft-delete + version management.

    All methods raise psycopg2.DatabaseError on failure.
    """

    # ── Status constants (6 状态) ───────────────────────────────────
    STATUS_DRAFT = 0
    STATUS_REVIEW_PENDING = 1
    STATUS_APPROVED = 2
    STATUS_PUBLISHED = 3
    STATUS_DEPRECATED = 4
    STATUS_ARCHIVED = 5

    _STATUS_NAMES = {
        0: "draft", 1: "review_pending", 2: "approved",
        3: "published", 4: "deprecated", 5: "archived",
    }

    # ── ASIL constants ─────────────────────────────────────────────
    ASIL_QM = 0
    ASIL_A = 1
    ASIL_B = 2
    ASIL_C = 3
    ASIL_D = 4

    _ASIL_NAMES = {0: "QM", 1: "ASIL_A", 2: "ASIL_B", 3: "ASIL_C", 4: "ASIL_D"}

    # ── AUTOSAR layer bitmask ──────────────────────────────────────
    AUTOSAR_ASW = 1  # bit 0
    AUTOSAR_RTE = 2  # bit 1
    AUTOSAR_BSW = 4  # bit 2
    AUTOSAR_HW = 8   # bit 3

    def __init__(self, conn):
        """Initialize with a psycopg2 connection from PostgresStore."""
        self.conn = conn

    # ================================================================
    # Helpers
    # ================================================================

    def _ensure_schema(self):
        """Create the knowledge schema if not exists."""
        with self.conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS knowledge;")
        self.conn.commit()

    def _row_to_dict(self, cursor, row) -> dict:
        """Convert a psycopg2 RealDictRow or tuple row to a plain dict."""
        if row is None:
            return None
        if hasattr(cursor, 'description'):
            col_names = [desc[0] for desc in cursor.description]
            result = dict(zip(col_names, row))
        else:
            result = dict(row)
        # Deserialize JSONB fields
        for field in ('hw_bom', 'ota_binding', 'code_paths', 'safety_goals', 'tcl_doc_slot'):
            if field in result and isinstance(result[field], str):
                try:
                    result[field] = json.loads(result[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        # Handle dtc_codes for non-array backends
        if 'dtc_codes' in result and isinstance(result['dtc_codes'], str):
            try:
                result['dtc_codes'] = json.loads(result['dtc_codes'])
            except (json.JSONDecodeError, TypeError):
                result['dtc_codes'] = result['dtc_codes'].strip('{}').split(',') if result['dtc_codes'] else []
        if 'tags' in result and isinstance(result['tags'], str):
            try:
                result['tags'] = json.loads(result['tags'])
            except (json.JSONDecodeError, TypeError):
                result['tags'] = result['tags'].strip('{}').split(',') if result['tags'] else []
        return result

    def _serialize_jsonb(self, value):
        """Serialize a Python value to JSON string for JSONB storage."""
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, default=str)

    def _build_filter_clause(self, filters: dict, param_idx_start: int = 0) -> tuple:
        """Build WHERE clause and params from a filter dict.

        Supported filters:
        - status: int or list[int]
        - asil: int
        - autosar_layer: int (bitmask match)
        - author_id: str
        - confidence_min / confidence_max: int
        - is_deleted: bool (default False)
        - tags: list[str] (array overlap)
        - dtc_codes: list[str] (array overlap)
        - platform: str (JSONB path match hw_bom)
        - safety_goal_id: str (JSONB array match)
        - ota_version: str (JSONB extract)
        - code_path_stale: bool
        - keyword: str (full-text search on title+content)
        """
        clauses = []
        params = []
        idx = param_idx_start

        def _p(v):
            nonlocal idx
            idx += 1
            params.append(v)
            return f"${idx}"

        for key, val in filters.items():
            if key == 'status':
                if isinstance(val, (list, tuple)):
                    placeholders = ', '.join(_p(v) for v in val)
                    clauses.append(f"a.status IN ({placeholders})")
                else:
                    clauses.append(f"a.status = {_p(val)}")
            elif key == 'asil':
                clauses.append(f"a.asil = {_p(val)}")
            elif key == 'autosar_layer':
                clauses.append(f"a.autosar_layer & {_p(val)} > 0")
            elif key == 'author_id':
                clauses.append(f"a.author_id = {_p(val)}")
            elif key == 'confidence_min':
                clauses.append(f"a.confidence >= {_p(val)}")
            elif key == 'confidence_max':
                clauses.append(f"a.confidence <= {_p(val)}")
            elif key == 'is_deleted':
                clauses.append(f"a.is_deleted = {_p(bool(val))}")
            elif key == 'tags':
                clauses.append(f"a.tags && {_p(list(val))}")
            elif key == 'dtc_codes':
                clauses.append(f"a.dtc_codes && {_p(list(val))}")
            elif key == 'platform':
                # JSONB path query: hw_bom contains object with matching platform
                clauses.append(f"a.hw_bom @> {_p('[{\"platform\": \"' + val + '\"}]')}")
            elif key == 'safety_goal_id':
                clauses.append(
                    f"a.safety_goals @> {_p('[{\"safety_goal_id\": \"' + val + '\"}]')}"
                )
            elif key == 'code_path_stale':
                clauses.append(f"a.code_path_stale = {_p(bool(val))}")
            elif key == 'keyword':
                clauses.append(
                    f"to_tsvector('english', a.title || ' ' || a.content)"
                    f" @@ plainto_tsquery('english', {_p(val)})"
                )
            elif key == 'dtc_code_prefix':
                clauses.append(f"EXISTS (SELECT 1 FROM unnest(a.dtc_codes) AS c WHERE c LIKE {_p(val || '%')})")

        return clauses, params, idx

    # ================================================================
    # KB CRUD
    # ================================================================

    def create_article(self, article: dict) -> dict:
        """Create a new KB article. Returns the created row.

        Required fields: title, author_id, asil (or safety_level)
        Optional fields: summary, content, body_format, status, reviewer_id,
                         tags, hw_bom, ota_binding, dtc_codes, code_paths,
                         safety_goals, tcl_doc_slot, code_path_stale
        """
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.kb_articles (
                    title, summary, content, body_format, status, asil,
                    autosar_layer, hw_bom, ota_binding, dtc_codes,
                    tcl_doc_slot, safety_goals, code_paths,
                    author_id, reviewer_id, tags,
                    confidence, confidence_decay_policy, code_path_stale,
                    current_version, created_at, updated_at
                ) VALUES (
                    %(title)s, %(summary)s, %(content)s, %(body_format)s,
                    %(status)s, %(asil)s,
                    %(autosar_layer)s,
                    %(hw_bom)s::jsonb, %(ota_binding)s::jsonb,
                    %(dtc_codes)s,
                    %(tcl_doc_slot)s::jsonb, %(safety_goals)s::jsonb,
                    %(code_paths)s::jsonb,
                    %(author_id)s, %(reviewer_id)s, %(tags)s,
                    %(confidence)s, %(confidence_decay_policy)s,
                    %(code_path_stale)s,
                    1, %(now)s, %(now)s
                )
                RETURNING *
            """, {
                "title": article.get("title", ""),
                "summary": article.get("summary", ""),
                "content": article.get("content", ""),
                "body_format": article.get("body_format", 0),
                "status": article.get("status", self.STATUS_DRAFT),
                "asil": article.get("asil", article.get("safety_level", self.ASIL_QM)),
                "autosar_layer": article.get("autosar_layer", 0),
                "hw_bom": self._serialize_jsonb(article.get("hw_bom", [])),
                "ota_binding": self._serialize_jsonb(article.get("ota_binding")),
                "dtc_codes": article.get("dtc_codes", []),
                "tcl_doc_slot": self._serialize_jsonb(article.get("tcl_doc_slot")),
                "safety_goals": self._serialize_jsonb(article.get("safety_goals", [])),
                "code_paths": self._serialize_jsonb(article.get("code_paths", [])),
                "author_id": article["author_id"],
                "reviewer_id": article.get("reviewer_id"),
                "tags": article.get("tags", []),
                "confidence": article.get("confidence", 100),
                "confidence_decay_policy": article.get("confidence_decay_policy", 0),
                "code_path_stale": article.get("code_path_stale", False),
                "now": now,
            })
            row = cur.fetchone()
            self.conn.commit()
            return self._row_to_dict(cur, row)

    def get_article(self, article_id: uuid.UUID, include_deleted: bool = False) -> Optional[dict]:
        """Get a single KB article by UUID. Returns None if not found."""
        with self.conn.cursor() as cur:
            if include_deleted:
                cur.execute(
                    "SELECT * FROM knowledge.kb_articles WHERE id = %s",
                    (str(article_id),)
                )
            else:
                cur.execute(
                    "SELECT * FROM knowledge.kb_articles WHERE id = %s AND NOT is_deleted",
                    (str(article_id),)
                )
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def update_article(self, article_id: uuid.UUID, updates: dict) -> Optional[dict]:
        """Update an existing KB article. Returns updated row or None.

        Automatically increments current_version and captures version snapshot
        if content-affecting fields change (title, summary, content, hw_bom, etc.)
        """
        allowed_fields = {
            "title", "summary", "content", "body_format", "status",
            "asil", "autosar_layer", "hw_bom", "ota_binding", "dtc_codes",
            "tcl_doc_slot", "safety_goals", "code_paths", "code_path_stale",
            "reviewer_id", "tags", "confidence", "confidence_decay_policy",
        }
        now = datetime.now().isoformat()

        set_parts = []
        params = {}

        for field in allowed_fields:
            if field in updates:
                if field in ("hw_bom", "ota_binding", "tcl_doc_slot", "safety_goals", "code_paths"):
                    set_parts.append(f"{field} = :{field}::jsonb")
                    params[field] = json.dumps(updates[field], ensure_ascii=False, default=str)
                elif field in ("dtc_codes", "tags"):
                    set_parts.append(f"{field} = :{field}")
                    params[field] = updates[field]
                else:
                    set_parts.append(f"{field} = :{field}")
                    params[field] = updates[field]

        if not set_parts:
            return self.get_article(article_id)

        set_parts.append("updated_at = :updated_at")
        params["updated_at"] = now
        params["id"] = str(article_id)

        # Check if this is a content-affecting update → increment version
        content_fields = {"title", "summary", "content", "hw_bom", "ota_binding",
                          "dtc_codes", "code_paths", "safety_goals", "asil", "autosar_layer"}
        if content_fields & set(updates.keys()):
            set_parts.append("current_version = current_version + 1")

        sql = f"""
            UPDATE knowledge.kb_articles
            SET {', '.join(set_parts)}
            WHERE id = :id AND NOT is_deleted
            RETURNING *
        """
        # Convert :param to %(param)s for psycopg2
        sql = sql.replace(":", "%(")

        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            self.conn.commit()
            return self._row_to_dict(cur, row) if row else None

    def soft_delete(self, article_id: uuid.UUID) -> bool:
        """Soft-delete a KB article. Returns True if deleted, False if not found.

        NOTE: Does NOT check for cross-references (caller should check via
        CROSS-03 before calling this).
        """
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE knowledge.kb_articles
                SET is_deleted = true, deleted_at = %(now)s, updated_at = %(now)s
                WHERE id = %(id)s AND NOT is_deleted
                RETURNING id
            """, {"id": str(article_id), "now": now})
            row = cur.fetchone()
            self.conn.commit()
            return row is not None

    def hard_delete(self, article_id: uuid.UUID) -> bool:
        """Physically delete a KB article. Returns True if deleted.

        Caller MUST check CROSS-03 cross-references before calling this.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM knowledge.kb_articles WHERE id = %s RETURNING id",
                (str(article_id),)
            )
            row = cur.fetchone()
            self.conn.commit()
            return row is not None

    def restore(self, article_id: uuid.UUID) -> Optional[dict]:
        """Restore a soft-deleted KB article. Returns the restored row."""
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE knowledge.kb_articles
                SET is_deleted = false, deleted_at = NULL, updated_at = %(now)s
                WHERE id = %(id)s AND is_deleted
                RETURNING *
            """, {"id": str(article_id), "now": now})
            row = cur.fetchone()
            self.conn.commit()
            return self._row_to_dict(cur, row) if row else None

    # ================================================================
    # KB List / Search
    # ================================================================

    def list_articles(self, filters: dict = None, limit: int = 50,
                      offset: int = 0, sort_by: str = "updated_at",
                      sort_dir: str = "DESC") -> tuple:
        """List KB articles with optional filters.

        Returns (list_of_dicts, total_count).
        """
        if filters is None:
            filters = {}
        if "is_deleted" not in filters:
            filters["is_deleted"] = False

        where_clauses, params, _ = self._build_filter_clause(filters)
        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

        # Validate sort
        allowed_sorts = {"updated_at", "created_at", "confidence", "title", "status", "asil"}
        if sort_by not in allowed_sorts:
            sort_by = "updated_at"
        sort_dir = "ASC" if sort_dir.upper() == "ASC" else "DESC"

        # Ensure table alias
        where_sql = where_sql.replace("a.", "")

        with self.conn.cursor() as cur:
            # Count
            cur.execute(
                f"SELECT COUNT(*) FROM knowledge.kb_articles a WHERE {where_sql}",
                params if params else None
            )
            total = cur.fetchone()[0]

            # Data
            sql = f"""
                SELECT a.* FROM knowledge.kb_articles a
                WHERE {where_sql}
                ORDER BY a.{sort_by} {sort_dir}
                LIMIT %s OFFSET %s
            """
            cur.execute(sql, params + [limit, offset])
            rows = cur.fetchall()
            return [self._row_to_dict(cur, r) for r in rows], total

    def search_by_dtc(self, dtc_code: str, limit: int = 20) -> list:
        """Search KB articles by DTC code (exact or prefix)."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT a.* FROM knowledge.kb_articles a
                WHERE NOT a.is_deleted
                  AND EXISTS (
                      SELECT 1 FROM unnest(a.dtc_codes) AS c
                      WHERE c LIKE %s
                  )
                ORDER BY a.updated_at DESC
                LIMIT %s
            """, (dtc_code + '%' if len(dtc_code) < 5 else dtc_code, limit))
            rows = cur.fetchall()
            return [self._row_to_dict(cur, r) for r in rows]

    # ================================================================
    # Version Snapshot Management
    # ================================================================

    def create_version_snapshot(self, article_id: uuid.UUID, changed_by: str,
                                change_summary: str = "") -> dict:
        """Capture a complete content snapshot of the current article as a new version.

        Returns the created kb_version row.
        """
        article = self.get_article(article_id)
        if not article:
            raise ValueError(f"Article {article_id} not found")

        new_version = article["current_version"]  # already incremented by update

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.kb_versions (
                    article_id, version, title, summary, content,
                    body_format, asil, autosar_layer, hw_bom, ota_binding,
                    dtc_codes, code_paths, tags, safety_goals,
                    change_summary, changed_by, confidence
                ) VALUES (
                    %(article_id)s, %(version)s, %(title)s, %(summary)s,
                    %(content)s, %(body_format)s, %(asil)s,
                    %(autosar_layer)s,
                    %(hw_bom)s::jsonb, %(ota_binding)s::jsonb,
                    %(dtc_codes)s, %(code_paths)s::jsonb,
                    %(tags)s, %(safety_goals)s::jsonb,
                    %(change_summary)s, %(changed_by)s, %(confidence)s
                )
                RETURNING *
            """, {
                "article_id": str(article_id),
                "version": new_version,
                "title": article["title"],
                "summary": article["summary"],
                "content": article["content"],
                "body_format": article["body_format"],
                "asil": article["asil"],
                "autosar_layer": article["autosar_layer"],
                "hw_bom": self._serialize_jsonb(article["hw_bom"]),
                "ota_binding": self._serialize_jsonb(article.get("ota_binding")),
                "dtc_codes": article.get("dtc_codes", []),
                "code_paths": self._serialize_jsonb(article.get("code_paths", [])),
                "tags": article.get("tags", []),
                "safety_goals": self._serialize_jsonb(article.get("safety_goals", [])),
                "change_summary": change_summary,
                "changed_by": changed_by,
                "confidence": article["confidence"],
            })
            version = self._row_to_dict(cur, cur.fetchone())

            # Link article to latest version
            cur.execute("""
                UPDATE knowledge.kb_articles
                SET latest_version_id = %(version_id)s
                WHERE id = %(article_id)s
            """, {"version_id": version["id"], "article_id": str(article_id)})

            self.conn.commit()
            return version

    def get_version(self, article_id: uuid.UUID, version: int) -> Optional[dict]:
        """Get a specific version of an article."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM knowledge.kb_versions
                WHERE article_id = %s AND version = %s
            """, (str(article_id), version))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def list_versions(self, article_id: uuid.UUID) -> list:
        """List all versions of an article, newest first."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM knowledge.kb_versions
                WHERE article_id = %s
                ORDER BY version DESC
            """, (str(article_id),))
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    def rollback_to_version(self, article_id: uuid.UUID, version: int,
                            operator_id: str, reason: str = "") -> Optional[dict]:
        """Rollback an article to a specific version.

        Creates a new version with the old content (preserving rollback history).
        Returns the updated article.
        """
        old_version = self.get_version(article_id, version)
        if not old_version:
            return None

        updates = {
            "title": old_version["title"],
            "summary": old_version["summary"],
            "content": old_version["content"],
            "body_format": old_version["body_format"],
            "asil": old_version["asil"],
            "autosar_layer": old_version["autosar_layer"],
            "hw_bom": old_version["hw_bom"],
            "ota_binding": old_version.get("ota_binding"),
            "dtc_codes": old_version.get("dtc_codes", []),
            "code_paths": old_version.get("code_paths", []),
            "tags": old_version.get("tags", []),
            "safety_goals": old_version.get("safety_goals", []),
            "confidence": old_version["confidence"],
        }

        result = self.update_article(article_id, updates)
        if result:
            self.create_version_snapshot(
                article_id, changed_by=operator_id,
                change_summary=f"Rollback to v{version}: {reason}",
            )
            # Record audit
            self._record_audit_log(
                article_id=article_id,
                action=4,  # rollback
                operator_id=operator_id,
                comment=f"Rollback to v{version}: {reason}",
                detail={"rolled_back_to": version},
            )
        return result

    # ================================================================
    # Audit Log
    # ================================================================

    def _record_audit_log(self, article_id: uuid.UUID, action: int,
                          operator_id: str, comment: str = "",
                          version_id: uuid.UUID = None,
                          old_status: int = None, new_status: int = None,
                          detail: dict = None):
        """Record a KB version audit log entry (internal)."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.kb_version_audit_logs (
                    version_id, article_id, action, operator_id,
                    comment, old_status, new_status, detail_json
                ) VALUES (
                    %(version_id)s, %(article_id)s, %(action)s,
                    %(operator_id)s, %(comment)s, %(old_status)s,
                    %(new_status)s, %(detail)s::jsonb
                )
            """, {
                "version_id": str(version_id) if version_id else None,
                "article_id": str(article_id),
                "action": action,
                "operator_id": operator_id,
                "comment": comment,
                "old_status": old_status,
                "new_status": new_status,
                "detail": json.dumps(detail) if detail else None,
            })
        self.conn.commit()

    def record_audit_log(self, article_id: uuid.UUID, action: int,
                         operator_id: str, comment: str = "",
                         version_id: uuid.UUID = None,
                         old_status: int = None, new_status: int = None,
                         detail: dict = None):
        """Public interface to record a KB version audit log entry."""
        self._record_audit_log(
            article_id=article_id, action=action,
            operator_id=operator_id, comment=comment,
            version_id=version_id,
            old_status=old_status, new_status=new_status,
            detail=detail,
        )

    def list_audit_logs(self, article_id: uuid.UUID = None,
                         limit: int = 50, offset: int = 0) -> list:
        """List KB audit logs, optionally filtered by article."""
        with self.conn.cursor() as cur:
            if article_id:
                cur.execute("""
                    SELECT * FROM knowledge.kb_version_audit_logs
                    WHERE article_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (str(article_id), limit, offset))
            else:
                cur.execute("""
                    SELECT * FROM knowledge.kb_version_audit_logs
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ================================================================
    # Code Path Reverse Index
    # ================================================================

    def add_code_path(self, article_id: uuid.UUID, repo: str, file_path: str,
                      line_start: int = None, line_end: int = None,
                      language: str = "") -> dict:
        """Add a source code path association to a KB article."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.knowledge_code_paths
                    (article_id, repo, file_path, line_start, line_end, language)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (str(article_id), repo, file_path, line_start, line_end, language))
            row = cur.fetchone()
            self.conn.commit()
            return self._row_to_dict(cur, row)

    def find_articles_by_code_path(self, repo: str = None,
                                    file_path: str = None) -> list:
        """Reverse lookup: find articles associated with a given code path."""
        conditions = []
        params = []
        if repo:
            conditions.append("cp.repo = %s")
            params.append(repo)
        if file_path:
            conditions.append("cp.file_path = %s")
            params.append(file_path)

        where = " AND ".join(conditions) if conditions else "TRUE"

        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT a.* FROM knowledge.kb_articles a
                JOIN knowledge.knowledge_code_paths cp ON cp.article_id = a.id
                WHERE {where} AND NOT a.is_deleted
                ORDER BY a.updated_at DESC
            """, params)
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    def mark_code_path_stale(self, article_id: uuid.UUID) -> dict:
        """Mark an article's code_path_stale flag and reduce confidence."""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE knowledge.kb_articles
                SET code_path_stale = true,
                    confidence = GREATEST(confidence - 10, 0),
                    updated_at = now()
                WHERE id = %s AND NOT is_deleted
                RETURNING *
            """, (str(article_id),))
            row = cur.fetchone()
            self.conn.commit()
            return self._row_to_dict(cur, row) if row else None

    # ================================================================
    # Status Transition Helpers (KB-13)
    # ================================================================

    def _validate_status_transition(self, current_status: int, new_status: int) -> bool:
        """Validate state machine transitions (KB-13)."""
        allowed = {
            self.STATUS_DRAFT: [self.STATUS_REVIEW_PENDING],  # submit review
            self.STATUS_REVIEW_PENDING: [self.STATUS_APPROVED, self.STATUS_DRAFT],  # approve or reject
            self.STATUS_APPROVED: [self.STATUS_PUBLISHED, self.STATUS_DEPRECATED],  # publish or deprecate
            self.STATUS_PUBLISHED: [self.STATUS_DEPRECATED],  # mark expired
            self.STATUS_DEPRECATED: [self.STATUS_APPROVED],  # restore after review
            self.STATUS_ARCHIVED: [],  # terminal
        }
        return new_status in allowed.get(current_status, [])

    def transition_status(self, article_id: uuid.UUID, new_status: int,
                          operator_id: str, comment: str = "",
                          reviewer_ids: list = None) -> Optional[dict]:
        """Transition an article's status with validation.

        Records audit log on each transition.
        Returns updated article or None if article not found.
        Returns (article, error_msg) tuple if transition invalid.
        """
        article = self.get_article(article_id)
        if not article:
            return None, "Article not found"

        old_status = article["status"]
        if not self._validate_status_transition(old_status, new_status):
            return None, f"Invalid transition from {self._STATUS_NAMES.get(old_status, old_status)} " \
                         f"to {self._STATUS_NAMES.get(new_status, new_status)}"

        # ASIL gate (KB-02)
        if new_status == self.STATUS_APPROVED and old_status == self.STATUS_REVIEW_PENDING:
            asil = article["asil"]
            if asil >= self.ASIL_B:
                if not reviewer_ids or len(reviewer_ids) == 0:
                    return None, f"ASIL {self._ASIL_NAMES.get(asil, asil)} requires at least one independent review"
            if asil >= self.ASIL_D:
                if not reviewer_ids or len(reviewer_ids) < 2:
                    return None, f"ASIL D requires at least two independent reviewers"

        article = self.update_article(article_id, {"status": new_status})
        if article:
            self._record_audit_log(
                article_id=article_id,
                action=2 if new_status == self.STATUS_APPROVED else 1,
                operator_id=operator_id,
                comment=comment,
                old_status=old_status,
                new_status=new_status,
                detail={"reviewer_ids": reviewer_ids} if reviewer_ids else None,
            )

            # Confidence reset on deprecation → approval (KB-08)
            if old_status == self.STATUS_DEPRECATED and new_status == self.STATUS_APPROVED:
                self._reset_confidence(article_id, operator_id)

        return article, None

    def _reset_confidence(self, article_id: uuid.UUID, operator_id: str) -> dict:
        """Reset confidence to 100 and record a version snapshot."""
        article = self.update_article(article_id, {"confidence": 100})
        if article:
            self.create_version_snapshot(
                article_id, changed_by=operator_id,
                change_summary="Confidence reset after manual review",
            )
        return article
