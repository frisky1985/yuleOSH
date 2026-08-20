#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Deploy State — 审查锚定: codegen 部署状态查询 (single source of truth).

背景 (2026-08-12, window-anti-pinch run-20260812-033339 复盘):
  codegen 提案被护栏拒绝时 (deployed=[]), 后续代码审查步骤仍照常执行,
  审的是「基线代码 / 失败产物」→ 6 个 verdict errors 全部是审查错对象。
  审查的职责是卡住「本次 run 的质量」, 不是卡「历史基线」——基线质量
  由项目自身 CI (Layer 1/2) 把关。

本模块提供唯一事实源:
  - load_deploy_report(project_dir)  读 .yuleosh/reports/codegen-deploy.json
  - has_deployed_code(project_dir)   本次 run 是否有代码部署
  - deployed_files(project_dir)      本次部署的文件相对路径列表 (diff 聚焦用)
  - maybe_skip_code_review(session, step_key, reviewer)
      无部署 → 写 status=skipped 报告并返回路径 (honest skip)
      有部署 → 返回 None (审查照常)

P0 门禁例外: review-critical-safety 是全局安全门禁, 不调用本模块,
永远执行 (见 review_critical_safety.py)。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("pipeline.deploy_state")

# codegen-deploy 报告的规范路径 (与 step_codegen_deploy 一致)
_REPORT_REL = ".yuleosh/reports/codegen-deploy.json"

# 判定「本次 run 无代码部署」的 status 集合 (step_codegen_deploy 产出)
NO_DEPLOY_STATUSES = {
    "skipped",                    # 无 generated src/ 产物 (planning 模式)
    "skipped_codegen_failed",     # codegen 失败, 护栏拒绝部署
    "skipped_api_mismatch",       # 生成 API 破坏既有契约, 护栏拒绝部署
    "empty",                      # 有目录但无文件可部署
    "deployed_behavior_regression",  # 部署后被行为护栏检测回归 → 已回滚 src/
                                     # 部署内容已被回滚, 视为无部署 (审查锚定基线)
    "skipped_src_protected",       # OSH_GUARD_PROTECT_SRC=1 且 src/ 有未提交
                                   # 改动 → 跳过部署 (保护用户手动代码)
}

# 部署成功 status (step_codegen_deploy 产出)
DEPLOYED_STATUSES = {"deployed"}


def deploy_report_path(project_dir: str | Path) -> Path:
    """codegen-deploy 报告的绝对路径。"""
    return Path(project_dir) / _REPORT_REL


def load_deploy_report(project_dir: str | Path) -> Optional[dict]:
    """读取 codegen-deploy 报告; 不存在/损坏返回 None。"""
    p = deploy_report_path(project_dir)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Cannot parse %s: %s", p, e)
    return None


def deploy_status(project_dir: str | Path) -> str:
    """本次 run 的部署状态字符串 (报告 status; 无报告返回 'no-report')。"""
    report = load_deploy_report(project_dir)
    if not report:
        return "no-report"
    return str(report.get("status", "unknown"))


def has_deployed_code(project_dir: str | Path) -> bool:
    """本次 run 是否有代码部署。

    - 报告 status=deployed 且有 deployed 列表 → True
    - 无报告 (pipeline 非 codegen 模式或早期版本) → True (保守: 审查照常,
      不因缺失报告误 skip)
    - 报告 status 在 NO_DEPLOY_STATUSES → False
    """
    report = load_deploy_report(project_dir)
    if not report:
        return True
    status = str(report.get("status", ""))
    if status in DEPLOYED_STATUSES:
        return True
    if status in NO_DEPLOY_STATUSES:
        return False
    # 未知 status: 看 deployed 列表兜底
    deployed = report.get("deployed") or []
    return bool(deployed)


def deployed_files(project_dir: str | Path) -> list[str]:
    """本次 run 部署的文件相对路径列表 (diff 聚焦输入)。

    返回空列表表示本次无部署 (调用方应跳过代码审查)。
    """
    report = load_deploy_report(project_dir)
    if not report:
        return []
    deployed = report.get("deployed") or []
    return [str(f) for f in deployed if f]


def _write_skip_report(
    session,
    step_key: str,
    reviewer: str,
    reason: str,
    deploy_status_str: str,
) -> str:
    """写 status=skipped 的审查报告 (与 handler_base._write_skip_report 同语义)。

    verdict 传播对 status=skipped 不记 errors → pipeline 不再「假红」。
    """
    out_path = Path(session.session_dir) / f"{step_key}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "step": step_key,
                "session": getattr(session, "name", ""),
                "reviewer": reviewer,
                "timestamp": datetime.now().isoformat(),
                "status": "skipped",
                "reason": reason,
                "deploy_status": deploy_status_str,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return str(out_path)


def maybe_skip_code_review(
    session,
    step_key: str,
    reviewer: str = "小克",
) -> Optional[str]:
    """审查锚定: 本次 run 无代码部署时 honest-skip 代码审查步骤。

    返回 str (skip 报告路径) 表示应跳过; None 表示审查照常执行。

    Parameters
    ----------
    session : PipelineSession
        当前 pipeline 会话 (提供 project_dir / session_dir / name)。
    step_key : str
        审查步骤 key (用于报告文件名, 如 ``review-memory``)。
    reviewer : str
        审查者角色名 (写入报告)。
    """
    project_dir = getattr(session, "project_dir", None)
    if not project_dir:
        # 无项目目录时无法判定部署状态 — 保守: 审查照常执行。
        # (2026-08-20 污染复盘: 回退 cwd 会误读仓库根目录残留的
        #  .yuleosh/reports/codegen-deploy.json — 某次从仓库根跑 mock pipeline
        #  写入 status=skipped, 导致全部 step-handler 测试误 skip 47+ 项)
        return None
    project_dir = Path(project_dir)
    status = deploy_status(project_dir)
    if has_deployed_code(project_dir):
        return None

    reason = (
        f"本次 run 无代码部署 (codegen-deploy status={status}) — "
        "代码审查无审查对象; 基线代码质量由项目 CI 把关"
    )
    log.info(
        "Step [%s] skipped by deploy anchor: status=%s (no code deployed)",
        step_key, status,
    )
    return _write_skip_report(session, step_key, reviewer, reason, status)
