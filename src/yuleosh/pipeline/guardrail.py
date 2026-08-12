#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
行为护栏基础设施 (2026-08-13, 老板拍板 1+2+3+4).

把 codegen-deploy 单点行为护栏升级为全 pipeline 可复用的体系:

  1. ChangeSet   — 变更集模型: {rel_path: original_bytes | None(新增)}
                   备份/回滚的单一数据形态, 任何写入点都能套用。
  2. 备份落盘     — .yuleosh/guardrail/backup-<run_id>/ 文件级持久化,
                   codegen-deploy 写, 下游门禁步骤读 (内存 dict 会随
                   deploy 步骤结束而消失, 门禁联动无备份可用)。
  3. TestRunner  — 测试执行协议 (run(project_dir, force_rebuild) -> TestResult)。
                   CCTestRunner 包装 run_c_test_suite; Python/Go runner
                   后续按同一协议实现。
  4. maybe_rollback_on_gate_failure — 门禁联动回滚 (方案 A):
                   门禁失败 + 部署生效 + 备份在 → 回滚 src → 重跑本门禁
                   隔离验证: 基线通过 = 确认部署回归 (保持回滚);
                   基线也失败 = 非部署问题 (undo 恢复部署, 标 RED 人工介入)。
                   只对行为类门禁白名单生效 (coverage/misra 不联动 —
                   覆盖率低/规范违规不是行为回归, 回滚基线只会更糟)。

设计约束:
  - 不改变 run_c_test_suite 的语义 — CCTestRunner 只是薄包装。
  - 回滚/undo 都是 staged: 先写临时文件再 rename, 防半状态。
  - 所有函数无 LLM 调用 — 确定性逻辑, 可单测。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Optional, Protocol, runtime_checkable

log = logging.getLogger("pipeline.guardrail")

# ---------------------------------------------------------------------------
# 路径约定
# ---------------------------------------------------------------------------

# 备份根目录: <project_dir>/.yuleosh/guardrail/backup-<run_id>/
GUARDRAIL_ROOT_REL = ".yuleosh/guardrail"


def guardrail_root(project_dir: str | Path) -> Path:
    return Path(project_dir) / GUARDRAIL_ROOT_REL


def backup_dir(project_dir: str | Path, run_id: str) -> Path:
    """单次 run 的备份目录: .yuleosh/guardrail/backup-<run_id>/"""
    return guardrail_root(project_dir) / f"backup-{run_id}"


# ---------------------------------------------------------------------------
# ChangeSet — 变更集模型
# ---------------------------------------------------------------------------

# ChangeSet: {相对路径: 部署前原始 bytes | None(新增文件, 回滚=删除)}
ChangeSet = dict[str, Optional[bytes]]

# 备份目录内布局:
#   backup-<run_id>/
#     changeset.json     — {rel_path: "orig" | "new"} + 元数据
#     orig/<rel_path>    — 部署前原始文件 (内容)
#     new/<rel_path>     — 部署后文件 (undo 恢复部署用)


def save_change_set(
    project_dir: str | Path,
    run_id: str,
    changeset: ChangeSet,
    deployed_after: Optional[Mapping[str, Optional[bytes]]] = None,
) -> Path:
    """把变更集持久化到 .yuleosh/guardrail/backup-<run_id>/。

    Parameters
    ----------
    changeset : ChangeSet
        {rel_path: 部署前原始 bytes | None}
    deployed_after : ChangeSet, optional
        {rel_path: 部署后 bytes} — undo (非部署问题恢复部署) 时用。

    Returns
    -------
    Path
        备份目录。
    """
    bdir = backup_dir(project_dir, run_id)
    orig_dir = bdir / "orig"
    new_dir = bdir / "new"
    orig_dir.mkdir(parents=True, exist_ok=True)
    new_dir.mkdir(parents=True, exist_ok=True)

    # 先写内容文件 (原子: 先临时再 rename)
    manifest: dict[str, str] = {}
    for rel, orig in changeset.items():
        safe = _safe_rel(rel)
        if orig is None:
            manifest[safe] = "new"
        else:
            manifest[safe] = "orig"
            _atomic_write(orig_dir / safe, orig)
    for rel, content in (deployed_after or {}).items():
        if content is not None:
            _atomic_write(new_dir / _safe_rel(rel), content)

    manifest_path = bdir / "changeset.json"
    _atomic_write(
        manifest_path,
        json.dumps(
            {
                "run_id": run_id,
                "created_at": datetime.now().isoformat(),
                "manifest": manifest,
            },
            indent=2,
            ensure_ascii=False,
        ).encode("utf-8"),
    )
    log.info("ChangeSet saved: %s (%d files)", bdir, len(changeset))
    return bdir


def load_change_set(project_dir: str | Path, run_id: str) -> Optional[ChangeSet]:
    """从磁盘加载变更集; 不存在/损坏返回 None。"""
    bdir = backup_dir(project_dir, run_id)
    manifest_path = bdir / "changeset.json"
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = data.get("manifest") or {}
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Cannot parse %s: %s", manifest_path, e)
        return None

    changeset: ChangeSet = {}
    for rel, kind in manifest.items():
        if kind == "new":
            changeset[rel] = None
        else:
            orig_path = bdir / "orig" / _safe_rel(rel)
            try:
                changeset[rel] = orig_path.read_bytes()
            except OSError as e:
                log.warning("ChangeSet restore missing orig %s: %s", orig_path, e)
                changeset[rel] = None
    return changeset


def load_deployed_after(project_dir: str | Path, run_id: str) -> ChangeSet:
    """加载部署后内容 (undo 用); 无则空 dict。"""
    bdir = backup_dir(project_dir, run_id)
    new_dir = bdir / "new"
    result: ChangeSet = {}
    if not new_dir.exists():
        return result
    for p in sorted(new_dir.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(new_dir))
            try:
                result[rel] = p.read_bytes()
            except OSError:
                continue
    return result


def find_latest_change_set(project_dir: str | Path) -> Optional[tuple[str, ChangeSet]]:
    """找最近一次持久化的变更集 (门禁联动用, 不含 run_id 显式传入)。

    Returns
    -------
    Optional[tuple[str, ChangeSet]]
        (run_id, changeset); 无备份返回 None。
    """
    root = guardrail_root(project_dir)
    if not root.exists():
        return None
    backups = sorted(
        (d for d in root.glob("backup-*") if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for bdir in backups:
        run_id = bdir.name.removeprefix("backup-")
        cs = load_change_set(project_dir, run_id)
        if cs is not None:
            return run_id, cs
    return None


def apply_change_set(project_dir: str | Path, changeset: ChangeSet) -> None:
    """把变更集应用到项目: 恢复原始内容 (回滚)。staged 写入。"""
    project_dir = Path(project_dir)
    for rel, orig in changeset.items():
        dst = project_dir / rel
        if orig is None:
            # 部署前不存在 → 回滚 = 删除该文件
            try:
                dst.unlink()
            except OSError:
                pass
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(dst, orig)


def apply_deployed_after(project_dir: str | Path, changeset: ChangeSet) -> None:
    """把部署后内容重新应用到项目 (undo 回滚 — 非部署问题恢复部署)。"""
    project_dir = Path(project_dir)
    for rel, content in changeset.items():
        if content is None:
            continue
        dst = project_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(dst, content)


# ---------------------------------------------------------------------------
# TestRunner 协议
# ---------------------------------------------------------------------------


@dataclass
class TestResult:
    """测试执行结果 (统一形态, 跨 runner 可比)。"""

    runner: str
    status: str            # passed / failed / skipped / unknown
    passed: int = 0
    failed: int = 0
    returncode: Optional[int] = None
    output: str = ""
    extra: dict = field(default_factory=dict)


@runtime_checkable
class TestRunner(Protocol):
    """测试执行协议 — 任何测试后端实现该接口即可被护栏复用。

    run() 必须真实执行 (或如实返回 status=skipped/unknown), 不得静默
    假通过。force_rebuild=True 表示强制造全新构建 (行为护栏/门禁联动
    场景, 防 mtime 同秒假通过)。
    """

    name: str

    def run(self, project_dir: str | Path, force_rebuild: bool = False) -> TestResult:
        ...  # pragma: no cover


class CCTestRunner:
    """C 项目测试 runner — 包装 run_c_test_suite (ctest/unity/ceedling/gcc)。"""

    name = "c-test"

    def __init__(self, timeout_build: int = 300, timeout_ctest: int = 300):
        self.timeout_build = timeout_build
        self.timeout_ctest = timeout_ctest

    def run(self, project_dir: str | Path, force_rebuild: bool = False) -> TestResult:
        from yuleosh.pipeline.step_handlers.test_c_unit import run_c_test_suite

        raw = run_c_test_suite(
            project_dir,
            timeout_build=self.timeout_build,
            timeout_ctest=self.timeout_ctest,
            force_rebuild=force_rebuild,
        )
        return TestResult(
            runner=raw.get("runner", "none"),
            status=raw.get("status", "unknown"),
            passed=raw.get("passed", 0),
            failed=raw.get("failed", 0),
            returncode=raw.get("returncode"),
            output=raw.get("output", ""),
            extra={
                "c_files": raw.get("c_files", 0),
                "c_test_files": raw.get("c_test_files", 0),
                "c_header_files": raw.get("c_header_files", 0),
            },
        )


class IntegrationTestRunner:
    """接口/集成测试 runner — pytest -m integration / go -tags=integration。

    与 step_integration_test 的 runner 逻辑保持一致 (同一命令/解析),
    保证门禁联动「回滚后重跑」与原始门禁口径一致。
    """

    name = "integration-test"

    def run(self, project_dir: str | Path, force_rebuild: bool = False) -> TestResult:
        import re
        import subprocess
        import sys

        project_dir = Path(project_dir)
        test_output = ""
        result_returncode = None
        test_runner = "none"

        test_dir = project_dir / "tests"
        if (test_dir / "conftest.py").exists() or test_dir.exists():
            try:
                pytest_cmd = [
                    sys.executable, "-m", "pytest", "tests/", "-q",
                    "-m", "integration",
                ]
                probe = subprocess.run(
                    [sys.executable, "-m", "pytest", "--help"],
                    capture_output=True, text=True, timeout=30,
                )
                if "--timeout=" in (probe.stdout or "") or "--timeout=" in (probe.stderr or ""):
                    pytest_cmd.append("--timeout=120")
                result = subprocess.run(
                    pytest_cmd, capture_output=True, text=True,
                    timeout=180, cwd=project_dir,
                )
                test_output = (result.stdout or "") + "\n" + (result.stderr or "")
                result_returncode = result.returncode
                test_runner = "pytest-integration"
            except FileNotFoundError:
                pass
            except subprocess.TimeoutExpired:
                test_output = "TIMEOUT: pytest integration tests exceeded 180s"
                test_runner = "pytest-integration-timeout"

        if test_runner == "none":
            go_mod = project_dir / "go.mod"
            if go_mod.exists():
                try:
                    result = subprocess.run(
                        ["go", "test", "-tags=integration", "./..."],
                        capture_output=True, text=True,
                        timeout=300, cwd=project_dir,
                    )
                    test_output = (result.stdout or "") + "\n" + (result.stderr or "")
                    result_returncode = result.returncode
                    test_runner = "go-integration"
                except FileNotFoundError:
                    pass
                except subprocess.TimeoutExpired:
                    test_output = "TIMEOUT: Go integration tests exceeded 300s"
                    test_runner = "go-integration-timeout"

        if test_runner == "none":
            return TestResult(
                runner="none", status="unknown",
                output="No integration test framework found",
            )

        passed, failed = _parse_test_counts_impl(test_output, test_runner)
        # pytest exit 5 = 无匹配测试 (not a failure)
        if result_returncode == 5 and test_runner == "pytest-integration":
            status = "skipped"
        elif result_returncode is not None and result_returncode != 0:
            status = "failed"
        elif failed > 0:
            status = "failed"
        else:
            status = "passed"

        return TestResult(
            runner=test_runner,
            status=status,
            passed=passed,
            failed=failed,
            returncode=result_returncode,
            output=test_output[:3000],
        )


def _parse_test_counts_impl(output: str, runner: str) -> tuple[int, int]:
    """解析 pytest/go 测试输出 (与 test_integration._parse_test_counts 同逻辑)。"""
    import re

    passed = 0
    failed = 0
    if not output:
        return passed, failed

    if runner.startswith("pytest"):
        m = re.search(r"(\d+)\s+passed", output)
        if m:
            passed = int(m.group(1))
        m = re.search(r"(\d+)\s+failed", output)
        if m:
            failed = int(m.group(1))
    elif runner.startswith("go"):
        ok_lines = re.findall(r"^ok\s+\S+", output, re.MULTILINE)
        fail_lines = re.findall(r"^FAIL\s+\S+", output, re.MULTILINE)
        passed = len(ok_lines)
        failed = len(fail_lines)
    return passed, failed


# ---------------------------------------------------------------------------
# 行为类门禁白名单 (方案 A 联动范围)
# ---------------------------------------------------------------------------

# 联动回滚只对「行为测试类」门禁生效:
#   - c-unit-test / integration-test / self-test / qemu-run
# 明确不联动 (反模式):
#   - c-coverage-gate / coverage-gate  — 覆盖率低≠行为回归, 回滚基线只会更糟
#   - misra-review / 静态 review       — 规范违规, 基线可能就有
BEHAVIOR_GATES = frozenset({
    "c-unit-test",
    "integration-test",
    "self-test",
    "qemu-run",
})


# ---------------------------------------------------------------------------
# 门禁联动回滚 (方案 A)
# ---------------------------------------------------------------------------


def maybe_rollback_on_gate_failure(
    session,
    step_key: str,
    gate_result: TestResult,
    runner: TestRunner | None = None,
) -> dict:
    """门禁失败时联动回滚 (隔离验证模式)。

    触发条件 (全部满足才进入联动流程):
      1. 步骤在行为类门禁白名单 (BEHAVIOR_GATES)
      2. 门禁 verdict failed (status == "failed")
      3. 本次 run 有部署生效 (codegen-deploy report status == "deployed")
      4. 有持久化备份 (find_latest_change_set 非空)
    任一不满足 → 返回空 dict (调用方走原逻辑, 零行为变化)。

    联动流程:
      - 回滚 src → 重跑本门禁 (force_rebuild=True, 用同一 runner)
      - 基线通过 → 确认是部署回归 → 保持回滚, 更新 deploy 报告
        status=deployed_behavior_regression + deployed 清空
      - 基线也失败 → 非部署问题 → undo 恢复部署 → 标 gate_failed_independent
        (不碰 deploy 报告, 让 pipeline 按原逻辑标 RED 人工介入)

    Parameters
    ----------
    session : PipelineSession
        当前 pipeline 会话 (project_dir / run_id)。
    step_key : str
        门禁步骤 key (白名单判定)。
    gate_result : TestResult
        本次门禁的执行结果。
    runner : TestRunner, optional
        重跑门禁用的 runner; None 时按步骤类型解析 (C 项目默认 CCTestRunner)。

    Returns
    -------
    dict
        {} — 未联动 (条件不满足)
        {"action": "rolled_back", "rerun": TestResult, "run_id": str}
        {"action": "gate_failed_independent", "rerun": TestResult, "run_id": str}
    """
    if step_key not in BEHAVIOR_GATES:
        return {}
    if gate_result.status != "failed":
        return {}

    project_dir = Path(getattr(session, "project_dir", None) or ".")
    run_id = str(getattr(session, "run_id", "") or "")

    # 条件 3: 有部署生效
    try:
        from yuleosh.pipeline.deploy_state import load_deploy_report
        report = load_deploy_report(project_dir)
    except Exception as e:  # pragma: no cover - defensive
        log.debug("deploy report check failed: %s", e)
        report = None
    if not report or str(report.get("status", "")) != "deployed":
        return {}

    # 条件 4: 有持久化备份 (优先当前 run, 兜底最近一次)
    changeset: ChangeSet | None = None
    backup_run_id = run_id
    if run_id:
        changeset = load_change_set(project_dir, run_id)
    if changeset is None:
        found = find_latest_change_set(project_dir)
        if found:
            backup_run_id, changeset = found
    if changeset is None:
        log.warning(
            "Gate [%s] failed but no guardrail backup found — no rollback "
            "(baseline/environment issue, not deploy regression)",
            step_key,
        )
        return {}

    deployed_after = load_deployed_after(project_dir, backup_run_id)

    if runner is None:
        runner = CCTestRunner()

    # ── 回滚 src 到基线 ──
    log.warning(
        "Gate [%s] failed (failed=%d) with deploy active — rolling back src/ "
        "to baseline for isolation verification (backup run=%s)",
        step_key, gate_result.failed, backup_run_id,
    )
    try:
        apply_change_set(project_dir, changeset)
    except OSError as e:
        log.error("Rollback failed, cannot run isolation verification: %s", e)
        return {}

    # ── 重跑本门禁 (隔离验证) ──
    rerun = runner.run(project_dir, force_rebuild=True)

    if rerun.status == "passed":
        # 基线通过 → 确认是部署回归 → 保持回滚
        log.warning(
            "Gate [%s] rollback verified: baseline passes after rollback — "
            "deployment was the regression cause; keeping src/ rolled back",
            step_key,
        )
        _mark_deploy_regression(project_dir, report)
        return {
            "action": "rolled_back",
            "rerun": rerun,
            "run_id": backup_run_id,
        }

    # 基线也失败 → 非部署问题 → undo 恢复部署
    log.warning(
        "Gate [%s] rollback NOT verified: baseline also fails after rollback "
        "(status=%s) — failure is independent of deployment; restoring deployed src/",
        step_key, rerun.status,
    )
    if deployed_after:
        try:
            apply_deployed_after(project_dir, deployed_after)
        except OSError as e:
            log.error("Undo rollback failed: %s — src/ left at baseline!", e)
            return {"action": "rollback_undo_failed", "rerun": rerun, "run_id": backup_run_id}
    return {
        "action": "gate_failed_independent",
        "rerun": rerun,
        "run_id": backup_run_id,
    }


def _mark_deploy_regression(project_dir: Path, report: dict) -> None:
    """更新 codegen-deploy 报告: 部署已回滚, deployed 清空, 视为无部署。"""
    try:
        from yuleosh.pipeline.deploy_state import deploy_report_path
        p = deploy_report_path(project_dir)
        report = dict(report)
        report["status"] = "deployed_behavior_regression"
        report["deployed"] = []
        report["guardrail_rolled_back"] = True
        p.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log.info("deploy report updated: status=deployed_behavior_regression (rolled back)")
    except Exception as e:  # pragma: no cover - defensive
        log.error("Failed to update deploy report after rollback: %s", e)


# ---------------------------------------------------------------------------
# OSH_GUARD_PROTECT_SRC (4): 保护用户手动改动的 src
# ---------------------------------------------------------------------------


def src_has_uncommitted_changes(project_dir: str | Path) -> list[str] | None:
    """src/ 是否有 git 未提交改动。

    Returns
    -------
    list[str] | None
        None — 非 git 仓库或 git 不可用 (保护开关下应保守视为有改动? 不,
        调用方按 None=无法判断 处理, 默认不阻断, 只告警)。
        空列表 — src/ 干净。
        非空 — 未提交改动的文件相对路径。
    """
    project_dir = Path(project_dir)
    try:
        import subprocess
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", "src/"],
            capture_output=True, text=True, timeout=10, cwd=project_dir,
            check=False,
        )
        if result.returncode != 0:
            return None
        changed = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # 格式: "XY path" — 取路径部分 (跳过状态码)
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                changed.append(parts[1])
        return changed
    except Exception as e:  # pragma: no cover - defensive
        log.debug("git status check failed: %s", e)
        return None


def protect_src_enabled() -> bool:
    """OSH_GUARD_PROTECT_SRC=1 时保护 src/ (部署前检查未提交改动)。"""
    return os.environ.get("OSH_GUARD_PROTECT_SRC", "0") == "1"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_rel(rel: str) -> str:
    """把相对路径转成安全的文件系统相对路径 (防目录穿越)。"""
    return str(Path(rel)).replace("..", "__")


def _atomic_write(path: Path, content: bytes) -> None:
    """原子写: 先写临时文件再 rename, 防半状态。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(content)
    try:
        os.replace(tmp, path)
    except OSError:
        # 跨设备等极端情况: 回退直接写
        shutil.copyfile(tmp, path)
        tmp.unlink(missing_ok=True)
