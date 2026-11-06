#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Evidence Chain — 把 ASPICE 证据链生成可校验的 JSON + 单文件 HTML。

设计约束（见 ``chain_rules.yaml``）：

* **真源优先**：只消费 ``.osh/evidence/traceability-matrix.json`` 与
  ``.osh/`` 下的 CI / 测试 / 评审产物；矩阵缺失时才调用
  :func:`yuleosh.alm.traceability.generate_lrt`。
* **fail-closed**：结构门禁（schema / ID / 重复 / 悬空边 / 孤儿需求 /
  必需产物缺失 / 过程门禁）任一 ERROR → ``chain.summary.status=FAIL``，
  CLI 退出码非 0。
* **HTML 只是视图**：``chain.json`` 是权威产物；HTML 单文件、离线、
  含数据内嵌、深链与抽屉，但不允许把 FAIL 渲染成通过。

对外 API：

  collect_chain(project_dir)      — 采集 + 校验，返回 chain dict
  validate_chain(chain)           — 返回 problems 列表
  render_html(chain)              — 返回完整 HTML 字符串
  write_chain(chain, evidence_dir) — 落盘 chain.json + 证据链总览.html
  cmd_evidence_chain(...)         — CLI 入口（退出码 fail-closed）
"""

from __future__ import annotations

import hashlib
import html as _html
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from yuleosh.alm.traceability import (
    generate_lrt,
    scan_ci_results,
    scan_review_artifacts,
    scan_test_reports,
    write_authoritative_traceability,
)
from yuleosh.report import visualization

log = logging.getLogger("evidence.chain")

RULES_PATH = Path(__file__).with_name("chain_rules.yaml")
CHAIN_JSON = "chain.json"
CHAIN_HTML = "证据链总览.html"

REQUIRED_TOP_KEYS = ("schema", "nodes", "edges", "artifacts", "gates", "problems")

NODE_COLORS = {
    "requirement": "#2563eb",
    "code": "#7c3aed",
    "test": "#10b981",
    "review": "#f59e0b",
}
EDGE_COLORS = {
    "implement": "#7c3aed",
    "verify": "#10b981",
    "review": "#f59e0b",
    "derive": "#64748b",
}
STATUS_COLORS = {
    "covered": "#22c55e",
    "partial": "#f59e0b",
    "gap": "#ef4444",
    "unknown": "#6b7280",
}


# ═══════════════════════════════════════════════════════════════════════
# Rules / helpers
# ═══════════════════════════════════════════════════════════════════════


def load_rules(path: Optional[Path] = None) -> dict:
    """Load and minimally validate ``chain_rules.yaml``."""
    rules_path = Path(path) if path else RULES_PATH
    data = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or "schema" not in data:
        raise ValueError(f"invalid chain rules: {rules_path}")
    return data


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _evidence_dir(project_dir: str, evidence_dir: Optional[str] = None) -> Path:
    return Path(evidence_dir) if evidence_dir else Path(project_dir) / ".osh" / "evidence"


def _rel_posix(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def _grade(pct: float) -> str:
    if pct >= 90:
        return "E3"
    if pct >= 60:
        return "E2"
    if pct > 0:
        return "E1"
    return "NI"


def _coverage(part: int, total: int) -> float:
    return round(part / total * 100, 1) if total else 0.0


# ═══════════════════════════════════════════════════════════════════════
# Collection
# ═══════════════════════════════════════════════════════════════════════


def _load_requirement_rows(project_dir: Path, ev_dir: Path) -> tuple[list[dict], str]:
    """Load requirements from the authoritative matrix, else generate it."""
    matrix_path = ev_dir / "traceability-matrix.json"

    def _read_matrix() -> Optional[list[dict]]:
        try:
            data = json.loads(matrix_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if data.get("schema") != "osh-traceability-v1":
            return None
        rows = data.get("requirements")
        return rows if isinstance(rows, list) else None

    if matrix_path.exists():
        rows = _read_matrix()
        if rows is not None:
            return rows, "traceability-matrix.json"

    # 缺失或被破坏：以权威生成器重建矩阵，确保证据链有真源且产物可归档。
    try:
        write_authoritative_traceability(str(project_dir))
        rows = _read_matrix()
        if rows is not None:
            return rows, "alm.traceability.write_authoritative_traceability"
    except (OSError, ValueError) as exc:
        log.warning("authoritative traceability generation failed: %s", exc)

    lrt = generate_lrt(str(project_dir))
    rows = []
    for req in (lrt.get("lrm") or {}).get("requirements") or []:
        rows.append({
            "req_id": req.get("id", ""),
            "statement": req.get("statement", ""),
            "section": req.get("section", ""),
            "has_code": bool(req.get("has_code")),
            "has_test": bool(req.get("has_test")),
            "has_review": bool(req.get("has_review")),
            "code_files": [str(p) for p in (req.get("code_files") or [])],
            "test_files": sorted({
                str(t.get("file", "")) for t in (req.get("test_reports") or [])
                if isinstance(t, dict) and t.get("file")
            }),
        })
    return rows, "alm.traceability.generate_lrt"


def _collect_artifacts(project_dir: Path, ev_dir: Path) -> list[dict]:
    artifacts: list[dict] = []
    if not ev_dir.exists():
        return artifacts
    for path in sorted(ev_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in (CHAIN_JSON, CHAIN_HTML):
            continue
        if path.suffix.lower() not in (".md", ".json", ".html", ".zip", ".yaml", ".yml", ".csv"):
            continue
        artifacts.append({
            "id": f"artifact:{_rel_posix(path, ev_dir)}",
            "path": _rel_posix(path, project_dir),
            "href": os.path.relpath(str(path), str(ev_dir)).replace(os.sep, "/"),
            "name": path.name,
            "kind": path.suffix.lstrip(".").lower(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        })
    return artifacts


def _test_status_map(project_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for report in scan_test_reports(str(project_dir)):
        file_key = Path(str(report.get("file", ""))).name
        if not file_key:
            continue
        if int(report.get("failed", 0) or 0) > 0 or str(report.get("status")) == "failed":
            mapping[file_key] = "failed"
        elif str(report.get("status")) == "passed":
            mapping[file_key] = "passed"
        else:
            mapping.setdefault(file_key, "unknown")
    return mapping


def _review_edges(rows: list[dict], reviews: list[dict]) -> list[dict]:
    """Map requirement → review by matching reviewed file names."""
    edges: list[dict] = []
    for req in rows:
        if not req.get("has_review"):
            continue
        rid = str(req.get("req_id") or "")
        names = {Path(str(p)).name for p in (req.get("code_files") or []) + (req.get("test_files") or [])}
        names.discard("")
        for review in reviews:
            reviewed = {Path(str(p)).name for p in (review.get("reviewed_files") or [])}
            findings_text = " ".join(str(x) for x in (review.get("findings") or []))
            if (names & reviewed) or (rid and rid in findings_text):
                edges.append({
                    "from": rid,
                    "to": f"review:{review.get('session', 'unknown')}",
                    "kind": "review",
                })
    return edges


def collect_chain(
    project_dir: str,
    evidence_dir: Optional[str] = None,
    rules: Optional[dict] = None,
) -> dict:
    """Collect the evidence chain from yuleOSH truth-source artifacts."""
    rules = rules or load_rules()
    project = Path(project_dir)
    ev_dir = _evidence_dir(str(project), evidence_dir)
    rows, source = _load_requirement_rows(project, ev_dir)

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add_node(node: dict) -> None:
        existing = nodes.get(node["id"])
        if existing is None:
            nodes[node["id"]] = node
        else:
            existing.setdefault("refs", [])
            for ref in node.get("refs", []):
                if ref not in existing["refs"]:
                    existing["refs"].append(ref)

    def add_edge(source_id: str, target_id: str, kind: str) -> None:
        edges.append({"from": source_id, "to": target_id, "kind": kind})

    tests = _test_status_map(project)
    for row in rows:
        rid = str(row.get("req_id") or "").strip()
        if not rid:
            continue
        statement = str(row.get("statement") or "")
        add_node({
            "id": rid,
            "type": "requirement",
            "title": statement[:120] or rid,
            "status": "covered" if row.get("has_test") else ("partial" if row.get("has_code") else "gap"),
            "refs": [str(row.get("section") or "")] if row.get("section") else [],
            "has_code": bool(row.get("has_code")),
            "has_test": bool(row.get("has_test")),
            "has_review": bool(row.get("has_review")),
        })
        for code_file in row.get("code_files") or []:
            code_id = f"code:{str(code_file).replace(os.sep, '/')}"
            add_node({
                "id": code_id,
                "type": "code",
                "title": Path(str(code_file)).name,
                "status": "evidence",
                "refs": [str(code_file)],
            })
            add_edge(rid, code_id, "implement")
        for test_file in row.get("test_files") or []:
            test_id = f"test:{str(test_file).replace(os.sep, '/')}"
            add_node({
                "id": test_id,
                "type": "test",
                "title": Path(str(test_file)).name,
                "status": tests.get(Path(str(test_file)).name, "unknown"),
                "refs": [str(test_file)],
            })
            add_edge(rid, test_id, "verify")

    reviews = scan_review_artifacts(str(project))
    for review in reviews:
        session = str(review.get("session") or "unknown")
        add_node({
            "id": f"review:{session}",
            "type": "review",
            "title": session,
            "status": "findings" if review.get("findings") else "clean",
            "refs": [str(p) for p in (review.get("reviewed_files") or [])],
        })
    for edge in _review_edges(rows, reviews):
        if edge["from"] in nodes and edge["to"] in nodes:
            add_edge(edge["from"], edge["to"], "review")

    # SYS.1 → SWE.1 derivation edges (only when both endpoints exist).
    try:
        matrix = json.loads((ev_dir / "traceability-matrix.json").read_text(encoding="utf-8"))
        sys_trace = matrix.get("sys_trace") or {}
    except (json.JSONDecodeError, OSError):
        sys_trace = {}
    for sys_id, swe_id in (sys_trace.get("sys_to_swe") or {}).items():
        swe_target = swe_id if isinstance(swe_id, str) else ", ".join(map(str, swe_id or []))
        if str(sys_id) in nodes and swe_target in nodes:
            add_edge(str(sys_id), swe_target, "derive")

    ci_results = scan_ci_results(str(project))
    test_reports = scan_test_reports(str(project))
    artifacts = _collect_artifacts(project, ev_dir)

    total = len(rows)
    with_code = sum(1 for r in rows if r.get("has_code"))
    with_test = sum(1 for r in rows if r.get("has_test"))
    with_review = sum(1 for r in rows if r.get("has_review"))
    ci_failed = [c for c in ci_results if str(c.get("status", "")).lower() in ("failed", "fail", "error")]
    tests_failed = sum(int(t.get("failed", 0) or 0) for t in test_reports)

    thresholds = rules.get("thresholds") or {}
    min_test = float(thresholds.get("min_test_coverage_pct", 60))
    min_code = float(thresholds.get("min_code_coverage_pct", 60))
    review_required = bool(thresholds.get("review_required", False))

    code_pct = _coverage(with_code, total)
    test_pct = _coverage(with_test, total)
    review_pct = _coverage(with_review, total)

    def gate(gid: str, severity: str, passed: Optional[bool], detail: str) -> dict:
        if passed is None:
            status = "WARNING"
        else:
            status = "PASS" if passed else "FAIL"
        return {"id": gid, "severity": severity, "status": status, "detail": detail}

    process_gates = [
        gate("G-REQ", "ERROR", total > 0, f"{total} requirement(s) parsed"),
        gate("G-CODE", "ERROR", code_pct >= min_code,
             f"implementation coverage {code_pct}% (threshold {min_code:g}%)"),
        gate("G-TEST", "ERROR", test_pct >= min_test,
             f"test coverage {test_pct}% (threshold {min_test:g}%)"),
        gate("G-REVIEW", "ERROR" if review_required else "WARNING", True if with_review else None,
             f"{with_review}/{total} requirement(s) reviewed"),
        gate("G-CI", "ERROR", None if not ci_results else not ci_failed,
             "no CI results" if not ci_results else f"{len(ci_results)} run(s), {len(ci_failed)} failed"),
    ]

    chain = {
        "schema": (rules.get("schema") or {}).get("name", "osh-evidence-chain-v1"),
        "schema_version": (rules.get("schema") or {}).get("version", "1.0.0"),
        "generated_at": datetime.now().isoformat(),
        "project_dir": str(project),
        "source": source,
        "nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["id"])),
        "edges": [
            {"from": src, "to": dst, "kind": kind}
            for src, dst, kind in sorted(
                {(e["from"], e["to"], e["kind"]) for e in edges},
                key=lambda item: (item[2], item[0], item[1]),
            )
        ],
        "artifacts": artifacts,
        "ci_results": ci_results,
        "gates": process_gates,
        "problems": [],
        "metrics": {
            "requirements": total,
            "with_code": with_code,
            "with_test": with_test,
            "with_review": with_review,
            "code_coverage_pct": code_pct,
            "test_coverage_pct": test_pct,
            "review_coverage_pct": review_pct,
            "tests": len(test_reports),
            "tests_failed": tests_failed,
            "ci_runs": len(ci_results),
            "ci_failed": len(ci_failed),
            "reviews": len(reviews),
            "artifacts": len(artifacts),
        },
        "summary": {},
    }

    problems = validate_chain(chain, rules)
    chain["problems"] = problems
    chain["gates"] = _structural_gates(rules, problems, process_gates)
    chain["summary"] = _summarize(chain)
    return chain


def _structural_gates(rules: dict, problems: list[dict], process_gates: list[dict]) -> list[dict]:
    """Append structural gate rows (E-CHAIN-*) to the process gates."""
    rows: list[dict] = list(process_gates)
    for spec in rules.get("gates") or []:
        gid = str(spec.get("id", ""))
        if not gid or gid == "E-CHAIN-GATE":
            continue
        related = [p for p in problems if p.get("code") == gid]
        if any(p.get("severity") == "ERROR" for p in related):
            status = "FAIL"
        elif related:
            status = "WARNING"
        else:
            status = "PASS"
        rows.append({
            "id": gid,
            "severity": str(spec.get("severity", "ERROR")),
            "status": status,
            "detail": related[0]["message"] if related else str(spec.get("rule", "ok")),
        })
    failed = [g for g in rows
              if g.get("status") == "FAIL" and g.get("severity") == "ERROR"]
    rows.append({
        "id": "E-CHAIN-GATE",
        "severity": "ERROR",
        "status": "FAIL" if failed else "PASS",
        "detail": ", ".join(str(g["id"]) for g in failed) if failed else "all ERROR gates passed",
    })
    return rows


def _summarize(chain: dict) -> dict:
    nodes = chain.get("nodes") or []
    edges = chain.get("edges") or []
    metrics = chain.get("metrics") or {}
    gates = chain.get("gates") or []
    problems = chain.get("problems") or []
    errors = [p for p in problems if p.get("severity") == "ERROR"]
    warnings = [p for p in problems if p.get("severity") != "ERROR"]
    gates_fail = [g for g in gates if g.get("status") == "FAIL"]
    return {
        "status": "FAIL" if errors or gates_fail else "PASS",
        "nodes": len(nodes),
        "edges": len(edges),
        "requirements": metrics.get("requirements", 0),
        "test_coverage_pct": metrics.get("test_coverage_pct", 0),
        "code_coverage_pct": metrics.get("code_coverage_pct", 0),
        "artifacts": metrics.get("artifacts", 0),
        "gates_pass": sum(1 for g in gates if g.get("status") == "PASS"),
        "gates_fail": len(gates_fail),
        "problems_error": len(errors),
        "problems_warning": len(warnings),
    }


# ═══════════════════════════════════════════════════════════════════════
# Validation (fail-closed)
# ═══════════════════════════════════════════════════════════════════════


def _problem(code: str, severity: str, message: str, **extra: Any) -> dict:
    item = {"code": code, "severity": severity, "message": message}
    item.update({k: v for k, v in extra.items() if v is not None})
    return item


def validate_chain(chain: dict, rules: Optional[dict] = None) -> list[dict]:
    """Validate a chain dict and return problems (ERROR / WARNING)."""
    rules = rules or load_rules()
    id_rules = rules.get("id_rules") or {}
    req_pattern = re.compile(id_rules.get("requirement_pattern", r"^[A-Z][A-Za-z0-9_.\-]{2,}$"))
    link_pattern = re.compile(id_rules.get("linked_pattern", r"^[a-z]+:[^\s]+$"))

    problems: list[dict] = []
    schema = rules.get("schema") or {}

    if chain.get("schema") != schema.get("name", "osh-evidence-chain-v1"):
        problems.append(_problem(
            "E-CHAIN-SCHEMA", "ERROR",
            f"schema mismatch: expected {schema.get('name')!r}, got {chain.get('schema')!r}",
        ))
    expected_version = schema.get("version")
    if expected_version and chain.get("schema_version") != expected_version:
        problems.append(_problem(
            "E-CHAIN-SCHEMA", "ERROR",
            f"schema version mismatch: expected {expected_version!r}, "
            f"got {chain.get('schema_version')!r}",
        ))
    for key in REQUIRED_TOP_KEYS:
        if key not in chain:
            problems.append(_problem("E-CHAIN-SCHEMA", "ERROR", f"missing top-level key: {key}"))

    nodes = chain.get("nodes") if isinstance(chain.get("nodes"), list) else []
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            problems.append(_problem("E-CHAIN-SCHEMA", "ERROR", "node entry is not an object"))
            continue
        node_id = str(node.get("id", ""))
        if not node_id:
            problems.append(_problem("E-CHAIN-ID", "ERROR", "node with empty id"))
            continue
        if node_id in seen:
            problems.append(_problem("E-CHAIN-DUP", "ERROR", f"duplicate node id: {node_id}", node=node_id))
        seen.add(node_id)
        pattern = req_pattern if node.get("type") == "requirement" else link_pattern
        if not pattern.match(node_id):
            problems.append(_problem("E-CHAIN-ID", "ERROR", f"invalid node id: {node_id}", node=node_id))

    dangling = 0
    edges = chain.get("edges") if isinstance(chain.get("edges"), list) else []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        src, dst = str(edge.get("from", "")), str(edge.get("to", ""))
        if src not in seen or dst not in seen:
            dangling += 1
            problems.append(_problem(
                "E-CHAIN-DANGLING", "ERROR",
                f"dangling edge {src} -> {dst} ({edge.get('kind', '')})",
            ))

    implemented = {str(e.get("from")) for e in edges
                   if isinstance(e, dict) and e.get("kind") in ("implement", "verify")}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("type") != "requirement":
            continue
        if str(node.get("id")) not in implemented:
            problems.append(_problem(
                "E-CHAIN-ORPHAN", "ERROR",
                f"requirement has no code/test evidence: {node.get('id')}",
                node=str(node.get("id")),
            ))
        elif not node.get("has_review"):
            problems.append(_problem(
                "W-CHAIN-REVIEW", "WARNING",
                f"requirement not covered by review: {node.get('id')}",
                node=str(node.get("id")),
            ))

    required = rules.get("required_evidence") or []
    artifacts = chain.get("artifacts") if isinstance(chain.get("artifacts"), list) else []
    by_name = {str(a.get("name", "")): a for a in artifacts if isinstance(a, dict)}
    project_dir = Path(str(chain.get("project_dir") or "."))
    for name in required:
        artifact = by_name.get(str(name))
        if not artifact:
            problems.append(_problem(
                "E-CHAIN-ARTIFACT-MISSING", "ERROR",
                f"required evidence artifact missing: {name}",
            ))
            continue
        if not str(artifact.get("sha256") or ""):
            problems.append(_problem(
                "E-CHAIN-ARTIFACT-MISSING", "ERROR",
                f"required evidence artifact has empty SHA256: {name}",
            ))
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        path_text = str(artifact.get("path") or "")
        if not path_text:
            continue
        path = Path(path_text)
        if not path.is_absolute():
            path = project_dir / path
        if not path.exists():
            problems.append(_problem(
                "E-CHAIN-ARTIFACT-MISSING", "ERROR",
                f"artifact recorded but not found: {path_text}",
            ))

    failed_gates = [g for g in (chain.get("gates") or [])
                    if isinstance(g, dict)
                    and g.get("status") == "FAIL" and g.get("severity") == "ERROR"]
    if failed_gates:
        problems.append(_problem(
            "E-CHAIN-GATE", "ERROR",
            "ERROR gates failed: " + ", ".join(str(g.get("id")) for g in failed_gates),
        ))

    return problems


# ═══════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════


def write_chain(
    chain: dict,
    evidence_dir: Optional[str] = None,
    render: bool = True,
) -> dict:
    """Write ``chain.json`` (and optionally the HTML overview)."""
    project = Path(str(chain.get("project_dir") or "."))
    ev_dir = _evidence_dir(str(project), evidence_dir)
    ev_dir.mkdir(parents=True, exist_ok=True)

    json_path = ev_dir / CHAIN_JSON
    json_path.write_text(json.dumps(chain, indent=2, ensure_ascii=False), encoding="utf-8")
    output = {"json": str(json_path), "html": None}
    if render:
        html_path = ev_dir / CHAIN_HTML
        html_path.write_text(render_html(chain), encoding="utf-8")
        output["html"] = str(html_path)
    return output


# ═══════════════════════════════════════════════════════════════════════
# HTML rendering (single-file, offline, fail-closed)
# ═══════════════════════════════════════════════════════════════════════


COLUMNS = [
    ("requirement", "需求 / 来源", "STK · SYS · SWE"),
    ("code", "实现", "implementation"),
    ("test", "测试 / 验证", "verification"),
    ("review", "评审", "SUP.1"),
]
CARD_W, CARD_H, COL_GAP, X0, Y0, YGAP = 232, 62, 300, 24, 52, 12


def _esc(value: Any) -> str:
    return _html.escape(str(value), quote=True)


def _layout(chain: dict) -> tuple[dict[str, dict], int, int]:
    positions: dict[str, dict] = {}
    max_y = Y0
    for col_index, (node_type, _title, _sub) in enumerate(COLUMNS):
        col_nodes = sorted(
            (n for n in chain.get("nodes") or [] if n.get("type") == node_type),
            key=lambda n: str(n.get("id")),
        )
        y = Y0
        for node in col_nodes:
            positions[str(node["id"])] = {
                "x": X0 + col_index * COL_GAP,
                "y": y,
                "w": CARD_W,
                "h": CARD_H,
            }
            y += CARD_H + YGAP
        max_y = max(max_y, y)
    width = X0 + len(COLUMNS) * COL_GAP
    height = max(max_y + 40, 420)
    return positions, width, height


def _trace_svg(chain: dict, positions: dict[str, dict], width: int, height: int) -> str:
    markers = "".join(
        f'<marker id="arrow-{kind}" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker>'
        for kind, color in EDGE_COLORS.items()
    )
    parts = [
        f'<svg class="edges" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<defs>{markers}</defs>',
    ]
    for edge in chain.get("edges") or []:
        src = positions.get(str(edge.get("from")))
        dst = positions.get(str(edge.get("to")))
        if not src or not dst:
            continue
        x1, y1 = src["x"] + src["w"], src["y"] + src["h"] / 2
        x2, y2 = dst["x"], dst["y"] + dst["h"] / 2
        if x2 <= x1:
            x2 = dst["x"] + dst["w"]
        mid = (x1 + x2) / 2
        color = EDGE_COLORS.get(str(edge.get("kind")), "#94a3b8")
        parts.append(
            f'<path class="edge edge-{_esc(edge.get("kind"))}" '
            f'd="M {x1} {y1} C {mid} {y1}, {mid} {y2}, {x2} {y2}" '
            f'stroke="{color}" fill="none" marker-end="url(#arrow-{_esc(edge.get("kind"))})" '
            f'data-source="{_esc(edge.get("from"))}" data-target="{_esc(edge.get("to"))}"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _node_cards(chain: dict, positions: dict[str, dict]) -> str:
    cards = []
    for node in chain.get("nodes") or []:
        node_id = str(node.get("id"))
        pos = positions.get(node_id)
        if not pos:
            continue
        node_type = str(node.get("type"))
        color = NODE_COLORS.get(node_type, "#64748b")
        status_color = STATUS_COLORS.get(str(node.get("status")), "#6b7280")
        refs = " · ".join(str(r) for r in (node.get("refs") or []) if r)
        cards.append(
            f'<div class="node" data-node-id="{_esc(node_id)}" '
            f'data-search="{_esc((node_id + " " + str(node.get("title", "")) + " " + refs).lower())}" '
            f'tabindex="0" style="left:{pos["x"]}px;top:{pos["y"]}px;width:{pos["w"]}px;height:{pos["h"]}px;'
            f'border-left:4px solid {color};">'
            f'<div class="node-top"><span class="node-type" style="color:{color}">{_esc(node_type)}</span>'
            f'<span class="dot" style="background:{status_color}" title="{_esc(node.get("status"))}"></span></div>'
            f'<div class="node-title">{_esc(node.get("title"))}</div>'
            f'<div class="node-id">{_esc(node_id)}</div>'
            f'</div>'
        )
    return "".join(cards)


def _artifact_rows(chain: dict) -> tuple[str, int]:
    rows = []
    nodes = chain.get("nodes") or []
    review_ids = [str(n.get("id")) for n in nodes if n.get("type") == "review"]
    req_ids = [str(n.get("id")) for n in nodes if n.get("type") == "requirement"]
    for artifact in chain.get("artifacts") or []:
        name = str(artifact.get("name", ""))
        related: list[str] = []
        if "traceability" in name:
            related = req_ids[:6]
        elif "review" in name:
            related = review_ids[:6]
        links = " ".join(
            f'<a class="chip" href="#/node/{_esc(nid)}">{_esc(nid)}</a>'
            for nid in related
        ) or '<span class="muted">—</span>'
        rows.append(
            f'<tr data-artifact-id="{_esc(artifact.get("id"))}">'
            f'<td><a href="{_esc(artifact.get("href"))}" target="_blank" rel="noopener">'
            f'{_esc(artifact.get("path"))}</a> '
            f'<a class="chip" href="#/artifact/{_esc(artifact.get("id"))}">详情</a></td>'
            f'<td>{_esc(artifact.get("kind"))}</td>'
            f'<td>{int(artifact.get("size_bytes", 0)):,}</td>'
            f'<td><code title="{_esc(artifact.get("sha256"))}">'
            f'{_esc(str(artifact.get("sha256", ""))[:16])}…</code></td>'
            f'<td>{links}</td></tr>'
        )
    return "".join(rows), len(chain.get("artifacts") or [])


def _gate_rows(chain: dict) -> str:
    rows = []
    for gate_row in chain.get("gates") or []:
        status = str(gate_row.get("status"))
        cls = {"PASS": "ok", "FAIL": "bad", "WARNING": "warn"}.get(status, "muted")
        rows.append(
            f'<tr class="gate-{cls}" data-gate-id="{_esc(gate_row.get("id"))}">'
            f'<td><a href="#/gate/{_esc(gate_row.get("id"))}">{_esc(gate_row.get("id"))}</a></td>'
            f'<td>{_esc(gate_row.get("severity"))}</td>'
            f'<td><span class="pill {cls}">{_esc(status)}</span></td>'
            f'<td>{_esc(gate_row.get("detail"))}</td></tr>'
        )
    return "".join(rows)


def _problem_rows(chain: dict) -> str:
    if not chain.get("problems"):
        return '<tr><td colspan="4" class="muted">无问题 — 所有结构门禁通过</td></tr>'
    rows = []
    for problem in chain.get("problems") or []:
        node = problem.get("node")
        node_cell = f'<a class="chip" href="#/node/{_esc(node)}">{_esc(node)}</a>' if node else '<span class="muted">—</span>'
        rows.append(
            f'<tr><td><span class="pill {"bad" if problem.get("severity") == "ERROR" else "warn"}">'
            f'{_esc(problem.get("severity"))}</span></td>'
            f'<td>{_esc(problem.get("code"))}</td>'
            f'<td>{_esc(problem.get("message"))}</td>'
            f'<td>{node_cell}</td></tr>'
        )
    return "".join(rows)


def _kpi_cards(chain: dict) -> str:
    summary = chain.get("summary") or {}
    metrics = chain.get("metrics") or {}
    status = str(summary.get("status", "FAIL"))
    cards = [
        ("链状态", status, "bad" if status == "FAIL" else "ok"),
        ("需求", str(metrics.get("requirements", 0)), ""),
        ("测试覆盖", f'{float(metrics.get("test_coverage_pct", 0)):.0f}%', ""),
        ("节点 / 边", f'{summary.get("nodes", 0)} / {summary.get("edges", 0)}', ""),
        ("门禁", f'{summary.get("gates_pass", 0)} 通过 / {summary.get("gates_fail", 0)} 失败',
         "bad" if summary.get("gates_fail") else "ok"),
        ("问题", f'{summary.get("problems_error", 0)} ERROR / {summary.get("problems_warning", 0)} WARN',
         "bad" if summary.get("problems_error") else "ok"),
    ]
    return "".join(
        f'<div class="kpi {cls}"><div class="kpi-value">{_esc(value)}</div>'
        f'<div class="kpi-label">{_esc(label)}</div></div>'
        for label, value, cls in cards
    )


def _chart_domains(chain: dict) -> list[dict]:
    metrics = chain.get("metrics") or {}
    total = int(metrics.get("requirements", 0))
    return [
        {"id": "REQ→CODE", "title": "实现覆盖", "coverage_pct": metrics.get("code_coverage_pct", 0),
         "score": _grade(float(metrics.get("code_coverage_pct", 0))),
         "gap_count": max(total - int(metrics.get("with_code", 0)), 0)},
        {"id": "REQ→TEST", "title": "测试覆盖", "coverage_pct": metrics.get("test_coverage_pct", 0),
         "score": _grade(float(metrics.get("test_coverage_pct", 0))),
         "gap_count": max(total - int(metrics.get("with_test", 0)), 0)},
        {"id": "REQ→REVIEW", "title": "评审覆盖", "coverage_pct": metrics.get("review_coverage_pct", 0),
         "score": _grade(float(metrics.get("review_coverage_pct", 0))),
         "gap_count": max(total - int(metrics.get("with_review", 0)), 0)},
    ]


def _requirement_grades(chain: dict) -> list[str]:
    grades = []
    for node in chain.get("nodes") or []:
        if node.get("type") != "requirement":
            continue
        if node.get("has_code") and node.get("has_test") and node.get("has_review"):
            grades.append("E3")
        elif node.get("has_code") and node.get("has_test"):
            grades.append("E2")
        elif node.get("has_code") or node.get("has_test"):
            grades.append("E1")
        else:
            grades.append("NI")
    return grades


def render_html(chain: dict) -> str:
    """Render the self-contained evidence-chain overview."""
    summary = chain.get("summary") or {}
    metrics = chain.get("metrics") or {}
    status = str(summary.get("status", "FAIL"))
    status_cls = "ok" if status == "PASS" else "bad"
    project_name = Path(str(chain.get("project_dir") or "project")).name
    generated = str(chain.get("generated_at", ""))

    positions, width, height = _layout(chain)
    edge_svg = _trace_svg(chain, positions, width, height)
    cards = _node_cards(chain, positions)
    artifact_rows, artifact_count = _artifact_rows(chain)
    gate_rows = _gate_rows(chain)
    problem_rows = _problem_rows(chain)
    kpi_cards = _kpi_cards(chain)

    domains = _chart_domains(chain)
    coverage_svg = visualization.coverage_bar(domains, width=520)
    donut_svg = visualization.bp_pass_donut(
        int(summary.get("gates_pass", 0)),
        int(summary.get("gates_pass", 0)) + int(summary.get("gates_fail", 0)),
        size=170,
    )
    dist_svg = visualization.score_distribution(_requirement_grades(chain), width=320, height=170)
    gap_svg = visualization.gap_heatmap(domains, width=520)

    ci_rows = "".join(
        f'<tr><td>{_esc(c.get("layer"))}</td><td>{_esc(c.get("status"))}</td>'
        f'<td>{_esc(c.get("timestamp"))}</td></tr>'
        for c in (chain.get("ci_results") or [])
    ) or '<tr><td colspan="3" class="muted">无 CI 结果</td></tr>'

    data_json = json.dumps(chain, ensure_ascii=False, default=str).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>证据链总览 — {_esc(project_name)}</title>
<style>
  :root {{
    --bg:#f8fafc; --card:#ffffff; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0;
    --ok:#16a34a; --bad:#dc2626; --warn:#d97706; --accent:#2563eb;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Noto Sans SC',sans-serif; }}
  header {{ background:linear-gradient(135deg,#0f172a,#1e293b); color:#fff; padding:22px 28px; }}
  header h1 {{ margin:0 0 6px; font-size:22px; letter-spacing:.5px; }}
  header .meta {{ color:#cbd5e1; font-size:13px; }}
  .badge {{ display:inline-block; padding:4px 12px; border-radius:999px; font-weight:700;
            font-size:13px; margin-left:10px; }}
  .badge.ok {{ background:#dcfce7; color:#166534; }}
  .badge.bad {{ background:#fee2e2; color:#991b1b; }}
  main {{ padding:22px 28px 60px; max-width:1500px; margin:0 auto; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
  .kpi-value {{ font-size:20px; font-weight:800; }}
  .kpi-label {{ color:var(--muted); font-size:12px; margin-top:4px; }}
  .kpi.bad .kpi-value {{ color:var(--bad); }}
  .kpi.ok .kpi-value {{ color:var(--ok); }}
  .charts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(360px,1fr)); gap:12px; margin-top:14px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; }}
  .card h2 {{ margin:0 0 12px; font-size:15px; }}
  .tabs {{ display:flex; gap:8px; margin:18px 0 10px; flex-wrap:wrap; }}
  .tabs button {{ border:1px solid var(--line); background:#fff; border-radius:8px;
                  padding:8px 16px; cursor:pointer; font-size:13px; color:var(--ink); }}
  .tabs button.active {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
  .toolbar {{ display:flex; gap:10px; align-items:center; margin-bottom:10px; }}
  .toolbar input {{ flex:1; max-width:420px; padding:8px 12px; border:1px solid var(--line);
                    border-radius:8px; font-size:13px; }}
  .view {{ display:none; }}
  .view.active {{ display:block; }}
  .trace-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:10px; background:#fff; }}
  .trace-canvas {{ position:relative; }}
  .edges {{ position:absolute; inset:0; pointer-events:none; }}
  .col-head {{ position:absolute; top:14px; font-size:12px; color:var(--muted);
               font-weight:700; letter-spacing:.4px; }}
  .node {{ position:absolute; background:#fff; border:1px solid var(--line); border-radius:9px;
           padding:8px 10px; cursor:pointer; box-shadow:0 1px 2px rgba(15,23,42,.08);
           transition:transform .12s, box-shadow .12s; overflow:hidden; }}
  .node:hover, .node:focus {{ transform:translateY(-2px); box-shadow:0 8px 18px rgba(15,23,42,.14); outline:none; }}
  .node.dim {{ opacity:.18; }}
  .node-top {{ display:flex; justify-content:space-between; align-items:center; }}
  .node-type {{ font-size:10px; text-transform:uppercase; font-weight:800; letter-spacing:.6px; }}
  .dot {{ width:8px; height:8px; border-radius:50%; }}
  .node-title {{ font-size:12px; font-weight:700; margin-top:4px; line-height:1.3;
                 display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
  .node-id {{ font-size:10px; color:var(--muted); margin-top:3px; white-space:nowrap;
              overflow:hidden; text-overflow:ellipsis; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; background:#fff; }}
  th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:middle; }}
  th {{ background:#f1f5f9; color:#334155; font-size:12px; }}
  .pill {{ display:inline-block; padding:2px 9px; border-radius:999px; font-size:11px; font-weight:700; }}
  .pill.ok {{ background:#dcfce7; color:#166534; }}
  .pill.bad {{ background:#fee2e2; color:#991b1b; }}
  .pill.warn {{ background:#fef3c7; color:#92400e; }}
  .muted {{ color:var(--muted); }}
  .chip {{ display:inline-block; background:#eff6ff; color:#1d4ed8; border-radius:6px;
           padding:2px 7px; font-size:11px; text-decoration:none; margin:1px; }}
  code {{ font-size:11px; color:#475569; }}
  .drawer {{ position:fixed; top:0; right:0; width:min(440px,92vw); height:100%; background:#fff;
             box-shadow:-12px 0 32px rgba(15,23,42,.18); transform:translateX(105%);
             transition:transform .18s; z-index:20; display:flex; flex-direction:column; }}
  .drawer.open {{ transform:translateX(0); }}
  .drawer-head {{ padding:16px 18px; border-bottom:1px solid var(--line); display:flex;
                  justify-content:space-between; align-items:center; }}
  .drawer-body {{ padding:16px 18px; overflow:auto; font-size:13px; line-height:1.6; }}
  .drawer-close {{ border:0; background:#f1f5f9; border-radius:8px; padding:6px 10px; cursor:pointer; }}
  .kv {{ margin:8px 0; }}
  .kv strong {{ display:inline-block; min-width:76px; color:var(--muted); }}
  .drawer h3 {{ font-size:14px; margin:16px 0 6px; }}
  .reopen {{ position:fixed; right:18px; bottom:18px; z-index:21; display:none;
             border:0; border-radius:999px; padding:10px 16px; background:var(--accent);
             color:#fff; cursor:pointer; box-shadow:0 6px 18px rgba(37,99,235,.35); }}
  .reopen.show {{ display:block; }}
  footer {{ padding:16px 28px 40px; color:var(--muted); font-size:12px; max-width:1500px; margin:0 auto; }}
</style>
</head>
<body>
<header>
  <h1>证据链总览 <span class="badge {status_cls}">{_esc(status)}</span></h1>
  <div class="meta">项目 {_esc(project_name)} · schema {_esc(chain.get("schema"))} v{_esc(chain.get("schema_version", ""))}
    · 生成 {_esc(generated)} · 真源 {_esc(chain.get("source"))}</div>
</header>
<main>
  <div class="kpis">{kpi_cards}</div>

  <div class="charts">
    <div class="card"><h2>证据覆盖率（按链路环节）</h2>{coverage_svg}</div>
    <div class="card"><h2>门禁通过率</h2>{donut_svg}</div>
    <div class="card"><h2>需求证据分级</h2>{dist_svg}</div>
    <div class="card"><h2>缺口分布</h2>{gap_svg}</div>
  </div>

  <div class="tabs" role="tablist">
    <button class="active" data-view="trace">追溯链</button>
    <button data-view="artifacts">证据库 ({artifact_count})</button>
    <button data-view="closure">过程闭环</button>
  </div>

  <section id="view-trace" class="view active">
    <div class="toolbar">
      <input id="search" type="search" placeholder="搜索节点 ID / 标题 / 文件…">
      <span class="muted">点击节点打开详情抽屉；边表示 implement / verify / review。</span>
    </div>
    <div class="trace-wrap">
      <div class="trace-canvas" style="width:{width}px;height:{height}px;">
        {edge_svg}
        <div class="col-head" style="left:{X0}px;">需求 / 来源</div>
        <div class="col-head" style="left:{X0 + COL_GAP}px;">实现</div>
        <div class="col-head" style="left:{X0 + 2 * COL_GAP}px;">测试 / 验证</div>
        <div class="col-head" style="left:{X0 + 3 * COL_GAP}px;">评审</div>
        {cards}
      </div>
    </div>
  </section>

  <section id="view-artifacts" class="view">
    <div class="card">
      <h2>证据库 — 产物、哈希与自动关联</h2>
      <table>
        <thead><tr><th>产物（点击打开）</th><th>类型</th><th>字节</th><th>SHA256</th><th>关联节点</th></tr></thead>
        <tbody>{artifact_rows}</tbody>
      </table>
    </div>
  </section>

  <section id="view-closure" class="view">
    <div class="card" style="margin-bottom:12px;">
      <h2>过程门禁（fail-closed）</h2>
      <table>
        <thead><tr><th>门禁</th><th>等级</th><th>状态</th><th>说明</th></tr></thead>
        <tbody>{gate_rows}</tbody>
      </table>
    </div>
    <div class="card" style="margin-bottom:12px;">
      <h2>问题清单</h2>
      <table>
        <thead><tr><th>级别</th><th>规则</th><th>消息</th><th>节点</th></tr></thead>
        <tbody>{problem_rows}</tbody>
      </table>
    </div>
    <div class="card">
      <h2>CI 结果</h2>
      <table>
        <thead><tr><th>Layer</th><th>状态</th><th>时间</th></tr></thead>
        <tbody>{ci_rows}</tbody>
      </table>
    </div>
  </section>
</main>

<aside class="drawer" id="drawer" aria-hidden="true">
  <div class="drawer-head">
    <strong id="drawer-title">节点详情</strong>
    <button class="drawer-close" id="drawer-close">关闭</button>
  </div>
  <div class="drawer-body" id="drawer-body"></div>
</aside>
<button class="reopen" id="reopen">重新打开详情</button>

<footer>
  本页面为离线单文件视图，数据来源 <code>chain.json</code>。
  证据结论以 <code>chain.json</code> 与真源产物为准；HTML 不得作为通过依据。
</footer>

<script id="chain-data" type="application/json">{data_json}</script>
<script>
(function () {{
  var DATA = JSON.parse(document.getElementById('chain-data').textContent);
  var nodes = {{}}, edges = DATA.edges || [], artifacts = {{}}, gates = {{}};
  (DATA.nodes || []).forEach(function (n) {{ nodes[n.id] = n; }});
  (DATA.artifacts || []).forEach(function (a) {{ artifacts[a.id] = a; }});
  (DATA.gates || []).forEach(function (g) {{ gates[g.id] = g; }});

  function esc(s) {{
    return String(s === undefined || s === null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }}

  var drawer = document.getElementById('drawer');
  var reopen = document.getElementById('reopen');
  var drawerTitle = document.getElementById('drawer-title');
  var drawerBody = document.getElementById('drawer-body');

  function showView(name) {{
    document.querySelectorAll('.view').forEach(function (v) {{
      v.classList.toggle('active', v.id === 'view-' + name);
    }});
    document.querySelectorAll('.tabs button').forEach(function (b) {{
      b.classList.toggle('active', b.getAttribute('data-view') === name);
    }});
  }}

  function linkFor(id) {{
    return '<a class="chip" href="#/node/' + encodeURIComponent(id) + '">' + esc(id) + '</a>';
  }}

  function openNode(id) {{
    var node = nodes[id];
    if (!node) {{ return false; }}
    drawerTitle.textContent = node.type + ' · ' + node.id;
    var incoming = edges.filter(function (e) {{ return e.to === id; }});
    var outgoing = edges.filter(function (e) {{ return e.from === id; }});
    var html = '<div class="kv"><strong>状态</strong>' + esc(node.status) + '</div>'
      + '<div class="kv"><strong>标题</strong>' + esc(node.title) + '</div>';
    if (node.refs && node.refs.length) {{
      html += '<div class="kv"><strong>关联</strong>' + node.refs.map(esc).join(' · ') + '</div>';
    }}
    if (node.has_code !== undefined) {{
      html += '<div class="kv"><strong>覆盖</strong>code=' + esc(node.has_code)
        + ' · test=' + esc(node.has_test) + ' · review=' + esc(node.has_review) + '</div>';
    }}
    html += '<h3>出边 (' + outgoing.length + ')</h3>';
    html += outgoing.length ? outgoing.map(function (e) {{
      return '<div>' + esc(e.kind) + ' → ' + linkFor(e.to) + '</div>';
    }}).join('') : '<div class="muted">无</div>';
    html += '<h3>入边 (' + incoming.length + ')</h3>';
    html += incoming.length ? incoming.map(function (e) {{
      return '<div>' + linkFor(e.from) + ' → ' + esc(e.kind) + '</div>';
    }}).join('') : '<div class="muted">无</div>';
    drawerBody.innerHTML = html;
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    reopen.classList.add('show');
    return true;
  }}

  function openArtifact(id) {{
    var art = artifacts[id];
    if (!art) {{ return false; }}
    showView('artifacts');
    document.querySelectorAll('[data-artifact-id]').forEach(function (row) {{
      row.style.background = row.getAttribute('data-artifact-id') === id ? '#fef9c3' : '';
      if (row.getAttribute('data-artifact-id') === id) {{ row.scrollIntoView({{block:'center'}}); }}
    }});
    return true;
  }}

  function openGate(id) {{
    showView('closure');
    var row = document.querySelector('[data-gate-id="' + (window.CSS && CSS.escape ? CSS.escape(id) : id) + '"]');
    if (row) {{ row.style.background = '#fef9c3'; row.scrollIntoView({{block:'center'}}); }}
    var gate = gates[id];
    if (gate) {{
      drawerTitle.textContent = '门禁 · ' + id;
      drawerBody.innerHTML = '<div class="kv"><strong>等级</strong>' + esc(gate.severity) + '</div>'
        + '<div class="kv"><strong>状态</strong>' + esc(gate.status) + '</div>'
        + '<div class="kv"><strong>说明</strong>' + esc(gate.detail) + '</div>';
      drawer.classList.add('open');
      reopen.classList.add('show');
    }}
    return true;
  }}

  function closeDrawer() {{
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
  }}

  function route() {{
    var hash;
    try {{ hash = decodeURIComponent(location.hash || ''); }} catch (err) {{ return; }}
    var m = hash.match(/^#\\/(node|artifact|gate|view)\\/(.+)$/);
    if (!m) {{ return; }}
    if (m[1] === 'node') {{ showView('trace'); openNode(m[2]); }}
    else if (m[1] === 'artifact') {{ openArtifact(m[2]); }}
    else if (m[1] === 'gate') {{ openGate(m[2]); }}
    else if (m[1] === 'view') {{ showView(m[2]); }}
  }}

  document.addEventListener('click', function (ev) {{
    var nodeEl = ev.target.closest('.node');
    if (nodeEl) {{
      var id = nodeEl.getAttribute('data-node-id');
      location.hash = '#/node/' + encodeURIComponent(id);
      openNode(id);
      return;
    }}
    if (ev.target.id === 'drawer-close') {{ closeDrawer(); return; }}
    if (ev.target.id === 'reopen') {{ drawer.classList.add('open'); return; }}
    var chip = ev.target.closest('a.chip');
    if (chip && chip.getAttribute('href').indexOf('#/node/') === 0) {{
      ev.preventDefault();
      var target = decodeURIComponent(chip.getAttribute('href').slice(7));
      location.hash = '#/node/' + encodeURIComponent(target);
      showView('trace'); openNode(target);
    }}
    var tab = ev.target.closest('.tabs button');
    if (tab) {{
      var name = tab.getAttribute('data-view');
      location.hash = '#/view/' + name;
      showView(name);
    }}
  }});

  document.addEventListener('keydown', function (ev) {{
    if (ev.key === 'Escape') {{ closeDrawer(); }}
  }});

  var search = document.getElementById('search');
  if (search) {{
    search.addEventListener('input', function () {{
      var q = search.value.trim().toLowerCase();
      document.querySelectorAll('.node').forEach(function (el) {{
        var hit = !q || (el.getAttribute('data-search') || '').indexOf(q) >= 0;
        el.classList.toggle('dim', !hit);
      }});
    }});
  }}

  window.addEventListener('hashchange', route);
  route();
}})();
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════


def cmd_evidence_chain(
    project_dir: str,
    evidence_dir: Optional[str] = None,
    check_only: bool = False,
    render: bool = True,
    as_json: bool = False,
) -> int:
    """CLI entry: collect, validate, persist, optionally render HTML.

    Returns process exit code (0=PASS, 1=FAIL) so pipelines can gate on it.
    """
    chain = collect_chain(project_dir, evidence_dir=evidence_dir)
    written = write_chain(chain, evidence_dir=evidence_dir, render=render and not check_only)
    summary = chain.get("summary") or {}

    if as_json:
        print(json.dumps(chain, indent=2, ensure_ascii=False, default=str))
    else:
        print("Evidence Chain")
        print("=" * 60)
        print(f"  project : {project_dir}")
        print(f"  status  : {summary.get('status')}")
        print(f"  nodes   : {summary.get('nodes')} | edges: {summary.get('edges')} "
              f"| artifacts: {summary.get('artifacts')}")
        print(f"  coverage: code {summary.get('code_coverage_pct')}% "
              f"| test {summary.get('test_coverage_pct')}%")
        print(f"  gates   : {summary.get('gates_pass')} pass / {summary.get('gates_fail')} fail")
        print(f"  json    : {written['json']}")
        if written.get("html"):
            print(f"  html    : {written['html']}")
        for problem in chain.get("problems") or []:
            print(f"  [{problem.get('severity')}] {problem.get('code')}: {problem.get('message')}")
    return 0 if summary.get("status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover - manual CLI use
    import argparse

    parser = argparse.ArgumentParser(description="Generate/validate yuleOSH evidence chain")
    parser.add_argument("--project-dir", default=os.getcwd())
    parser.add_argument("--evidence-dir", default=None)
    parser.add_argument("--check", action="store_true", help="validate only (no HTML)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    raise SystemExit(cmd_evidence_chain(
        args.project_dir, args.evidence_dir, check_only=args.check, as_json=args.json,
    ))
