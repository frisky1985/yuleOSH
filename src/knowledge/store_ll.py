# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Lessons Learned (LL) — PostgreSQL store layer.

Implements CRUD for LL entries (lessons table) with:
- 8-state lifecycle closure tracking
- DTC association
- Audit log recording (CROSS-04)
- Action plan management
- Test seed generation
"""

import json
import uuid
from datetime import datetime
from typing import Optional


class LessonsLearnedStore:
    """LL entry CRUD + closure management + audit.

    All methods raise psycopg2.DatabaseError on failure.
    """

    # ── LL status constants (8 状态) ───────────────────────────────
    STATUS_OPEN = 0
    STATUS_INVESTIGATING = 1
    STATUS_ACTION_PLANNED = 2
    STATUS_IMPLEMENTED = 3
    STATUS_MITIGATED = 4
    STATUS_VERIFIED = 5
    STATUS_CLOSED = 6
    STATUS_REJECTED = 7

    _STATUS_NAMES = {
        0: "open", 1: "investigating", 2: "action_planned",
        3: "implemented", 4: "mitigated", 5: "verified",
        6: "closed", 7: "rejected",
    }

    # ── Severity constants (5 级) ──────────────────────────────────
    SEVERITY_INFO = 0
    SEVERITY_MINOR = 1
    SEVERITY_MAJOR = 2
    SEVERITY_CRITICAL = 3
    SEVERITY_CATASTROPHIC = 4

    _SEVERITY_NAMES = {0: "info", 1: "minor", 2: "major", 3: "critical", 4: "catastrophic"}

    # ── Category constants ─────────────────────────────────────────
    CATEGORY_DESIGN = 0
    CATEGORY_CODING = 1
    CATEGORY_TEST = 2
    CATEGORY_PROCESS = 3
    CATEGORY_REQUIREMENT = 4
    CATEGORY_INTEGRATION = 5
    CATEGORY_HW = 6
    CATEGORY_OTHER = 7

    _CATEGORY_NAMES = {
        0: "design", 1: "coding", 2: "test", 3: "process",
        4: "requirement", 5: "integration", 6: "hw", 7: "other",
    }

    # ── Source constants ───────────────────────────────────────────
    SOURCE_MANUAL = 0
    SOURCE_AUTO_BUG = 1
    SOURCE_CI_FAILURE = 2
    SOURCE_OTA_INCIDENT = 3
    SOURCE_CUSTOMER_COMPLAINT = 4
    SOURCE_FMEA_DERIVED = 5
    SOURCE_AUDIT_FINDING = 6
    SOURCE_AFTERMARKET = 7

    # ── ASIL constants ─────────────────────────────────────────────
    ASIL_QM = 0
    ASIL_A = 1
    ASIL_B = 2
    ASIL_C = 3
    ASIL_D = 4

    def __init__(self, conn):
        self.conn = conn

    # ================================================================
    # Helpers
    # ================================================================

    def _row_to_dict(self, cursor, row) -> dict:
        """Convert a psycopg2 row to a plain dict."""
        if row is None:
            return None
        if hasattr(cursor, 'description'):
            col_names = [desc[0] for desc in cursor.description]
            result = dict(zip(col_names, row))
        else:
            result = dict(row)
        # Deserialize JSONB
        for field in ('closure_journal',):
            if field in result and isinstance(result[field], str):
                try:
                    result[field] = json.loads(result[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        # Handle array fields
        for field in ('applied_to', 'dtc_codes'):
            if field in result and isinstance(result[field], str):
                try:
                    result[field] = json.loads(result[field])
                except (json.JSONDecodeError, TypeError):
                    result[field] = result[field].strip('{}').split(',') if result[field] else []
        return result

    def _serialize_jsonb(self, value):
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, default=str)

    # ================================================================
    # LL CRUD
    # ================================================================

    def create_lesson(self, lesson: dict) -> dict:
        """Create a new LL entry. Returns the created row.

        Required fields: title, author_id
        Optional fields: description, root_cause, resolution, severity,
                         status, category, safety_level, source, source_ref,
                         article_id, ota_version, ota_fix_version,
                         applied_to, assignee_id, dtc_codes, confidence
        """
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.lessons (
                    source, source_ref, title, description,
                    severity, status, category, safety_level,
                    article_id, ota_version, ota_fix_version,
                    root_cause, resolution, applied_to,
                    author_id, assignee_id, confidence,
                    dtc_codes, closure_journal, created_at, updated_at
                ) VALUES (
                    %(source)s, %(source_ref)s, %(title)s, %(description)s,
                    %(severity)s, %(status)s, %(category)s, %(safety_level)s,
                    %(article_id)s, %(ota_version)s, %(ota_fix_version)s,
                    %(root_cause)s, %(resolution)s, %(applied_to)s,
                    %(author_id)s, %(assignee_id)s, %(confidence)s,
                    %(dtc_codes)s, %(closure_journal)s::jsonb,
                    %(now)s, %(now)s
                )
                RETURNING *
            """, {
                "source": lesson.get("source", self.SOURCE_MANUAL),
                "source_ref": lesson.get("source_ref", ""),
                "title": lesson["title"],
                "description": lesson.get("description", ""),
                "severity": lesson.get("severity", self.SEVERITY_INFO),
                "status": lesson.get("status", self.STATUS_OPEN),
                "category": lesson.get("category", self.CATEGORY_OTHER),
                "safety_level": lesson.get("safety_level", self.ASIL_QM),
                "article_id": str(lesson["article_id"]) if lesson.get("article_id") else None,
                "ota_version": lesson.get("ota_version"),
                "ota_fix_version": lesson.get("ota_fix_version"),
                "root_cause": lesson.get("root_cause", ""),
                "resolution": lesson.get("resolution", ""),
                "applied_to": lesson.get("applied_to", []),
                "author_id": lesson["author_id"],
                "assignee_id": lesson.get("assignee_id"),
                "confidence": lesson.get("confidence", 80),
                "dtc_codes": lesson.get("dtc_codes", []),
                "closure_journal": self._serialize_jsonb(lesson.get("closure_journal", [])),
                "now": now,
            })
            row = cur.fetchone()
            self.conn.commit()

            result = self._row_to_dict(cur, row)
            # Record audit
            self._record_audit_log(
                lesson_id=result["id"],
                action=1,  # created
                operator_id=lesson["author_id"],
                comment="Lesson created",
                new_status=self.STATUS_OPEN,
                new_confidence=result.get("confidence", 80),
            )
            return result

    def get_lesson(self, lesson_id: uuid.UUID) -> Optional[dict]:
        """Get a single LL entry by UUID."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM knowledge.lessons WHERE id = %s",
                (str(lesson_id),)
            )
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def update_lesson(self, lesson_id: uuid.UUID, updates: dict,
                      operator_id: str = "") -> Optional[dict]:
        """Update an LL entry. Returns updated row or None.

        Records audit log for status/severity/confidence changes.
        """
        allowed_fields = {
            "title", "description", "root_cause", "resolution",
            "severity", "status", "category", "safety_level",
            "article_id", "ota_version", "ota_fix_version",
            "applied_to", "assignee_id", "confidence",
            "dtc_codes", "closure_journal",
            "source", "source_ref", "pending_review",
            "aftermarket_hits", "sign_off_id", "closed_at",
        }
        now = datetime.now().isoformat()

        # Snapshot old values for audit
        old = self.get_lesson(lesson_id)
        if not old:
            return None

        set_parts = []
        params = {}

        for field in allowed_fields:
            if field in updates:
                if field == "closure_journal":
                    set_parts.append(f"{field} = :{field}::jsonb")
                    params[field] = self._serialize_jsonb(updates[field])
                elif field in ("applied_to", "dtc_codes"):
                    set_parts.append(f"{field} = :{field}")
                    params[field] = updates[field]
                else:
                    set_parts.append(f"{field} = :{field}")
                    params[field] = updates[field]

        if not set_parts:
            return old

        set_parts.append("updated_at = :updated_at")
        params["updated_at"] = now
        params["id"] = str(lesson_id)

        sql = f"""
            UPDATE knowledge.lessons
            SET {', '.join(set_parts)}
            WHERE id = :id
            RETURNING *
        """
        sql = sql.replace(":", "%(")

        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            self.conn.commit()

            if row and operator_id:
                result = self._row_to_dict(cur, row)
                # Record audit for significant changes
                self._record_audit_if_changed(result, old, operator_id)

            return self._row_to_dict(cur, row) if row else None

    # ================================================================
    # Status Transition (LL-07: 8 状态闭环节点)
    # ================================================================

    def _validate_status_transition(self, current_status: int, new_status: int) -> bool:
        """Validate LL 8-state lifecycle transitions (LL-07)."""
        allowed = {
            self.STATUS_OPEN: [self.STATUS_INVESTIGATING, self.STATUS_REJECTED],
            self.STATUS_INVESTIGATING: [self.STATUS_ACTION_PLANNED, self.STATUS_OPEN],
            self.STATUS_ACTION_PLANNED: [self.STATUS_IMPLEMENTED, self.STATUS_INVESTIGATING],
            self.STATUS_IMPLEMENTED: [self.STATUS_MITIGATED, self.STATUS_ACTION_PLANNED],
            self.STATUS_MITIGATED: [self.STATUS_VERIFIED, self.STATUS_IMPLEMENTED],
            self.STATUS_VERIFIED: [self.STATUS_CLOSED, self.STATUS_MITIGATED],
            self.STATUS_CLOSED: [],  # terminal
            self.STATUS_REJECTED: [self.STATUS_OPEN],  # can reopen
        }
        return new_status in allowed.get(current_status, [])

    def transition_status(self, lesson_id: uuid.UUID, new_status: int,
                          operator_id: str, description: str = "",
                          verification_method: str = "review",
                          sign_off_id: str = None) -> tuple:
        """Transition an LL entry's status with validation.

        Returns (updated_lesson, error_msg). error_msg is None on success.
        Records closure_journal entry on each transition.
        """
        lesson = self.get_lesson(lesson_id)
        if not lesson:
            return None, "Lesson not found"

        old_status = lesson["status"]
        if not self._validate_status_transition(old_status, new_status):
            return None, f"Invalid transition from {self._STATUS_NAMES.get(old_status, old_status)} " \
                         f"to {self._STATUS_NAMES.get(new_status, new_status)}"

        # ASIL gate (LL-02): ASIL B/C/D verified → closed requires sign-off
        if old_status == self.STATUS_VERIFIED and new_status == self.STATUS_CLOSED:
            asil = lesson.get("safety_level", self.ASIL_QM)
            if asil >= self.ASIL_B and not sign_off_id:
                return None, f"ASIL {self._ASIL_NAMES.get(asil, asil)} closure requires independent sign-off"

        # Build closure_journal entry
        now = datetime.now().isoformat()
        journal = lesson.get("closure_journal", []) or []
        journal.append({
            "from_status": old_status,
            "to_status": new_status,
            "at": now,
            "by": operator_id,
            "method": verification_method,
            "description": description,
        })

        updates = {
            "status": new_status,
            "closure_journal": journal,
        }
        if sign_off_id:
            updates["sign_off_id"] = sign_off_id

        # Auto-set closed_at
        if new_status == self.STATUS_CLOSED:
            updates["closed_at"] = now

        result = self.update_lesson(lesson_id, updates, operator_id=operator_id)
        if result and new_status == self.STATUS_CLOSED:
            self._record_audit_log(
                lesson_id=lesson_id,
                action=9,  # close
                operator_id=operator_id,
                comment=description or "Lesson closed",
                old_status=old_status,
                new_status=new_status,
                detail={"verification_method": verification_method},
            )

        return result, None

    # ================================================================
    # DTC Association & Aftermarket (LL-05, LL-06)
    # ================================================================

    def associate_dtc(self, lesson_id: uuid.UUID, dtc_code: str) -> bool:
        """Associate a DTC code with an LL entry."""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE knowledge.lessons
                SET dtc_codes = array_append(dtc_codes, %(dtc)s),
                    updated_at = now()
                WHERE id = %(id)s AND NOT (%(dtc)s = ANY(dtc_codes))
                RETURNING id
            """, {"id": str(lesson_id), "dtc": dtc_code})
            row = cur.fetchone()
            self.conn.commit()
            return row is not None

    def mark_pending_review(self, lesson_id: uuid.UUID) -> bool:
        """Mark an LL entry as pending_review (e.g., DTC threshold exceeded)."""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE knowledge.lessons
                SET pending_review = true, updated_at = now()
                WHERE id = %s
                RETURNING id
            """, (str(lesson_id),))
            row = cur.fetchone()
            self.conn.commit()
            if row:
                self._record_audit_log(
                    lesson_id=lesson_id,
                    action=11,  # dtc_threshold
                    operator_id="system",
                    comment="DTC aftermarket threshold exceeded, marked pending_review",
                )
            return row is not None

    def increment_aftermarket_hits(self, lesson_id: uuid.UUID) -> int:
        """Increment aftermarket hit counter and check threshold."""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE knowledge.lessons
                SET aftermarket_hits = aftermarket_hits + 1,
                    updated_at = now()
                WHERE id = %s
                RETURNING aftermarket_hits
            """, (str(lesson_id),))
            hits = cur.fetchone()
            self.conn.commit()
            return hits[0] if hits else 0

    # ================================================================
    # Lesson Actions Management
    # ================================================================

    def create_action(self, lesson_id: uuid.UUID, action: dict) -> dict:
        """Create a corrective action for a lesson."""
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.lesson_actions (
                    lesson_id, action_type, description, assignee_id,
                    status, due_at, evidence_id, created_at, updated_at
                ) VALUES (
                    %(lesson_id)s, %(action_type)s, %(description)s,
                    %(assignee_id)s, %(status)s, %(due_at)s,
                    %(evidence_id)s, %(now)s, %(now)s
                )
                RETURNING *
            """, {
                "lesson_id": str(lesson_id),
                "action_type": action.get("action_type", 0),
                "description": action.get("description", ""),
                "assignee_id": action.get("assignee_id", ""),
                "status": action.get("status", 0),
                "due_at": action.get("due_at"),
                "evidence_id": action.get("evidence_id"),
                "now": now,
            })
            row = cur.fetchone()
            self.conn.commit()
            return self._row_to_dict(cur, row)

    def list_actions(self, lesson_id: uuid.UUID) -> list:
        """List all corrective actions for a lesson."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM knowledge.lesson_actions
                WHERE lesson_id = %s
                ORDER BY created_at ASC
            """, (str(lesson_id),))
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ================================================================
    # Test Seeds (LL-04)
    # ================================================================

    def create_test_seed(self, lesson_id: uuid.UUID, seed: dict) -> dict:
        """Create a test seed from a closed LL entry."""
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.lesson_test_seeds (
                    lesson_id, test_layer, test_type, scenario_desc,
                    suggested_code, ci_artifact, status, auto_generated,
                    created_at
                ) VALUES (
                    %(lesson_id)s, %(test_layer)s, %(test_type)s,
                    %(scenario_desc)s, %(suggested_code)s, %(ci_artifact)s,
                    %(status)s, %(auto_generated)s, %(now)s
                )
                RETURNING *
            """, {
                "lesson_id": str(lesson_id),
                "test_layer": seed.get("test_layer", 4),  # default Unit
                "test_type": seed.get("test_type", 0),
                "scenario_desc": seed.get("scenario_desc", ""),
                "suggested_code": seed.get("suggested_code", ""),
                "ci_artifact": seed.get("ci_artifact"),
                "status": seed.get("status", 0),  # proposed
                "auto_generated": seed.get("auto_generated", True),
                "now": now,
            })
            row = cur.fetchone()
            self.conn.commit()

        # Record audit
        self._record_audit_log(
            lesson_id=lesson_id,
            action=8,  # generate_test_seed
            operator_id=seed.get("created_by", "system"),
            comment="Test seed auto-generated from lesson closure",
        )
        return self._row_to_dict(cur, row)

    def list_test_seeds(self, lesson_id: uuid.UUID) -> list:
        """List all test seeds for a lesson."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM knowledge.lesson_test_seeds
                WHERE lesson_id = %s
                ORDER BY created_at DESC
            """, (str(lesson_id),))
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ================================================================
    # List / Search
    # ================================================================

    def list_lessons(self, filters: dict = None, limit: int = 50,
                     offset: int = 0, sort_by: str = "updated_at",
                     sort_dir: str = "DESC") -> tuple:
        """List LL entries with optional filters.

        Supported filters:
        - status: int or list[int]
        - severity: int or list[int]
        - category: int
        - safety_level: int
        - source: int
        - author_id: str
        - assignee_id: str
        - pending_review: bool
        - keyword: str (full-text on title+description)
        """
        if filters is None:
            filters = {}

        clauses = []
        params = []

        filter_map = {
            "status": "status",
            "severity": "severity",
            "category": "category",
            "safety_level": "safety_level",
            "source": "source",
            "author_id": "author_id",
            "assignee_id": "assignee_id",
            "pending_review": "pending_review",
        }

        for key, col in filter_map.items():
            if key in filters:
                val = filters[key]
                if isinstance(val, (list, tuple)):
                    placeholders = ', '.join(['%s'] * len(val))
                    clauses.append(f"{col} IN ({placeholders})")
                    params.extend(val)
                elif isinstance(val, bool):
                    clauses.append(f"{col} = %s")
                    params.append(val)
                else:
                    clauses.append(f"{col} = %s")
                    params.append(val)

        if "keyword" in filters:
            clauses.append(
                "to_tsvector('english', title || ' ' || COALESCE(description, ''))"
                " @@ plainto_tsquery('english', %s)"
            )
            params.append(filters["keyword"])

        where_sql = " AND ".join(clauses) if clauses else "TRUE"

        allowed_sorts = {"updated_at", "created_at", "severity", "title", "status"}
        if sort_by not in allowed_sorts:
            sort_by = "updated_at"
        sort_dir = "ASC" if sort_dir.upper() == "ASC" else "DESC"

        with self.conn.cursor() as cur:
            # Count
            cur.execute(
                f"SELECT COUNT(*) FROM knowledge.lessons WHERE {where_sql}",
                params
            )
            total = cur.fetchone()[0]

            # Data
            cur.execute(
                f"SELECT * FROM knowledge.lessons WHERE {where_sql}"
                f" ORDER BY {sort_by} {sort_dir}"
                f" LIMIT %s OFFSET %s",
                params + [limit, offset]
            )
            rows = cur.fetchall()
            return [self._row_to_dict(cur, r) for r in rows], total

    def search_by_dtc(self, dtc_code: str, limit: int = 20) -> list:
        """Search LL entries by DTC code (exact or prefix)."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM knowledge.lessons
                WHERE EXISTS (
                    SELECT 1 FROM unnest(dtc_codes) AS c
                    WHERE c LIKE %s
                )
                ORDER BY updated_at DESC
                LIMIT %s
            """, (dtc_code + '%' if len(dtc_code) < 5 else dtc_code, limit))
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ================================================================
    # Audit Log (CROSS-04)
    # ================================================================

    def _record_audit_log(self, lesson_id: uuid.UUID, action: int,
                          operator_id: str, comment: str = "",
                          old_status: int = None, new_status: int = None,
                          old_severity: int = None, new_severity: int = None,
                          old_confidence: int = None, new_confidence: int = None,
                          detail: dict = None):
        """Internal: record an LL audit log entry."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.ll_audit_logs (
                    lesson_id, action, operator_id, comment,
                    old_status, new_status,
                    old_severity, new_severity,
                    old_confidence, new_confidence,
                    detail_json
                ) VALUES (
                    %(lesson_id)s, %(action)s, %(operator_id)s,
                    %(comment)s,
                    %(old_status)s, %(new_status)s,
                    %(old_severity)s, %(new_severity)s,
                    %(old_confidence)s, %(new_confidence)s,
                    %(detail)s::jsonb
                )
            """, {
                "lesson_id": str(lesson_id),
                "action": action,
                "operator_id": operator_id,
                "comment": comment,
                "old_status": old_status,
                "new_status": new_status,
                "old_severity": old_severity,
                "new_severity": new_severity,
                "old_confidence": old_confidence,
                "new_confidence": new_confidence,
                "detail": json.dumps(detail) if detail else None,
            })
        self.conn.commit()

    def _record_audit_if_changed(self, new: dict, old: dict, operator_id: str):
        """Record audit entries for significant field changes."""
        # Status change
        if new.get("status") != old.get("status"):
            self._record_audit_log(
                lesson_id=old["id"],
                action=2,  # status_change
                operator_id=operator_id,
                old_status=old.get("status"),
                new_status=new.get("status"),
            )

        # Severity change
        if new.get("severity") != old.get("severity"):
            self._record_audit_log(
                lesson_id=old["id"],
                action=3,  # severity_change
                operator_id=operator_id,
                old_severity=old.get("severity"),
                new_severity=new.get("severity"),
            )

        # Confidence change
        if new.get("confidence") != old.get("confidence"):
            self._record_audit_log(
                lesson_id=old["id"],
                action=5,  # confidence_change
                operator_id=operator_id,
                old_confidence=old.get("confidence"),
                new_confidence=new.get("confidence"),
            )

    def record_audit_log(self, lesson_id: uuid.UUID, action: int,
                         operator_id: str, comment: str = "",
                         old_status: int = None, new_status: int = None,
                         old_confidence: int = None, new_confidence: int = None,
                         detail: dict = None):
        """Public interface to record an LL audit log entry."""
        self._record_audit_log(
            lesson_id=lesson_id, action=action,
            operator_id=operator_id, comment=comment,
            old_status=old_status, new_status=new_status,
            old_confidence=old_confidence, new_confidence=new_confidence,
            detail=detail,
        )

    def list_audit_logs(self, lesson_id: uuid.UUID = None,
                         limit: int = 50, offset: int = 0) -> list:
        """List LL audit logs, optionally filtered by lesson."""
        with self.conn.cursor() as cur:
            if lesson_id:
                cur.execute("""
                    SELECT * FROM knowledge.ll_audit_logs
                    WHERE lesson_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (str(lesson_id), limit, offset))
            else:
                cur.execute("""
                    SELECT * FROM knowledge.ll_audit_logs
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]
