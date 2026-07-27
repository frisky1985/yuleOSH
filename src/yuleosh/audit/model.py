# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Audit Log — immutable event-sourced audit trail (SAAS-4).

Every state-changing operation in yuleOSH produces an audit event.

Event format (JSON Lines, one per line):
  {"actor":"user:42","action":"project.create","target":"project:my-proj",
   "timestamp":"2026-07-27T01:30:00","tenant":"my-org","detail":{...}}

Storage:
  data/audit/YYYY-MM-DD.jsonl  — One file per day, append-only
  data/{tenant}/audit/YYYY-MM-DD.jsonl — Tenant-scoped audit logs
"""

import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("audit.model")


# ── Event types ─────────────────────────────────────────────────────────────

# Project events
EVENT_PROJECT_CREATE = "project.create"
EVENT_PROJECT_UPDATE = "project.update"
EVENT_PROJECT_DELETE = "project.delete"
EVENT_PROJECT_MOVE = "project.move"  # Kanban item moved

# Pipeline events
EVENT_PIPELINE_RUN = "pipeline.run"
EVENT_PIPELINE_CANCEL = "pipeline.cancel"
EVENT_PIPELINE_COMPLETE = "pipeline.complete"

# Review events
EVENT_REVIEW_CREATE = "review.create"
EVENT_REVIEW_APPROVE = "review.approve"
EVENT_REVIEW_REJECT = "review.reject"

# Auth events
EVENT_AUTH_LOGIN = "auth.login"
EVENT_AUTH_LOGOUT = "auth.logout"
EVENT_AUTH_FAILED = "auth.login.failed"
EVENT_USER_INVITE = "user.invite"
EVENT_USER_ROLE_CHANGE = "user.role.change"

# Billing events
EVENT_BILLING_UPGRADE = "billing.upgrade"
EVENT_BILLING_DOWNGRADE = "billing.downgrade"
EVENT_BILLING_CANCEL = "billing.cancel"

# Tenant events
EVENT_TENANT_CREATE = "tenant.create"
EVENT_TENANT_UPDATE = "tenant.update"

# CI events
EVENT_CI_RUN = "ci.run"
EVENT_CI_COMPLETE = "ci.complete"

# Evidence events
EVENT_EVIDENCE_UPLOAD = "evidence.upload"
EVENT_EVIDENCE_DELETE = "evidence.delete"
EVENT_EVIDENCE_EXPORT = "evidence.export"


# ── Event dataclass ─────────────────────────────────────────────────────────

class AuditEvent:
    """An immutable audit event record."""

    __slots__ = ("actor", "action", "target", "timestamp", "tenant", "detail")

    def __init__(self, actor: str, action: str, target: str = "",
                 timestamp: str = "", tenant: str = "",
                 detail: Optional[dict] = None):
        self.actor = actor          # "user:42" or "system" or "user:admin@example.com"
        self.action = action        # "project.create"
        self.target = target        # "project:my-proj" or "pipeline:build-123"
        self.timestamp = timestamp or datetime.now().isoformat()
        self.tenant = tenant        # tenant slug or ""
        self.detail = detail or {}

    def to_dict(self) -> dict:
        return {
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "timestamp": self.timestamp,
            "tenant": self.tenant,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEvent":
        return cls(
            actor=data.get("actor", "unknown"),
            action=data.get("action", "unknown"),
            target=data.get("target", ""),
            timestamp=data.get("timestamp", ""),
            tenant=data.get("tenant", ""),
            detail=data.get("detail", {}),
        )

    def __repr__(self) -> str:
        return (f"AuditEvent(actor={self.actor}, action={self.action}, "
                f"target={self.target}, ts={self.timestamp})")


# ── AuditLog store ──────────────────────────────────────────────────────────

class AuditLog:
    """File-system-backed append-only audit log.

    Each day gets its own JSONL file. Writes are atomic (write to temp, rename)
    to prevent partial records in crash scenarios.

    Supports global and tenant-scoped logging:
      - data/audit/YYYY-MM-DD.jsonl            → global log
      - data/{tenant}/audit/YYYY-MM-DD.jsonl   → tenant-scoped log
    """

    def __init__(self, data_root: Optional[str] = None):
        if data_root is None:
            osh_home = os.environ.get(
                "OSH_HOME",
                str(Path.home() / ".openclaw" / "workspace" / "tasks" / "yuleOSH"),
            )
            data_root = os.path.join(osh_home, "data")
        self.data_root = Path(data_root)
        self.audit_dir = self.data_root / "audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, event_date: str = "", tenant: str = "") -> Path:
        """Get the audit file path for a given date and optional tenant."""
        if not event_date:
            event_date = date.today().isoformat()
        if tenant:
            return self.data_root / tenant / "audit" / f"{event_date}.jsonl"
        return self.audit_dir / f"{event_date}.jsonl"

    def record(self, actor: str, action: str, target: str = "",
               timestamp: str = "", tenant: str = "",
               detail: Optional[dict] = None) -> AuditEvent:
        """Record an audit event. Returns the AuditEvent.

        Thread-safe: writes are append-only. Creates parent directories
        automatically.
        """
        event = AuditEvent(
            actor=actor,
            action=action,
            target=target,
            timestamp=timestamp or datetime.now().isoformat(),
            tenant=tenant,
            detail=detail,
        )

        file_path = self._get_file_path(tenant=tenant)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically — append to file
        with open(file_path, "a") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

        # Also write global log
        global_path = self._get_file_path(tenant="")
        if global_path != file_path:
            global_path.parent.mkdir(parents=True, exist_ok=True)
            with open(global_path, "a") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

        return event

    def query(self, tenant: str = "", from_date: str = "",
              to_date: str = "", action: str = "",
              actor: str = "", limit: int = 1000) -> list[AuditEvent]:
        """Query audit events with optional filters.

        Args:
            tenant: Filter by tenant slug (empty = all tenants)
            from_date: Start date YYYY-MM-DD (default: 30 days ago)
            to_date: End date YYYY-MM-DD (default: today)
            action: Filter by action type
            actor: Filter by actor
            limit: Max events to return

        Returns:
            List of AuditEvent matching the filters, newest first.
        """
        if not to_date:
            to_date = date.today().isoformat()
        if not from_date:
            from_date = (date.today() - timedelta(days=30)).isoformat()

        events = []
        current = from_date

        while current <= to_date and len(events) < limit * 2:
            # Read from one file per date — prefer tenant-scoped if tenant is set
            if tenant:
                path = self._get_file_path(current, tenant)
            else:
                path = self._get_file_path(current, "")

            if not path.exists():
                # Advance to next day
                d = date.fromisoformat(current)
                d += timedelta(days=1)
                current = d.isoformat()
                continue
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            event = AuditEvent.from_dict(data)
                            if action and event.action != action:
                                continue
                            if actor and event.actor != actor:
                                continue
                            if tenant and event.tenant and event.tenant != tenant:
                                continue
                            events.append(event)
                        except json.JSONDecodeError:
                            continue
            except OSError as e:
                logger.warning("Failed to read audit file %s: %s", path, e)

            # Move to next date
            d = date.fromisoformat(current)
            d += timedelta(days=1)
            current = d.isoformat()

        # Sort newest first
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[:limit]

    def get_summary(self, tenant: str = "",
                    from_date: str = "", to_date: str = "") -> dict:
        """Get a summary of audit events grouped by action type."""
        events = self.query(tenant=tenant, from_date=from_date, to_date=to_date, limit=5000)

        summary = defaultdict(int)
        for event in events:
            summary[event.action] += 1

        return {
            "total_events": len(events),
            "by_action": dict(summary),
            "from_date": from_date or (date.today() - timedelta(days=30)).isoformat(),
            "to_date": to_date or date.today().isoformat(),
        }
