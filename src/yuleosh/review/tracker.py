#!/usr/bin/env python3

# @req RS-003
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Review finding tracker — persistent lifecycle management for review findings.

Findings are written to .osh/reviews/<task_name>/findings.jsonl (append-only).
Resolution events are appended as close records.
The tracker can generate traceability closure reports linking req_ids to findings.

Usage:
    tracker = FindingTracker(project_dir, "code-review")
    tracker.record_findings(session)
    tracker.close_finding(fid, "fixed by adding include guard")
    open_f = tracker.get_open_findings(req_id="RS-001")
    count = tracker.auto_close_if_verified("RS-001", {"passed": True})
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .run import ReviewSession


class FindingTracker:
    def __init__(self, project_dir: str, task_name: str) -> None:
        self.project_dir = Path(project_dir)
        self.task_name = task_name
        self._findings_path = (
            self.project_dir / ".osh" / "reviews" / task_name / "findings.jsonl"
        )
        self._findings_path.parent.mkdir(parents=True, exist_ok=True)

    def record_findings(self, session: "ReviewSession") -> None:
        """Append all open findings from *session* to findings.jsonl."""
        with self._findings_path.open("a", encoding="utf-8") as f:
            for review in session.reviews:
                for finding in review.findings:
                    record = {
                        "event": "open",
                        "finding_id": getattr(finding, "finding_id", ""),
                        "severity": finding.severity,
                        "category": finding.category,
                        "file": finding.file,
                        "line": finding.line,
                        "message": finding.message,
                        "req_ids": getattr(finding, "req_ids", []),
                        "status": getattr(finding, "status", "open"),
                        "opened_at": datetime.now().isoformat(),
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def close_finding(
        self, finding_id: str, resolution: str, resolver: str = "auto"
    ) -> bool:
        """Append a close event for *finding_id*. Returns True if the finding existed."""
        all_records = self._read_all()
        open_ids = {r["finding_id"] for r in all_records if r.get("event") == "open"}
        if finding_id not in open_ids:
            return False
        close_record = {
            "event": "close",
            "finding_id": finding_id,
            "resolution": resolution,
            "resolver": resolver,
            "resolved_at": datetime.now().isoformat(),
        }
        with self._findings_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(close_record, ensure_ascii=False) + "\n")
        return True

    def get_open_findings(self, req_id: str | None = None) -> list[dict]:
        """Return findings not yet closed, optionally filtered by req_id."""
        records = self._read_all()
        closed_ids: set[str] = set()
        open_findings: dict[str, dict] = {}

        for r in records:
            fid = r.get("finding_id", "")
            if r.get("event") == "open":
                open_findings[fid] = r
            elif r.get("event") == "close":
                closed_ids.add(fid)

        result = [f for fid, f in open_findings.items() if fid not in closed_ids]
        if req_id is not None:
            result = [f for f in result if req_id in (f.get("req_ids") or [])]
        return result

    def closure_report(self, req_ids: list[str]) -> dict:
        """Return per-req closure stats: {req_id: {open, closed, findings}}."""
        report: dict[str, dict] = {}
        closed_ids = self._closed_ids()
        for rid in req_ids:
            findings = self._all_findings_for_req(rid)
            open_f = [f for f in findings if f["finding_id"] not in closed_ids]
            closed_f = [f for f in findings if f["finding_id"] in closed_ids]
            report[rid] = {
                "open": len(open_f),
                "closed": len(closed_f),
                "findings": findings,
            }
        return report

    def auto_close_if_verified(self, req_id: str, verifier_result: dict) -> int:
        """Auto-close all open findings for *req_id* when verifier reports passed."""
        if not verifier_result.get("passed"):
            return 0
        open_findings = self.get_open_findings(req_id=req_id)
        count = 0
        for f in open_findings:
            if self.close_finding(
                f["finding_id"],
                resolution="verified_by_test",
                resolver="auto",
            ):
                count += 1
        return count

    # ── internals ────────────────────────────────────────────────────────

    def _read_all(self) -> list[dict]:
        if not self._findings_path.exists():
            return []
        records = []
        for line in self._findings_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return records

    def _closed_ids(self) -> set[str]:
        return {
            r["finding_id"]
            for r in self._read_all()
            if r.get("event") == "close"
        }

    def _all_findings_for_req(self, req_id: str) -> list[dict]:
        return [
            r for r in self._read_all()
            if r.get("event") == "open" and req_id in (r.get("req_ids") or [])
        ]
