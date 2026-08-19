#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Merged-step runner helpers — 合并 handler 公共逻辑 (2026-08-19 八轮决策)。

合并 handler 模式（checkpoint v9）: 内部顺序调用旧 handler（保留各自专属
prompt/检查深度/超时），收集子报告 status 合并，输出合并 JSON 到
session.session_dir。旧 handler 文件保留不删，PIPELINE_STEPS 只引用新
handler。

合并语义:
  - 任一子报告 status == failed → merged failed
  - 任一子报告 status == retry → merged retry（failed 优先）
  - 全部 skipped → merged skipped
  - 否则 → merged passed
  - warning 视为非阻断（记录 warning 列表，不进 status）

异常语义: 子 handler 抛 PipelineStepError（如 codex-verify 缺陷阻断 /
qemu 失败 / coverage gate 阻断）→ 合并 handler 记录该 section 为 failed
并 **re-raise**（保留原阻断语义：orchestrator 捕获后 fail_step + break）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError

log = logging.getLogger("pipeline.step_handlers.merged_step")

__all__ = [
    "merge_statuses",
    "read_sub_status",
    "run_substeps",
    "write_merged_report",
]


def read_sub_status(report_path: str | Path | None) -> str:
    """Read a sub-handler report's status.

    JSON reports carry a ``status`` field (skipped/passed/failed/retry/warning).
    Markdown self-test reports carry ``- **Failed**: N`` — derive failed/passed.
    Missing/unreadable reports default to ``"unknown"`` (treated as warn).
    """
    if not report_path:
        return "unknown"
    p = Path(str(report_path))
    if not p.exists():
        return "unknown"
    try:
        if p.suffix.lower() == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                st = str(data.get("status", "")).strip().lower()
                if st:
                    return st
                # JSON 报告没有 status 字段时用语义字段兜底
                if data.get("gate_passed") is True:
                    return "passed"
                if data.get("gate_passed") is False and data.get("skipped"):
                    return "skipped"
                if data.get("all_passed") is True:
                    return "passed"
                if data.get("all_passed") is False:
                    return "failed"
            return "unknown"
        # Markdown self-test report
        text = p.read_text(encoding="utf-8", errors="ignore")
        m = __import__("re").search(r"-\s*\*\*Failed\*\*:\s*(\d+)", text)
        if m:
            return "failed" if int(m.group(1)) > 0 else "passed"
        if "- **Status**:" in text:
            return "passed" if "✅" in text or "PASS" in text.upper() else "failed"
    except Exception as e:  # pragma: no cover - defensive  # noqa: BLE001
        log.warning("read_sub_status failed for %s: %s", report_path, e)
    return "unknown"


def merge_statuses(statuses: list[str]) -> str:
    """Merge sub-report statuses: failed > retry > skipped > passed."""
    normalized = [s.strip().lower() for s in statuses if s]
    if not normalized:
        return "skipped"
    if any(s in ("failed", "incomplete") for s in normalized):
        return "failed"
    if any(s == "retry" for s in normalized):
        return "retry"
    if any(s == "warning" for s in normalized):
        return "warning"
    if all(s == "skipped" for s in normalized):
        return "skipped"
    return "passed"


def run_substeps(
    session: PipelineSession,
    step_key: str,
    substeps: list[tuple[str, Callable[[PipelineSession], str]]],
    summary_prefix: str = "",
) -> tuple[dict, str]:
    """Run sub-handlers sequentially, merge statuses, write merged JSON.

    Parameters
    ----------
    session : PipelineSession
        Active pipeline session.
    step_key : str
        Merged step key (report file name base).
    substeps : list[(name, handler_fn)]
        Sub-handlers to call in order. Each returns a report path.
    summary_prefix : str
        Optional prefix for the merged summary line.

    Returns
    -------
    (report, out_path)
        The merged report dict and the written JSON path.
    """
    sections: list[dict] = []
    statuses: list[str] = []
    first_error: PipelineStepError | None = None

    for name, fn in substeps:
        section: dict = {"name": name}
        try:
            path = fn(session)
            section["report"] = str(path)
            section["status"] = read_sub_status(path)
            statuses.append(section["status"])
            log.info("[%s] sub-step %s -> %s (%s)", step_key, name, path,
                     section["status"])
        except PipelineStepError as e:
            section["status"] = "failed"
            section["error"] = str(e)
            statuses.append("failed")
            if first_error is None:
                first_error = e
            log.error("[%s] sub-step %s failed: %s", step_key, name, e)
        except Exception as e:  # pragma: no cover - defensive  # noqa: BLE001
            section["status"] = "failed"
            section["error"] = f"unexpected error: {e}"
            statuses.append("failed")
            if first_error is None:
                first_error = PipelineStepError(f"[{step_key}] {name}: {e}")
            log.exception("[%s] sub-step %s crashed", step_key, name)

        sections.append(section)

    merged = merge_statuses(statuses)
    section_summary = ", ".join(
        f"{s.get('name', '?')}={s.get('status', '?')}" for s in sections
    )
    report = {
        "step": step_key,
        "session": getattr(session, "name", ""),
        "timestamp": datetime.now(UTC).isoformat(),
        "status": merged,
        "merged": True,
        "sections": sections,
        "summary": (
            f"{summary_prefix}合并审查完成 — status={merged} ({section_summary})"
        ),
    }
    out_path = write_merged_report(session, step_key, report)

    if first_error is not None:
        raise first_error

    return report, out_path


def write_merged_report(session: PipelineSession, step_key: str,
                        report: dict) -> str:
    """Write the merged step report JSON into the session dir."""
    out_path = Path(session.session_dir) / f"{step_key}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return str(out_path)