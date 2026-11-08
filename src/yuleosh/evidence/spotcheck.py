#!/usr/bin/env python3

# @req RS-005
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Semantic spot-check sampling for traceability links.

Coverage numbers say a link exists; they say nothing about whether the link is
semantically right. This module picks a deterministic, reproducible sample of
requirement → implementation pairs so a human reviewer can confirm that the
``@req`` annotation points at code that actually implements the statement.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

DEFAULT_COUNT = 20
_ANNOTATION_RE = re.compile(
    r"@req\s*[\(\s]\s*([A-Za-z][A-Za-z0-9_.\-]+(?:\s*,\s*[A-Za-z][A-Za-z0-9_.\-]+)*)",
    re.IGNORECASE,
)


def load_requirements(matrix_path: str | Path) -> list[dict]:
    """Read requirement rows from the authoritative traceability matrix."""
    payload = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    return [
        row for row in (payload.get("requirements") or [])
        if isinstance(row, dict) and row.get("req_id")
    ]


def sample_requirements(rows: list[dict], count: int = DEFAULT_COUNT) -> list[dict]:
    """Deterministically sample rows by hashing the requirement ID.

    The same matrix always yields the same sample, so review evidence can be
    reproduced by a third party without storing the random seed.
    """
    if count <= 0:
        return []
    ranked = sorted(
        rows,
        key=lambda row: hashlib.sha256(str(row["req_id"]).encode("utf-8")).hexdigest(),
    )
    return ranked[:count]


def _annotated_ids(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    ids: list[str] = []
    for match in _ANNOTATION_RE.finditer(text):
        for rid in match.group(1).split(","):
            rid = rid.strip().upper()
            if rid and rid not in ids:
                ids.append(rid)
    return ids


def render_checklist(
    rows: list[dict],
    project_dir: str | Path,
    count: int = DEFAULT_COUNT,
) -> str:
    """Render a markdown spot-check sheet for a deterministic sample."""
    project = Path(project_dir)
    sample = sample_requirements(rows, count)

    lines = [
        "# 语义抽检清单（注解 ↔ 需求正文）",
        "",
        f"> 自动生成：按 `sha256(req_id)` 排序取前 {len(sample)} 条，样本可复现。",
        "> 抽检目的：覆盖率只能证明链接存在，不能证明链接正确。",
        "> 逐条核对：代码文件中的 `@req` 是否指向该需求，实现内容是否与需求正文一致。",
        "",
        "| # | 需求 ID | 需求正文（截断） | 关联实现文件 | 注解核对 | 语义匹配 | 备注 |",
        "|--:|:--------|:----------------|:-------------|:--------|:--------|:-----|",
    ]

    for idx, row in enumerate(sample, start=1):
        rid = str(row.get("req_id"))
        statement = " ".join(str(row.get("statement") or "").split())[:80]
        files = [str(f) for f in (row.get("code_files") or [])][:2]
        checks = []
        for rel in files:
            ids = _annotated_ids(project / rel)
            mark = "✓" if rid.upper() in ids else "—"
            checks.append(f"`{rel}` {mark}")
        files_cell = "<br>".join(checks) if checks else "_(无实现文件)_"
        lines.append(
            f"| {idx} | {rid} | {statement} | {files_cell} "
            "| [ ] 一致<br>[ ] 不一致 | [ ] 匹配<br>[ ] 不匹配 |  |"
        )

    lines += [
        "",
        "## 处置约定",
        "",
        "- **注解核对不一致**：代码缺少或错标 `@req` → 记为评审发现，修正注解。",
        "- **语义不匹配**：实现与需求正文不符 → 记为评审发现，回到需求或代码修复。",
        "- 抽检结果写入独立评审记录的 `findings`，不要直接修改本清单。",
        "",
    ]
    return "\n".join(lines)
