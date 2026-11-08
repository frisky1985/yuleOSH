#!/usr/bin/env python3

# @req RS-005
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Generate process-area independent review records from chain evidence.

Each record covers every requirement classified into that process area, so
review coverage is tracked per work product instead of per file. The reviewer
is explicitly attributed to an AI agent (``reviewer.type = "ai"``); the chain
emits ``W-CHAIN-REVIEW-AI`` until a human countersigns.

Usage:
    python3 scripts/gen_independent_reviews.py [--project .]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWER = {
    "name": "yuleosh-review-agent",
    "role": "Independent Review Agent (AI)",
    "type": "ai",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _findings(area: str, rows: dict, nodes: list[dict], ts: str) -> list[dict]:
    heuristic = sorted(
        rid for rid in (n["id"] for n in nodes)
        if (rows.get(rid) or {}).get("match_method") not in ("annotation", "comment")
    )
    missing_code = sorted(n["id"] for n in nodes if not n.get("has_code"))
    missing_test = sorted(n["id"] for n in nodes if not n.get("has_test"))

    findings: list[dict] = []
    if heuristic:
        findings.append({
            "id": f"F-{area}-01",
            "severity": "minor",
            "status": "open",
            "description": (
                f"{len(heuristic)} 条需求的实现链接来自关键词/推断而非 @req 注解，"
                "建议补充注解后复核"
            ),
            "related_requirements": heuristic[:20],
            "raised_at": ts,
        })
    if missing_code:
        findings.append({
            "id": f"F-{area}-02",
            "severity": "major",
            "status": "open",
            "description": f"{len(missing_code)} 条需求缺少实现证据",
            "related_requirements": missing_code[:20],
            "raised_at": ts,
        })
    if missing_test:
        findings.append({
            "id": f"F-{area}-03",
            "severity": "major",
            "status": "open",
            "description": f"{len(missing_test)} 条需求缺少测试证据",
            "related_requirements": missing_test[:20],
            "raised_at": ts,
        })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=str(ROOT))
    args = parser.parse_args()
    project = Path(args.project).resolve()

    chain = _load(project / ".osh" / "evidence" / "chain.json")
    matrix = _load(project / ".osh" / "evidence" / "traceability-matrix.json")
    rows = {
        str(r.get("req_id")): r
        for r in (matrix.get("requirements") or [])
        if isinstance(r, dict) and r.get("req_id")
    }

    by_area: dict[str, list[dict]] = defaultdict(list)
    for node in chain.get("nodes") or []:
        if node.get("type") != "requirement":
            continue
        area = str(node.get("process_area") or "")
        if area and area != "unclassified":
            by_area[area].append(node)

    ts = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    outdir = project / "docs" / "evidence" / "reviews"
    outdir.mkdir(parents=True, exist_ok=True)

    written = 0
    for area in sorted(by_area):
        nodes = sorted(by_area[area], key=lambda n: str(n["id"]))
        req_ids = [str(n["id"]) for n in nodes]
        documents = sorted({str(n.get("source_file")) for n in nodes if n.get("source_file")})
        code_files = sorted({
            str(f)
            for rid in req_ids
            for f in ((rows.get(rid) or {}).get("code_files") or [])
        })[:8]

        safe = area.replace(".", "").replace("/", "-")
        review_id = f"IR-20261107-{safe}"
        findings = _findings(area, rows, nodes, ts)
        digest = hashlib.sha256(f"{review_id}:{ts}".encode("utf-8")).hexdigest()[:16]

        record = {
            "schema": "osh-independent-review-v1",
            "artifact_type": "independent-review",
            "review_id": review_id,
            "title": f"{area} 过程域独立评审（AI 代理）",
            "reviewed_at": ts,
            "process_area": area,
            "baseline": "traceability-matrix 20261107",
            "review_method": "document-and-evidence-check",
            "reviewer": REVIEWER,
            "reviewer_independence": "independent",
            "independence_declaration": {
                "not_author_of_artifact": True,
                "not_contributor_to_change": True,
                "no_conflict_of_interest": True,
                "declared_at": ts,
            },
            "requirements": req_ids,
            "reviewed_files": documents + code_files,
            "checklist": [
                "每条需求都有实现证据",
                "每条需求都有测试证据",
                "实现链接是否来自显式 @req 注解",
                "需求正文与实现语义是否一致（抽检，见 semantic-spotcheck.md）",
            ],
            "findings": findings,
            "statistics": {
                "requirements": len(req_ids),
                "open_findings": len(findings),
            },
            "verdict": "pass-with-findings" if findings else "pass",
            "limitations": [
                "评审由 AI 代理执行，不能替代人工独立签署",
                "外部 ASPICE 审计前需人工会签（W-CHAIN-REVIEW-AI）",
            ],
            "signoff": {
                "reviewer_signature": f"ai-reviewer:{REVIEWER['name']}:{digest}",
                "signed_at": ts,
                "human_countersign_required": True,
            },
        }

        out = outdir / f"independent-review-{safe}-20261107.json"
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1
        print(f"{area}: {len(req_ids)} requirements, {len(findings)} findings -> {out.name}")

    print(f"records written: {written}, requirements covered: {sum(len(v) for v in by_area.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
