#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Traceability matrix generator.

Generates Requirement ↔ Code ↔ Test ↔ Review bidirectional
traceability reports (LRM / LRT) for ASPICE CL2 compliance.

Sources:
  1. Spec SHALL statements (from docs/spec.md or specs/*.md)
  2. Review artifacts (.yuleosh/sessions/*/code-review.json)
  3. Test reports (.yuleosh/sessions/*/*test*.json)
  4. CI results (.osh/ci/layer1-*.json)
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("yuleosh.alm.traceability")


# ── SHALL statement extraction ─────────────────────────────────────────


def extract_shall_statements(spec_path: str) -> list[dict]:
    """Extract SHALL statements from a specification file (markdown).

    Returns list of dicts with keys:
      - id:          Auto-generated SHALL-{n} identifier
      - req_id:      Spec-defined ID (e.g. SWE-MISRA-S1) if available
      - statement:   The full SHALL text
      - line:        Line number in the spec file
      - section:     Section heading (if available)

    Spec-defined IDs are parsed from patterns like ``**SWE-MISRA-S1**: ...``
    on the same line as the SHALL keyword.
    """
    spec_file = Path(spec_path)
    if not spec_file.exists():
        log.warning("Spec file not found: %s", spec_path)
        return []

    try:
        text = spec_file.read_text(encoding="utf-8")
    except OSError as e:
        log.error("Cannot read spec file: %s", e)
        return []

    lines = text.split("\n")
    shall_statements = []
    current_section = ""

    # Pattern to match spec-defined IDs like **SWE-MISRA-S1**: or [REQ-MISRA-S1.1]
    spec_id_pattern = re.compile(r'(?:\*\*(\w[\w-]+)\*\*\s*:|\[([\w][\w.-]+)\])')

    # Broad SHALL keyword search — works for both English and Chinese text
    shall_keyword_pattern = re.compile(r'\bSHALL\b|\bshall\b|\bMUST\b|\bmust\b')

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()

        # Track section headings
        if stripped.startswith("#"):
            current_section = stripped.lstrip("#").strip()

        # Look for SHALL / MUST keywords
        if shall_keyword_pattern.search(stripped):
            statement = stripped.strip()
            # Trim leading list markers
            statement = re.sub(r"^[\s]*[-*+]\s+", "", statement)
            statement = re.sub(r"^\d+[.)]\s+", "", statement)

            # Parse spec-defined ID from **ID**: prefix or [REQ-xxx] marker
            # Use trimmed `statement` (after list marker removal) for matching
            req_id = None
            spec_id_match = spec_id_pattern.match(statement)
            if spec_id_match:
                # group(1) = **ID**: pattern, group(2) = [REQ-xxx] pattern
                req_id = spec_id_match.group(1) or spec_id_match.group(2)

            shall_statements.append({
                "id": f"SHALL-{len(shall_statements) + 1}",
                "req_id": req_id,
                "statement": statement,
                "line": idx,
                "section": current_section,
            })

    log.info("Extracted %d SHALL statements from %s", len(shall_statements), spec_path)
    return shall_statements


def extract_shall_from_text(text: str) -> list[dict]:
    """Extract SHALL statements from raw text (no file I/O)."""
    lines = text.split("\n")
    shall_statements = []
    current_section = ""

    shall_keyword_pattern = re.compile(r'\bSHALL\b|\bshall\b|\bMUST\b|\bmust\b')

    spec_id_pattern = re.compile(r'(?:\*\*(\w[\w-]+)\*\*\s*:|\[([\w][\w.-]+)\])')

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            current_section = stripped.lstrip("#").strip()
        if shall_keyword_pattern.search(stripped):
            statement = stripped.strip()
            statement = re.sub(r"^[\s]*[-*+]\s+", "", statement)
            statement = re.sub(r"^\d+[.)]\s+", "", statement)

            # Parse spec-defined ID
            req_id = None
            spec_id_match = spec_id_pattern.match(statement)
            if spec_id_match:
                req_id = spec_id_match.group(1) or spec_id_match.group(2)

            shall_statements.append({
                "id": f"SHALL-{len(shall_statements) + 1}",
                "req_id": req_id,
                "statement": statement,
                "line": idx,
                "section": current_section,
            })

    return shall_statements


# ── Review artifact scan ────────────────────────────────────────────────


def scan_review_artifacts(project_dir: str) -> list[dict]:
    """Scan .yuleosh/sessions/ for code-review.json artifacts.

    Returns list of dicts with keys:
      - session: Session name
      - agent:   Agent that performed the review
      - reviewed_files: List of file paths reviewed
      - findings: List of finding descriptions
    """
    sessions_dir = Path(project_dir) / ".yuleosh" / "sessions"
    if not sessions_dir.exists():
        log.info("No sessions directory found at %s", sessions_dir)
        return []

    reviews = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        review_file = session_dir / "code-review.json"
        if not review_file.exists():
            continue

        try:
            data = json.loads(review_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Cannot parse %s: %s", review_file, e)
            continue

        reviewed_files = []
        findings = []
        if isinstance(data, dict):
            reviewed_files = data.get("reviewed_files", data.get("files", []))
            if isinstance(reviewed_files, dict):
                reviewed_files = list(reviewed_files.keys())
            findings_text = data.get("findings", data.get("issues", []))
            if isinstance(findings_text, list):
                for f in findings_text:
                    if isinstance(f, dict):
                        findings.append(f.get("description", str(f)))
                    elif isinstance(f, str):
                        findings.append(f)

        reviews.append({
            "session": session_dir.name,
            "agent": data.get("agent", "unknown") if isinstance(data, dict) else "unknown",
            "reviewed_files": reviewed_files,
            "findings": findings,
        })

    log.info("Found %d review artifacts", len(reviews))
    return reviews


# ── Test report scan ────────────────────────────────────────────────────


def scan_test_reports(project_dir: str) -> list[dict]:
    """Scan .yuleosh/sessions/ for *test*.json reports.

    Returns list of dicts with keys:
      - session:  Session name
      - step:     Test step name
      - status:   Test status (passed/failed/skipped)
      - passed:   Number of passed tests
      - failed:   Number of failed tests
      - output:   Test output (truncated)
    """
    sessions_dir = Path(project_dir) / ".yuleosh" / "sessions"
    if not sessions_dir.exists():
        log.info("No sessions directory found at %s", sessions_dir)
        return []

    reports = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        for test_file in session_dir.glob("*test*.json"):
            try:
                data = json.loads(test_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Cannot parse %s: %s", test_file, e)
                continue

            if isinstance(data, dict):
                reports.append({
                    "session": session_dir.name,
                    "step": data.get("step", test_file.stem),
                    "status": data.get("status", "unknown"),
                    "passed": data.get("passed", 0),
                    "failed": data.get("failed", 0),
                    "runner": data.get("test_runner", data.get("runner", "unknown")),
                    "file": str(test_file),
                })

    log.info("Found %d test reports", len(reports))
    return reports


# ── CI result scan ──────────────────────────────────────────────────────


def scan_ci_results(project_dir: str) -> list[dict]:
    """Scan .osh/ci/ for layer result JSON files.

    Returns list of dicts with keys:
      - layer: CI layer name
      - status: Layer status
      - timestamp: Run timestamp
    """
    ci_dir = Path(project_dir) / ".osh" / "ci"
    if not ci_dir.exists():
        log.info("No CI results directory at %s", ci_dir)
        return []

    results = []
    for result_file in sorted(ci_dir.glob("layer*.json")):
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Cannot parse %s: %s", result_file, e)
            continue

        if isinstance(data, dict):
            results.append({
                "layer": data.get("layer", result_file.stem),
                "status": data.get("status", "unknown"),
                "timestamp": data.get("timestamp", ""),
                "file": str(result_file),
            })

    log.info("Found %d CI results", len(results))
    return results


# ── LRM: Lateral Requirements Matrix ────────────────────────────────────


def generate_lrm(project_dir: str, spec_path: Optional[str] = None) -> dict:
    """Generate LRM (Lateral Requirements Matrix).

    Maps each SHALL statement to:
      - Source files implementing it (Code)
      - Tests verifying it (Test)
      - Reviews covering it (Review)

    Returns dict with 'requirements' list and summary stats.
    """
    # Resolve spec path
    if spec_path is None or not Path(spec_path).exists():
        candidates = [
            Path(project_dir) / "docs" / "spec.md",
            Path(project_dir) / "specs" / "spec.md",
        ]
        for c in candidates:
            if c.exists():
                spec_path = str(c)
                break

    if spec_path is None or not Path(spec_path).exists():
        log.warning("No spec file found for LRM generation")
        return {"requirements": [], "summary": {"total": 0, "no_code": 0, "no_test": 0}}

    # Extract requirements
    shalls = extract_shall_statements(spec_path)
    reviews = scan_review_artifacts(project_dir)
    test_reports = scan_test_reports(project_dir)

    # Build code → requirement mapping by scanning src/ for comments
    src_dir = Path(project_dir) / "src"
    code_map = _scan_comments_for_requirements(src_dir, shalls)

    requirements = []
    for shall in shalls:
        req_id = shall["id"]

        # Find code that references this requirement
        matching_code = code_map.get(req_id, [])
        if not matching_code:
            # Fallback: search by keyword
            keywords = _extract_keywords(shall["statement"])
            matching_code = _find_code_by_keywords(src_dir, keywords)

        # Find tests that reference this requirement
        matching_tests = _find_tests_for_requirement(test_reports, req_id, shall["statement"])

        # Find reviews that reference this requirement
        matching_reviews = _find_reviews_for_requirement(reviews, req_id, shall["statement"])

        requirements.append({
            "id": req_id,
            "req_id": shall.get("req_id"),
            "statement": shall["statement"],
            "section": shall.get("section", ""),
            "code_files": matching_code,
            "test_reports": matching_tests,
            "reviews": matching_reviews,
            "has_code": len(matching_code) > 0,
            "has_test": len(matching_tests) > 0,
            "has_review": len(matching_reviews) > 0,
            "step_handlers": _find_step_handlers_for_requirement(project_dir, req_id, shall),
        })

    # Summary
    total = len(requirements)
    no_code = sum(1 for r in requirements if not r["has_code"])
    no_test = sum(1 for r in requirements if not r["has_test"])
    no_review = sum(1 for r in requirements if not r["has_review"])

    return {
        "requirements": requirements,
        "summary": {
            "total": total,
            "with_code": total - no_code,
            "without_code": no_code,
            "with_test": total - no_test,
            "without_test": no_test,
            "with_review": total - no_review,
            "without_review": no_review,
            "coverage_pct": round((total - no_test) / total * 100, 1) if total > 0 else 0.0,
        },
        "generated_at": datetime.now().isoformat(),
    }


# ── LRT: Lateral Requirements Traceability ─────────────────────────────


def generate_lrt(project_dir: str, spec_path: Optional[str] = None) -> dict:
    """Generate LRT (Lateral Requirements Traceability).

    Full bidirectional trace: Spec Requirement ↔ Code ↔ Test ↔ Review,
    plus a coverage gap analysis.

    Contains all LRM data plus additional cross-reference details.
    """
    lrm = generate_lrm(project_dir, spec_path)
    reviews = scan_review_artifacts(project_dir)
    test_reports = scan_test_reports(project_dir)
    ci_results = scan_ci_results(project_dir)

    # Cross-reference: list orphaned test files (no matching SHALL)
    orphaned_tests = _find_orphaned_tests(test_reports, lrm["requirements"])

    # Gap analysis
    gaps = []
    for req in lrm["requirements"]:
        if not req["has_code"]:
            gaps.append({
                "type": "no_code",
                "req_id": req["id"],
                "statement": req["statement"],
            })
        if not req["has_test"]:
            gaps.append({
                "type": "no_test",
                "req_id": req["id"],
                "statement": req["statement"],
            })
        if not req["has_review"]:
            gaps.append({
                "type": "no_review",
                "req_id": req["id"],
                "statement": req["statement"],
            })

    return {
        "lrm": lrm,
        "reviews_available": len(reviews),
        "test_reports_available": len(test_reports),
        "ci_results_available": len(ci_results),
        "orphaned_test_files": orphaned_tests,
        "gap_analysis": {
            "total_gaps": len(gaps),
            "gaps": gaps,
            "missing_code_count": sum(1 for g in gaps if g["type"] == "no_code"),
            "missing_test_count": sum(1 for g in gaps if g["type"] == "no_test"),
            "missing_review_count": sum(1 for g in gaps if g["type"] == "no_review"),
        },
        "generated_at": datetime.now().isoformat(),
    }


# ── Full traceability report ────────────────────────────────────────────


def generate_traceability_report(project_dir: str,
                                  spec_path: Optional[str] = None,
                                  output_dir: Optional[str] = None) -> dict:
    """Generate full traceability report with LRM + LRT + recommendations.

    Args:
        project_dir: Project root directory.
        spec_path:   Path to spec file (optional, auto-detected).
        output_dir:  Directory for output files (optional, defaults to .yuleosh/).

    Returns:
        Dict with keys: lrm, lrt, coverage_summary, recommendations.
    """
    project_path = Path(project_dir).resolve()

    # Generate LRT (includes LRM + gap analysis)
    lrt = generate_lrt(project_dir, spec_path)

    # Coverage summary
    summary = lrt.get("lrm", {}).get("summary", {})
    gaps = lrt.get("gap_analysis", {})

    coverage_summary = {
        "requirements_total": summary.get("total", 0),
        "test_coverage_pct": summary.get("coverage_pct", 0.0),
        "code_coverage": f"{summary.get('with_code', 0)}/{summary.get('total', 0)}",
        "review_coverage": f"{summary.get('with_review', 0)}/{summary.get('total', 0)}",
        "total_gaps": gaps.get("total_gaps", 0),
        "orphaned_tests": len(lrt.get("orphaned_test_files", [])),
    }

    # Recommendations
    recommendations = []
    total = summary.get("total", 0)
    if total > 0:
        if summary.get("without_code", 0) > total * 0.3:
            recommendations.append(
                "⚠️ 超过 30% 的需求缺少代码实现映射 — 建议在注释中添加 'REQ-ID: SHALL-N' 标记"
            )
        if summary.get("without_test", 0) > total * 0.2:
            recommendations.append(
                "⚠️ 超过 20% 的需求缺少测试覆盖 — 建议补充对应测试用例"
            )
        if summary.get("coverage_pct", 100) < 60:
            recommendations.append(
                "🔴 测试覆盖率低于 60% — 可能影响 ASPICE CL1 审计通过"
            )

    if lrt.get("orphaned_test_files"):
        recommendations.append(
            f"📋 发现 {len(lrt['orphaned_test_files'])} 个测试文件无对应需求关联 — "
            "建议在测试报告中添加 'SHALL-N' 引用"
        )

    # Write output if requested
    out = {
        "lrm": lrt.get("lrm", {}),
        "lrt": lrt,
        "coverage_summary": coverage_summary,
        "recommendations": recommendations,
        "generated_at": datetime.now().isoformat(),
    }

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        report_file = out_path / "traceability-report.json"
        try:
            report_file.write_text(
                json.dumps(out, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info("Traceability report written to %s", report_file)
        except OSError as e:
            log.error("Cannot write traceability report: %s", e)

    return out


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════


def _find_step_handlers_for_requirement(project_dir: str, req_id: str,
                                              shall: dict) -> list[dict]:
    """Find step handler reports that reference a given requirement.

    Scans .yuleosh/sessions/ for JSON reports from pipeline step handlers
    that contain a ``req_ids`` or ``spec_ref`` field matching the req_id
    or SHALL id.
    """
    sessions_dir = Path(project_dir) / ".yuleosh" / "sessions"
    if not sessions_dir.exists():
        return []

    matching = []
    req_id_pattern = re.compile(re.escape(req_id))
    shall_id_pattern = re.compile(re.escape(shall["id"]))

    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        for report_file in session_dir.glob("*.json"):
            try:
                data = json.loads(report_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(data, dict):
                continue

            # Check req_ids field in step handler report
            report_req_ids = data.get("req_ids", [])
            if isinstance(report_req_ids, list):
                if req_id in report_req_ids or shall["id"] in report_req_ids:
                    matching.append({
                        "session": session_dir.name,
                        "step": data.get("step", report_file.stem),
                        "file": str(report_file),
                    })
                    continue

            # Check spec_ref field
            spec_ref = data.get("spec_ref", "")
            if isinstance(spec_ref, str) and (req_id in spec_ref or shall["id"] in spec_ref):
                matching.append({
                    "session": session_dir.name,
                    "step": data.get("step", report_file.stem),
                    "file": str(report_file),
                })
                continue

            # Scan full JSON text for req_id
            text = json.dumps(data)
            if req_id_pattern.search(text) or shall_id_pattern.search(text):
                matching.append({
                    "session": session_dir.name,
                    "step": data.get("step", report_file.stem),
                    "file": str(report_file),
                })

    return matching


def _scan_comments_for_requirements(src_dir: Path, shalls: list[dict]) -> dict:
    """Scan source files for comments referencing SHALL IDs.

    Looks for patterns like::
        // REQ: SHALL-1
        /* REQ-ID: SHALL-3, SHALL-5 */
    """
    if not src_dir.exists():
        return {}

    code_map: dict[str, list[str]] = {}
    for s in shalls:
        code_map[s["id"]] = []

    req_pattern = re.compile(r'SHALL-\d+')
    comment_pattern = re.compile(r'REQ[- ]?(?:ID)?[:\s]+(.*?)(?:\*/|$)', re.IGNORECASE)

    for source_file in src_dir.rglob("*.py"):
        if not source_file.is_file():
            continue
        try:
            text = source_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Scan for SHALL references in both comments and code
        found_ids = set()
        for match in req_pattern.findall(text):
            if match in code_map:
                found_ids.add(match)

        for req_id in found_ids:
            rel_path = str(source_file.relative_to(src_dir.parent))
            if rel_path not in code_map.get(req_id, []):
                if req_id in code_map:
                    code_map[req_id].append(rel_path)

    return code_map


def _extract_keywords(statement: str) -> list[str]:
    """Extract meaningful keywords from a SHALL statement."""
    # Remove common stop words
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "as", "is", "was", "be",
        "are", "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "could", "should", "may", "might",
        "shall", "must", "not", "no", "its", "it's", "their", "them",
        "they", "this", "that", "these", "those",
    }
    tokens = re.findall(r'\b[a-zA-Z_]\w+\b', statement.lower())
    return [t for t in tokens if t not in stop_words and len(t) > 2]


def _find_code_by_keywords(src_dir: Path, keywords: list[str]) -> list[str]:
    """Find source files matching the given keywords."""
    if not src_dir.exists() or not keywords:
        return []

    matching = []
    for source_file in sorted(src_dir.rglob("*.py")):
        if not source_file.is_file():
            continue
        try:
            text = source_file.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        # Count matching keywords
        matches = sum(1 for kw in keywords if kw in text)
        if matches > 0:
            rel = str(source_file.relative_to(src_dir.parent))
            matching.append(rel)

    return matching[:20]  # limit


def _find_tests_for_requirement(test_reports: list[dict], req_id: str,
                                 statement: str) -> list[dict]:
    """Find test reports referencing a specific requirement."""
    matching = []
    keywords = _extract_keywords(statement)

    for report in test_reports:
        output_text = json.dumps(report).lower()

        # Direct match on req_id
        if req_id.lower() in output_text:
            matching.append(report)
            continue

        # Keyword match
        kw_matches = sum(1 for kw in keywords if kw in output_text)
        if len(keywords) > 0 and kw_matches >= max(2, len(keywords) // 3):
            matching.append(report)

    return matching


def _find_reviews_for_requirement(reviews: list[dict], req_id: str,
                                   statement: str) -> list[dict]:
    """Find reviews referencing a specific requirement."""
    matching = []
    keywords = _extract_keywords(statement)

    for review in reviews:
        review_text = json.dumps(review).lower()

        if req_id.lower() in review_text:
            matching.append(review)
            continue

        kw_matches = sum(1 for kw in keywords if kw in review_text)
        if len(keywords) > 0 and kw_matches >= max(2, len(keywords) // 3):
            matching.append(review)

    return matching


def _find_orphaned_tests(test_reports: list[dict],
                          requirements: list[dict]) -> list[str]:
    """Find test files not associated with any requirement."""
    req_ids = {r["id"] for r in requirements}
    orphaned = []

    for report in test_reports:
        report_text = json.dumps(report)
        has_ref = any(req_id in report_text for req_id in req_ids)
        if not has_ref:
            orphaned.append(report.get("file", "unknown"))

    return orphaned


__all__ = [
    "extract_shall_statements",
    "extract_shall_from_text",
    "scan_review_artifacts",
    "scan_test_reports",
    "scan_ci_results",
    "generate_lrm",
    "generate_lrt",
    "generate_traceability_report",
]
