# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH FMEA — PostgreSQL store layer.

Implements CRUD for FMEA entries and items with:
- DFMEA / PFMEA unified model (fmea_scope)
- Classic RPN (severity × occurrence × detection) — GENERATED ALWAYS column
- AIAG-VDA Action Priority (ap_priority: H/M/L)
- Cross-ECU failure chain management
- Item forking (FMEA-09)
- Audit logging (CROSS-04)
"""

import json
import uuid
from datetime import datetime
from typing import Optional


class FMEAStore:
    """FMEA entry + item CRUD + cross-ECU chain management.

    All methods raise psycopg2.DatabaseError on failure.
    """

    # ── FMEA scope (DFMEA vs PFMEA) ────────────────────────────────
    SCOPE_DESIGN = 0   # DFMEA
    SCOPE_PROCESS = 1  # PFMEA

    # ── Entry status (4 状态) ──────────────────────────────────────
    ENTRY_DRAFT = 0
    ENTRY_REVIEW = 1
    ENTRY_APPROVED = 2
    ENTRY_SUPERSEDED = 3

    # ── Item status (6 状态) ───────────────────────────────────────
    ITEM_OPEN = 0
    ITEM_ANALYSIS = 1
    ITEM_ACTION_PLANNED = 2
    ITEM_ACTION_DONE = 3
    ITEM_VERIFIED = 4
    ITEM_CLOSED = 5

    _ITEM_STATUS_NAMES = {
        0: "open", 1: "analysis", 2: "action_planned",
        3: "action_done", 4: "verified", 5: "closed",
    }

    # ── Action priority ────────────────────────────────────────────
    AP_H = "H"
    AP_M = "M"
    AP_L = "L"

    # ── Cross-ECU relation types ───────────────────────────────────
    CROSS_CASCADE = 0
    CROSS_SHARED_CAUSE = 1
    CROSS_REDUNDANCY = 2
    CROSS_FEEDBACK = 3

    # ── Scope enum ─────────────────────────────────────────────────
    SINGLE_ECU = 0
    CROSS_ECU = 1
    SYSTEM_LEVEL = 2

    # ── Action status ──────────────────────────────────────────────
    ACT_PROPOSED = 0
    ACT_APPROVED = 1
    ACT_IN_PROGRESS = 2
    ACT_DONE = 3
    ACT_VERIFIED = 4
    ACT_CANCELLED = 5

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
        # Handle array fields
        for field in ('dtc_codes', 'evidence_ids'):
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
    # FMEA Entry CRUD
    # ================================================================

    def create_entry(self, entry: dict) -> dict:
        """Create a new FMEA entry (DFMEA or PFMEA).

        Required fields: name, system, creator_id
        Optional fields: description, subsystem, fmea_scope, scope,
                         fmea_version, safety_level, article_id,
                         parent_entry_id, reviewer_id, status,
                         source_yaml, source_hash,
                         process_step, process_parameter, etc. (PFMEA)
        """
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.fmea_entries (
                    name, description, fmea_scope, system, subsystem,
                    scope, fmea_version, safety_level, article_id,
                    parent_entry_id, creator_id, reviewer_id, status,
                    source_yaml, source_hash,
                    process_step, process_parameter,
                    process_machine, station_id, material_id,
                    created_at, updated_at
                ) VALUES (
                    %(name)s, %(description)s, %(fmea_scope)s,
                    %(system)s, %(subsystem)s,
                    %(scope)s, %(fmea_version)s, %(safety_level)s,
                    %(article_id)s, %(parent_entry_id)s,
                    %(creator_id)s, %(reviewer_id)s, %(status)s,
                    %(source_yaml)s, %(source_hash)s,
                    %(process_step)s, %(process_parameter)s,
                    %(process_machine)s, %(station_id)s, %(material_id)s,
                    %(now)s, %(now)s
                )
                RETURNING *
            """, {
                "name": entry["name"],
                "description": entry.get("description", ""),
                "fmea_scope": entry.get("fmea_scope", self.SCOPE_DESIGN),
                "system": entry["system"],
                "subsystem": entry.get("subsystem", ""),
                "scope": entry.get("scope", self.SINGLE_ECU),
                "fmea_version": entry.get("fmea_version", "0.1.0"),
                "safety_level": entry.get("safety_level", self.ASIL_QM),
                "article_id": str(entry["article_id"]) if entry.get("article_id") else None,
                "parent_entry_id": str(entry["parent_entry_id"]) if entry.get("parent_entry_id") else None,
                "creator_id": entry["creator_id"],
                "reviewer_id": entry.get("reviewer_id"),
                "status": entry.get("status", self.ENTRY_DRAFT),
                "source_yaml": entry.get("source_yaml", ""),
                "source_hash": entry.get("source_hash", ""),
                "process_step": entry.get("process_step", ""),
                "process_parameter": entry.get("process_parameter", ""),
                "process_machine": entry.get("process_machine", ""),
                "station_id": entry.get("station_id", ""),
                "material_id": entry.get("material_id", ""),
                "now": now,
            })
            row = cur.fetchone()
            self.conn.commit()

            result = self._row_to_dict(cur, row)
            # Record audit
            self._record_audit_log(
                fmea_entry_id=result["id"],
                action=1,  # entry_created
                operator_id=entry["creator_id"],
                comment=f"FMEA entry '{entry['name']}' created",
                detail={"fmea_scope": entry.get("fmea_scope", 0),
                        "system": entry["system"]},
            )
            return result

    def get_entry(self, entry_id: uuid.UUID) -> Optional[dict]:
        """Get a single FMEA entry by UUID."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM knowledge.fmea_entries WHERE id = %s",
                (str(entry_id),)
            )
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def get_entry_by_system(self, system: str) -> Optional[dict]:
        """Get the latest FMEA entry for a given system name."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM knowledge.fmea_entries
                WHERE system = %s
                ORDER BY fmea_version DESC, updated_at DESC
                LIMIT 1
            """, (system,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def update_entry(self, entry_id: uuid.UUID, updates: dict,
                     operator_id: str = "") -> Optional[dict]:
        """Update an FMEA entry. Returns updated row or None.

        Records audit log for status/version changes.
        """
        allowed_fields = {
            "name", "description", "fmea_scope", "system", "subsystem",
            "scope", "fmea_version", "safety_level", "article_id",
            "parent_entry_id", "reviewer_id", "status",
            "source_yaml", "source_hash",
            "process_step", "process_parameter",
            "process_machine", "station_id", "material_id",
        }
        now = datetime.now().isoformat()

        old = self.get_entry(entry_id)
        if not old:
            return None

        set_parts = []
        params = {}

        for field in allowed_fields:
            if field in updates:
                set_parts.append(f"{field} = %({field})s")
                params[field] = updates[field]

        if not set_parts:
            return old

        set_parts.append("updated_at = %(updated_at)s")
        params["updated_at"] = now
        params["id"] = str(entry_id)

        with self.conn.cursor() as cur:
            cur.execute(f"""
                UPDATE knowledge.fmea_entries
                SET {', '.join(set_parts)}
                WHERE id = %(id)s
                RETURNING *
            """, params)
            row = cur.fetchone()
            self.conn.commit()

            if row and operator_id:
                result = self._row_to_dict(cur, row)
                if result.get("status") != old.get("status"):
                    self._record_audit_log(
                        fmea_entry_id=entry_id,
                        action=2,  # entry_status_change
                        operator_id=operator_id,
                        old_status=old.get("status"),
                        new_status=result.get("status"),
                    )

            return self._row_to_dict(cur, row) if row else None

    def list_entries(self, filters: dict = None, limit: int = 50,
                     offset: int = 0) -> tuple:
        """List FMEA entries with optional filters.

        Filters: system, subsystem, fmea_scope, scope, status, safety_level
        """
        if filters is None:
            filters = {}

        clauses = []
        params = []

        for key in ("system", "subsystem", "fmea_scope", "scope", "status", "safety_level"):
            if key in filters:
                val = filters[key]
                if isinstance(val, (list, tuple)):
                    placeholders = ', '.join(['%s'] * len(val))
                    clauses.append(f"{key} IN ({placeholders})")
                    params.extend(val)
                else:
                    clauses.append(f"{key} = %s")
                    params.append(val)

        where_sql = " AND ".join(clauses) if clauses else "TRUE"

        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM knowledge.fmea_entries WHERE {where_sql}",
                params
            )
            total = cur.fetchone()[0]

            cur.execute(
                f"SELECT * FROM knowledge.fmea_entries WHERE {where_sql}"
                f" ORDER BY updated_at DESC LIMIT %s OFFSET %s",
                params + [limit, offset]
            )
            rows = cur.fetchall()
            return [self._row_to_dict(cur, r) for r in rows], total

    # ================================================================
    # FMEA Item CRUD
    # ================================================================

    def create_item(self, entry_id: uuid.UUID, item: dict) -> dict:
        """Create a new FMEA item (failure mode) under an entry.

        rpn is auto-calculated via GENERATED ALWAYS AS (severity × occurrence × detection).
        ap_priority should be set by the caller (AIAG-VDA matrix calculation).

        Required fields: function_desc, component, failure_mode,
                         failure_effect, failure_cause,
                         severity, occurrence, detection
        Optional fields: item_index, autosar_layer, safety_level, layer,
                         failure_mechanism, current_control, control_type,
                         recommended_action,
                         ap_severity, ap_occurrence, ap_detection, ap_priority,
                         planned_severity, planned_occurrence, planned_detection,
                         dtc_codes, evidence_ids, confidence, status
        """
        now = datetime.now().isoformat()

        # Auto-assign item_index if not provided
        if "item_index" not in item:
            with self.conn.cursor() as c:
                c.execute(
                    "SELECT COALESCE(MAX(item_index), 0) + 1 FROM knowledge.fmea_items WHERE fmea_entry_id = %s",
                    (str(entry_id),)
                )
                item["item_index"] = c.fetchone()[0]

        # Validate planned RPN: if any planned field is set, all three are needed
        planned_fields = (item.get("planned_severity"), item.get("planned_occurrence"), item.get("planned_detection"))
        if any(f is not None for f in planned_fields):
            for f in planned_fields:
                if f is None:
                    raise ValueError("planned_severity, planned_occurrence, and planned_detection must all be set together")

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.fmea_items (
                    fmea_entry_id, item_index,
                    autosar_layer, safety_level,
                    function_desc, component, layer,
                    failure_mode, failure_effect, failure_cause,
                    failure_mechanism,
                    severity, occurrence, detection,
                    ap_severity, ap_occurrence, ap_detection, ap_priority,
                    current_control, control_type,
                    recommended_action,
                    planned_severity, planned_occurrence, planned_detection,
                    dtc_codes, evidence_ids,
                    confidence, status,
                    created_at, updated_at
                ) VALUES (
                    %(entry_id)s, %(item_index)s,
                    %(autosar_layer)s, %(safety_level)s,
                    %(function_desc)s, %(component)s, %(layer)s,
                    %(failure_mode)s, %(failure_effect)s, %(failure_cause)s,
                    %(failure_mechanism)s,
                    %(severity)s, %(occurrence)s, %(detection)s,
                    %(ap_severity)s, %(ap_occurrence)s, %(ap_detection)s,
                    %(ap_priority)s,
                    %(current_control)s, %(control_type)s,
                    %(recommended_action)s,
                    %(planned_severity)s, %(planned_occurrence)s,
                    %(planned_detection)s,
                    %(dtc_codes)s, %(evidence_ids)s,
                    %(confidence)s, %(status)s,
                    %(now)s, %(now)s
                )
                RETURNING *
            """, {
                "entry_id": str(entry_id),
                "item_index": item["item_index"],
                "autosar_layer": item.get("autosar_layer", 0),
                "safety_level": item.get("safety_level", self.ASIL_QM),
                "function_desc": item["function_desc"],
                "component": item["component"],
                "layer": item.get("layer", ""),
                "failure_mode": item["failure_mode"],
                "failure_effect": item["failure_effect"],
                "failure_cause": item["failure_cause"],
                "failure_mechanism": item.get("failure_mechanism", ""),
                "severity": item["severity"],
                "occurrence": item["occurrence"],
                "detection": item["detection"],
                "ap_severity": item.get("ap_severity"),
                "ap_occurrence": item.get("ap_occurrence"),
                "ap_detection": item.get("ap_detection"),
                "ap_priority": item.get("ap_priority"),
                "current_control": item.get("current_control", ""),
                "control_type": item.get("control_type", 0),
                "recommended_action": item.get("recommended_action", ""),
                "planned_severity": item.get("planned_severity"),
                "planned_occurrence": item.get("planned_occurrence"),
                "planned_detection": item.get("planned_detection"),
                "dtc_codes": item.get("dtc_codes", []),
                "evidence_ids": item.get("evidence_ids", []),
                "confidence": item.get("confidence", 100),
                "status": item.get("status", self.ITEM_OPEN),
                "now": now,
            })
            row = cur.fetchone()
            self.conn.commit()

            result = self._row_to_dict(cur, row)

            # Get the entry for the operator
            entry = self.get_entry(entry_id)
            operator_id = entry.get("creator_id", "system") if entry else "system"

            # Record audit
            self._record_item_audit_log(
                fmea_item_id=result["id"],
                action=3,  # item_created
                operator_id=operator_id,
                comment=f"FMEA item '{result['failure_mode']}' created",
                detail={
                    "entry_id": str(entry_id),
                    "rpn": result.get("rpn"),
                    "ap_priority": result.get("ap_priority"),
                },
            )
            return result

    def get_item(self, item_id: uuid.UUID) -> Optional[dict]:
        """Get a single FMEA item by UUID."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM knowledge.fmea_items WHERE id = %s",
                (str(item_id),)
            )
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def update_item(self, item_id: uuid.UUID, updates: dict,
                    operator_id: str = "") -> Optional[dict]:
        """Update an FMEA item. Returns updated row or None.

        Records audit log for status/RPN/AP changes.
        """
        allowed_fields = {
            "function_desc", "component", "layer",
            "failure_mode", "failure_effect", "failure_cause",
            "failure_mechanism",
            "severity", "occurrence", "detection",
            "ap_severity", "ap_occurrence", "ap_detection", "ap_priority",
            "current_control", "control_type",
            "recommended_action",
            "planned_severity", "planned_occurrence", "planned_detection",
            "dtc_codes", "evidence_ids",
            "autosar_layer", "safety_level",
            "confidence", "status", "item_index",
        }
        now = datetime.now().isoformat()

        old = self.get_item(item_id)
        if not old:
            return None

        set_parts = []
        params = {}

        for field in allowed_fields:
            if field in updates:
                if field in ("dtc_codes", "evidence_ids"):
                    set_parts.append(f"{field} = %({field})s")
                    params[field] = updates[field]
                else:
                    set_parts.append(f"{field} = %({field})s")
                    params[field] = updates[field]

        if not set_parts:
            return old

        set_parts.append("updated_at = %(updated_at)s")
        params["updated_at"] = now
        params["id"] = str(item_id)

        with self.conn.cursor() as cur:
            cur.execute(f"""
                UPDATE knowledge.fmea_items
                SET {', '.join(set_parts)}
                WHERE id = %(id)s
                RETURNING *
            """, params)
            row = cur.fetchone()
            self.conn.commit()

            if row and operator_id:
                result = self._row_to_dict(cur, row)
                self._record_item_audit_if_changed(result, old, operator_id)

            return self._row_to_dict(cur, row) if row else None

    def list_items(self, entry_id: uuid.UUID) -> list:
        """List all FMEA items under an entry, ordered by item_index."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM knowledge.fmea_items
                WHERE fmea_entry_id = %s
                ORDER BY item_index ASC
            """, (str(entry_id),))
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    def fork_item(self, item_id: uuid.UUID, new_entry_id: uuid.UUID,
                  override_fields: dict = None) -> dict:
        """Fork (derive) a new FMEA item from an existing one (FMEA-09).

        All fields are copied from the source item, with optional overrides.
        The new item is created under new_entry_id with status=open.
        """
        source = self.get_item(item_id)
        if not source:
            raise ValueError(f"Source item {item_id} not found")

        # Build new item from source + overrides
        new_item = dict(source)
        for key in ("id", "fmea_entry_id", "rpn", "planned_rpn", "created_at", "updated_at"):
            new_item.pop(key, None)
        new_item["status"] = self.ITEM_OPEN
        new_item["item_index"] = None  # auto-assign

        # Apply overrides
        if override_fields:
            new_item.update(override_fields)

        result = self.create_item(new_entry_id, new_item)

        # Record the fork in the original item's audit log
        self._record_item_audit_log(
            fmea_item_id=item_id,
            action=13,  # fork
            operator_id="system",
            comment=f"Forked to item {result['id']}",
            detail={"target_item_id": str(result["id"]),
                    "target_entry_id": str(new_entry_id)},
        )

        return result

    # ================================================================
    # Cross-ECU Failure Chain (FMEA-03)
    # ================================================================

    def create_cross_ecu_link(self, source_item_id: uuid.UUID,
                               target_item_id: uuid.UUID,
                               relation_type: int = 0,
                               propagation_desc: str = "",
                               propagation_delay: str = None,
                               source_ecu_id: str = "",
                               target_ecu_id: str = "",
                               signal_name: str = "") -> dict:
        """Create a cross-ECU failure propagation link between two items."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.fmea_item_cross_ecu (
                    source_item_id, target_item_id, relation_type,
                    propagation_desc, propagation_delay,
                    source_ecu_id, target_ecu_id, signal_name
                ) VALUES (
                    %(source)s, %(target)s, %(rel)s,
                    %(desc)s, %(delay)s,
                    %(src_ecu)s, %(tgt_ecu)s, %(signal)s
                )
                RETURNING *
            """, {
                "source": str(source_item_id),
                "target": str(target_item_id),
                "rel": relation_type,
                "desc": propagation_desc,
                "delay": propagation_delay,
                "src_ecu": source_ecu_id,
                "tgt_ecu": target_ecu_id,
                "signal": signal_name,
            })
            row = cur.fetchone()
            self.conn.commit()
            result = self._row_to_dict(cur, row)

            # Mark both items as open (FMEA-03: cascade status reset)
            self.update_item(source_item_id, {"status": self.ITEM_OPEN},
                             operator_id="system")
            self.update_item(target_item_id, {"status": self.ITEM_OPEN},
                             operator_id="system")

            self._record_item_audit_log(
                fmea_item_id=source_item_id,
                action=10,  # cross_ecu_update
                operator_id="system",
                comment="Cross-ECU link created, status reset to open",
                detail={"link_id": str(result["id"]),
                        "target_item": str(target_item_id)},
            )

            return result

    def list_cross_ecu_links(self, item_id: uuid.UUID = None,
                              entry_id: uuid.UUID = None) -> list:
        """List cross-ECU links, filtered by item or by entry."""
        with self.conn.cursor() as cur:
            if item_id:
                cur.execute("""
                    SELECT * FROM knowledge.fmea_item_cross_ecu
                    WHERE source_item_id = %s OR target_item_id = %s
                    ORDER BY created_at DESC
                """, (str(item_id), str(item_id)))
            elif entry_id:
                cur.execute("""
                    SELECT l.* FROM knowledge.fmea_item_cross_ecu l
                    JOIN knowledge.fmea_items si ON si.id = l.source_item_id
                    JOIN knowledge.fmea_items ti ON ti.id = l.target_item_id
                    WHERE si.fmea_entry_id = %(entry)s
                       OR ti.fmea_entry_id = %(entry)s
                    ORDER BY l.created_at DESC
                """, {"entry": str(entry_id)})
            else:
                cur.execute("""
                    SELECT * FROM knowledge.fmea_item_cross_ecu
                    ORDER BY created_at DESC
                """)
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    def get_cross_ecu_chain_graph(self, entry_id: uuid.UUID) -> dict:
        """Get the full cross-ECU chain as a directed graph for visualization.

        Returns {"nodes": [...], "edges": [...]} where:
        - nodes: list of {id, entry_id, item_index, failure_mode, component, ecu_id}
        - edges: list of {source, target, relation_type, propagation_desc, signal_name}
        """
        items = self.list_items(entry_id)
        links = self.list_cross_ecu_links(entry_id=entry_id)

        nodes = []
        for item in items:
            node = {
                "id": str(item["id"]),
                "fmea_entry_id": str(item["fmea_entry_id"]),
                "item_index": item["item_index"],
                "failure_mode": item["failure_mode"],
                "component": item["component"],
                "ecu_id": "",
            }
            nodes.append(node)

        edges = []
        for link in links:
            edge = {
                "source": str(link["source_item_id"]),
                "target": str(link["target_item_id"]),
                "relation_type": link["relation_type"],
                "propagation_desc": link["propagation_desc"],
                "signal_name": link["signal_name"],
                "propagation_delay": link["propagation_delay"],
            }
            edges.append(edge)

        return {"nodes": nodes, "edges": edges}

    # ================================================================
    # FMEA Actions
    # ================================================================

    def create_action(self, item_id: uuid.UUID, action: dict) -> dict:
        """Create a corrective action for an FMEA item."""
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.fmea_actions (
                    fmea_item_id, description, owner_id,
                    rpn_before, rpn_after, status, priority,
                    due_at, evidence_id, test_link_id,
                    created_at, updated_at
                ) VALUES (
                    %(item_id)s, %(description)s, %(owner_id)s,
                    %(rpn_before)s, %(rpn_after)s, %(status)s,
                    %(priority)s, %(due_at)s, %(evidence_id)s,
                    %(test_link_id)s, %(now)s, %(now)s
                )
                RETURNING *
            """, {
                "item_id": str(item_id),
                "description": action["description"],
                "owner_id": action.get("owner_id", ""),
                "rpn_before": action.get("rpn_before", 0),
                "rpn_after": action.get("rpn_after"),
                "status": action.get("status", self.ACT_PROPOSED),
                "priority": action.get("priority", 1),
                "due_at": action.get("due_at"),
                "evidence_id": action.get("evidence_id"),
                "test_link_id": str(action["test_link_id"]) if action.get("test_link_id") else None,
                "now": now,
            })
            row = cur.fetchone()
            self.conn.commit()
            result = self._row_to_dict(cur, row)

            self._record_item_audit_log(
                fmea_item_id=item_id,
                action=6,  # action_created
                operator_id=action.get("owner_id", "system"),
                comment=f"Action: {action['description'][:60]}",
            )
            return result

    def list_actions(self, item_id: uuid.UUID) -> list:
        """List all corrective actions for an FMEA item."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM knowledge.fmea_actions
                WHERE fmea_item_id = %s
                ORDER BY created_at DESC
            """, (str(item_id),))
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ================================================================
    # DTC Search (FMEA-07)
    # ================================================================

    def search_items_by_dtc(self, dtc_code: str, limit: int = 20) -> list:
        """Search FMEA items by DTC code (exact or prefix)."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT fi.*, fe.name AS entry_name, fe.system AS entry_system
                FROM knowledge.fmea_items fi
                JOIN knowledge.fmea_entries fe ON fe.id = fi.fmea_entry_id
                WHERE EXISTS (
                    SELECT 1 FROM unnest(fi.dtc_codes) AS c
                    WHERE c LIKE %s
                )
                ORDER BY fi.rpn DESC
                LIMIT %s
            """, (dtc_code + '%' if len(dtc_code) < 5 else dtc_code, limit))
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    def get_dtc_fmea_matrix(self, dtc_code: str) -> list:
        """Get the DTC → FMEA failure mode matrix view."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    d.dtc_code, d.dtc_description,
                    fi.id AS fmea_item_id,
                    fi.failure_mode,
                    fi.failure_effect,
                    fi.rpn,
                    fi.ap_priority,
                    fi.status AS item_status,
                    fe.name AS entry_name,
                    fe.system AS entry_system
                FROM knowledge.knowledge_dtc_map d
                JOIN knowledge.fmea_items fi ON fi.id = d.fmea_item_id
                JOIN knowledge.fmea_entries fe ON fe.id = fi.fmea_entry_id
                WHERE d.dtc_code = %s
                ORDER BY fi.rpn DESC
            """, (dtc_code,))
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ================================================================
    # Fork Entry (FMEA-09)
    # ================================================================

    def fork_entry(self, entry_id: uuid.UUID, new_name: str = None,
                   overrides: dict = None) -> dict:
        """Fork (derive) a new FMEA entry from an existing one.

        All items are copied. The new entry's status is draft.
        Returns the new entry.
        """
        source = self.get_entry(entry_id)
        if not source:
            raise ValueError(f"Source entry {entry_id} not found")

        new_entry = {
            "name": new_name or f"{source['name']} (fork)",
            "description": source.get("description", ""),
            "fmea_scope": source.get("fmea_scope", self.SCOPE_DESIGN),
            "system": source.get("system", ""),
            "subsystem": source.get("subsystem", ""),
            "scope": source.get("scope", self.SINGLE_ECU),
            "fmea_version": "0.1.0",
            "safety_level": source.get("safety_level", self.ASIL_QM),
            "article_id": source.get("article_id"),
            "parent_entry_id": entry_id,
            "creator_id": source.get("creator_id", "system"),
            "reviewer_id": None,
            "status": self.ENTRY_DRAFT,
            "source_yaml": source.get("source_yaml", ""),
            "source_hash": "",
        }
        if overrides:
            new_entry.update(overrides)

        # Create entry
        result = self.create_entry(new_entry)

        # Copy all items
        source_items = self.list_items(entry_id)
        for item in source_items:
            for key in ("id", "fmea_entry_id", "rpn", "planned_rpn",
                        "created_at", "updated_at"):
                item.pop(key, None)
            item["status"] = self.ITEM_OPEN
            item["item_index"] = None
            self.create_item(result["id"], item)

        # Record fork audit
        self._record_entry_audit_log(
            fmea_entry_id=entry_id,
            action=13,  # fork
            operator_id=new_entry.get("creator_id", "system"),
            comment=f"Entry forked to '{result['name']}'",
            detail={"target_entry": str(result["id"])},
        )

        return result

    # ================================================================
    # Audit Log (CROSS-04)
    # ================================================================

    def _record_entry_audit_log(self, fmea_entry_id: uuid.UUID, action: int,
                                operator_id: str, comment: str = "",
                                old_status: int = None, new_status: int = None,
                                detail: dict = None):
        """Internal: record an FMEA entry-level audit log."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.fmea_audit_logs (
                    fmea_entry_id, action, operator_id, comment,
                    detail_json
                ) VALUES (%s, %s, %s, %s, %s::jsonb)
            """, (
                str(fmea_entry_id), action, operator_id, comment,
                json.dumps(detail) if detail else None,
            ))
        self.conn.commit()

    def _record_item_audit_log(self, fmea_item_id: uuid.UUID, action: int,
                               operator_id: str, comment: str = "",
                               detail: dict = None):
        """Internal: record an FMEA item-level audit log."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.fmea_audit_logs (
                    fmea_item_id, action, operator_id, comment,
                    detail_json
                ) VALUES (%s, %s, %s, %s, %s::jsonb)
            """, (
                str(fmea_item_id), action, operator_id, comment,
                json.dumps(detail) if detail else None,
            ))
        self.conn.commit()

    def _record_item_audit_if_changed(self, new: dict, old: dict, operator_id: str):
        """Record audit entries for significant FMEA item changes."""
        # Status change
        if new.get("status") != old.get("status"):
            self._record_item_audit_log(
                fmea_item_id=old["id"],
                action=4,  # item_status_change
                operator_id=operator_id,
                old_status=old.get("status"),
                new_status=new.get("status"),
                detail={"item_index": old.get("item_index")},
            )

        # RPN change (any of S/O/D changed)
        for field in ("severity", "occurrence", "detection"):
            if new.get(field) != old.get(field):
                self._record_item_audit_log(
                    fmea_item_id=old["id"],
                    action=5,  # rpn_update
                    operator_id=operator_id,
                    comment=f"RPN changed: {old.get('rpn')} → {new.get('rpn')}",
                    detail={"field": field, "old": old.get(field), "new": new.get(field)},
                )
                break

        # AP priority change
        if new.get("ap_priority") != old.get("ap_priority"):
            self._record_item_audit_log(
                fmea_item_id=old["id"],
                action=12,  # ap_change
                operator_id=operator_id,
                comment=f"AP priority changed: {old.get('ap_priority')} → {new.get('ap_priority')}",
                detail={"old_ap": old.get("ap_priority"), "new_ap": new.get("ap_priority")},
            )

        # Confidence change
        if new.get("confidence") != old.get("confidence"):
            self._record_item_audit_log(
                fmea_item_id=old["id"],
                action=8,  # confidence_change
                operator_id=operator_id,
                old_confidence=old.get("confidence"),
                new_confidence=new.get("confidence"),
            )

    def list_audit_logs(self, entry_id: uuid.UUID = None,
                         item_id: uuid.UUID = None,
                         limit: int = 50, offset: int = 0) -> list:
        """List FMEA audit logs, optionally filtered."""
        with self.conn.cursor() as cur:
            if item_id:
                cur.execute("""
                    SELECT * FROM knowledge.fmea_audit_logs
                    WHERE fmea_item_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (str(item_id), limit, offset))
            elif entry_id:
                cur.execute("""
                    SELECT * FROM knowledge.fmea_audit_logs
                    WHERE fmea_entry_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (str(entry_id), limit, offset))
            else:
                cur.execute("""
                    SELECT * FROM knowledge.fmea_audit_logs
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
            return [self._row_to_dict(cur, r) for r in cur.fetchall()]

    # ================================================================
    # Bulk Operations
    # ================================================================

    def bulk_create_items(self, entry_id: uuid.UUID, items: list) -> list:
        """Bulk create FMEA items under an entry (for YAML import)."""
        results = []
        for item in items:
            results.append(self.create_item(entry_id, item))
        return results

    def sync_from_yaml(self, entry_id: uuid.UUID, yaml_items: list,
                       source_hash: str) -> dict:
        """Sync FMEA items from YAML.

        Returns diff: {inserted: N, updated: N, deleted: N, unchanged: N}
        """
        existing = {str(it["item_index"]): it for it in self.list_items(entry_id)}
        incoming = {it["item_index"]: it for it in yaml_items}

        inserted = 0
        updated = 0
        deleted = 0
        unchanged = 0

        # Process incoming items
        for idx, item in incoming.items():
            if idx not in existing:
                self.create_item(entry_id, item)
                inserted += 1
            else:
                old = existing[idx]
                # Check if anything changed
                changed = any(
                    item.get(k) != old.get(k)
                    for k in ("failure_mode", "failure_effect", "failure_cause",
                              "severity", "occurrence", "detection",
                              "current_control", "recommended_action",
                              "ap_severity", "ap_occurrence", "ap_detection")
                )
                if changed:
                    item["item_index"] = idx
                    self.update_item(old["id"], item, operator_id="yaml_sync")
                    updated += 1
                else:
                    unchanged += 1

        # Check for deleted items (in existing but not in incoming)
        for idx in existing:
            if idx not in incoming:
                # Don't physically delete — mark as superseded (close them)
                self.update_item(existing[idx]["id"],
                                 {"status": self.ITEM_CLOSED},
                                 operator_id="yaml_sync")
                deleted += 1

        # Update entry source hash
        self.update_entry(entry_id, {"source_hash": source_hash},
                          operator_id="yaml_sync")

        # Record sync audit
        self._record_entry_audit_log(
            fmea_entry_id=entry_id,
            action=9,  # yaml_sync
            operator_id="yaml_sync",
            comment=f"YAML sync: +{inserted} ~{updated} -{deleted} ={unchanged}",
        )

        return {
            "inserted": inserted,
            "updated": updated,
            "deleted": deleted,
            "unchanged": unchanged,
        }
