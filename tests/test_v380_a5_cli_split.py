# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""v3.8.0 Track2 — A5 CLI 拆分验收测试（acceptance-matrix T-A5-*）。

覆盖:
  - T-A5-01..04 四命令组迁移后行为保持（parser 装配 + 可调用）
  - T-A5-05 CLI 测试全绿（import 路径兼容）
  - T-A5-06-neg tests/ 无 sys.path.insert（A-P2-05 清理）
  - T-A5-07 parser 参数契约
  - T-A5-08-neg 无复制逻辑（共享 helper 单份）
  - T-A5-09 main.py ≤ 1200 行
  - T-A5-10-neg 无循环导入
"""

import subprocess
import sys
from pathlib import Path


class TestA5CommandsMoved:
    """T-A5-01..04 — 四命令组可经 cli.main 与 commands 模块调用."""

    def test_traceability_cmds(self):
        import yuleosh.cli.main as m
        from yuleosh.cli.commands.traceability import (
            cmd_traceability_report, cmd_traceability_export,
            cmd_traceability_matrix,
        )
        assert m.cmd_traceability_report is cmd_traceability_report
        assert m.cmd_traceability_export is cmd_traceability_export
        assert m.cmd_traceability_matrix is cmd_traceability_matrix

    def test_misra_cmds(self):
        import yuleosh.cli.main as m
        from yuleosh.cli.commands.misra import (
            cmd_misra_deviate, cmd_misra_trend, cmd_misra_profile_list,
            cmd_misra_profile_set, cmd_misra_report,
        )
        assert m.cmd_misra_deviate is cmd_misra_deviate
        assert m.cmd_misra_trend is cmd_misra_trend
        assert m.cmd_misra_profile_list is cmd_misra_profile_list
        assert m.cmd_misra_profile_set is cmd_misra_profile_set
        assert m.cmd_misra_report is cmd_misra_report

    def test_swe6_cmds(self):
        import yuleosh.cli.main as m
        from yuleosh.cli.commands.swe6 import cmd_swe6_status, cmd_swe6_check
        assert m.cmd_swe6_status is cmd_swe6_status
        assert m.cmd_swe6_check is cmd_swe6_check

    def test_review_diff_cmd(self):
        import yuleosh.cli.main as m
        from yuleosh.cli.commands.review_diff import cmd_review_diff
        assert m.cmd_review_diff is cmd_review_diff


class TestA5ParserContract:
    """T-A5-07 — parser 参数契约."""

    def test_subcommand_tree(self):
        import yuleosh.cli.main as m
        p = m._build_parser()
        subs = p._subparsers._group_actions[0].choices
        for grp in ("traceability", "misra", "swe6", "review"):
            assert grp in subs
        tr = subs["traceability"]._subparsers._group_actions[0].choices
        assert set(tr.keys()) == {"report", "matrix", "export"}
        ms = subs["misra"]._subparsers._group_actions[0].choices
        assert set(ms.keys()) == {"trend", "report", "profile", "deviate"}
        s6 = subs["swe6"]._subparsers._group_actions[0].choices
        assert set(s6.keys()) == {"status", "check"}
        rv = subs["review"]._subparsers._group_actions[0].choices
        assert set(rv.keys()) == {"auto", "task", "diff"}

    def test_help_runs(self):
        """yuleosh --help 与各子命令 --help 正常退出 0."""
        repo = Path(__file__).resolve().parent.parent
        for args in (["--help"], ["misra", "--help"], ["swe6", "--help"],
                     ["traceability", "--help"], ["review", "diff", "--help"]):
            r = subprocess.run(
                [sys.executable, "-m", "yuleosh.cli.main"] + args,
                cwd=str(repo), env={"PYTHONPATH": str(repo / "src"),
                                    "PATH": "/usr/bin:/bin",
                                    "OSH_HOME": str(repo)},
                capture_output=True, text=True, timeout=60,
            )
            assert r.returncode == 0, f"{args}: rc={r.returncode} {r.stderr[-300:]}"


class TestA5NoSysPath:
    """T-A5-06-neg — tests/ 无 sys.path.insert（A-P2-05 清理）."""

    def test_no_sys_path_insert_in_tests(self):
        hits = []
        for p in (Path(__file__).resolve().parent).rglob("*.py"):
            if p.name == "test_v380_a5_cli_split.py":
                continue  # this file's own docs mention the literal
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if "sys.path.insert" in line:
                    hits.append(f"{p.name}:{i}")
        assert hits == [], f"tests/ sys.path.insert 残留: {hits}"


class TestA5NoCopy:
    """T-A5-08-neg — 共享 helper 无复制."""

    def test_ensure_tool_deps_single_copy(self):
        src_root = Path(__file__).resolve().parent.parent / "src"
        hits = []
        for p in src_root.rglob("*.py"):
            if p.name == "main.py" or "commands" in str(p):
                hits.append(str(p.relative_to(src_root.parent)))
        # _ensure_tool_deps 定义应仅存在于 cli/main.py（未随组复制）
        count = 0
        for p in src_root.rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            if "def _ensure_tool_deps" in text:
                count += 1
        assert count == 1, f"_ensure_tool_deps 定义 {count} 份"


class TestA5MainSlim:
    """T-A5-09 — main.py ≤ 1200 行."""

    def test_main_slim(self):
        p = Path(__file__).resolve().parent.parent / "src/yuleosh/cli/main.py"
        lines = len(p.read_text(encoding="utf-8").splitlines())
        assert lines <= 1200, f"main.py {lines} 行 > 1200"


class TestA5NoCycle:
    """T-A5-10-neg — 无循环导入."""

    def test_cold_import_all_modules(self):
        import yuleosh.cli.main
        import yuleosh.cli.commands.traceability
        import yuleosh.cli.commands.misra
        import yuleosh.cli.commands.swe6
        import yuleosh.cli.commands.review_diff
        assert yuleosh.cli.main is not None
