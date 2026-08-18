# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""SWC 软件编程规范 code-style 扫描器测试.

覆盖:
- 各检查器: 缩进/TAB/行宽/一行一语句/控制大括号/宏括号/宏全大写/单字符变量/
  类型前缀/常量左值/goto/注释量
- CI stage 行为: 非阻断默认 / block_on 阻断 / 无规则文件跳过
- pre-commit hook 集成: staged 文件扫描 + 快照对比
- build_code_review_prompt style_rules 注入 (空字符串 = 不注入)
"""

import json
from pathlib import Path

from yuleosh.ci.stages.code_style import (
    _comment_ratio,
    _load_rules,
    format_style_rules_for_review,
    run_code_style,
    scan_file,
    scan_project,
)


def _lines(text: str):
    return [(i + 1, ln) for i, ln in enumerate(text.splitlines())]


def _stripped(text: str):
    return _lines(text)


class TestIndent:
    def test_4_space_multiple_ok(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("int main(void)\n{\n    return 0;\n}\n")
        result = scan_file(src)
        assert not [v for v in result.violations if v.rule_id == "1-1"]

    def test_2_space_indent_violation(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("int main(void)\n{\n  return 0;\n}\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "1-1"]
        assert vios, "2-space indent must be flagged"
        assert "4 的倍数" in vios[0].message

    def test_tab_indent_counts_as_violation_or_tab(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("int main(void)\n{\n\treturn 0;\n}\n")
        result = scan_file(src)
        tab_vios = [v for v in result.violations if v.rule_id == "1-8"]
        assert tab_vios, "TAB must be flagged by 1-8"


class TestLineLength:
    def test_short_line_ok(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("int counter = 1;\n")
        result = scan_file(src)
        # 仅检查行宽相关规则（2-1 注释量/3-4 单字符等其它规则不在此断言）
        assert not [v for v in result.violations if v.rule_id == "1-3"]

    def test_long_code_line_violation(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("int result = some_function_call(arg1, arg2, arg3, arg4, arg5, arg6, arg7, arg8, arg9);\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "1-3"]
        assert vios, ">80 char code line must be flagged"
        assert vios[0].line == 1

    def test_long_comment_line_not_flagged(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("// " + "x" * 120 + "\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "1-3"]
        assert not vios, "long comment line should not be flagged"

    def test_long_string_literal_not_flagged(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text('const char *msg = "' + "y" * 100 + '";\n')
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "1-3"]
        assert not vios, "long string literal should not be flagged"


class TestOneStatement:
    def test_two_statements_one_line(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("a = 1; b = 2;\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "1-6"]
        assert vios

    def test_single_statement_ok(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("a = 1;\n")
        assert not [v for v in scan_file(src).violations if v.rule_id == "1-6"]


class TestControlBraces:
    def test_if_without_braces(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("if (x) return;\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "1-7"]
        assert vios, "if without braces must be flagged"

    def test_if_with_braces_ok(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("if (x)\n{\n    return;\n}\n")
        assert not [v for v in scan_file(src).violations if v.rule_id == "1-7"]


class TestNoTab:
    def test_tab_flagged(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("int x;\tint y;\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "1-8"]
        assert vios


class TestMacroUpper:
    def test_lowercase_macro(self, tmp_path):
        src = Path(tmp_path) / "a.h"
        src.write_text("#define lock_timeout 1000\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "3-7"]
        assert vios, "lowercase macro must be flagged"

    def test_upper_macro_ok(self, tmp_path):
        src = Path(tmp_path) / "a.h"
        src.write_text("#define LOCK_TIMEOUT 1000\n")
        assert not [v for v in scan_file(src).violations if v.rule_id == "3-7"]


class TestMacroParens:
    def test_macro_without_parens(self, tmp_path):
        src = Path(tmp_path) / "a.h"
        src.write_text("#define RECT_AREA(a, b) a * b\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "7-1"]
        assert vios, "macro expression without parens must be flagged"

    def test_macro_with_parens_ok(self, tmp_path):
        src = Path(tmp_path) / "a.h"
        src.write_text("#define RECT_AREA(a, b) ((a) * (b))\n")
        assert not [v for v in scan_file(src).violations if v.rule_id == "7-1"]

    def test_macro_multi_stmt_braces(self, tmp_path):
        src = Path(tmp_path) / "a.h"
        src.write_text("#define INIT_RECT(a, b) \\\n    a = 0; \\\n    b = 0;\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "7-2"]
        assert vios, "multi-statement macro without braces must be flagged"


class TestSingleCharVar:
    def test_single_char_var(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("int a = 1;\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "3-4"]
        assert vios, "single char var must be flagged"

    def test_named_var_ok(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("int counter = 1;\n")
        assert not [v for v in scan_file(src).violations if v.rule_id == "3-4"]


class TestTypePrefix:
    def test_missing_prefix(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("uint16_t speed = 100;\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "3-6"]
        assert vios, "uint16_t var without uw/u16 prefix must be flagged"

    def test_with_prefix_ok(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("uint16_t uwSpeed = 100;\n")
        assert not [v for v in scan_file(src).violations if v.rule_id == "3-6"]

    def test_no_duplicate_reports(self, tmp_path):
        """uint16_t 同时匹配 uw 和 u16 前缀规则, 只能报一次。"""
        src = Path(tmp_path) / "a.c"
        src.write_text("uint16_t speed = 100;\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "3-6"]
        assert len(vios) == 1


class TestConstLeft:
    def test_const_right_flagged(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("if (x == 5)\n{\n}\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "11-19"]
        assert vios, "const on right must be flagged (info)"

    def test_const_left_ok(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("if (5 == x)\n{\n}\n")
        assert not [v for v in scan_file(src).violations if v.rule_id == "11-19"]


class TestNoGoto:
    def test_goto_flagged(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("goto error_exit;\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "11-18"]
        assert vios


class TestMacroParamMutation:
    def test_macro_with_increment(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("b = SQUARE(a++);\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "7-3"]
        assert vios, "macro call with ++ arg must be flagged"


class TestCommentRatio:
    def test_low_comment_ratio(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("int x = 1;\nint y = 2;\nint z = 3;\nint w = 4;\n")
        result = scan_file(src)
        vios = [v for v in result.violations if v.rule_id == "2-1"]
        assert vios, "low comment ratio must be flagged"

    def test_high_comment_ratio_ok(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("/* header comment block with enough chars */\nint x = 1;\n// line comment\n")
        assert not [v for v in scan_file(src).violations if v.rule_id == "2-1"]


class TestCommentRatioHelper:
    def test_ratio_calculation(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("// aaa\nint x;\n")
        ratio = _comment_ratio(src, "a.c", _lines(src.read_text()))
        assert ratio is not None
        assert ratio["comment_chars"] > 0

    def test_empty_file(self, tmp_path):
        src = Path(tmp_path) / "a.c"
        src.write_text("")
        ratio = _comment_ratio(src, "a.c", _lines(""))
        assert ratio is None or ratio["total_chars"] == 0


class TestRulesLoader:
    def test_load_real_ruleset(self):
        """真实 swc-c-rules.yaml 必须可加载且含 218 条规则。"""
        repo_root = Path(__file__).resolve().parent.parent.parent
        rules = _load_rules(repo_root / "swc-c-rules.yaml")
        assert rules, "swc-c-rules.yaml must exist at repo root"
        assert len(rules) >= 200
        # 32 条 auto_checkable code_style 规则
        auto = [r for r in rules.values() if r.get("auto_checkable")]
        assert len(auto) >= 30


class TestScanProject:
    def test_ignores_build_dirs(self, tmp_path):
        """排除集必须跳过 build*/cmake 等构建产物目录。"""
        proj = tmp_path / "proj"
        (proj / "src").mkdir(parents=True)
        (proj / "build-review").mkdir(parents=True)
        (proj / "cmake").mkdir(parents=True)
        (proj / "src" / "main.c").write_text("int main(void) { return 0; }\n")
        (proj / "build-review" / "gen.c").write_text("int gen = 1;\n")
        result = scan_project(proj)
        files_scanned = {v.file for v in result.violations}
        # 即使 gen.c 有违规也不应出现在结果中（目录被排除）
        assert not any("build-review" in f for f in files_scanned)


class TestStage:
    def _make_ci(self):
        from yuleosh.ci.result import CIResult
        return CIResult(1, "test")

    def test_no_rules_file_skips(self, tmp_path):
        """无 swc-c-rules.yaml → stage 跳过, 不失败 (不破坏 pipeline)。"""
        proj = tmp_path / "proj"
        proj.mkdir()
        ci = self._make_ci()
        ok = run_code_style(str(proj), ci)
        assert ok is True
        # 平台约定: skip 不记录 stages
        assert ci.stages == []

    def test_violations_non_blocking_default(self, tmp_path):
        """有违规但未配置 block_on → stage 通过 (warning, 不记录 stages)。"""
        proj = tmp_path / "proj"
        (proj / "src").mkdir(parents=True)
        (proj / "src" / "main.c").write_text("uint16_t bad = 1;\n")
        # 复制规则文件到项目根
        repo_root = Path(__file__).resolve().parent.parent.parent
        import shutil
        shutil.copy(repo_root / "swc-c-rules.yaml", proj / "swc-c-rules.yaml")
        ci = self._make_ci()
        ok = run_code_style(str(proj), ci)
        assert ok is True
        # 平台约定: warning 不记录 stages (仅 failure/error)
        assert ci.stages == []

    def test_block_on_violations(self, tmp_path):
        """显式 block_on=True → stage 失败。"""
        proj = tmp_path / "proj"
        (proj / "src").mkdir(parents=True)
        (proj / "src" / "main.c").write_text("uint16_t bad = 1;\n")
        repo_root = Path(__file__).resolve().parent.parent.parent
        import shutil
        shutil.copy(repo_root / "swc-c-rules.yaml", proj / "swc-c-rules.yaml")
        ci = self._make_ci()
        ok = run_code_style(str(proj), ci, block_on_violations=True)
        assert ok is False
        assert ci.stages[-1]["status"] == "failed"

    def test_report_written(self, tmp_path):
        proj = tmp_path / "proj"
        (proj / "src").mkdir(parents=True)
        (proj / "src" / "main.c").write_text("int main(void) { return 0; }\n")
        repo_root = Path(__file__).resolve().parent.parent.parent
        import shutil
        shutil.copy(repo_root / "swc-c-rules.yaml", proj / "swc-c-rules.yaml")
        ci = self._make_ci()
        run_code_style(str(proj), ci)
        report_path = proj / ".yuleosh" / "reports" / "code-style-report.json"
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert "summary" in data
        assert "violations" in data


class TestStyleRulesInjection:
    def test_format_style_rules(self):
        """从真实规则集提取 manual_review 规则文本。"""
        repo_root = Path(__file__).resolve().parent.parent.parent
        text = format_style_rules_for_review(repo_root / "swc-c-rules.yaml")
        assert text, "manual_review rules must be extracted"
        assert "软件编程规范" in text
        assert "manual" not in text  # 只含语义规则

    def test_empty_when_no_rules(self, tmp_path):
        text = format_style_rules_for_review(tmp_path / "missing.yaml")
        assert text == ""

    def test_prompt_injection_backward_compat(self):
        """style_rules 默认空 → prompt 与之前一致 (无 SWC 段落)。"""
        from yuleosh.pipeline.prompts import build_code_review_prompt
        _sys_p, user_p = build_code_review_prompt(
            spec_content="spec",
            spec_name="spec.md",
            session_name="s1",
            artifact_contents={},
            source_files=[],
            timestamp="ts",
        )
        assert "SWC" not in user_p

    def test_prompt_injection_with_rules(self):
        from yuleosh.pipeline.prompts import build_code_review_prompt
        _sys_p, user_p = build_code_review_prompt(
            spec_content="spec",
            spec_name="spec.md",
            session_name="s1",
            artifact_contents={},
            source_files=[],
            timestamp="ts",
            style_rules="SWC rule text",
        )
        assert "SWC" in user_p
        assert "SWC rule text" in user_p


class TestPreCommitHook:
    def test_code_style_hook_non_blocking(self, tmp_path):
        """hook 的 code-style 部分异常/违规都不返回非零。"""
        from yuleosh.hooks.pre_commit import _run_code_style_hook
        # 不存在的规则文件 → 静默跳过
        _run_code_style_hook(tmp_path, [str(tmp_path / "x.c")])  # 不应抛异常
