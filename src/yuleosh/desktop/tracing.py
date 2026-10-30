# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Desktop traceability governance (ASPICE CL2 minimal loop).

Builds a project-level requirement ↔ code ↔ test matrix from the artifacts
that actually live in a desktop workspace (``requirements/``, ``design/``,
``code/``, ``tests/``), independent of pipeline session history. This closes
the desktop gap where :func:`yuleosh.alm.traceability.generate_lrt` only scans
``docs/`` and ``.osh/sessions/``.

Artifacts::

    {project}/.osh/evidence/traceability-matrix.json
    {project}/.osh/evidence/traceability-{baseline}.json   # 绑定基线时

API consumers get:

* refresh  — regenerate the matrix after a change, optionally bound to a baseline
* reverse  — code/test file → requirements (for impact analysis)
* gate     — completeness verdict reused by ``pipeline/gates.py``
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from yuleosh.desktop import baseline as baseline_mod, workspace

TRACE_REL = Path(".osh") / "evidence" / "traceability-matrix.json"

_REQ_ID_RE = re.compile(
    r"@req\s*[\(\s]\s*([A-Z][A-Z0-9_\-\.]+(?:\s*,\s*[A-Z][A-Z0-9_\-\.]+)*)",
    re.IGNORECASE,
)


def _files_mentioning(base: Path, needle: str) -> list[str]:
    hits = []
    if not base.is_dir():
        return hits
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle in text:
            hits.append(str(f.relative_to(base.parent)))
    return hits


def _validate_rel(project_id: str, rel_path: str) -> Path:
    proj_dir = workspace._project_dir(project_id)
    target = (proj_dir / rel_path).resolve()
    try:
        target.relative_to(proj_dir.resolve())
    except ValueError:
        raise ValueError("path escapes project directory")
    return target


def _spec_path(project_id: str, spec: str | None = None) -> str | None:
    proj_dir = workspace._project_dir(project_id)
    if spec:
        target = _validate_rel(project_id, spec)
        if not target.is_file():
            raise FileNotFoundError(f"Spec not found: {spec}")
        return str(target)
    for rel in (
        "requirements/requirements.md",
        "docs/spec.md",
        "docs/software-requirements.md",
    ):
        p = proj_dir / rel
        if p.is_file():
            return str(p)
    return None


def _requirement_ids(project_id: str, spec_path: str | None) -> dict[str, str]:
    """Return ``{req_id: statement}`` from the spec, with annotation fallback."""
    ids: dict[str, str] = {}
    if spec_path:
        from yuleosh.alm.traceability import extract_shall_statements
        for item in extract_shall_statements(spec_path):
            rid = (item.get("req_id") or item.get("id") or "").strip().upper()
            if rid:
                ids.setdefault(rid, (item.get("statement") or "").strip())

    if ids:
        return ids

    # 没有可用 spec 时，从代码/测试/设计中的 @req 注解反推需求集合。
    proj_dir = workspace._project_dir(project_id)
    for sub in ("code", "tests", "design"):
        base = proj_dir / sub
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in _REQ_ID_RE.finditer(text):
                for rid in m.group(1).split(","):
                    rid = rid.strip().upper()
                    if rid:
                        ids.setdefault(rid, "")
    return ids


def build_matrix(project_id: str, spec: str | None = None,
                 baseline: str | None = None) -> dict:
    """Build a traceability matrix from desktop artifacts (no file writes)."""
    workspace._load_meta(project_id)
    spec_path = _spec_path(project_id, spec)
    req_ids = _requirement_ids(project_id, spec_path)

    proj_dir = workspace._project_dir(project_id)
    rows = []
    with_code = with_test = 0
    linked_tests: set[str] = set()

    for rid, statement in sorted(req_ids.items()):
        code = _files_mentioning(proj_dir / "code", rid)
        tests = _files_mentioning(proj_dir / "tests", rid)
        design = _files_mentioning(proj_dir / "design", rid)
        review = _files_mentioning(proj_dir / "evidence", rid)
        with_code += 1 if code else 0
        with_test += 1 if tests else 0
        linked_tests.update(tests)
        rows.append({
            "req_id": rid,
            "statement": statement[:160],
            "section": "",
            "has_code": bool(code),
            "has_test": bool(tests),
            "has_review": bool(review),
            "code_files": code,
            "test_files": tests,
            "design_files": design,
            "status": "Covered" if tests else "Not Covered",
        })

    all_tests = {str(p.relative_to(proj_dir)) for p in (proj_dir / "tests").rglob("*")
                 if p.is_file()} if (proj_dir / "tests").is_dir() else set()
    orphaned = sorted(all_tests - linked_tests)

    total = len(rows)
    pct = round(with_test / total * 100.0, 1) if total else 0.0
    return {
        "schema": "osh-traceability-v1",
        "source": "desktop.tracing",
        "generated": datetime.now().isoformat(),
        "baseline": baseline,
        "summary": {
            "total_requirements": total,
            "with_test_coverage": with_test,
            "with_implementation": with_code,
            "coverage_pct": pct,
            "orphaned_tests": len(orphaned),
        },
        "requirements": rows,
        "orphaned_test_files": orphaned,
    }


def refresh(project_id: str, body: dict[str, Any] | None = None) -> dict:
    """Regenerate the matrix and optionally archive a baseline-bound snapshot."""
    body = body or {}
    baseline_name = (body.get("baseline") or "").strip() or None
    if baseline_name:
        # 不存在/非法名称会分别抛 FileNotFoundError / ValueError。
        baseline_mod.load_baseline(project_id, baseline_name)

    matrix = build_matrix(
        project_id,
        spec=(body.get("spec") or "").strip() or None,
        baseline=baseline_name,
    )

    proj_dir = workspace._project_dir(project_id)
    out = proj_dir / TRACE_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")

    snapshot = None
    if baseline_name:
        snap = proj_dir / ".osh" / "evidence" / f"traceability-{baseline_name}.json"
        snap.write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
        snapshot = str(snap.relative_to(proj_dir))

    return {
        "matrix": matrix,
        "json": str(TRACE_REL),
        "snapshot": snapshot,
        "baseline": baseline_name,
    }


def load_matrix(project_id: str) -> dict | None:
    workspace._load_meta(project_id)
    p = workspace._project_dir(project_id) / TRACE_REL
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def reverse_lookup(project_id: str, file_path: str) -> dict:
    """Return requirements linked to a code/test/design file."""
    workspace._load_meta(project_id)
    rel = file_path.strip()
    if not rel:
        raise ValueError("file is required")
    target = _validate_rel(project_id, rel)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {rel}")

    matrix = build_matrix(project_id)
    reqs = []
    for row in matrix["requirements"]:
        if (rel in row.get("code_files", [])
                or rel in row.get("test_files", [])
                or rel in row.get("design_files", [])):
            reqs.append(row)
    return {
        "file": rel,
        "requirement_ids": [r["req_id"] for r in reqs],
        "requirements": reqs,
    }


def gate_verdict(matrix: dict, threshold: float | None = None) -> dict:
    """Evaluate traceability completeness for the quality gate."""
    from yuleosh.pipeline.gates import traceability_gate
    return traceability_gate(matrix, threshold=threshold)
