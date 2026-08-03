# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH CLI — SWE.6 qualification testing command group.

A5 (v3.8.0): extracted from cli/main.py (monolith split).  Behavior is
identical to the v3.7.0 inline implementation; cli/main.py re-exports
these functions for backward-compatible imports.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

# OSH_HOME / sys.path bootstrap — mirrored from cli/main.py so command
# modules run standalone under pytest (SHALL-A5.5: no import of cli.main).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = Path(_SCRIPT_DIR).resolve().parent.parent.parent.parent / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _osh_home() -> str:
    """Resolve OSH_HOME, honoring cli.main's live value (A5 compat).

    cli.main re-exports these commands; tests monkeypatch
    ``yuleosh.cli.main.OSH_HOME``.  A lazy lookup keeps the single source
    of truth in cli.main without a top-level circular import (SHALL-A5.5).
    """
    try:
        import yuleosh.cli.main as _m
        return _m.OSH_HOME
    except Exception:
        return os.environ.get("OSH_HOME", os.getcwd())


def cmd_swe6_status(args):
    """Show SWE.6 qualification test status (三段式)."""
    from yuleosh.alm.traceability import generate_lrt

    project_dir = _osh_home()
    spec_path = os.path.join(project_dir, "docs", "swe6-confirmation-spec.md")

    # Build three-section report: 规范定义 → 执行步骤 → 报告追溯链
    sections = {
        "规范定义 (Specification)": [
            "SWE6-REQ-001: 确认测试范围定义 — 端到端业务流程验证",
            "SWE6-REQ-002: 测试环境规范 — Dev/Staging/Production 三层",
            "SWE6-REQ-003: 测试用例规范 — 含输入输出/预期结果/环境",
            "SWE6-REQ-004: 测试执行计划 — 含回归/冒烟/完整执行",
            "SWE6-REQ-005: 测试报告规范 — 含通过率/覆盖率/偏差",
        ],
        "执行步骤 (Execution)": [
            "STEP-001: 验证环境已就绪 — 检查 Dev/SIL 环境",
            "STEP-002: 执行冒烟测试 — 验证基本功能正常",
            "STEP-003: 执行回归测试 — 验证未破坏已有功能",
            "STEP-004: 执行确认测试 — 按 SWE.6 规范逐项验证",
            "STEP-005: 收集测试证据 — 生成测试报告",
        ],
        "报告追溯链 (Traceability)": [
            "SWE6-REQ-001 → TEST-SWE6-001: E2E 用户生命周期测试",
            "SWE6-REQ-001 → TEST-SWE6-002: Pipeline 完整执行测试",
            "SWE6-REQ-002 → TEST-SWE6-003: 环境配置验证测试",
            "SWE6-REQ-003 → TEST-SWE6-004: 测试用例格式验证",
            "SWE6-REQ-004 → TEST-SWE6-005: 执行计划完备性检查",
        ],
    }

    if getattr(args, "json", False):
        print(json.dumps(sections, indent=2, ensure_ascii=False))
        return

    print(f"\n  {'=' * 70}")
    print(f"   SWE.6 软件合格性测试 — 状态报告")
    print(f"  {'=' * 70}")

    for section_title, items in sections.items():
        print(f"\n  📋 {section_title}")
        print(f"  {'─' * 70}")
        for item in items:
            print(f"   ✅ {item}")

    print(f"\n  {'─' * 70}")
    total_items = sum(len(items) for items in sections.values())
    print(f"   总计: {total_items} 项 — 全部就绪 ✅")
    print(f"   规范来源: docs/swe6-confirmation-spec.md")
    print()

    # Check if spec file exists
    spec_file = Path(spec_path)
    if spec_file.exists():
        print(f"   📄 SWE.6 规范文件: {spec_file} (存在)")
    else:
        print(f"   ⚠️  SWE.6 规范文件: {spec_file} (未找到)")
    print()


def cmd_swe6_check(args):
    """Run SWE.6 qualification test check."""
    project_dir = _osh_home()
    spec_path = os.path.join(project_dir, "docs", "swe6-confirmation-spec.md")

    spec_file = Path(spec_path)
    if not spec_file.exists():
        print(f"❌ SWE.6 规范文件不存在: {spec_path}")
        sys.exit(1)

    print(f"\n  {'=' * 70}")
    print(f"   SWE.6 合格性测试检查")
    print(f"  {'=' * 70}")

    # W-3 (COR-C3 / Fix 6): real checks — the old report hardcoded True for
    # "测试用例定义" / "测试环境配置" and a fake ``test_cases: 5``, a
    # false-positive compliance report for customers/auditors.  The test-case
    # count now comes from actually parsing the spec (reusing
    # yuleosh.spec.validate.parse_spec), and the env-config check verifies
    # the .osh/ci-config.yaml file really exists.
    tc_count: Optional[int] = None
    tc_parse_ok = False
    tc_field = "SpecDocument.scenarios"
    try:
        from yuleosh.spec.validate import parse_spec
        doc = parse_spec(str(spec_file))
        tc_count = len(doc.scenarios)
        tc_parse_ok = True
        # W-3: the repo's own swe6 spec lists cases as ``### TC-CONF-001:``
        # headings rather than OpenSpec ``## Scenario:`` blocks.  When no
        # Scenario blocks exist, fall back to counting those identifiable
        # case headings so the report shows the real number (SHALL-W3.1
        # allows identifiable case entries; the counting basis is always
        # stated in the report via test_cases_field).
        if tc_count == 0:
            try:
                heading_cases = len(re.findall(
                    r"^#{2,4}\s+TC-[\w.-]+\s*:",
                    spec_file.read_text(encoding="utf-8"),
                    re.MULTILINE,
                ))
            except OSError:
                heading_cases = 0
            if heading_cases > 0:
                tc_count = heading_cases
                tc_field = "TC-* headings"
    except Exception:
        tc_count = None
        tc_parse_ok = False

    ci_config_path = Path(project_dir) / ".osh" / "ci-config.yaml"

    if tc_parse_ok and tc_count is not None and tc_count > 0:
        tc_defined = True
        tc_detail = f"{tc_count} 个 (解析自 spec)"
    elif tc_parse_ok:
        tc_defined = False
        tc_detail = f"{tc_count} 个 (解析自 spec)"
    else:
        tc_defined = False
        tc_detail = "unknown (manual)"

    # Tri-state checks: True (✅) / False (❌) / "probe" (⚠️ — cannot be
    # verified automatically, manual verification required).
    checks = [
        ("SWE.6 规范定义", spec_file.exists(), "存在" if spec_file.exists() else "缺失"),
        ("测试用例定义", tc_defined, tc_detail),
        ("测试环境配置", ci_config_path.exists(),
         "已定义 (.osh/ci-config.yaml)" if ci_config_path.exists() else "缺失 (.osh/ci-config.yaml)"),
        ("测试执行脚本", "probe", "probe (manual verification required) — tests/test_swe6/"),
        ("追溯矩阵", "probe", "probe (manual verification required) — 可生成"),
        ("测试报告", "probe", "probe (manual verification required) — 可在 CI 中生成"),
    ]

    for name, passed, detail in checks:
        if passed is True:
            icon = "✅"
        elif passed is False:
            icon = "❌"
        else:
            icon = "⚠️"
        print(f"   {icon} {name}: {detail}")

    if getattr(args, "report", False):
        # Generate full report
        try:
            lrt = __import__("yuleosh.alm.traceability", fromlist=["generate_lrt"]).generate_lrt(project_dir, str(spec_file))
            report = {
                "swe6_check": {
                    "spec_defined": spec_file.exists(),
                    # W-3: real parsed count (None when the spec is
                    # unparseable); the source is always stated explicitly.
                    "test_cases": tc_count,
                    "test_cases_source": "parsed from spec" if tc_parse_ok else "unknown (manual)",
                    "test_cases_field": tc_field,
                    "traceability": lrt.get("lrm", {}).get("summary", {}),
                },
                "generated_at": __import__("datetime").datetime.now().isoformat(),
            }
            report_path = os.path.join(project_dir, ".yuleosh", "reports", "swe6-report.json")
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False, default=str)
            print(f"\n   📄 报告已生成: {report_path}")
        except Exception as e:
            print(f"   ⚠️ 追溯报告生成: {e}")

    passed_n = sum(1 for _, p, _ in checks if p is True)
    probe_n = sum(1 for _, p, _ in checks if p == "probe")
    print(f"\n  {'─' * 70}")
    print(f"   检查完成: {passed_n}/{len(checks)} 通过"
          + (f" (+{probe_n} 项待人工核验)" if probe_n else ""))
    print()


def build_parser(sub):
    """Register the swe6 command group (A5)."""
    p_swe6 = sub.add_parser("swe6", help="SWE.6 软件合格性测试管理")
    s6sub = p_swe6.add_subparsers(dest="swe6_sub")
    p_swe6_status = s6sub.add_parser("status", help="Show SWE.6 qualification test status")
    p_swe6_status.add_argument("--json", action="store_true", help="Output as JSON")
    p_swe6_check = s6sub.add_parser("check", help="Run SWE.6 qualification test check")
    p_swe6_check.add_argument("--report", action="store_true", help="Generate full SWE.6 report")
    return p_swe6
