#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Automatic Audit Report Generator — ASPICE dimension reports.

Produces ASPICE-aligned audit reports by traversing yuleOSH evidence
data and organizing findings by ASPICE process dimensions
(SWE.1–SWE.6, SYS.1–SYS.5, MAN.3, SUP.1, SUP.9, SUP.10).

HONEST GRADING (P0-4): dimension scores are EVIDENCE-COVERAGE grades
(E1/E2/E3/NI) computed from the passing-evidence ratio. They are NOT
Automotive SPICE capability levels (AL) and do NOT constitute any formal
ASPICE assessment result — see the disclaimer rendered in every report
(HTML legend / text export).

Output formats:
  - HTML (self-contained report)
  - JSON (machine-readable)
  - Plain text (CLI-friendly)

Usage:
    from yuleosh.report.audit_report import AuditReportGenerator

    gen = AuditReportGenerator(evidence_dir="./.osh/evidence")
    report = gen.generate_aspice_report(
        project_name="BCM Project",
        version="v1.5.0",
    )
    gen.export_html(report, "output/aspice-report.html")
    gen.export_pdf(report, "output/aspice-report.pdf")   # requires weasyprint
"""

from __future__ import annotations

import html
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("yuleosh.report.audit_report")


# ═══════════════════════════════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class EvidenceItem:
    """A single piece of evidence for a process dimension."""
    process: str             # e.g. "SWE.1", "SWE.5"
    category: str            # e.g. "requirement", "test", "review"
    title: str               # Short description
    ref_id: str              # Source ID (REQ-ID, TC-ID, review session)
    path: str                # File path or URL
    status: str              # "passed" | "failed" | "approved" | "not_reviewed"
    details: str = ""        # Additional detail
    timestamp: str = ""      # ISO timestamp
    evidence_type: str = "test"  # "test" | "review" | "analysis" | "document"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProcessDimension:
    """ASPICE process dimension evaluation (evidence-coverage grading, P0-4)."""
    process_id: str          # e.g. "SWE.1"
    title: str               # e.g. "Software Requirements Analysis"
    score: str               # "E1" | "E2" | "E3" | "NI"  — 证据覆盖度等级，非 ASPICE 能力等级
    coverage_pct: float      # 0.0–100.0
    evidence_count: int
    gap_count: int
    findings: list[dict] = field(default_factory=list)
    evidences: list[EvidenceItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AspiceReport:
    """Full ASPICE audit report."""
    project_name: str
    version: str
    generated_at: str
    report_id: str
    overall_score: str        # "E1" | "E2" | "E3" | "NI"  — 证据覆盖度等级，非 ASPICE 能力等级
    overall_coverage_pct: float
    total_evidences: int
    total_gaps: int
    dimensions: list[ProcessDimension] = field(default_factory=list)
    summary_by_process: dict = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════
# Evidence scanner
# ═══════════════════════════════════════════════════════════════════════


class EvidenceScanner:
    """Scans yuleOSH evidence artifacts and organizes by ASPICE dimension."""

    # ASPICE process dimensions and their evidence mapping rules
    PROCESS_DIMENSIONS = {
        "SWE.1": {
            "title": "Software Requirements Analysis",
            "evidence_types": ["spec", "requirement"],
            "description": "Requirements specification, traceability to system requirements",
        },
        "SWE.2": {
            "title": "Software Architectural Design",
            "evidence_types": ["architecture", "design"],
            "description": "Software architecture, interface specification, static/dynamic design",
        },
        "SWE.3": {
            "title": "Software Detailed Design and Unit Construction",
            "evidence_types": ["code", "detailed_design"],
            "description": "Source code, detailed design documentation",
        },
        "SWE.4": {
            "title": "Software Unit Verification",
            "evidence_types": ["unit_test", "code_review"],
            "description": "Unit test results, code review findings, coverage reports",
        },
        "SWE.5": {
            "title": "Software Integration and Integration Test",
            "evidence_types": ["integration_test"],
            "description": "Integration test results, interface tests",
        },
        "SWE.6": {
            "title": "Software Qualification Test",
            "evidence_types": ["qualification_test"],
            "description": "Qualification test results, requirements-based tests",
        },
        "SYS.1": {
            "title": "System Requirements Elicitation",
            "evidence_types": ["system_requirement"],
            "description": "Stakeholder requirements, system requirements specification",
        },
        "SYS.2": {
            "title": "System Requirements Analysis",
            "evidence_types": ["system_analysis"],
            "description": "System requirements analysis, technical specification",
        },
        "SYS.3": {
            "title": "System Architectural Design",
            "evidence_types": ["system_architecture"],
            "description": "System architecture, hardware-software allocation",
        },
        "SYS.4": {
            "title": "System Integration and Integration Test",
            "evidence_types": ["system_integration_test"],
            "description": "System integration tests",
        },
        "SYS.5": {
            "title": "System Qualification Test",
            "evidence_types": ["system_qualification_test"],
            "description": "System qualification tests, validation results",
        },
        "MAN.3": {
            "title": "Project Management",
            "evidence_types": ["plan", "progress"],
            "description": "Project plan, progress tracking, risk management",
        },
        "SUP.1": {
            "title": "Quality Assurance",
            "evidence_types": ["audit", "quality_check"],
            "description": "Quality assurance records, process compliance evidence",
        },
        "SUP.9": {
            "title": "Problem Resolution Management",
            "evidence_types": ["issue", "defect"],
            "description": "Defect reports, issue tracking, problem resolution",
        },
        "SUP.10": {
            "title": "Change Management",
            "evidence_types": ["change_request"],
            "description": "Change requests, impact analysis, change records",
        },
    }

    def __init__(self, evidence_dir: str = ".osh/evidence"):
        self.evidence_dir = Path(evidence_dir)
        self._cache: dict[str, list[EvidenceItem]] = {}

    def scan_all(self) -> dict[str, list[EvidenceItem]]:
        """Scan all evidence files and organize by ASPICE process.

        Returns dict[process_id, list[EvidenceItem]]
        """
        result: dict[str, list[EvidenceItem]] = {}

        # Initialize empty lists for each dimension
        for pid in self.PROCESS_DIMENSIONS:
            result[pid] = []

        if not self.evidence_dir.exists():
            log.warning("Evidence directory not found: %s", self.evidence_dir)
            return result

        # Scan for evidence JSON files in subdirectories
        for evidence_file in sorted(self.evidence_dir.rglob("*.json")):
            try:
                raw = json.loads(evidence_file.read_text(encoding="utf-8", errors="replace"))
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Cannot parse evidence file %s: %s", evidence_file, e)
                continue

            # Handle both dict and list JSON files
            items = raw if isinstance(raw, list) else [raw]
            for data in items:
                process_id = self._classify_evidence(data, evidence_file)
                if process_id and process_id in result:
                    item = self._to_evidence_item(data, evidence_file)
                    result[process_id].append(item)

        self._cache = result
        return result

    def _classify_evidence(self, data: Any, file_path: Path) -> Optional[str]:
        """Classify a piece of evidence into its ASPICE process dimension."""
        if not isinstance(data, dict):
            return None
        # Explicit process field takes precedence
        process = data.get("process", "").upper()
        if process in self.PROCESS_DIMENSIONS:
            return process

        # Classify by evidence type
        etype = data.get("type", data.get("evidence_type", "")).lower()

        # SWE.1 — requirements
        if etype in ("requirement", "spec", "shall", "requirements"):
            return "SWE.1"

        # SWE.2 — architecture
        if etype in ("architecture", "design", "arch_review"):
            return "SWE.2"

        # SWE.3 — code
        if etype in ("code", "source", "implementation", "detailed_design"):
            return "SWE.3"

        # SWE.4 — unit tests
        if etype in ("unit_test", "code_review", "review", "misra", "coverage"):
            return "SWE.4"

        # SWE.5 — integration tests
        if etype in ("integration_test", "integration", "interface"):
            return "SWE.5"

        # SWE.6 — qualification tests
        if etype in ("qualification_test", "system_test", "acceptance"):
            return "SWE.6"

        # SYS.x — system-level
        if etype in ("system_requirement", "system_analysis"):
            # Check for system/sys prefix in the filename or path
            path_str = str(file_path).lower()
            if "system" in path_str or "sys" in path_str:
                return self._classify_system(file_path, etype)
            return "SYS.1"

        # MAN.3
        if etype in ("plan", "progress", "project_plan"):
            return "MAN.3"

        # SUP.1
        if etype in ("audit", "quality", "compliance"):
            return "SUP.1"

        # SUP.9
        if etype in ("issue", "defect", "problem"):
            return "SUP.9"

        # SUP.10
        if etype in ("change", "change_request"):
            return "SUP.10"

        # Fallback: try to infer from file path/name keywords
        path_lower = str(file_path).lower()
        if "swe.1" in path_lower or "swe1" in path_lower:
            return "SWE.1"
        if "swe.2" in path_lower or "swe2" in path_lower:
            return "SWE.2"
        if "swe.3" in path_lower:
            return "SWE.3"
        if "swe.4" in path_lower or "swe4" in path_lower:
            return "SWE.4"
        if "swe.5" in path_lower or "swe5" in path_lower:
            return "SWE.5"
        if "swe.6" in path_lower or "swe6" in path_lower:
            return "SWE.6"

        return None

    def _classify_system(self, file_path: Path, etype: str) -> str:
        """Classify SYS evidence by file name."""
        path_lower = str(file_path).lower()
        if "sys.1" in path_lower or "elicitation" in path_lower:
            return "SYS.1"
        if "sys.2" in path_lower or "analysis" in path_lower:
            return "SYS.2"
        if "sys.3" in path_lower or "arch" in path_lower:
            return "SYS.3"
        if "sys.4" in path_lower or "integration" in path_lower:
            return "SYS.4"
        if "sys.5" in path_lower or "qualification" in path_lower:
            return "SYS.5"
        return "SYS.1"

    def _to_evidence_item(self, data: Any, file_path: Path) -> EvidenceItem:
        """Convert a raw JSON evidence dict to an EvidenceItem dataclass."""
        if not isinstance(data, dict):
            data = {}
        rel_path = str(file_path.relative_to(self.evidence_dir.parent)
                       if file_path.is_relative_to(self.evidence_dir.parent)
                       else file_path)
        return EvidenceItem(
            process=data.get("process", ""),
            category=data.get("type", data.get("evidence_type", "unknown")),
            title=data.get("title", data.get("description", file_path.stem)),
            ref_id=data.get("id", data.get("req_id", data.get("test_id", file_path.stem))),
            path=rel_path,
            status=data.get("status", data.get("result", "unknown")),
            details=data.get("details", data.get("output", "")),
            timestamp=data.get("timestamp", data.get("generated_at", "")),
            evidence_type=data.get("type", data.get("evidence_type", "document")),
        )


# ═══════════════════════════════════════════════════════════════════════
# Audit Report Generator
# ═══════════════════════════════════════════════════════════════════════


class AuditReportGenerator:
    """Generates ASPICE-aligned audit reports from yuleOSH evidence data."""

    def __init__(
        self,
        evidence_dir: str = ".osh/evidence",
        requirements_file: str = "",
        tests_file: str = "",
    ):
        self.scanner = EvidenceScanner(evidence_dir)
        self.requirements_file = Path(requirements_file) if requirements_file else None
        self.tests_file = Path(tests_file) if tests_file else None
        self._project_root = Path(evidence_dir).resolve().parent

    def generate_aspice_report(
        self,
        project_name: str = "Unnamed Project",
        version: str = "0.0.0",
    ) -> AspiceReport:
        """Generate a full ASPICE audit report.

        Traverses all evidence data, classifies by ASPICE process dimension,
        computes coverage and gap scores for each dimension.
        """
        evidence_by_process = self.scanner.scan_all()
        evidence_dir = self.scanner.evidence_dir

        # Also scan conventional data directories for supplementary information
        supplementary = self._scan_supplementary_sources()

        dimensions = []
        total_evidences = 0
        total_gaps = 0
        dimension_scores: list[float] = []

        for pid in sorted(EvidenceScanner.PROCESS_DIMENSIONS.keys()):
            dim_info = EvidenceScanner.PROCESS_DIMENSIONS[pid]
            evidences = evidence_by_process.get(pid, [])

            # Merge supplementary evidence for this process
            supp_for_process = supplementary.get(pid, [])
            all_evidences = evidences + supp_for_process

            # Deduplicate by ref_id
            seen_refs: set[str] = set()
            deduped: list[EvidenceItem] = []
            for ev in all_evidences:
                if ev.ref_id not in seen_refs:
                    seen_refs.add(ev.ref_id)
                    deduped.append(ev)

            # Score computation
            evidence_count = len(deduped)
            total_evidences += evidence_count

            # Determine scoring thresholds per process
            passing = sum(1 for e in deduped if e.status in ("passed", "approved", "ok"))
            failing = sum(1 for e in deduped if e.status in ("failed", "not_reviewed", "rejected"))

            if evidence_count == 0:
                coverage_pct = 0.0
                score = "NI"
                gap_count = 1  # Complete absence = 1 gap
            else:
                coverage_pct = round((passing / evidence_count) * 100, 1)
                gap_count = failing

                # P0-4: E1–E3 are EVIDENCE-COVERAGE grades derived from the
                # passing-evidence ratio — explicitly NOT ASPICE capability
                # levels (AL). Never present them as a formal assessment.
                if coverage_pct >= 90 and failing == 0:
                    score = "E3"
                elif coverage_pct >= 70 and failing < evidence_count * 0.2:
                    score = "E2"
                elif coverage_pct >= 30:
                    score = "E1"
                else:
                    score = "NI"

            total_gaps += gap_count
            if score != "NI":
                dimension_scores.append(coverage_pct)

            # Build findings list for gaps
            findings = []
            for ev in deduped:
                if ev.status in ("failed", "rejected"):
                    findings.append({
                        "type": "failed_evidence",
                        "ref_id": ev.ref_id,
                        "title": ev.title,
                        "details": ev.details,
                    })

            # Generate recommendations for this dimension
            if evidence_count == 0:
                findings.append({
                    "type": "missing_evidence",
                    "details": f"No evidence found for process {pid} ({dim_info['title']})",
                })

            dim = ProcessDimension(
                process_id=pid,
                title=dim_info["title"],
                score=score,
                coverage_pct=coverage_pct,
                evidence_count=evidence_count,
                gap_count=gap_count,
                findings=findings,
                evidences=deduped,
            )
            dimensions.append(dim)

        # Overall score
        overall_coverage = round(
            sum(d.coverage_pct for d in dimensions) / len(dimensions), 1
        ) if dimensions else 0.0

        avg_coverage = overall_coverage
        # P0-4: same evidence-coverage grading as per-dimension scores —
        # NOT an ASPICE capability level.
        if avg_coverage >= 90 and total_gaps == 0:
            overall_score = "E3"
        elif avg_coverage >= 70:
            overall_score = "E2"
        elif avg_coverage >= 30:
            overall_score = "E1"
        else:
            overall_score = "NI"

        # Generate recommendations
        recommendations = self._generate_recommendations(dimensions)

        # Summary by process
        summary_by_process = {}
        for dim in dimensions:
            summary_by_process[dim.process_id] = {
                "score": dim.score,
                "coverage_pct": dim.coverage_pct,
                "evidence_count": dim.evidence_count,
                "gap_count": dim.gap_count,
            }

        report_id = f"ASPICE-AUDIT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

        return AspiceReport(
            project_name=project_name,
            version=version,
            generated_at=datetime.now(timezone.utc).isoformat(),
            report_id=report_id,
            overall_score=overall_score,
            overall_coverage_pct=overall_coverage,
            total_evidences=total_evidences,
            total_gaps=total_gaps,
            dimensions=dimensions,
            summary_by_process=summary_by_process,
            recommendations=recommendations,
        )

    def _scan_supplementary_sources(self) -> dict[str, list[EvidenceItem]]:
        """Scan additional data sources (requirements, tests) as supplementary evidence."""
        supplementary: dict[str, list[EvidenceItem]] = {}

        # Requirements → SWE.1
        if self.requirements_file and self.requirements_file.exists():
            try:
                reqs = json.loads(self.requirements_file.read_text(encoding="utf-8"))
                items = []
                if isinstance(reqs, list):
                    for r in reqs:
                        items.append(EvidenceItem(
                            process="SWE.1",
                            category="requirement",
                            title=r.get("title", ""),
                            ref_id=r.get("id", ""),
                            path=f"data/requirements/requirements.json",
                            status=r.get("status", "unknown"),
                            details=f"Priority: {r.get('priority','')}, ASIL: {r.get('asil','')}",
                            timestamp=r.get("created_at", ""),
                            evidence_type="requirement",
                        ))
                supplementary["SWE.1"] = items
            except (json.JSONDecodeError, OSError):
                pass

        # Test cases → SWE.5/SWE.6
        if self.tests_file and self.tests_file.exists():
            try:
                data = json.loads(self.tests_file.read_text(encoding="utf-8"))
                tcs = data.get("test_cases", []) if isinstance(data, dict) else []
                swe5_items = []
                swe6_items = []
                for tc in tcs:
                    level = tc.get("test_level", "SWE.5")
                    _reqs = tc.get("requirement_ids") or []
                    _tags = tc.get("tags") or []
                    item = EvidenceItem(
                        process=level,
                        category="test",
                        title=tc.get("title", ""),
                        ref_id=tc.get("id", ""),
                        path=f"data/tests/test-cases.json",
                        status="passed" if (tc.get("last_run") or {}).get("status") == "passed" else "unknown",
                        details=f"Req: {','.join(_reqs)} | Tags: {','.join(_tags)}",
                        timestamp=(tc.get("last_run") or {}).get("timestamp", ""),
                        evidence_type="test",
                    )
                    if level == "SWE.6":
                        swe6_items.append(item)
                    else:
                        swe5_items.append(item)
                if swe5_items:
                    supplementary["SWE.5"] = swe5_items
                if swe6_items:
                    supplementary["SWE.6"] = swe6_items
            except (json.JSONDecodeError, OSError):
                pass

        return supplementary

    def _generate_recommendations(self, dimensions: list[ProcessDimension]) -> list[str]:
        """Generate actionable recommendations from the ASPICE audit."""
        recs = []

        for dim in dimensions:
            pid = dim.process_id
            if dim.score == "NI":
                recs.append(
                    f"[{pid}] ❌ 无可用证据 — 请提供符合过程 {pid} ({dim.title}) 的工作产品"
                )
            elif dim.score == "E1" and dim.evidence_count > 0:
                missing = [f for f in dim.findings if f.get("type") == "missing_evidence"]
                if missing:
                    recs.append(
                        f"[{pid}] ⚠️ 部分证据缺失 — {len(missing)} 项缺失，建议补充"
                    )
                failed = [f for f in dim.findings if f.get("type") == "failed_evidence"]
                if failed:
                    recs.append(
                        f"[{pid}] 🔴 {len(failed)} 项证据未通过 — 需修复后才可提升至 E2"
                    )
            elif dim.score == "E2":
                failed = [f for f in dim.findings if f.get("type") == "failed_evidence"]
                if not failed:
                    recs.append(
                        f"[{pid}] ✅ E2 已满足 — 可通过增加过程绩效指标证据提升至 E3"
                    )

        # Cross-dimension recommendations
        swe_dims = [d for d in dimensions if d.process_id.startswith("SWE")]
        all_passing = all(d.score != "NI" for d in swe_dims)
        if all_passing:
            recs.append(
                "🏆 所有 SWE 维度均有证据覆盖 — 可启动 ASPICE CL1 正式评估准备"
            )

        if not all_passing:
            ni_dims = [d.process_id for d in swe_dims if d.score == "NI"]
            recs.append(
                f"⚠️ {len(ni_dims)} 个 SWE 维度无证据: {', '.join(ni_dims)} — "
                f"建议优先补充以达成 CL1"
            )

        if not recs:
            recs.append("✅ 无重大发现 — 建议持续维护证据链")

        return recs

    # ── Export: JSON ──────────────────────────────────────────────────

    def export_json(self, report: AspiceReport, output_path: str) -> str:
        """Export the ASPICE report to JSON format.

        Returns the output file path.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        data = report.to_dict()
        # Convert dataclass nested objects
        data["dimensions"] = [d.to_dict() for d in report.dimensions]

        out.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("ASPICE report exported to JSON: %s", out)
        return str(out)

    # ── Export: HTML ──────────────────────────────────────────────────

    def export_html(self, report: AspiceReport, output_path: str) -> str:
        """Export the ASPICE report to a self-contained HTML file.

        Returns the output file path.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        html_content = self._render_html(report)
        out.write_text(html_content, encoding="utf-8")
        log.info("ASPICE report exported to HTML: %s", out)
        return str(out)

    def _render_html(self, report: AspiceReport) -> str:
        """Render the ASPICE report as a standalone HTML page."""
        # Color mapping for scores (P0-4: evidence-coverage grades)
        score_color = {
            "E3": "#22c55e",
            "E2": "#eab308",
            "E1": "#f97316",
            "NI":  "#ef4444",
        }
        score_label = {
            "E3": "E3 — 证据覆盖度高 (≥90% 通过, 0 失败)",
            "E2": "E2 — 证据覆盖度中 (≥70% 通过, <20% 失败)",
            "E1": "E1 — 证据覆盖度低 (≥30% 通过)",
            "NI":  "NI — 无证据或覆盖度 <30%",
        }

        dim_rows = ""
        for dim in report.dimensions:
            color = score_color.get(dim.score, "#6b7280")
            findings_html = ""
            for f in dim.findings:
                if f.get("type") == "missing_evidence":
                    findings_html += f"<li class='finding-warn'>⚠️ {html.escape(f['details'])}</li>"
                elif f.get("type") == "failed_evidence":
                    findings_html += (
                        f"<li class='finding-err'>🔴 {html.escape(f['ref_id'])} — "
                        f"{html.escape(f.get('title', ''))}: {html.escape(f.get('details', ''))}</li>"
                    )
            if not findings_html:
                findings_html = "<li class='finding-ok'>✅ 无发现</li>"

            dim_rows += f"""
            <tr>
                <td><strong>{dim.process_id}</strong></td>
                <td>{html.escape(dim.title)}</td>
                <td style="color:{color}; font-weight:bold;">{dim.score}</td>
                <td>{dim.coverage_pct}%</td>
                <td>{dim.evidence_count}</td>
                <td>{dim.gap_count}</td>
                <td><ul style="margin:0; padding-left:1.2em;">{findings_html}</ul></td>
            </tr>"""

        recs_html = ""
        for r in report.recommendations:
            recs_html += f"<li>{html.escape(r)}</li>"

        overall_color = score_color.get(report.overall_score, "#6b7280")

        html_str = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ASPICE Audit Report — {html.escape(report.project_name)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          max-width: 1100px; margin: 2em auto; padding: 0 1em; color: #1f2937; background: #f8fafc; }}
  h1, h2, h3 {{ color: #111827; }}
  .meta {{ color: #6b7280; font-size: 0.9em; }}
  .summary-card {{ background: white; border-radius: 8px; padding: 1.5em; margin: 1em 0;
                  box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .overall-score {{ font-size: 2.5em; font-weight: bold; text-align: center; padding: 0.3em 0; }}
  .overall-label {{ text-align: center; color: #6b7280; font-size: 0.9em; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1em 0; background: white;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: 0.75em 1em; text-align: left; border-bottom: 1px solid #e5e7eb; }}
  th {{ background: #374151; color: white; font-weight: 600; }}
  tr:hover {{ background: #f3f4f6; }}
  .finding-err {{ color: #dc2626; }}
  .finding-warn {{ color: #d97706; }}
  .finding-ok {{ color: #16a34a; }}
  ul {{ padding-left: 1.5em; }}
  .recs {{ background: white; border-radius: 8px; padding: 1.5em; margin: 1em 0;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .footer {{ margin-top: 2em; text-align: center; color: #9ca3af; font-size: 0.8em; }}
  .badge {{ display: inline-block; padding: 0.2em 0.6em; border-radius: 4px;
            color: white; font-weight: bold; font-size: 0.85em; }}
  .badge-green {{ background: #22c55e; }}
  .badge-yellow {{ background: #eab308; }}
  .badge-orange {{ background: #f97316; }}
  .badge-red {{ background: #ef4444; }}
  .badge-gray {{ background: #6b7280; }}
</style>
</head>
<body>

<h1>🔍 ASPICE Audit Report</h1>
<div class="meta">
  <p><strong>Project:</strong> {html.escape(report.project_name)} | <strong>Version:</strong> {html.escape(report.version)}</p>
  <p><strong>Report ID:</strong> {html.escape(report.report_id)} | <strong>Generated:</strong> {html.escape(report.generated_at)}</p>
</div>

<div class="summary-card">
  <div class="overall-score" style="color:{overall_color};">{report.overall_score}</div>
  <div class="overall-label">{score_label.get(report.overall_score, '')}</div>
  <p style="text-align:center; margin-top:1em;">
    <strong>Overall Coverage:</strong> {report.overall_coverage_pct}% &nbsp;|&nbsp;
    <strong>Total Evidence Items:</strong> {report.total_evidences} &nbsp;|&nbsp;
    <strong>Total Gaps:</strong> {report.total_gaps}
  </p>
</div>

<h2>Process Dimension Coverage</h2>
<table>
<thead>
  <tr>
    <th>Process</th>
    <th>Title</th>
    <th>Score</th>
    <th>Coverage</th>
    <th>Evidence</th>
    <th>Gaps</th>
    <th>Findings</th>
  </tr>
</thead>
<tbody>
  {dim_rows}
</tbody>
</table>

<h2>Recommendations</h2>
<div class="recs">
  <ul>{recs_html}</ul>
</div>

<h2>Score Legend</h2>
<table>
<thead><tr><th>Level</th><th>Description</th><th>Criteria (evidence coverage)</th></tr></thead>
<tbody>
  <tr><td><span class="badge badge-green">E3</span></td><td>证据覆盖度高</td><td>≥90% coverage, zero failing</td></tr>
  <tr><td><span class="badge badge-yellow">E2</span></td><td>证据覆盖度中</td><td>≥70% coverage, &lt;20% failures</td></tr>
  <tr><td><span class="badge badge-orange">E1</span></td><td>证据覆盖度低</td><td>≥30% coverage</td></tr>
  <tr><td><span class="badge badge-red">NI</span></td><td>无证据 / 覆盖度不足</td><td>&lt;30% coverage or no evidence</td></tr>
</tbody>
</table>

<div class="recs" style="border-left: 4px solid #f97316;">
  <strong>⚠️ 重要说明（非 ASPICE 能力等级）：</strong>
  E1–E3 仅为<strong>证据覆盖度分级</strong>，由通过状态证据的占比计算得出，
  <strong>不是 Automotive SPICE 能力等级（Capability Level）</strong>，也不构成任何
  正式的 ASPICE 评估结论（如 CL1 等）。如需正式评估，请咨询经认可的评估机构。
</div>

<div class="footer">
  Generated by yuleOSH Audit Report Generator — {html.escape(report.generated_at)}
</div>

</body>
</html>"""
        return html_str

    # ── Export: PDF ───────────────────────────────────────────────────

    def export_pdf(self, report: AspiceReport, output_path: str) -> str:
        """Export the ASPICE report to PDF.

        Requires ``weasyprint`` to be installed.
        Falls back to HTML if weasyprint is unavailable.

        Returns the output file path (PDF or HTML fallback).
        """
        try:
            import weasyprint
        except ImportError:
            log.warning(
                "weasyprint not available — falling back to HTML export. "
                "Install with: pip install weasyprint"
            )
            return self.export_html(report, output_path.replace(".pdf", ".html"))

        # Render HTML first
        html_content = self._render_html(report)

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        try:
            weasyprint.HTML(string=html_content).write_pdf(str(out))
            log.info("ASPICE report exported to PDF: %s", out)
            return str(out)
        except Exception as e:
            log.error("weasyprint PDF generation failed: %s", e)
            # Fallback: save as HTML
            html_path = output_path.replace(".pdf", ".html")
            return self.export_html(report, html_path)

    # ── Export: Text (CLI-friendly) ───────────────────────────────────

    def export_text(self, report: AspiceReport, output_path: str = "") -> str:
        """Export the ASPICE report as plain text.

        If output_path is empty, returns the text string directly.
        Otherwise writes to the file and returns the path.
        """
        lines = []
        lines.append("=" * 72)
        lines.append(f"  ASPICE AUDIT REPORT — {report.project_name} v{report.version}")
        lines.append("=" * 72)
        lines.append(f"  Report ID: {report.report_id}")
        lines.append(f"  Generated: {report.generated_at}")
        lines.append(f"  Overall Score: {report.overall_score}")
        lines.append(f"  Overall Coverage: {report.overall_coverage_pct}%")
        lines.append(f"  Total Evidence: {report.total_evidences}")
        lines.append(f"  Total Gaps: {report.total_gaps}")
        lines.append("")
        lines.append("  ⚠️ 重要说明: E1–E3 仅为证据覆盖度分级，不是 Automotive SPICE")
        lines.append("  能力等级 (Capability Level)，也不构成任何正式的 ASPICE 评估结论。")
        lines.append("")

        # By dimension
        for dim in report.dimensions:
            lines.append("-" * 72)
            lines.append(f"  {dim.process_id}: {dim.title}")
            lines.append(f"    Score: {dim.score}  |  Coverage: {dim.coverage_pct}%  |  "
                         f"Evidence: {dim.evidence_count}  |  Gaps: {dim.gap_count}")
            for f in dim.findings:
                if f.get("type") == "missing_evidence":
                    lines.append(f"    ⚠️  {f['details']}")
                elif f.get("type") == "failed_evidence":
                    lines.append(f"    🔴 {f['ref_id']}: {f.get('details', '')}")
            if not dim.findings:
                lines.append("    ✅  No findings")
            lines.append("")

        # Recommendations
        lines.append("=" * 72)
        lines.append("  RECOMMENDATIONS")
        lines.append("=" * 72)
        for r in report.recommendations:
            lines.append(f"    • {r}")

        text = "\n".join(lines)

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            log.info("ASPICE report exported to text: %s", out)
            return str(out)

        return text


# ═══════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════


def main():
    """CLI entry point for ``yuleosh audit-report``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate ASPICE audit report from yuleOSH evidence data",
    )
    parser.add_argument("--evidence-dir", default=".osh/evidence",
                        help="Evidence data directory (default: .osh/evidence)")
    parser.add_argument("--requirements", default="",
                        help="Requirements JSON file (data/requirements/requirements.json)")
    parser.add_argument("--tests", default="",
                        help="Test cases JSON file (data/tests/test-cases.json)")
    parser.add_argument("--project", default="yuleOSH Project",
                        help="Project name for the report header")
    parser.add_argument("--version", default="1.0.0",
                        help="Project version")
    parser.add_argument("--output", default=".",
                        help="Output directory for report files")
    parser.add_argument("--format", choices=["html", "pdf", "json", "text", "all"],
                        default="all",
                        help="Output format (default: all)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    gen = AuditReportGenerator(
        evidence_dir=args.evidence_dir,
        requirements_file=args.requirements or None,
        tests_file=args.tests or None,
    )

    report = gen.generate_aspice_report(
        project_name=args.project,
        version=args.version,
    )

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    formats = ["html", "pdf", "json", "text"] if args.format == "all" else [args.format]
    exported = []

    for fmt in formats:
        if fmt == "html":
            path = gen.export_html(report, str(out_dir / "aspice-report.html"))
            exported.append(f"HTML: {path}")
        elif fmt == "pdf":
            path = gen.export_pdf(report, str(out_dir / "aspice-report.pdf"))
            exported.append(f"PDF:  {path}")
        elif fmt == "json":
            path = gen.export_json(report, str(out_dir / "aspice-report.json"))
            exported.append(f"JSON: {path}")
        elif fmt == "text":
            path = gen.export_text(report, str(out_dir / "aspice-report.txt"))
            exported.append(f"TEXT: {path}")

    print("\n".join(exported))
    print(f"\nOverall Score: {report.overall_score}")
    print(f"Coverage: {report.overall_coverage_pct}%")
    for r in report.recommendations:
        print(f"  • {r}")


if __name__ == "__main__":
    main()


__all__ = [
    "AuditReportGenerator",
    "AspiceReport",
    "ProcessDimension",
    "EvidenceItem",
    "EvidenceScanner",
    "main",
]
