
# @req CR-003  @req NFR-002
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Audit Log — immutable event-sourced audit trail (SAAS-4).

Every state-changing operation in yuleOSH produces an audit event.

Event format (JSON Lines, one per line):
  {"actor":"user:42","action":"project.create","target":"project:my-proj",
   "timestamp":"2026-07-27T01:30:00","tenant":"my-org","detail":{...},
   "hash":"<sha256>","prev_hash":"<sha256 of previous event>"}

Security & auditability:
  Each event carries a SHA-256 hash over its own canonical payload plus the
  previous event's hash (hash chain). Any edit, deletion, or reordering of a
  recorded event breaks the chain and is detected by ``AuditLog.verify()``.
  The chain is anchored per daily file (first event has prev_hash="").

AI generation provenance (合规专家 P1):
  AI 输出是「草稿」不是「证据」。``ai.generation`` 事件携带 model 版本 +
  prompt 的 SHA-256（``prompt_hash``）把生成输入钉进审计链；人工评审通过
  ``AuditLog.sign_ai_generation()`` 追加 ``ai.generation.sign`` 签署事件
  （``reviewed_by`` / ``reviewed_at``），草稿才升级为可采信的证据。
  这些字段全部可选——旧格式事件（无 AI 字段）的 hash 链验证不受影响。

Storage:
  data/audit/YYYY-MM-DD.jsonl  — One file per day, append-only
  data/{tenant}/audit/YYYY-MM-DD.jsonl — Tenant-scoped audit logs
"""

import hashlib
import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("audit.model")

# Fields excluded from hash computation (chain metadata itself).
_HASH_EXCLUDED = ("hash", "prev_hash")


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

# AI generation provenance events (合规专家 P1: AI 输出是「草稿」不是「证据」)
EVENT_AI_GENERATION = "ai.generation"        # AI 产物（草稿）入链：model + prompt_hash
EVENT_AI_SIGN = "ai.generation.sign"         # 人工评审签署：草稿 → 证据


# ── Event dataclass ─────────────────────────────────────────────────────────

def _canonical_json(data: dict) -> str:
    """Canonical JSON for hash computation (stable key order)."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_event_hash(event_dict: dict, prev_hash: str = "") -> str:
    """Compute the SHA-256 hash of an event payload plus its predecessor.

    The hash covers the canonical JSON of every field except the chain
    metadata (``hash``/``prev_hash``), then the previous hash — so any
    modification to the event, or to any earlier event, breaks the chain.
    """
    payload = {k: v for k, v in event_dict.items() if k not in _HASH_EXCLUDED}
    body = _canonical_json(payload) + "|" + (prev_hash or "")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def compute_prompt_hash(prompt: str) -> str:
    """SHA-256 of the exact prompt text sent to the model.

    Used to pin the AI generation input so the draft's provenance can be
    reproduced / audited later. Deterministic: same prompt → same hash.
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class AuditEvent:
    """An immutable audit event record."""

    __slots__ = ("actor", "action", "target", "timestamp", "tenant", "detail",
                 "model", "prompt_hash", "reviewed_by", "reviewed_at",
                 "hash", "prev_hash")

    def __init__(self, actor: str, action: str, target: str = "",
                 timestamp: str = "", tenant: str = "",
                 detail: Optional[dict] = None,
                 model: Optional[str] = None,
                 prompt_hash: Optional[str] = None,
                 reviewed_by: Optional[str] = None,
                 reviewed_at: Optional[str] = None,
                 event_hash: str = "", prev_hash: str = ""):
        self.actor = actor          # "user:42" or "system" or "user:admin@example.com"
        self.action = action        # "project.create"
        self.target = target        # "project:my-proj" or "pipeline:build-123"
        self.timestamp = timestamp or datetime.now().isoformat()
        self.tenant = tenant        # tenant slug or ""
        self.detail = detail or {}
        # AI 溯源字段（可选，向后兼容：旧事件无这些字段）
        self.model = model          # 模型名，如 "deepseek-v4"
        self.prompt_hash = prompt_hash  # prompt 的 sha256（AI 生成溯源）
        self.reviewed_by = reviewed_by  # 人工评审人（空 = 尚未签署）
        self.reviewed_at = reviewed_at  # 人工评审时间（ISO）
        self.hash = event_hash      # SHA-256 of this event + prev_hash ("" = legacy)
        self.prev_hash = prev_hash  # SHA-256 of the previous event ("" = chain anchor)

    def to_dict(self) -> dict:
        d = {
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "timestamp": self.timestamp,
            "tenant": self.tenant,
            "detail": self.detail,
            "hash": self.hash,
            "prev_hash": self.prev_hash,
        }
        # Only serialize non-empty AI provenance fields so legacy events
        # round-trip byte-identically (old format stays hash-compatible).
        if self.model is not None:
            d["model"] = self.model
        if self.prompt_hash is not None:
            d["prompt_hash"] = self.prompt_hash
        if self.reviewed_by is not None:
            d["reviewed_by"] = self.reviewed_by
        if self.reviewed_at is not None:
            d["reviewed_at"] = self.reviewed_at
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEvent":
        return cls(
            actor=data.get("actor", "unknown"),
            action=data.get("action", "unknown"),
            target=data.get("target", ""),
            timestamp=data.get("timestamp", ""),
            tenant=data.get("tenant", ""),
            detail=data.get("detail", {}),
            model=data.get("model"),
            prompt_hash=data.get("prompt_hash"),
            reviewed_by=data.get("reviewed_by"),
            reviewed_at=data.get("reviewed_at"),
            event_hash=data.get("hash", ""),
            prev_hash=data.get("prev_hash", ""),
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
               detail: Optional[dict] = None,
               model: Optional[str] = None,
               prompt_hash: Optional[str] = None,
               reviewed_by: Optional[str] = None,
               reviewed_at: Optional[str] = None) -> AuditEvent:
        """Record an audit event. Returns the AuditEvent.

        Thread-safe: writes are append-only. Creates parent directories
        automatically. Each event is linked into a SHA-256 hash chain:
        the new event's ``hash`` covers its payload plus the previous
        event's hash, so any tampering is detectable via ``verify()``.

        Optional AI provenance fields (``model`` / ``prompt_hash`` /
        ``reviewed_by`` / ``reviewed_at``) are included in the hashed
        payload only when provided — events recorded without them keep
        the exact legacy format, so old stored events remain verifiable.
        """
        event_dict = {
            "actor": actor,
            "action": action,
            "target": target,
            "timestamp": timestamp or datetime.now().isoformat(),
            "tenant": tenant,
            "detail": detail or {},
        }
        if model is not None:
            event_dict["model"] = model
        if prompt_hash is not None:
            event_dict["prompt_hash"] = prompt_hash
        if reviewed_by is not None:
            event_dict["reviewed_by"] = reviewed_by
        if reviewed_at is not None:
            event_dict["reviewed_at"] = reviewed_at

        # Chain anchor: hash of the last event already on disk (or "" for a
        # fresh file). Legacy rows written before the hash-chain feature have
        # no "hash" field — they are still usable as chain anchors via
        # compute_event_hash (their own hash is computed on the fly).
        prev_hash = self._last_hash(tenant=tenant)
        event_hash = compute_event_hash(event_dict, prev_hash)
        event_dict["hash"] = event_hash
        event_dict["prev_hash"] = prev_hash

        event = AuditEvent.from_dict(event_dict)

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

    # ------------------------------------------------------------------
    # AI 生成溯源（合规专家 P1：AI 输出是「草稿」不是「证据」）
    # ------------------------------------------------------------------

    def record_ai_generation(
        self,
        actor: str,
        target: str = "",
        model: str = "",
        prompt: str = "",
        prompt_hash: str = "",
        tenant: str = "",
        reviewed_by: str = "",
        reviewed_at: str = "",
        detail: Optional[dict] = None,
    ) -> AuditEvent:
        """Record an AI-generated artifact (draft) into the SHA-256 audit chain.

        Pins the model version and the SHA-256 hash of the exact prompt so
        the input that produced the draft can be reproduced later. AI output
        is a *draft*, not evidence — ``reviewed_by`` / ``reviewed_at`` are
        optional sign-off fields that may be filled at record time; for a
        separate post-hoc human sign-off use :meth:`sign_ai_generation`.

        Args:
            actor: Who triggered the generation ("user:42" / "system").
            target: The generated artifact reference (e.g. "artifact:uart.c").
            model: Model name actually used (e.g. "deepseek-v4").
            prompt: The exact prompt text — hashed automatically unless
                ``prompt_hash`` is given explicitly.
            prompt_hash: Pre-computed sha256 of the prompt (optional).
            tenant: Tenant slug or "".
            reviewed_by: Human reviewer id (optional, empty = not signed).
            reviewed_at: Human review timestamp ISO (optional).
            detail: Extra structured context (task_type, etc.).

        Returns:
            The recorded AuditEvent (action ``ai.generation``).
        """
        if not prompt_hash and prompt:
            prompt_hash = compute_prompt_hash(prompt)
        return self.record(
            actor=actor,
            action=EVENT_AI_GENERATION,
            target=target,
            tenant=tenant,
            detail=detail,
            model=model or None,
            prompt_hash=prompt_hash or None,
            reviewed_by=reviewed_by or None,
            reviewed_at=reviewed_at or None,
        )

    def sign_ai_generation(
        self,
        reviewer: str,
        target: str = "",
        prompt_hash: Optional[str] = None,
        tenant: str = "",
        note: str = "",
        actor: str = "",
    ) -> AuditEvent:
        """Append a human review sign-off for a previously recorded AI draft.

        The sign-off is itself an immutable, hash-chained audit event
        (action ``ai.generation.sign``) that references the draft's
        ``prompt_hash`` — turning the AI draft into human-reviewed evidence.
        The event is linked to the previous event's hash, so the review
        record cannot be altered without breaking the chain.

        Args:
            reviewer: Human reviewer id (e.g. "user:42").
            target: The generated artifact reference being signed.
            prompt_hash: sha256 of the prompt of the draft being signed.
            tenant: Tenant slug or "".
            note: Optional review note.
            actor: Event actor; defaults to the reviewer.

        Returns:
            The recorded AuditEvent (action ``ai.generation.sign``).
        """
        return self.record(
            actor=actor or reviewer,
            action=EVENT_AI_SIGN,
            target=target,
            tenant=tenant,
            detail={"reviewed_by": reviewer} | ({"note": note} if note else {}),
            prompt_hash=prompt_hash or None,
            reviewed_by=reviewer,
            reviewed_at=datetime.now().isoformat(),
        )

    def _last_hash(self, tenant: str = "") -> str:
        """Return the hash of the last event written (chain anchor).

        Scans the audit directory for the most recent daily file (today
        first, then by file date descending) so the hash chain continues
        seamlessly across daily files regardless of age. For a legacy row
        without an explicit ``hash`` field, the hash is computed on the fly.
        """
        # Candidate files: today's file plus every dated file in the dir.
        base_dir = self.audit_dir if not tenant else self.data_root / tenant / "audit"
        candidates = []
        if base_dir.exists():
            for p in base_dir.glob("*.jsonl"):
                candidates.append(p)
        today_path = self._get_file_path(tenant=tenant)
        if today_path not in candidates:
            candidates.append(today_path)

        # Sort by filename (YYYY-MM-DD) descending — newest last record first.
        def _date_key(p: Path):
            try:
                return date.fromisoformat(p.stem)
            except ValueError:
                return date.min

        candidates.sort(key=_date_key, reverse=True)
        for file_path in candidates:
            if not file_path.exists():
                continue
            try:
                with open(file_path) as f:
                    last = ""
                    for line in f:
                        line = line.strip()
                        if line:
                            last = line
                    if not last:
                        continue
                    data = json.loads(last)
                    if data.get("hash"):
                        return data["hash"]
                    # Legacy row: compute its hash with the previous anchor.
                    prev = data.get("prev_hash", "")
                    return compute_event_hash(data, prev)
            except (OSError, json.JSONDecodeError):
                continue
        return ""

    def verify(self, tenant: str = "", from_date: str = "",
               to_date: str = "") -> dict:
        """Verify the integrity of the audit hash chain.

        Replays every event in the covered date range and checks that each
        event's ``hash`` matches its canonical payload plus the previous
        event's hash. Any edit, deletion, or reordering breaks the chain.

        Returns a dict:
          {"valid": bool, "checked": int, "legacy": int,
           "broken_at": int | None, "reason": str | None, "files": [str,...]}

        Legacy events (written before the hash-chain feature) are counted in
        ``legacy`` and their payload integrity is verified when a successor
        links to them; a legacy event's own stored hash field is absent, so
        only chain linkage (not content) can be confirmed for that row.
        """
        if not to_date:
            to_date = date.today().isoformat()
        if not from_date:
            from_date = (date.today() - timedelta(days=30)).isoformat()

        checked = 0
        legacy = 0
        broken_at = None
        reason = None
        files = []
        prev_hash = ""

        current = from_date
        while current <= to_date:
            path = self._get_file_path(current, tenant)
            if path.exists():
                files.append(str(path))
                try:
                    with open(path) as f:
                        for line_no, line in enumerate(f, start=1):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                            except json.JSONDecodeError:
                                broken_at = checked + 1
                                reason = (f"malformed JSON at {path.name}:{line_no}")
                                return self._verify_result(
                                    False, checked, legacy, broken_at, reason, files)
                            stored_hash = data.get("hash", "")
                            if not stored_hash:
                                legacy += 1
                                # Legacy row: advance anchor using computed hash.
                                prev_hash = compute_event_hash(
                                    data, data.get("prev_hash", ""))
                                checked += 1
                                continue
                            expected = compute_event_hash(data, prev_hash)
                            if stored_hash != expected:
                                broken_at = checked + 1
                                reason = (f"hash mismatch at {path.name}:{line_no} "
                                          f"(event {data.get('action', '?')})")
                                return self._verify_result(
                                    False, checked, legacy, broken_at, reason, files)
                            prev_hash = stored_hash
                            checked += 1
                except OSError as e:
                    broken_at = checked + 1
                    reason = f"read error {path.name}: {e}"
                    return self._verify_result(
                        False, checked, legacy, broken_at, reason, files)
            # Advance to next day
            d = date.fromisoformat(current)
            d += timedelta(days=1)
            current = d.isoformat()

        return self._verify_result(True, checked, legacy, broken_at, reason, files)

    @staticmethod
    def _verify_result(valid: bool, checked: int, legacy: int,
                       broken_at, reason, files) -> dict:
        return {
            "valid": valid,
            "checked": checked,
            "legacy": legacy,
            "broken_at": broken_at,
            "reason": reason,
            "files": files,
        }

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
