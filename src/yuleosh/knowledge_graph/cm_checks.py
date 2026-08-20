#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
CM Gate — 仓库管理检查（第九轮决策 2026-08-19, 角色=小仓）。

老板核对「项目-产品-需求-架构-开发-审查-测试-合规-仓库管理」九角色链条，
发现仓库管理（CM）角色完全缺失——merge-gate 只做 KG 图一致性/置信度检查，
无任何 git 提交/推送/工作区管理职责。本轮补齐：merge-gate 扩展为 CM Gate，
在 KG 检查基础上追加 4 项确定性 CM 检查（非 LLM，纯代码）：

  1. 工作区清洁检查   — 未提交改动 / 未跟踪文件清单（warning 不阻断，
     防他 agent 并行文件误伤）
  2. 提交规范检查     — HEAD commit message type(scope): subject 前缀校验
     + 文件范围合理性（是否含 artifacts/.osh/ 产物）
  3. 生成产物泄漏检查 — git ls-files 匹配 artifacts/ .osh/ htmlcov/
     __pycache__/ .benchmarks/ → 阻断 + 清单
  4. 部署护栏状态确认 — session_dir/deploy-changes.json 存在且非空
     （有部署动作必有变更集记录；无部署 skipped 则跳过）

任一 failed → gate failed；warning 仅记录。无 git 仓库 → 全部 skipped
（容错）。
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger("yuleosh.knowledge_graph.cm_checks")

__all__ = [
    "COMMIT_TYPES",
    "LEAK_PATTERNS",
    "run_cm_checks",
]

# 提交规范允许的 type 前缀（conventional commits）
COMMIT_TYPES = {
    "feat", "fix", "chore", "docs", "refactor", "test",
    "style", "perf", "build", "ci", "revert",
}

# 生成产物泄漏模式（git ls-files 匹配 → 阻断）
LEAK_PATTERNS = (
    "artifacts/",
    ".osh/",
    "htmlcov/",
    "__pycache__/",
    ".benchmarks/",
)

# 有意跟踪的源/文档（不视为生成产物泄漏）:
#   .osh/specs/           — OpenSpec 规范源 (2026-08-18 老板钦定: 项目规范
#                            SHALL 按 .osh/specs/<capability>/spec.md 结构化,
#                            git add 需 -f 但属规范真相源, 必须跟踪)
#   .osh/sprint-contract- — harness coding sprint 契约 (先定 done 标准产物)
# 匹配 .osh/ 前缀时先排除这些, 其余 .osh/sessions|.osh/cache 等仍判泄漏。
LEAK_EXCLUDE_PREFIXES = (
    ".osh/specs/",
    ".osh/sprint-contract-",
)


def _is_git_repo(project_dir: Path) -> bool:
    """True when the project dir is a git checkout."""
    return (project_dir / ".git").exists()


def _git(project_dir: Path, args: list[str]) -> subprocess.CompletedProcess:
    """Run a git command in the project dir (never hangs)."""
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True, text=True, timeout=15, cwd=str(project_dir),
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        log.warning("git %s failed: %s", args[0] if args else "", e)
        return subprocess.CompletedProcess(["git"], 1, "", str(e))


def check_workspace_clean(project_dir: Path) -> dict:
    """CM 检查 1: 工作区清洁 — 未提交改动 / 未跟踪文件。

    warning 不阻断（防他 agent 并行文件误伤）；changed_files 记录已跟踪
    文件的未提交改动，untracked_files 记录未跟踪非忽略文件。
    """
    result: dict = {
        "check": "workspace_clean",
        "status": "passed",
        "changed_files": [],
        "untracked_files": [],
    }
    if not _is_git_repo(project_dir):
        result["status"] = "skipped"
        result["reason"] = "not a git checkout"
        return result

    proc = _git(project_dir, ["status", "--porcelain"])
    if proc.returncode != 0:
        result["status"] = "warning"
        result["reason"] = f"git status failed: {proc.stderr[-300:]}"
        return result

    changed, untracked = [], []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        code = line[:2].strip()
        path = line[3:].strip()
        if code == "??":
            untracked.append(path)
        else:
            changed.append(path)

    result["changed_files"] = changed[:50]
    result["untracked_files"] = untracked[:50]
    if changed or untracked:
        # 未跟踪非忽略文件 → warning 不阻断（防他 agent 并行文件误伤）
        result["status"] = "warning"
        result["summary"] = (
            f"{len(changed)} changed + {len(untracked)} untracked file(s)"
        )
    else:
        result["summary"] = "workspace clean"
    return result


def check_commit_convention(project_dir: Path) -> dict:
    """CM 检查 2: 提交规范 — HEAD commit message type(scope): subject。

    前缀校验: feat/fix/chore/docs/refactor/test/style/perf/build/ci/revert。
    文件范围合理性: HEAD commit 是否含 artifacts/.osh/ 产物路径。
    """
    result: dict = {
        "check": "commit_convention",
        "status": "passed",
        "head_subject": "",
        "violations": [],
    }
    if not _is_git_repo(project_dir):
        result["status"] = "skipped"
        result["reason"] = "not a git checkout"
        return result

    proc = _git(project_dir, ["log", "-1", "--pretty=%s"])
    if proc.returncode != 0 or not proc.stdout.strip():
        result["status"] = "skipped"
        result["reason"] = "no commits yet"
        return result
    subject = proc.stdout.strip().splitlines()[0]
    result["head_subject"] = subject

    m = re.match(r"^([a-z]+)(?:\([^)]*\))?!?: .+", subject)
    if not m:
        result["violations"].append(
            f"HEAD commit message 不符合 conventional commits: '{subject}' — "
            f"需要 type(scope): subject 前缀 (feat/fix/chore/docs/refactor/"
            f"test/style/perf/build/ci/revert)"
        )
    elif m.group(1) not in COMMIT_TYPES:
        result["violations"].append(
            f"HEAD commit type '{m.group(1)}' 不在允许集合 "
            f"{sorted(COMMIT_TYPES)}"
        )

    # 文件范围合理性: HEAD commit 是否包含产物路径
    files_proc = _git(project_dir, ["show", "--name-only", "--pretty=format:", "-1"])
    if files_proc.returncode == 0:
        leaked_files = [
            f for f in files_proc.stdout.splitlines()
            if f.strip() and any(f.startswith(p) for p in LEAK_PATTERNS)
        ]
        if leaked_files:
            result["violations"].append(
                f"HEAD commit 包含生成产物: {leaked_files[:10]} — "
                f"artifacts/.osh/ 等不应入库"
            )

    if result["violations"]:
        result["status"] = "failed"
    return result


def check_generated_artifacts_leak(project_dir: Path) -> dict:
    """CM 检查 3: 生成产物泄漏 — git ls-files 匹配产物路径 → 阻断 + 清单。

    匹配 artifacts/ .osh/ htmlcov/ __pycache__/ .benchmarks/ 等生成物
    被 git 跟踪 = 仓库卫生违规（阻断）。
    """
    result: dict = {
        "check": "generated_artifacts_leak",
        "status": "passed",
        "leaked_files": [],
    }
    if not _is_git_repo(project_dir):
        result["status"] = "skipped"
        result["reason"] = "not a git checkout"
        return result

    proc = _git(project_dir, ["ls-files"])
    if proc.returncode != 0:
        result["status"] = "warning"
        result["reason"] = f"git ls-files failed: {proc.stderr[-300:]}"
        return result

    leaked = [
        f for f in proc.stdout.splitlines()
        if any(f.startswith(p) for p in LEAK_PATTERNS)
        and not any(f.startswith(x) for x in LEAK_EXCLUDE_PREFIXES)
    ]
    result["leaked_files"] = leaked[:50]
    if leaked:
        result["status"] = "failed"
        result["summary"] = f"{len(leaked)} tracked generated artifact(s)"
    else:
        result["summary"] = "no tracked generated artifacts"
    return result


def check_deploy_guardrail(project_dir: Path, session_dir: Path | None) -> dict:
    """CM 检查 4: 部署护栏状态确认。

    有部署动作（codegen-deploy 非 skipped）必有 deploy-changes.json
    变更集记录；无部署 skipped 则跳过。找不到变更集 → failed（部署
    证据链断裂）。
    """
    result: dict = {
        "check": "deploy_guardrail",
        "status": "passed",
        "deploy_changes_present": False,
        "deploy_status": "",
    }
    # 1. 读 codegen-deploy 报告确认部署状态
    deploy_report = Path(project_dir) / ".yuleosh" / "reports" / "codegen-deploy.json"
    deploy_status = ""
    if deploy_report.exists():
        try:
            data = json.loads(deploy_report.read_text(encoding="utf-8"))
            deploy_status = str(data.get("status", ""))
        except (OSError, json.JSONDecodeError):
            deploy_status = "unreadable"

    if deploy_status in ("skipped_codegen_failed", "skipped_api_mismatch",
                         "skipped", "empty", ""):
        # 无部署动作 → 跳过（自然无变更集）
        result["status"] = "skipped"
        result["deploy_status"] = deploy_status or "none"
        result["reason"] = "no deployment in this run — deploy-changes check not applicable"
        return result

    # 2. 有部署 → session_dir/deploy-changes.json 必须存在且非空
    if session_dir is None or not Path(session_dir).is_dir():
        result["status"] = "failed"
        result["summary"] = "deployment recorded but session_dir missing — evidence chain broken"
        return result

    changes_path = Path(session_dir) / "deploy-changes.json"
    if not changes_path.exists():
        result["status"] = "failed"
        result["summary"] = (
            f"deployment status='{deploy_status}' but {changes_path.name} "
            f"missing — deploy evidence chain broken"
        )
        return result

    try:
        changes = json.loads(changes_path.read_text(encoding="utf-8"))
        if isinstance(changes, list):
            result["deploy_changes_present"] = bool(changes)
        elif isinstance(changes, dict):
            result["deploy_changes_present"] = bool(changes.get("files") or
                                                       changes.get("deployed") or
                                                       changes)
        else:
            result["deploy_changes_present"] = False
    except (OSError, json.JSONDecodeError):
        result["deploy_changes_present"] = False

    if not result["deploy_changes_present"]:
        result["status"] = "failed"
        result["summary"] = "deploy-changes.json exists but is empty — evidence chain broken"
    else:
        result["status"] = "passed"
        result["summary"] = "deploy-changes.json present and non-empty"
    return result


def run_cm_checks(project_dir: str | Path, session_dir: str | Path | None = None) -> dict:
    """Run all 4 CM checks and aggregate.

    Returns a dict with:
      - checks: list of per-check results
      - status: passed | warning | failed | skipped
      - failed_checks / warnings: aggregates
    """
    pdir = Path(project_dir)
    sdir = Path(session_dir) if session_dir else None

    checks = [
        check_workspace_clean(pdir),
        check_commit_convention(pdir),
        check_generated_artifacts_leak(pdir),
        check_deploy_guardrail(pdir, sdir),
    ]

    failed = [c for c in checks if c["status"] == "failed"]
    warnings = [c for c in checks if c["status"] == "warning"]
    skipped_all = all(c["status"] == "skipped" for c in checks)

    if failed:
        status = "failed"
    elif warnings:
        status = "warning"
    elif skipped_all:
        status = "skipped"
    else:
        status = "passed"

    return {
        "status": status,
        "checks": checks,
        "failed_checks": [c["check"] for c in failed],
        "warning_checks": [c["check"] for c in warnings],
        "summary": (
            f"{len(failed)} failed / {len(warnings)} warning / "
            f"{len(checks) - len(failed) - len(warnings)} passed"
        ),
    }
