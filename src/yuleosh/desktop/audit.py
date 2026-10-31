# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Desktop compliance audit orchestration (P5).

One-click production of the ASPICE audit deliverables for a desktop project:

  1. Compliance check (BP pass/fail/partial summary)
  2. Evidence collection + report generation (traceability / coverage / ...)
  3. Compliance pack ZIP (``.osh/evidence/compliance-pack.zip``)
  4. ASPICE audit report (HTML + JSON + text) under ``.osh/reports/``

Design notes
------------
* **Fail-closed, no fake-green:** when evidence is absent the audit is
  reported as ``not_run`` rather than silently passing.
* **E1–E3 are evidence-coverage grades, NOT ASPICE capability levels.**
  The disclaimer is rendered in every report and carried in the API
  response so callers can never mistake them for a formal assessment.
* **Non-fatal stages:** each stage runs in its own try/except; a failure
  in one stage does not block the others, but is recorded in the
  ``errors`` list so the summary stays honest.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from yuleosh.desktop import workspace

log = logging.getLogger("desktop.audit")

#: Disclaimer carried in every audit response — E1–E3 ≠ ASPICE CL.
DISCLAIMER_EVIDENCE_COVERAGE = (
    "E1–E3 are evidence-coverage grades computed from the "
    "passing-evidence ratio. They are NOT Automotive SPICE capability "
    "levels (CL) and do not constitute any formal ASPICE assessment "
    "result. A formal assessment must be performed by an accredited "
    "assessor."
)


def _project_meta(project_id: str) -> dict:
    return workspace._load_meta(project_id)


def _project_dir(project_id: str) -> Path:
    return workspace._project_dir(project_id)


def _evidence_dir(project_id: str) -> Path:
    return _project_dir(project_id) / ".osh" / "evidence"


def _reports_dir(project_id: str) -> Path:
    return _project_dir(project_id) / ".osh" / "reports"


def _safe_stage(name: str, fn, errors: list[str]) -> Any:
    """Run ``fn`` capturing exceptions into ``errors``.

    Returns the function's return value on success, ``None`` on failure.
    The exception is also logged.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — stage failure must not abort audit
        msg = f"{name} failed: {exc}"
        log.warning("audit stage %s", msg)
        errors.append(msg)
        return None


def _collect_workflow_summary(project_id: str) -> dict:
    """Collect SUP.1 / SUP.9 / MAN.3 record counts for the dashboard.

    Each source is isolated: a broken workflow store yields zeros for that
    source instead of failing the whole audit.
    """
    workflow: dict = {}

    try:
        from yuleosh.desktop import qa
        audits = qa.list_audits(project_id)
        workflow["qa"] = {
            "total": len(audits),
            "open": sum(1 for a in audits if a.get("status") == "open"),
            "closed": sum(1 for a in audits if a.get("status") == "closed"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("workflow qa summary failed: %s", exc)
        workflow["qa"] = {"total": 0, "open": 0, "closed": 0}

    try:
        from yuleosh.desktop import issues
        items = issues.list_issues(project_id)
        by_status: dict[str, int] = {}
        for i in items:
            s = i.get("status", "open")
            by_status[s] = by_status.get(s, 0) + 1
        workflow["issues"] = {
            "total": len(items),
            "open": sum(1 for i in items if i.get("status") != "closed"
                        and i.get("status") != "rejected"),
            "by_status": by_status,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("workflow issues summary failed: %s", exc)
        workflow["issues"] = {"total": 0, "open": 0, "by_status": {}}

    try:
        from yuleosh.desktop import project_mgmt
        risks = project_mgmt.list_risks(project_id)
        workflow["risks"] = {
            "total": len(risks),
            "open": sum(1 for r in risks if r.get("status") == "open"),
            "critical": sum(1 for r in risks if r.get("level") == "critical"),
        }
        milestones = project_mgmt.list_milestones(project_id)
        workflow["milestones"] = {
            "total": len(milestones),
            "completed": sum(1 for m in milestones if m.get("status") == "completed"),
            "in_progress": sum(1 for m in milestones if m.get("status") == "in_progress"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("workflow project-mgmt summary failed: %s", exc)
        workflow["risks"] = {"total": 0, "open": 0, "critical": 0}
        workflow["milestones"] = {"total": 0, "completed": 0, "in_progress": 0}

    # Fail-closed: no records at all → omit the section rather than
    # rendering a misleading wall of zeros.
    if all(
        (workflow.get(k) or {}).get("total", 0) == 0
        for k in ("qa", "issues", "risks", "milestones")
    ):
        return {}
    return workflow


def run_compliance_audit(project_id: str, body: Optional[dict] = None) -> dict:
    """Run the full compliance audit for a desktop project.

    Args:
        project_id: The desktop project identifier.
        body: Optional request body. Recognised keys:
            * ``version`` — project version string for the report header
              (defaults to the project meta ``version`` or ``"0.0.0"``).

    Returns:
        A dict with keys: ``ok``, ``status``, ``pack_path``,
        ``audit_report_path``, ``audit_report_json``, ``compliance_report_path``,
        ``bp_summary``, ``scores``, ``gaps``, ``disclaimer``, ``errors``.
    """
    body = body or {}
    errors: list[str] = []
    summary: dict = {
        "ok": False,
        "status": "not_run",
        "pack_path": None,
        "audit_report_path": None,
        "audit_report_json": None,
        "compliance_report_path": None,
        "bp_summary": {"total": 0, "passed": 0, "partial": 0, "failed": 0},
        "scores": {},
        "gaps": [],
        "disclaimer": DISCLAIMER_EVIDENCE_COVERAGE,
        "errors": errors,
        "generated_at": datetime.now().isoformat(),
    }

    # 0) Resolve project.
    try:
        meta = _project_meta(project_id)
    except FileNotFoundError:
        errors.append("Project not found")
        return summary

    proj_dir = _project_dir(project_id)
    project_name = meta.get("name", project_id)
    version = str(body.get("version") or meta.get("version") or "0.0.0")

    evidence_dir = _evidence_dir(project_id)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = _reports_dir(project_id)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 1) Compliance check — BP pass/fail summary.
    bp_summary = {"total": 0, "passed": 0, "partial": 0, "failed": 0}
    compliance_report_path: Optional[str] = None

    def _stage_compliance() -> dict:
        from yuleosh.compliance.compliance_checker import ComplianceChecker
        checker = ComplianceChecker(str(proj_dir))
        report = checker.run()
        s = report.get("summary", {})
        bp_summary["total"] = s.get("total_bps", 0)
        bp_summary["passed"] = s.get("passed", 0)
        bp_summary["partial"] = s.get("partial", 0)
        bp_summary["failed"] = s.get("failed", 0)
        # Persist the compliance markdown report for the compliance pack.
        out = proj_dir / ".osh" / "evidence" / "compliance-check-report.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(checker.generate_report_markdown(report), encoding="utf-8")
        return report

    report = _safe_stage("compliance-check", _stage_compliance, errors)
    if report is not None:
        compliance_report_path = str(
            proj_dir / ".osh" / "evidence" / "compliance-check-report.md"
        )
    summary["bp_summary"] = bp_summary

    # 2) Evidence collection + report generation.
    def _stage_evidence() -> None:
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(proj_dir))
        collector.collect_requirements()
        collector.collect_reviews()
        collector.collect_ci_results()
        collector.collect_sil_reports()
        collector.collect_session_data()
        collector.generate_traceability_matrix()
        collector.generate_requirement_coverage()
        collector.generate_code_coverage_report()
        collector.generate_acceptance_matrix()
        collector.aggregate_review_logs()

    _safe_stage("evidence-collection", _stage_evidence, errors)

    # 2b) Workflow evidence export (SUP.1 / SUP.9 / MAN.3).
    #     Runs before the pack stage so the exported reports are bundled.
    workflow_summary: dict = {}

    def _stage_workflow() -> None:
        from yuleosh.desktop import issues
        from yuleosh.desktop import project_mgmt
        from yuleosh.desktop import qa
        workflow_summary.update(_collect_workflow_summary(project_id))
        if qa.list_audits(project_id):
            qa.export_report(project_id)
        if issues.list_issues(project_id):
            issues.export_report(project_id)
        if project_mgmt.list_milestones(project_id) or project_mgmt.list_risks(project_id):
            project_mgmt.export_report(project_id)

    _safe_stage("workflow-export", _stage_workflow, errors)

    # 3) Compliance pack ZIP.
    pack_path: Optional[str] = None

    def _stage_pack() -> str:
        from yuleosh.evidence.generator import EvidenceCollector
        from yuleosh.evidence.compliance import pack_compliance_zip
        collector = EvidenceCollector(str(proj_dir))
        return pack_compliance_zip(collector)

    pack_path = _safe_stage("compliance-pack", _stage_pack, errors)

    # 4) Audit report (HTML + JSON + text).
    audit_report_path: Optional[str] = None
    audit_report_json: Optional[str] = None
    dashboard_path: Optional[str] = None
    scores: dict = {}
    gaps: list[dict] = []
    overall_score = "NI"

    def _stage_report() -> tuple:
        from yuleosh.report.audit_report import AuditReportGenerator
        gen = AuditReportGenerator(
            evidence_dir=str(evidence_dir),
        )
        rpt = gen.generate_aspice_report(
            project_name=project_name, version=version
        )
        html_path = reports_dir / "aspice-report.html"
        json_path = reports_dir / "aspice-report.json"
        text_path = reports_dir / "aspice-report.txt"
        dash_path = reports_dir / "aspice-dashboard.html"
        gen.export_html(rpt, str(html_path))
        gen.export_json(rpt, str(json_path))
        gen.export_text(rpt, str(text_path))
        gen.export_dashboard(
            rpt, str(dash_path), bp_summary=bp_summary, workflow=workflow_summary
        )
        return rpt, str(html_path), str(json_path), str(dash_path)

    rpt_tuple = _safe_stage("audit-report", _stage_report, errors)
    if rpt_tuple is not None:
        rpt, audit_report_path, audit_report_json, dashboard_path = rpt_tuple
        overall_score = rpt.overall_score
        for dim in rpt.dimensions:
            scores[dim.process_id] = {
                "score": dim.score,
                "coverage_pct": dim.coverage_pct,
                "evidence_count": dim.evidence_count,
                "gap_count": dim.gap_count,
            }
            for f in dim.findings:
                gaps.append({"process": dim.process_id, **f})

    summary.update({
        "pack_path": pack_path,
        "audit_report_path": audit_report_path,
        "audit_report_json": audit_report_json,
        "dashboard_path": dashboard_path,
        "compliance_report_path": compliance_report_path,
        "scores": scores,
        "gaps": gaps,
        "overall_score": overall_score,
        "workflow": workflow_summary,
    })

    # Determine overall run status (fail-closed).
    has_evidence = bool(scores) and overall_score != "NI"
    has_errors = bool(errors)
    if not has_evidence:
        summary["status"] = "not_run"
    elif has_errors:
        summary["status"] = "partial"
    else:
        summary["status"] = "completed"

    # Persist the latest summary for GET retrieval.
    summary_path = evidence_dir / "audit-summary.json"
    try:
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        errors.append(f"failed to persist audit summary: {exc}")

    summary["ok"] = summary["status"] in ("completed", "partial")
    return summary


def get_latest_summary(project_id: str) -> Optional[dict]:
    """Return the most recent audit summary, or ``None`` if none exists."""
    try:
        _project_meta(project_id)
    except FileNotFoundError:
        raise
    summary_path = _evidence_dir(project_id) / "audit-summary.json"
    if not summary_path.is_file():
        return None
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("failed to read audit summary %s: %s", summary_path, exc)
        return None
