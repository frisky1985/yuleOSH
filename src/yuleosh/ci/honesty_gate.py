#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
诚实性自检门禁 — Honesty Self-Check Gates (brainstorm-quality-guard-2026-08-08).

防回退套件的「门禁端」：一组注入式可红可绿的检查器。每个检查器对
「被注入假数据」的项目必须返回 failed（门禁红），对干净项目返回
passed/skipped。任一门禁在注入后仍绿 = 假绿复发 → 套件失败。

用例映射（brainstorm-quality-guard-2026-08-08 §1.2）:
  H1 空报告注入        → check_empty_evidence
  H3 缺失产物注入      → check_missing_artifacts
  H4 过期时间戳注入    → check_result_freshness   （本次新增 gate）
  H8 报告数字不一致注入 → check_misra_consistency  （本次新增 gate）
  H2/H5/H6/H7 已有单测覆盖（test_compliance_no_fake_green.py /
  test_mock_gate_no_fake_pass.py / test_security.py），此处不重复实现。

用法:
    python -m yuleosh.ci.honesty_gate <project_dir>   # 退出码 0=绿 1=红
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.honesty_gate")

# 门禁检查器返回 (status, messages)；status ∈ {"passed","failed","skipped"}


def _age_days(ts: str) -> Optional[float]:
    """Parse ISO timestamp → age in days (float). None if unparseable."""
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def check_empty_evidence(project_dir: str) -> tuple[str, list[str]]:
    """H1: 空自报对象（仅 type+status，无实质内容）不得撑绿。"""
    ev_dir = Path(project_dir) / ".osh" / "evidence"
    if not ev_dir.exists():
        return "skipped", ["no evidence dir — skip"]

    substantive_keys = {
        "title", "details", "verdict", "content", "findings", "items",
        "checks", "requirement", "score", "evidence", "description",
    }
    flagged: list[str] = []
    for f in sorted(ev_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and "type" in data and "status" in data:
            if not any(k in data for k in substantive_keys):
                flagged.append(f.name)

    if flagged:
        return "failed", [f"empty self-report objects: {', '.join(flagged)}"]
    return "passed", ["all evidence substantive"]


def check_missing_artifacts(project_dir: str) -> tuple[str, list[str]]:
    """H3: 缺失产物不得静默跳过（有结构缺文件 → 红）。"""
    required = [
        ".yuleosh/reports/misra-report.json",
        ".osh/evidence/manifest.json",
    ]
    has_structure = (
        (Path(project_dir) / ".yuleosh" / "reports").exists()
        or (Path(project_dir) / ".osh" / "evidence").exists()
    )
    if not has_structure:
        return "skipped", ["no CI artifact structure — skip"]

    missing = [rel for rel in required if not (Path(project_dir) / rel).exists()]
    if missing:
        return "failed", [f"required artifacts missing: {', '.join(missing)}"]
    return "passed", ["all required artifacts present"]


def check_result_freshness(
    project_dir: str, max_age_days: int = 30,
) -> tuple[str, list[str]]:
    """H4: CI 结果新鲜度 — 超过 *max_age_days* 天视为失效（门禁红）。

    扫描 ``.osh/ci/*.json`` 与 ``.yuleosh/reports/*.json`` 的
    completed_at/started_at/generated_at/timestamp 字段。
    """
    stale: list[str] = []
    checked = 0
    for rel_dir in (".osh/ci", ".yuleosh/reports"):
        base = Path(project_dir) / rel_dir
        if not base.exists():
            continue
        for f in base.glob("*.json"):
            try:
                data = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            ts = (
                data.get("completed_at") or data.get("started_at")
                or data.get("generated_at") or data.get("timestamp")
            )
            if not ts:
                continue
            age = _age_days(str(ts))
            if age is None:
                continue
            checked += 1
            if age > max_age_days:
                stale.append(f"{rel_dir}/{f.name}: {ts} ({age:.1f}d old)")

    if checked == 0 and not stale:
        return "skipped", ["no dated CI artifacts — skip"]
    if stale:
        return "failed", [f"stale CI results (> {max_age_days}d): {len(stale)}"]
    return "passed", [f"all {checked} CI artifacts fresh"]


def check_misra_consistency(project_dir: str) -> tuple[str, list[str]]:
    """H8: 报告数字必须可溯源 — total_violations 与 violations_raw 一致。"""
    report_path = Path(project_dir) / ".yuleosh" / "reports" / "misra-report.json"
    if not report_path.exists():
        return "skipped", ["no misra-report.json — skip"]

    try:
        data = json.loads(report_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return "failed", [f"misra-report.json unreadable: {e}"]

    total = data.get("total_violations")
    raw = data.get("violations_raw")
    issues: list[str] = []
    if total is not None and isinstance(raw, list) and total != len(raw):
        issues.append(f"total_violations={total} != violations_raw len={len(raw)}")
    groups = data.get("groups") or {}
    if isinstance(groups, dict) and isinstance(raw, list):
        raw_by_rule: dict = {}
        for v in raw:
            rid = v.get("rule_id", "")
            raw_by_rule[rid] = raw_by_rule.get(rid, 0) + 1
        for rid, g in groups.items():
            gcount = g.get("count", g.get("total")) if isinstance(g, dict) else None
            if gcount is not None and gcount != raw_by_rule.get(rid, 0):
                issues.append(f"groups[{rid}].count={gcount} != raw={raw_by_rule.get(rid, 0)}")

    if issues:
        return "failed", issues
    return "passed", ["misra-report consistent"]


def check_coverage_branch_data(project_dir: str) -> tuple[str, list[str]]:
    """H9: branch gate 配置了但无 branch 数据 → 红（防 0.0>=0.0 假绿旁路）。

    当 ci-config 设置了 c_fail_under_branch（branch gate 开启）而 coverage
    报告 totals.branches.found == 0（编译未开 branch 插桩）时，门禁必须红
    而不是 0.0 >= 0.0 真空通过。
    """
    # 1. 读取 ci-config 判断 branch gate 是否开启
    try:
        from yuleosh.ci.config import _get_ci_config
        cfg = _get_ci_config(str(project_dir))
        branch_gate = getattr(cfg.coverage, "c_fail_under_branch", None)
    except Exception:  # noqa: BLE001 — 读不到配置视为 branch gate 关闭（fail-open）
        branch_gate = None
    if branch_gate is None:
        return "skipped", ["no c_fail_under_branch configured — branch gate off"]

    # 2. 读取 coverage 报告
    report_path = Path(project_dir) / ".yuleosh" / "reports" / "c-coverage.json"
    if not report_path.exists():
        return "skipped", ["no c-coverage.json — skip"]

    try:
        data = json.loads(report_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return "failed", [f"c-coverage.json unreadable: {e}"]

    totals = data.get("totals") or {}
    branches = totals.get("branches") or {}
    found = branches.get("found", 0)
    branch_rate = data.get("branch_rate", 0.0)

    if found == 0:
        return "failed", [
            (
                f"branch gate configured ({branch_gate}) but no branch data "
                f"(found=0, branch_rate={branch_rate}); compile with "
                f"--coverage/--branch-probabilities to enable branch coverage"
            ),
        ]
    if branch_rate < branch_gate:
        return "failed", [f"branch_rate={branch_rate} < c_fail_under_branch={branch_gate}"]
    return "passed", [f"branch data present (found={found}), rate={branch_rate} >= {branch_gate}"]


ALL_CHECKS = {
    "empty-evidence": check_empty_evidence,
    "missing-artifacts": check_missing_artifacts,
    "freshness": check_result_freshness,
    "misra-consistency": check_misra_consistency,
    "coverage-branch-data": check_coverage_branch_data,
}


def run_honesty_gate(project_dir: str, ci=None) -> bool:
    """Run all honesty gates. Returns True if no gate failed.

    ``ci`` (optional CIResult) receives one stage per gate so the checks
    surface in layer reports like any other CI stage.
    """
    all_ok = True
    for name, fn in ALL_CHECKS.items():
        try:
            status, msgs = fn(project_dir)
        except Exception as e:  # pragma: no cover — defensive
            status, msgs = "failed", [str(e)]
        detail = "; ".join(msgs)
        if ci is not None:
            ci.add_stage(f"honesty-{name}", status, detail)
        print(f"    [honesty:{name}] {status}: {detail}")
        if status == "failed":
            all_ok = False
    return all_ok


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="yuleOSH honesty self-check gates")
    parser.add_argument("project_dir", nargs="?", default=".",
                        help="project root (default: current dir)")
    args = parser.parse_args(argv)

    ok = run_honesty_gate(args.project_dir)
    print(f"\n{'✅' if ok else '❌'} Honesty gate: {'ALL PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
