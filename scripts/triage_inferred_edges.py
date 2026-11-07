#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""分诊证据链中的推断追溯边，并生成补齐注解的工作清单。

``inferred``（关键词推断）边默认是 ``proposed``，不计入 ASPICE 覆盖；如果长期
不处理，会持续触发 ``W-CHAIN-LINK-UNAPPROVED``，把真正的告警淹没在噪声里。

本脚本把每条推断边逐条写入 ``docs/evidence/trace-decisions/`` 决策账本：

* 需求已有 ``exact`` 实现边 → ``superseded_by_exact_link``（冗余噪声）
* SYS.1 / SYS.3 / SWE.2 / SWE.3 等文档级需求 → ``non_code_requirement``
* 其余（通常是 SWE.1 代码需求缺 ``@req``）→ ``no_requirement_annotation``

账本只追加不覆盖：已有人工决策保持不变。代码级缺口同时写入
``docs/evidence/pending-reviews/annotation-worklist.md``，指导补注解。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

SCHEMA = "osh-trace-decisions-v1"
NON_CODE_AREAS = {"SYS.1", "SYS.3", "SWE.2", "SWE.3"}
DEFAULT_LEDGER = "docs/evidence/trace-decisions/inferred-implement.json"
DEFAULT_WORKLIST = "docs/evidence/pending-reviews/annotation-worklist.md"

REASONS = {
    "superseded_by_exact_link": "该需求已有 exact 实现边，关键词推断命中为冗余噪声",
    "non_code_requirement": "文档级需求由设计/架构产物满足，代码文件不是其实现证据",
    "no_requirement_annotation": "需求缺少 @req 注解；补齐前关键词推断边不得计入覆盖",
    "inferred_link_not_confirmed": "推断链接未经确认，默认拒绝",
}


def _rel(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def _load_existing(path: Path) -> dict[tuple[str, str, str], dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    decisions = data.get("decisions") if isinstance(data, dict) else None
    if not isinstance(decisions, list):
        return {}
    existing: dict[tuple[str, str, str], dict] = {}
    for entry in decisions:
        if not isinstance(entry, dict):
            continue
        key = (
            str(entry.get("from") or ""),
            str(entry.get("to") or ""),
            str(entry.get("kind") or ""),
        )
        if all(key):
            existing[key] = entry
    return existing


def _reason_for(edge: dict, req_node: dict, has_exact: bool) -> str:
    if edge.get("kind") != "implement":
        return "inferred_link_not_confirmed"
    if has_exact:
        return "superseded_by_exact_link"
    if str(req_node.get("process_area") or "") in NON_CODE_AREAS:
        return "non_code_requirement"
    return "no_requirement_annotation"


def _write_worklist(
    path: Path,
    missing: list[dict],
    non_code: list[dict],
    ledger_rel: str,
    chain_rel: str,
) -> None:
    lines = [
        "# 需求注解补齐工作清单",
        "",
        f"> 由 `scripts/triage_inferred_edges.py` 生成；推断边决策账本：`{ledger_rel}`。",
        f"> 真源：`{chain_rel}`。规则：只有实现/验证需求相关的代码才需要 `@req`，纯辅助代码不要求注解。",
        "",
        "## 代码级需求（需补 `@req`）",
        "",
    ]
    if not missing:
        lines.append("无缺口：所有代码级需求都已有 exact 实现边。")
    else:
        lines.append(
            f"共 {len(missing)} 条代码级需求只有关键词推断边，补齐注解后其实现边会转为 `exact` 并计入覆盖。"
        )
        lines.append("")
        by_area: dict[str, list[dict]] = defaultdict(list)
        for item in missing:
            by_area[str(item["area"] or "UNCLASSIFIED")].append(item)
        for area in sorted(by_area):
            lines.append(f"### {area}（{len(by_area[area])} 条）")
            lines.append("")
            for item in by_area[area]:
                title = str(item["title"] or "").strip().replace("\n", " ")
                lines.append(f"- [ ] **{item['req_id']}** — {title[:120]}")
                if item["files"]:
                    lines.append("  - 候选实现文件（关键词推断，仅供定位）：")
                    for file_path in item["files"]:
                        lines.append(f"    - `{file_path}`")
                lines.append(
                    f"  - 操作：确认实现该需求后，在文件顶部加 `# @req {item['req_id']}`"
                    "（JS/TS 用 `// @req`）。"
                )
            lines.append("")
    lines.extend([
        "## 文档级需求（不要求代码注解）",
        "",
        "以下过程域的需求由设计/架构文档满足，关键词命中的代码文件被判定为无效实现证据：",
        "",
        "| 过程域 | 需求数 |",
        "| --- | ---: |",
    ])
    area_counts = Counter(str(item["area"] or "UNCLASSIFIED") for item in non_code)
    for area in sorted(area_counts):
        lines.append(f"| {area} | {area_counts[area]} |")
    lines.extend([
        "",
        "## 收尾验证",
        "",
        "1. 补注解后重建矩阵与证据链：",
        "   `PYTHONPATH=src python3 -m yuleosh.cli.main evidence chain --check`",
        "2. 重新运行本脚本：已转为 exact 的需求会自动从本清单消失。",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".", help="项目根目录（默认当前目录）")
    parser.add_argument("--chain", default=None, help="chain.json 路径")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER, help="决策账本输出路径")
    parser.add_argument("--worklist", default=DEFAULT_WORKLIST, help="注解工作清单输出路径")
    args = parser.parse_args()

    project = Path(args.project).resolve()
    chain_path = Path(args.chain) if args.chain else project / ".osh" / "evidence" / "chain.json"
    if not chain_path.is_absolute():
        chain_path = project / chain_path
    if not chain_path.exists():
        print(f"chain.json 不存在：{chain_path}（先运行 evidence chain）")
        return 1
    chain = json.loads(chain_path.read_text(encoding="utf-8"))
    edges = [e for e in (chain.get("edges") or []) if isinstance(e, dict)]
    nodes = {str(n.get("id")): n for n in (chain.get("nodes") or []) if isinstance(n, dict)}

    accepted_impl = {
        str(e.get("from")) for e in edges
        if e.get("kind") == "implement" and e.get("status") == "accepted"
    }
    proposed = [e for e in edges if e.get("status") == "proposed"]
    proposed.sort(key=lambda e: (str(e.get("from")), str(e.get("to")), str(e.get("kind"))))

    ledger_path = Path(args.ledger)
    if not ledger_path.is_absolute():
        ledger_path = project / ledger_path
    existing = _load_existing(ledger_path)

    now = datetime.now().isoformat(timespec="seconds")
    # Append-only: existing decisions stay authoritative, even if the edge is no
    # longer `proposed` (e.g. it later became `exact`).
    decisions: dict[tuple[str, str, str], dict] = dict(existing)
    added = 0
    reason_counts: Counter[str] = Counter(
        str(entry.get("reason") or "") for entry in existing.values()
    )

    for edge in proposed:
        src, dst, kind = str(edge.get("from")), str(edge.get("to")), str(edge.get("kind"))
        key = (src, dst, kind)
        if key in decisions:
            continue
        req_node = nodes.get(src) or {}
        reason = _reason_for(edge, req_node, src in accepted_impl)
        decisions[key] = {
            "from": src,
            "to": dst,
            "kind": kind,
            "confidence": str(edge.get("confidence") or ""),
            "decision": "rejected",
            "reason": reason,
            "note": REASONS.get(reason, ""),
            "decided_by": "triage-inferred-edges",
            "decided_at": now,
        }
        added += 1
        reason_counts[reason] += 1

    # The worklist is derived from the ledger, not from the current edge status,
    # so it survives after decisions are applied and shows only unresolved gaps.
    missing_map: dict[str, dict] = {}
    non_code_map: dict[str, dict] = {}
    for (src, dst, kind), entry in decisions.items():
        if kind != "implement" or entry.get("decision") != "rejected":
            continue
        if src not in nodes:
            continue
        reason = str(entry.get("reason") or "")
        if reason == "non_code_requirement":
            non_code_map.setdefault(src, {
                "req_id": src,
                "title": str(nodes[src].get("title") or ""),
                "area": str(nodes[src].get("process_area") or ""),
            })
        elif reason == "no_requirement_annotation" and src not in accepted_impl:
            item = missing_map.setdefault(src, {
                "req_id": src,
                "title": str(nodes[src].get("title") or ""),
                "area": str(nodes[src].get("process_area") or ""),
                "files": [],
            })
            file_path = dst.split(":", 1)[-1]
            if file_path not in item["files"] and len(item["files"]) < 10:
                item["files"].append(file_path)

    decision_rows = [decisions[key] for key in sorted(decisions)]
    missing = sorted(missing_map.values(), key=lambda m: (str(m["area"]), str(m["req_id"])))
    non_code = sorted(non_code_map.values(), key=lambda m: (str(m["area"]), str(m["req_id"])))

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA,
        "generated_at": now,
        "source_chain": _rel(chain_path, project),
        "policy": (
            "rejected 边保留在 chain.json 供审计，但不计入 ASPICE 覆盖；"
            "补齐 @req 注解后 exact 边自动恢复为 accepted，旧决策不会降级 exact 边。"
        ),
        "summary": {
            "decisions": len(decision_rows),
            "added": added,
            "preserved": len(existing),
            "reasons": dict(sorted(reason_counts.items())),
            "code_requirements_missing_annotation": len(missing),
            "non_code_requirements": len(non_code),
        },
        "decisions": decision_rows,
    }
    ledger_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    worklist_path = Path(args.worklist)
    if not worklist_path.is_absolute():
        worklist_path = project / worklist_path
    _write_worklist(
        worklist_path, missing, non_code,
        _rel(ledger_path, project), _rel(chain_path, project),
    )

    print(
        f"决策账本：{ledger_path}（新增 {added}，保留 {len(existing)}，共 {len(decision_rows)} 条）"
    )
    print(
        f"工作清单：{worklist_path}"
        f"（代码级缺口 {len(missing)} 条，文档级需求 {len(non_code)} 条）"
    )
    for reason, count in sorted(reason_counts.items()):
        print(f"  - {reason}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
