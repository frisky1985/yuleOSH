#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Session retention — 会话目录的分层保留（2026-09-23）。

为什么需要
----------
``.osh/sessions`` 此前没有任何 retention 逻辑，历史全靠人工清。实测（2026-09-23）：

* 单次 24 步真实 run 只写 51 个文件 / 89 KB —— **字节维度十年内都不构成风险**；
* 真正的代价是**目录数**：曾累积 3611 个残留目录（99.6% 来自测试泄漏），
  而 ``api/artifacts.py`` 的 ``_sessions_roots()`` 每次请求都要遍历这些目录。

分层判据是「可再生性」，不是体积
--------------------------------
===========  ============================================  ==================
层           内容                                          处置
===========  ============================================  ==================
T0           运行态：空目录 / created 中止                  整体回收
T1           汇总层：``session.json`` / ``gate-summary.json``  永久
T2           LLM 产物：prd / architecture / final-report       永久（不可再生）
T3           确定性证据：``VOLATILE_STEPS`` 的产物            只留最近 ``keep_last`` 次
T4           调试原文（prompt / response）                  不落库（本模块不管）
===========  ============================================  ==================

T2 必须永久：本地 4B 模型跑一轮 1.5–2 小时，丢了不可复现。
T3 可以删：重跑是分钟级，且这些证据本来就每轮重算（见 ``step_cache``）。

用法
----
::

    prune_sessions(project_dir, keep_last=3, dry_run=True)   # 只出方案
    prune_sessions(project_dir, keep_last=3, dry_run=False)  # 真删

默认 ``dry_run=True`` —— 与 ``purge_step_cache`` 的默认相反。两者差别在于：
缓存删错了可以重算，而这里删掉的是历史目录结构，误删代价更高。
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from yuleosh.pipeline.gates import _artifact_paths
from yuleosh.pipeline.session import resolve_sessions_root
from yuleosh.pipeline.step_cache import VOLATILE_STEPS

log = logging.getLogger("pipeline.session_prune")

#: 状态表明「从未真正跑起来」→ T0，整体回收。
_ABORTED_STATUSES = frozenset({"created", "pending", "aborted"})

#: T1 汇总层 —— 任何情况下都不删（也是判断 run 是否存在的锚点）。
_ALWAYS_KEEP = frozenset({"session.json", "gate-summary.json"})

#: 属于 ``VOLATILE_STEPS``、但既不叫 ``<step_key>.json`` 又不在
#: ``gates._ARTIFACT_CANDIDATES`` 里的证据文件。
#:
#: 这是对 ``gates._artifact_paths`` 的**补集**，不是第二份完整清单 ——
#: 主体仍由映射产生，这里只补它漏掉的。
#:
#: 顺带记录一个未修的缺陷（不在本次改动范围）：``gates._ARTIFACT_CANDIDATES``
#: 漏了 ``qualification-test.json``（G10 步骤的实际产物名）与
#: ``c-coverage-gate.json``，导致对应门禁读不到产物里的真实 verdict、
#: 只能退回 ``session.steps`` 的状态。
_EXTRA_DETERMINISTIC_EVIDENCE = (
    "ctest-junit.xml",           # integration-test 的 ctest JUnit 报告
    "qualification-test.json",   # test-qualification 的实际产物名
    "c-coverage-gate.json",      # qemu-verify（合并了 c-coverage-gate）的产物
)


# ---------------------------------------------------------------------------
# 读取与判定
# ---------------------------------------------------------------------------

def _parse_ts(value: object) -> float:
    """ISO 时间串 → epoch 秒；缺失或解析失败返回 0.0。"""
    if not isinstance(value, str) or not value.strip():
        return 0.0
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def _read_meta(sdir: Path) -> dict:
    """读 session.json；缺失或损坏返回 {}（不抛）。"""
    try:
        meta = json.loads((sdir / "session.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 损坏的元数据不该阻断清理
        return {}
    return meta if isinstance(meta, dict) else {}


def _session_timestamp(sdir: Path, meta: dict) -> float:
    """run 的时间锚点：created_at → updated_at → 目录 mtime。"""
    for key in ("created_at", "updated_at"):
        ts = _parse_ts(meta.get(key))
        if ts:
            return ts
    try:
        return sdir.stat().st_mtime
    except OSError:
        return 0.0


def _is_aborted(sdir: Path, meta: dict) -> bool:
    """T0 判定：空目录，或状态表明从未跑起来。"""
    try:
        empty = not any(sdir.iterdir())
    except OSError:
        return False
    if empty:
        return True
    if not meta:
        return False
    return str(meta.get("status", "")).strip().lower() in _ABORTED_STATUSES


def deterministic_evidence_files(sdir: Path) -> list[Path]:
    """T3 层文件：``VOLATILE_STEPS`` 的产物（可分钟级重跑再生）。

    复用 ``gates._artifact_paths`` —— 它是「步骤 → 产物文件」的唯一映射
    （含 ``critical-safety-report.json`` / ``merge-gate-report.json`` 这类别名），
    避免在这里维护第二份清单而漂移。T1 汇总层永远排除在外。
    """
    files: list[Path] = []
    for step_key in sorted(VOLATILE_STEPS):
        files.extend(_artifact_paths(sdir, step_key))
    for name in _EXTRA_DETERMINISTIC_EVIDENCE:
        candidate = Path(sdir) / name
        if candidate.exists():
            files.append(candidate)
    # 去重 + 排除 T1 汇总层
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in files:
        if p.name in _ALWAYS_KEEP or p in seen:
            continue
        seen.add(p)
        unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# 方案计算（只读）
# ---------------------------------------------------------------------------

def plan_prune_root(root: Path, *, keep_last: int = 3) -> dict:
    """算出 sessions 根目录的保留方案；不修改磁盘。

    返回 ``{"root", "exists", "scanned", "aborted", "pruned",
    "kept_full", "files_removed", "bytes_freed", "dry_run"}``。

    ``dry_run`` 恒为 ``True`` —— 方案本身不含执行，只有 ``_apply`` 会改它。
    """
    root = Path(root)
    empty = {
        "root": str(root), "exists": False, "scanned": 0,
        "aborted": [], "pruned": {}, "kept_full": [],
        "files_removed": 0, "bytes_freed": 0, "dry_run": True,
    }
    if keep_last < 0:
        raise ValueError("keep_last must be >= 0")
    if not root.is_dir():
        return empty

    aborted: list[str] = []
    sessions: list[tuple[Path, float]] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        meta = _read_meta(d)
        if _is_aborted(d, meta):
            aborted.append(d.name)
        else:
            sessions.append((d, _session_timestamp(d, meta)))

    # 新的在前 —— 保留最近的 keep_last 个 run 的完整证据。
    sessions.sort(key=lambda item: (item[1], item[0].name), reverse=True)
    kept_full = [d.name for d, _ in sessions[:keep_last]]

    pruned: dict[str, list[str]] = {}
    files_removed = 0
    bytes_freed = 0
    for d, _ts in sessions[keep_last:]:
        removable = deterministic_evidence_files(d)
        if not removable:
            continue
        rels = []
        for p in removable:
            rels.append(str(p.relative_to(d)))
            try:
                bytes_freed += p.stat().st_size
            except OSError:
                pass
        pruned[d.name] = sorted(rels)
        files_removed += len(rels)

    return {
        "root": str(root),
        "exists": True,
        "scanned": len(sessions) + len(aborted),
        "aborted": sorted(aborted),
        "pruned": pruned,
        "kept_full": kept_full,
        "files_removed": files_removed,
        "bytes_freed": bytes_freed,
        "dry_run": True,
    }


def plan_prune(project_dir, *, keep_last: int = 3) -> dict:
    """算出一个项目的 ``<project>/.osh/sessions`` 保留方案。"""
    return plan_prune_root(Path(project_dir) / ".osh" / "sessions",
                           keep_last=keep_last)


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------

def _apply(plan: dict, *, dry_run: bool) -> dict:
    result = dict(plan)
    result["dry_run"] = dry_run
    if dry_run or not plan.get("exists"):
        return result

    root = Path(plan["root"])
    for name in plan["aborted"]:
        shutil.rmtree(root / name, ignore_errors=True)
    for name, rels in plan["pruned"].items():
        for rel in rels:
            try:
                (root / name / rel).unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:  # noqa: PERF203 — 单个文件失败不该中断整轮
                log.warning("prune failed for %s/%s: %s", name, rel, exc)
    return result


def prune_sessions(project_dir, *, keep_last: int = 3,
                   dry_run: bool = True) -> dict:
    """按 T0–T3 分层回收一个项目的会话目录。

    ``dry_run=True``（默认）只返回方案。``keep_last`` 是「完整保留多少个
    最近 run」—— 更早的 run 只裁掉 T3 确定性证据，T1/T2 仍在。
    """
    return _apply(plan_prune(project_dir, keep_last=keep_last), dry_run=dry_run)


def prune_sessions_root(root, *, keep_last: int = 3,
                        dry_run: bool = True) -> dict:
    """同 :func:`prune_sessions`，但直接给 sessions 根目录。

    默认根用 ``resolve_sessions_root()``（``OSH_SESSIONS_DIR`` 优先，
    否则 ``<OSH_HOME>/.osh/sessions``）。
    """
    return _apply(plan_prune_root(Path(root), keep_last=keep_last),
                  dry_run=dry_run)


def format_plan(plan: dict) -> str:
    """把方案渲染成可读文本 —— 清理必须显式，不静默。"""
    lines = [f"sessions root: {plan['root']}"]
    if not plan.get("exists"):
        lines.append("  (目录不存在，无需处理)")
        return "\n".join(lines)
    lines.append(f"  扫描 {plan['scanned']} 个会话目录")
    lines.append(f"  T0 整体回收: {len(plan['aborted'])} 个"
                 + (f" → {', '.join(plan['aborted'][:5])}"
                    + (" …" if len(plan['aborted']) > 5 else "")
                    if plan['aborted'] else ""))
    lines.append(f"  完整保留(T1+T2+T3): {len(plan['kept_full'])} 个"
                 + (f" → {', '.join(plan['kept_full'])}"
                    if plan['kept_full'] else ""))
    lines.append(f"  裁剪 T3 证据: {len(plan['pruned'])} 个 run / "
                 f"{plan['files_removed']} 个文件 / "
                 f"{plan['bytes_freed'] / 1024:.1f} KB")
    for name, rels in sorted(plan["pruned"].items()):
        lines.append(f"    {name}: {len(rels)} 个文件")
    if plan.get("dry_run"):
        lines.append("  (dry-run — 未删除任何内容)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m yuleosh.pipeline.session_prune",
        description="按 T0–T3 分层回收 pipeline 会话目录（默认 dry-run）。",
    )
    parser.add_argument("project_dir", nargs="?",
                        help="项目目录；省略则用 OSH_SESSIONS_DIR / OSH_HOME 解析出的根")
    parser.add_argument("--keep-last", type=int, default=3,
                        help="完整保留最近多少个 run（默认 3）")
    parser.add_argument("--apply", action="store_true",
                        help="真正执行删除（默认只打印方案）")
    args = parser.parse_args(argv)

    if args.project_dir:
        plan = plan_prune(args.project_dir, keep_last=args.keep_last)
    else:
        plan = plan_prune_root(resolve_sessions_root(), keep_last=args.keep_last)

    plan = _apply(plan, dry_run=not args.apply)
    print(format_plan(plan))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
