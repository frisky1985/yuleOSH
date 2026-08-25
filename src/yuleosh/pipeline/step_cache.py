#!/usr/bin/env python3

# @req RS-001
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step Cache — 确定性步骤内容寻址缓存 (B1, 2026-08-12).

背景 (老板确认方案 C 分级 B1): 修一个 bug 重跑 pipeline 时, 确定性步骤
(编译/测试/静态扫描) 的输入没变却要重跑 20-30 分钟。内容寻址缓存按
「输入指纹」复用这些步骤的产物, 重跑时间从分钟级降到秒级。

设计原则:
  - 只缓存确定性步骤 (verdict 由确定性逻辑决定, 无 LLM 主调用):
    相同输入 → 相同输出, 缓存零风险。
  - LLM 步骤永不缓存 (B2 opt-in 留接口): LLM 有随机性, 缓存会固化
    上次输出, 与「测试即契约」(让 LLM 迭代改进) 冲突。
  - 统一保守指纹 (隐式 DAG): spec + 全部 artifacts + src 树 +
    generated-code 树 + build 树 + ci-config + KG db。任何前置变化
    自然失效, 无需显式依赖传播。
  - 显式不静默: cached 步骤在 session.json 标记 + 打印 ♻️。

禁用: OSH_NO_CACHE=1
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("pipeline.step_cache")

# ---------------------------------------------------------------------------
# 步骤分类
# ---------------------------------------------------------------------------

# 可缓存: verdict 由确定性逻辑决定 (无 LLM 主调用)。
# 注意: review-* 嵌入式审查含 LLM 附加字段 (llm_review), 但 status 由
# 静态扫描决定 → 产物 verdict 确定性成立; 缓存命中时提示附加字段为旧值。
# 2026-08-19 (八轮决策, 24 步重构): 合并后的步骤 key 替换旧 key —
#   qemu-verify 替代 qemu-run + c-coverage-gate（确定性）；
#   verify-loop / code-review 含外部 agent + LLM → 不可缓存 (LLM_STEPS)。
CACHEABLE_STEPS = frozenset({
    "spec-check",
    "codegen-deploy",
    "c-unit-test",
    "misra-review",
    "coverage-review",
    "integration-test",
    "qemu-verify",
    "review-critical-safety",
    "fault-injection",
    "merge-gate",
    "test-qualification",
})

# 失败产物 status 集合 (2026-08-17 r21c 复盘): 这些状态的输出不得入缓存,
# 缓存命中时也视为 miss — 否则失败结果被后续 run 复用, 步骤永远不重跑。
# 不含 "skipped"/"skipped_src_protected"/"empty" — 那些是合法跳过 (planning
# 模式/保护用户代码/无生成物), 输入未变时复用跳过结论是正确的。
FAILED_STATUSES = frozenset({
    "failed",
    "error",
    "skipped_codegen_failed",       # codegen 失败, 护栏拒绝部署
    "skipped_api_mismatch",         # 生成 API 破坏既有契约
    "deployed_behavior_regression", # 部署后行为护栏检测回归 → 已回滚
})

# LLM 主调用步骤: 永不缓存 (B2 opt-in 接口预留)。
# 2026-08-19 (八轮决策, 24 步重构): verify-loop / code-review 为合并步骤
# （内部含外部 agent codex-verify / claude-review + LLM 审查）→ 不可缓存；
# 旧 key (self-test / self-test-review / review-linker 等) 已不再出现在
# PIPELINE_STEPS, 从集合移除（保留 claude-review / test-planning）。
LLM_STEPS = frozenset({
    "super-analysis",
    "prd",
    "prd-review",
    "architecture",
    "arch-review",
    "development",
    "development-review",
    "internal-code-review",
    "claude-review",
    "test-planning",
    "verify-loop",
    "code-review",
    "final-report",
})


def is_cacheable(step_key: str) -> bool:
    """该步骤是否可缓存 (确定性)。"""
    return step_key in CACHEABLE_STEPS


def is_llm_step(step_key: str) -> bool:
    """该步骤是否为 LLM 主调用步骤 (永不缓存)。"""
    return step_key in LLM_STEPS


def cache_enabled() -> bool:
    """缓存总开关: OSH_NO_CACHE=1 禁用。"""
    return os.environ.get("OSH_NO_CACHE", "") != "1"


# ---------------------------------------------------------------------------
# 指纹计算
# ---------------------------------------------------------------------------


def _file_hash(path: Path) -> str:
    """SHA-256 文件哈希 (前 16 hex, 防路径泄露)。"""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        pass
    return h.hexdigest()[:16]


def _tree_hash(root: Path) -> str:
    """递归树哈希: (相对路径 + 文件内容 hash) 排序拼接。

    跳过缓存/元数据目录 (__pycache__/.git/.pytest_cache/.osh 等) 与
    超大文件 (>5MB)。注意: 不跳过所有点开头目录 —— .yuleosh 是项目
    配置/报告目录, 必须计入指纹 (2026-08-12 修正)。
    """
    _SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".osh",
                  "cmake-build", "cmake-build-coverage"}
    if not root.exists():
        return ""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.stat().st_size > 5 * 1024 * 1024:
            continue
        h.update(str(p.relative_to(root)).encode("utf-8"))
        h.update(b":")
        h.update(_file_hash(p).encode("ascii"))
        h.update(b";")
    return h.hexdigest()[:16]


def compute_fingerprint(session, step_key: str) -> str:
    """确定性步骤指纹 — 只含代码/配置/状态, 不含文档 artifacts。

    组件: step_key + spec + src 树 + generated-code 树 + build 树 +
    .yuleosh/reports 树 + ci-config.yaml + knowledge_graph.db。

    设计要点 (2026-08-12 复盘修正):
      - 初版把「全部 session.artifacts」计入指纹 → LLM 文档 (super-analysis/
        prd/architecture) 每次 run 都变 → 确定性步骤永远 miss, 缓存形同虚设。
      - 修正: 代码步骤的输入是代码/配置/状态, 文档变化不应使其失效。
        LLM 文档变化只让 LLM 步骤重跑 (它们本来就不缓存)。
      - 锚定报告 (.yuleosh/reports/codegen-deploy.json) 计入 → codegen 部署
        状态变化时审查步骤正确失效。
    """
    h = hashlib.sha256()
    h.update(step_key.encode("utf-8"))

    # spec (需求变化 → 一切失效)
    spec = Path(session.spec_path)
    h.update(b"spec:")
    h.update(_file_hash(spec).encode("ascii"))
    h.update(b";")

    # 项目代码/产物树
    project_dir = Path(getattr(session, "project_dir", None) or ".")
    h.update(b"src:")
    h.update(_tree_hash(project_dir / "src").encode("ascii"))
    h.update(b";")
    h.update(b"gen:")
    h.update(_tree_hash(project_dir / "artifacts" / "generated-code").encode("ascii"))
    h.update(b";")
    h.update(b"build:")
    h.update(_tree_hash(project_dir / "build").encode("ascii"))
    h.update(b";")

    # 锚定报告 / 门禁报告
    h.update(b"reports:")
    h.update(_tree_hash(project_dir / ".yuleosh" / "reports").encode("ascii"))
    h.update(b";")

    # 配置 / KG 状态
    cfg = project_dir / ".yuleosh" / "ci-config.yaml"
    if cfg.exists():
        h.update(b"cfg:")
        h.update(_file_hash(cfg).encode("ascii"))
        h.update(b";")
    kg = project_dir / ".yuleosh" / "knowledge_graph.db"
    if kg.exists():
        h.update(b"kg:")
        h.update(_file_hash(kg).encode("ascii"))
        h.update(b";")

    return h.hexdigest()


# ---------------------------------------------------------------------------
# 缓存存储: .osh/cache/steps/<step_key>/<fingerprint>/output/<原文件名>
# ---------------------------------------------------------------------------


def _cache_root(project_dir: str | Path) -> Path:
    return Path(project_dir) / ".osh" / "cache" / "steps"


def _output_is_failed(path: Path) -> bool:
    """JSON 产物 status 是否属失败集合 (2026-08-17 r21c 复盘)。

    只对 JSON 产物做检查 (步骤输出多为 json/md/txt); 非 JSON 或无
    status 字段视为非失败 (保持原行为)。
    """
    try:
        if path.suffix.lower() != ".json":
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return str(data.get("status", "")) in FAILED_STATUSES
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        pass
    return False


def _cache_dir_outputs(d: Path) -> list[Path]:
    """缓存目录下 output/ 里的产物文件列表。"""
    out_dir = d / "output"
    if not out_dir.exists():
        return []
    return [p for p in out_dir.iterdir() if p.is_file()]


def lookup(project_dir: str | Path, step_key: str, fingerprint: str) -> Optional[Path]:
    """命中返回缓存目录, 未命中 None。

    2026-08-17 r21c 复盘: 失败产物 (status 属 FAILED_STATUSES) 视为
    miss — 失败缓存被复用会让步骤永远不重跑, 把上一次的 RED 固化进
    后续 run (codegen-deploy skipped_codegen_failed 曾被 r21c 复用)。
    """
    d = _cache_root(project_dir) / step_key / fingerprint
    if d.exists() and (d / "output").exists():
        out_files = _cache_dir_outputs(d)
        if out_files and not any(_output_is_failed(p) for p in out_files):
            return d
    return None


def store(
    project_dir: str | Path,
    step_key: str,
    fingerprint: str,
    output_path: str | Path,
) -> Path:
    """把步骤输出复制进缓存 (保留原文件名), 返回缓存目录。

    2026-08-17 r21c 复盘: 失败产物不入库 — 否则后续 run 指纹命中会
    复用上一次的 RED (codegen-deploy skipped_codegen_failed 曾被 r21c
    缓存命中, codegen 从未重跑, codex-verify 复现同一缺陷)。
    """
    d = _cache_root(project_dir) / step_key / fingerprint
    out = Path(output_path)
    if not out.exists():
        log.warning("step-cache store skipped: output missing %s", out)
        return d
    if _output_is_failed(out):
        log.warning(
            "step-cache store skipped: failed output %s (status in %s)",
            out, sorted(FAILED_STATUSES),
        )
        return d
    out_dir = d / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / out.name
    if dst.exists():
        dst.unlink()
    shutil.copy2(out, dst)
    meta = d / "fingerprint.json"
    meta.write_text(
        json.dumps(
            {
                "step": step_key,
                "fingerprint": fingerprint,
                "stored_at": datetime.now().isoformat(),
                "file": out.name,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info("step-cache stored: %s (%s)", step_key, fingerprint[:10])
    return d


def restore(
    project_dir: str | Path,
    step_key: str,
    fingerprint: str,
    session,
) -> str:
    """把缓存产物恢复到 session dir, 返回恢复路径。"""
    d = lookup(project_dir, step_key, fingerprint)
    if d is None:
        raise FileNotFoundError(
            f"step-cache miss: {step_key} {fingerprint[:10]}"
        )
    src = next((d / "output").iterdir())
    dst = Path(session.session_dir) / src.name
    shutil.copy2(src, dst)
    log.info("step-cache restored: %s → %s (%s)", src.name, dst, fingerprint[:10])
    return str(dst)


# ── Regression Baseline (基线快照, 2026-08-25) ─────────────────────────────
# 目的: 记录上次成功 pipeline run 的指标作为基线; 后续 run 与基线对比,
# 指标下降时发出警告或阻断, 防止「表面 GREEN 实际退步」。
#
# 存储: .yuleosh/baselines/<session_id>/metrics.json + latest_id.txt 指针
# （与 T-004 consistency CLI 的 .yuleosh/baselines/ 惯例保持一致）
# 对比规则:
#   coverage_pct: 下降 > 2% → WARN; 下降 > 5% → ERROR
#   misra_violations: 增加 > 0 → WARN; 增加 > 10 → ERROR
#   test_failed: 增加 > 0 → ERROR
#   gates_passed: 减少 → ERROR

from dataclasses import dataclass as _dc


@_dc
class BaselineMetrics:
    """Pipeline run metrics snapshot for regression comparison."""

    session_id: str
    run_at: str
    coverage_pct: float = 0.0
    misra_violations: int = 0
    test_passed: int = 0
    test_failed: int = 0
    gates_passed: int = 0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "run_at": self.run_at,
            "coverage_pct": self.coverage_pct,
            "misra_violations": self.misra_violations,
            "test_passed": self.test_passed,
            "test_failed": self.test_failed,
            "gates_passed": self.gates_passed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BaselineMetrics":
        return cls(
            session_id=d.get("session_id", ""),
            run_at=d.get("run_at", ""),
            coverage_pct=float(d.get("coverage_pct", 0.0)),
            misra_violations=int(d.get("misra_violations", 0)),
            test_passed=int(d.get("test_passed", 0)),
            test_failed=int(d.get("test_failed", 0)),
            gates_passed=int(d.get("gates_passed", 0)),
        )


def _baseline_root(project_dir) -> Path:
    return Path(project_dir) / ".yuleosh" / "baselines"


def save_baseline(
    project_dir, session_id: str, metrics: "BaselineMetrics"
) -> Path:
    """Persist *metrics* as the named baseline and update latest_id.txt pointer."""
    d = _baseline_root(project_dir) / session_id
    d.mkdir(parents=True, exist_ok=True)
    out = d / "metrics.json"
    out.write_text(json.dumps(metrics.to_dict(), indent=2), encoding="utf-8")
    (_baseline_root(project_dir) / "latest_id.txt").write_text(
        session_id, encoding="utf-8"
    )
    return out


def load_latest_baseline(project_dir) -> "Optional[BaselineMetrics]":
    """Load the most recently saved baseline, or None if not present."""
    ptr = _baseline_root(project_dir) / "latest_id.txt"
    if not ptr.exists():
        return None
    session_id = ptr.read_text(encoding="utf-8").strip()
    metrics_path = _baseline_root(project_dir) / session_id / "metrics.json"
    if not metrics_path.exists():
        return None
    try:
        return BaselineMetrics.from_dict(
            json.loads(metrics_path.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def compare_to_baseline(
    current: "BaselineMetrics", baseline: "BaselineMetrics"
) -> dict:
    """Compare *current* run metrics against *baseline*.

    Returns {status: "pass"|"warn"|"error", issues: [...]}
    """
    issues: list[dict] = []

    def _issue(metric, bval, cval, delta, severity):
        issues.append({
            "metric": metric,
            "baseline_val": bval,
            "current_val": cval,
            "delta": delta,
            "severity": severity,
        })

    cov_delta = current.coverage_pct - baseline.coverage_pct
    if cov_delta < -5:
        _issue("coverage_pct", baseline.coverage_pct, current.coverage_pct, cov_delta, "ERROR")
    elif cov_delta < -2:
        _issue("coverage_pct", baseline.coverage_pct, current.coverage_pct, cov_delta, "WARN")

    misra_delta = current.misra_violations - baseline.misra_violations
    if misra_delta > 10:
        _issue("misra_violations", baseline.misra_violations, current.misra_violations, misra_delta, "ERROR")
    elif misra_delta > 0:
        _issue("misra_violations", baseline.misra_violations, current.misra_violations, misra_delta, "WARN")

    fail_delta = current.test_failed - baseline.test_failed
    if fail_delta > 0:
        _issue("test_failed", baseline.test_failed, current.test_failed, fail_delta, "ERROR")

    gate_delta = current.gates_passed - baseline.gates_passed
    if gate_delta < 0:
        _issue("gates_passed", baseline.gates_passed, current.gates_passed, gate_delta, "ERROR")

    has_error = any(i["severity"] == "ERROR" for i in issues)
    has_warn = any(i["severity"] == "WARN" for i in issues)
    return {
        "status": "error" if has_error else ("warn" if has_warn else "pass"),
        "issues": issues,
    }


def extract_metrics_from_session(session_dir: Path) -> "BaselineMetrics":
    """Extract pipeline metrics from a completed session directory.

    Reads gate-summary.json, coverage report, MISRA report.
    Gracefully defaults to 0 when files are absent.
    """
    session_id = session_dir.name

    gates_passed = 0
    gate_summary = session_dir / "gate-summary.json"
    if gate_summary.exists():
        try:
            gs = json.loads(gate_summary.read_text(encoding="utf-8"))
            gates = gs.get("gates") or gs.get("results") or []
            if isinstance(gates, list):
                gates_passed = sum(
                    1 for g in gates
                    if isinstance(g, dict) and g.get("status") == "passed"
                )
            elif isinstance(gates, dict):
                gates_passed = sum(
                    1 for v in gates.values()
                    if isinstance(v, dict) and v.get("status") == "passed"
                )
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    coverage_pct = 0.0
    for cov_name in ("coverage-report.json", "coverage.json", "c-coverage.json"):
        cov_path = session_dir / cov_name
        if cov_path.exists():
            try:
                cov_data = json.loads(cov_path.read_text(encoding="utf-8"))
                totals = cov_data.get("totals") or cov_data
                raw = float(
                    totals.get("percent_covered")
                    or totals.get("line_rate", 0)
                    or 0
                )
                coverage_pct = raw * 100.0 if raw <= 1.0 else raw
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
            break

    misra_violations = 0
    for misra_name in ("misra-report.json", "misra-review.json"):
        mp = session_dir / misra_name
        if mp.exists():
            try:
                md = json.loads(mp.read_text(encoding="utf-8"))
                misra_violations = int(
                    md.get("violation_count") or md.get("total_violations") or 0
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
            break

    test_passed = test_failed = 0
    for test_name in ("test-results.json", "unit-test.json", "c-unit-test.json"):
        tp = session_dir / test_name
        if tp.exists():
            try:
                td = json.loads(tp.read_text(encoding="utf-8"))
                test_passed = int(td.get("passed") or td.get("tests_passed") or 0)
                test_failed = int(td.get("failed") or td.get("tests_failed") or 0)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
            break

    return BaselineMetrics(
        session_id=session_id,
        run_at=datetime.now().isoformat(),
        coverage_pct=coverage_pct,
        misra_violations=misra_violations,
        test_passed=test_passed,
        test_failed=test_failed,
        gates_passed=gates_passed,
    )
