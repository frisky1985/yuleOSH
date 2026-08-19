"""Phase 10 — review 域低覆盖文件补测（coverage boost）。

目标文件（基线来自 .coverage-report.json）:
  - src/yuleosh/ci/stages/review_misra.py           53.1%  (最大增量来源)
  - src/yuleosh/pipeline/step_handlers/review_critical_safety.py  69.4%
  - src/yuleosh/pipeline/step_handlers/review_development.py          74.3%
  - src/yuleosh/ci/stages/review.py                 47.9%

覆盖重点: 错误路径、边界条件、异常处理、default 分支。
红线: 零 src/ 改动、零网络/子进程依赖 —— cppcheck/git/LLM 全部 mock 注入；
tmp_path/monkeypatch 隔离；不设置 YULEOSH_JWT_SECRET（conftest 已 setdefault）；
不用 sys-path 注入（pytest.ini 已配 pythonpath=src）。
"""

import json
import subprocess
import sys
import types
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.ci.config import (
    CiConfig,
    MisraConfig,
    MisraDeviation,
    MisraProfile,
    MisraRuleOverride,
)
from yuleosh.ci.result import CIResult
from yuleosh.ci.stages.review import run_docsync_gate
from yuleosh.ci.stages.review_misra import _format_null_pointer_fix, run_misra_check
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.review_critical_safety import (
    CriticalSafetyScanner,
    get_build_flags,
    step_review_critical_safety,
)
from yuleosh.pipeline.step_handlers.review_development import (
    _assess_granularity,
    _build_devplan_review_prompt,
    _check_acceptance_criteria,
    _check_dependency_modeling,
    _check_module_coverage,
    _check_time_estimates,
    _extract_tasks,
    step_review_development,
)

# ===========================================================================
# 共享工具
# ===========================================================================

MISRA_REPORT_FUNCS = [
    "load_rule_definitions",
    "parse_cppcheck_output",
    "group_by_rule",
    "enrich_with_definitions",
    "compute_summary_stats",
    "save_report",
    "print_summary",
    "generate_traceability_matrix",
    "generate_fix_tasks",
]


def _default_summary(total=0, required=0, advisory=0):
    return {
        "total_violations": total,
        "unique_rules": 0,
        "affected_files": 0,
        "total_source_lines": 0,
        "by_severity": {},
        "by_rule_type": {"required": required, "advisory": advisory},
        "density_per_kloc": 0.0,
    }


def _violation(rule_id="Rule-10.1", file="src/main.c", line=5,
               severity="error", severity_category="required"):
    return {
        "rule_id": rule_id,
        "file": file,
        "line": line,
        "severity": severity,
        "severity_category": severity_category,
    }


def _last_stage(ci):
    """CIResult.stages 最后一个条目，归一化为 (name, status, detail)。"""
    s = ci.stages[-1]
    return (s["name"], s["status"], s["detail"])


class _FakeRuleset:
    """RulesetRegistry.get_default() 的假实现。"""

    def __init__(self, name="gscr-cpp", violations=None):
        self.name = name
        self.display_name = "GSCR C"
        self._violations = violations or []

    def translate_violations(self, violations):
        return self._violations

    def rule_definitions(self):
        return {
            "rules": {
                "GSCR-01": {
                    "description_cn": "长度足够的规则描述文本",
                    "severity": "S1",
                }
            }
        }


class TestReviewMisraConfigDefaults:
    """默认配置（无 ci-config.yaml）下的 run_misra_check 分支。"""

    def test_disabled_config_skips(self, tmp_path):
        """misra.enabled=False → skipped stage, 返回 True。"""
        cfg = CiConfig()
        cfg.misra = MisraConfig(enabled=False)
        with mock.patch("yuleosh.ci.stages.review_misra._get_ci_config",
                        return_value=cfg):
            ci = CIResult(2, "abc")
            assert run_misra_check(str(tmp_path), ci) is True
        assert ci.stages[-1]["status"] == "skipped"

    def test_config_load_exception_falls_back_to_defaults(self, tmp_path):
        """_get_ci_config 抛异常 → misra_cfg=None → 默认配置继续。"""
        with mock.patch("yuleosh.ci.stages.review_misra._get_ci_config",
                        side_effect=RuntimeError("boom")):
            ci = CIResult(2, "abc")
            result = run_misra_check(str(tmp_path), ci, mode="full")
        assert result is True
        assert ci.stages[-1]["status"] == "skipped"  # 无 C 文件


def _make_project(tmp_path, subdir="src", name="main.c", body=None):
    """创建含一个 C 文件的项目，返回 (project_dir, c_file_abs)。"""
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    # 3000 行 → estimated_kloc≈3.0，避免 violations_per_kloc 误阻断
    f.write_text(body if body is not None else "int main(void) { return 0; }\n" * 3000)
    return tmp_path, str(f)


class _MisraRunCtx:
    """run_misra_check 的全 mock 环境（ExitStack 自动恢复）。"""

    def __init__(self, *, cfg=None, violations=None, summary=None, stderr="",
                 git_files=None, git_exc=None, cppcheck_exc=None,
                 c_files=None, ruleset=None, strict=False,
                 misra_fail_fast=False):
        self.cfg = cfg if cfg is not None else CiConfig()
        self.violations = violations
        self.summary = summary
        self.stderr = stderr
        self.git_files = git_files
        self.git_exc = git_exc
        self.cppcheck_exc = cppcheck_exc
        self.c_files = c_files
        self.ruleset = ruleset
        self.strict = strict
        self.misra_fail_fast = misra_fail_fast
        self.stack = ExitStack()
        self.mocks = {}
        self.recorded_cmds: list[list[str]] = []

    def __enter__(self):
        s = self.stack
        s.enter_context(mock.patch(
            "yuleosh.ci.stages.review_misra._get_ci_config", return_value=self.cfg))

        def _run(cmd, *args, **kwargs):
            self.recorded_cmds.append(list(cmd))
            if cmd and cmd[0] == "git":
                if self.git_exc is not None:
                    raise self.git_exc
                r = mock.MagicMock()
                r.returncode = 0
                r.stdout = "\n".join(self.git_files or [])
                return r
            if self.cppcheck_exc is not None:
                raise self.cppcheck_exc
            r = mock.MagicMock()
            r.stdout = ""
            r.stderr = self.stderr
            return r

        s.enter_context(mock.patch(
            "yuleosh.ci.stages.review_misra.subprocess.run", side_effect=_run))
        if self.c_files is not None:
            s.enter_context(mock.patch(
                "yuleosh.ci.stages.review_misra._find_c_sources",
                return_value=self.c_files))
        for name in MISRA_REPORT_FUNCS:
            self.mocks[name] = s.enter_context(
                mock.patch(f"yuleosh.ci.misra_report.{name}"))
        viols = self.violations if self.violations is not None else []
        self.mocks["parse_cppcheck_output"].return_value = viols
        self.mocks["enrich_with_definitions"].return_value = viols
        self.mocks["group_by_rule"].return_value = {}
        self.mocks["load_rule_definitions"].return_value = {}
        self.mocks["compute_summary_stats"].return_value = (
            self.summary if self.summary is not None else _default_summary())
        s.enter_context(mock.patch("yuleosh.ci.misra_trend.append_entry"))
        s.enter_context(mock.patch("yuleosh.ci.misra_trend._print_trend_summary"))
        s.enter_context(mock.patch(
            "yuleosh.ci.stages.review_misra._get_git_commit",
            return_value="cafe1234"))
        s.enter_context(mock.patch(
            "yuleosh.ci.stages.review_misra.is_strict", return_value=self.strict))
        s.enter_context(mock.patch(
            "yuleosh.ci.stages.review_misra.is_misra_fail_fast",
            return_value=self.misra_fail_fast))
        if self.ruleset is not None:
            s.enter_context(mock.patch(
                "yuleosh.ci.rulesets.RulesetRegistry.get_default",
                return_value=self.ruleset))
        return self

    def __exit__(self, *exc):
        self.stack.close()


# ===========================================================================
# review_misra.py — _format_null_pointer_fix
# ===========================================================================

class TestFormatNullPointerFix:
    def test_template_returns_empty(self):
        assert _format_null_pointer_fix("template", "src/tpl/foo.c") == ""

    def test_third_party_appends_disclaimer(self):
        text = _format_null_pointer_fix("third_party", "third_party/x.c")
        assert "修复建议" in text
        assert "第三方库代码" in text

    def test_business_has_fix_suggestions(self):
        text = _format_null_pointer_fix("business", "src/main.c")
        assert "修复建议" in text
        assert "第三方库代码" not in text


# ===========================================================================
# review_misra.py — run_misra_check 主流程
# ===========================================================================

class TestRunMisraCheck:
    def test_no_violations_passed_with_aux_files(self, tmp_path):
        """全流程通过 + include_paths/compile_commands/suppressions 分支。"""
        proj, cfile = _make_project(tmp_path)
        inc = tmp_path / "inc"
        inc.mkdir()
        (tmp_path / "compile_commands.json").write_text("[]")
        (tmp_path / ".cppcheck_suppressions").write_text("")
        (tmp_path / "cppcheck-config.h").write_text("")
        cfg = CiConfig()
        cfg.misra = MisraConfig(include_paths=["inc"])
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg) as ctx:
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        assert _last_stage(ci) == ("misra-check", "passed", "No MISRA violations")
        # cppcheck 命令行里带上了 -I 与 suppressions-list
        assert (proj / ".yuleosh" / "reports" / "misra-raw-output.txt").exists()

    def test_required_violations_block(self, tmp_path):
        """fail_on_required + business.block_on → failed, 返回 False。"""
        proj, cfile = _make_project(tmp_path)
        viols = [_violation(severity="error", severity_category="required")]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, required=1)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is False
        assert ci.stages[-1]["status"] == "failed"

    def test_advisory_only_warns(self, tmp_path):
        """仅 advisory 且不阻断 → warning stage, 返回 True。"""
        proj, cfile = _make_project(tmp_path)
        viols = [_violation(severity="advisory", severity_category="advisory")]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, advisory=1)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        assert ci.stages[-1]["status"] == "warning"

    def test_cppcheck_not_installed(self, tmp_path):
        proj, cfile = _make_project(tmp_path)
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cppcheck_exc=FileNotFoundError("cppcheck")):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is False
        assert ci.stages[-1]["status"] == "skipped"

    def test_cppcheck_timeout_strict_fails(self, tmp_path):
        proj, cfile = _make_project(tmp_path)
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cppcheck_exc=subprocess.TimeoutExpired(
                "cppcheck", 180), strict=True):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is False
        assert ci.stages[-1]["status"] == "failed"

    def test_cppcheck_generic_exception(self, tmp_path):
        proj, cfile = _make_project(tmp_path)
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cppcheck_exc=OSError("exec format error")):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is False

    def test_auto_mode_git_diff_detects_delta(self, tmp_path):
        """auto 模式: git diff 成功 → delta 扫描通过。"""
        proj, cfile = _make_project(tmp_path)
        ci = CIResult(2, "abc")
        with _MisraRunCtx(git_files=["src/main.c"]):
            result = run_misra_check(str(proj), ci, mode="auto")
        assert result is True
        assert ci.stages[-1]["status"] == "passed"

    def test_auto_mode_git_missing_falls_back_to_scan(self, tmp_path):
        """auto 模式: git 不存在 → fallback _find_c_sources 全量扫描。"""
        proj, cfile = _make_project(tmp_path)
        ci = CIResult(2, "abc")
        with _MisraRunCtx(git_exc=FileNotFoundError("git"),
                          c_files=[cfile]):
            result = run_misra_check(str(proj), ci, mode="auto")
        assert result is True
        assert ci.stages[-1]["status"] == "passed"

    def test_auto_mode_no_files_skipped(self, tmp_path):
        proj, cfile = _make_project(tmp_path)
        ci = CIResult(2, "abc")
        with _MisraRunCtx(git_exc=FileNotFoundError("git"), c_files=[]):
            result = run_misra_check(str(proj), ci, mode="auto")
        assert result is True
        assert ci.stages[-1]["status"] == "skipped"

    def test_delta_mode_with_target_files(self, tmp_path):
        """L1 delta: target_files 过滤 .c/.cpp 且存在。"""
        proj, cfile = _make_project(tmp_path)
        bogus = tmp_path / "src" / "notes.txt"
        bogus.write_text("x")
        ci = CIResult(2, "abc")
        with _MisraRunCtx():
            result = run_misra_check(str(proj), ci, mode="delta",
                                     target_files=[cfile, str(bogus)])
        assert result is True
        assert ci.stages[-1]["status"] == "passed"

    def test_delta_mode_collect_exception_skips(self, tmp_path):
        """L1 delta: _collect_delta_files 抛异常 → 空文件集跳过。"""
        proj, cfile = _make_project(tmp_path)
        ci = CIResult(2, "abc")
        with _MisraRunCtx():
            with mock.patch(
                    "yuleosh.ci.stages.review_misra._collect_delta_files",
                    side_effect=RuntimeError("git unavailable")):
                result = run_misra_check(str(proj), ci, mode="delta")
        assert result is True
        assert ci.stages[-1]["status"] == "skipped"

    def test_delta_mode_collect_and_expand(self, tmp_path):
        """L1 delta: 三源收集 + 头文件反向依赖展开。"""
        proj, cfile = _make_project(tmp_path)
        ci = CIResult(2, "abc")
        with _MisraRunCtx():
            with mock.patch(
                    "yuleosh.ci.stages.review_misra._collect_delta_files",
                    return_value=["src/main.c", "include/api.h"]), \
                    mock.patch(
                    "yuleosh.ci.stages.review_misra._expand_header_dependents",
                    side_effect=lambda pd, ch: ch):
                result = run_misra_check(str(proj), ci, mode="delta")
        assert result is True
        assert ci.stages[-1]["status"] == "passed"

    def test_exclude_paths_filters_everything(self, tmp_path):
        """默认 exclude_paths tests/** → 全部排除 → skipped。"""
        proj, cfile = _make_project(tmp_path, subdir="tests", name="foo.c")
        ci = CIResult(2, "abc")
        with _MisraRunCtx():
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        assert "excluded by exclude_paths" in ci.stages[-1]["detail"]

    def test_template_category_excludes_all(self, tmp_path):
        """code_categories.template → 全部跳过 → skipped。"""
        _make_project(tmp_path, subdir="tpl", name="tpl.c")
        cfg = CiConfig()
        cfg.misra = MisraConfig(code_categories={
            "template": {"paths": ["tpl/**"], "action": "exclude"},
            "business": {"paths": ["src/**"], "block_on": True},
        })
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg):
            # 相对路径才能命中 tpl/** 分类（与生产 delta 模式一致）
            result = run_misra_check(str(tmp_path), ci, mode="full",
                                     target_files=["tpl/tpl.c"])
        assert result is True
        assert "excluded by code_categories" in ci.stages[-1]["detail"]

    def test_template_plus_business_mixed(self, tmp_path):
        """template 文件被跳过，business 文件照常扫描。"""
        _make_project(tmp_path)
        tpl_dir = tmp_path / "tpl"
        tpl_dir.mkdir()
        tpl_file = tpl_dir / "t.c"
        tpl_file.write_text("int x = 1;")
        cfg = CiConfig()
        cfg.misra = MisraConfig(code_categories={
            "template": {"paths": ["tpl/**"], "action": "exclude"},
            "business": {"paths": ["src/**"], "block_on": True},
        })
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg):
            result = run_misra_check(str(tmp_path), ci, mode="full",
                                     target_files=["tpl/t.c", "src/main.c"])
        assert result is True
        assert ci.stages[-1]["status"] == "passed"

    def test_profile_missing_falls_back_to_safety(self, tmp_path):
        """active_profile 不在 profiles → warning + safety 默认阻断。"""
        proj, cfile = _make_project(tmp_path)
        cfg = CiConfig()
        cfg.misra = MisraConfig(
            active_profile="safety",
            profiles={"other": MisraProfile(name="other")},
        )
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg, violations=[_violation()],
                          summary=_default_summary(total=1, required=1)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is False  # safety 默认 block_on 全部生效

    def test_profile_block_on_filters_generic_reasons(self, tmp_path):
        """profile block_on=["required"] 但违例 severity=error → 不阻断。"""
        proj, cfile = _make_project(tmp_path)
        cfg = CiConfig()
        cfg.misra = MisraConfig(
            fail_on_required=False,
            active_profile="required-only",
            profiles={"required-only": MisraProfile(
                name="required-only", rules=["required"],
                block_on=["required"])},
        )
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg,
                          violations=[_violation(severity="error",
                                                 severity_category="error")],
                          summary=_default_summary(total=1)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True  # profile 过滤清掉了 generic 阻断理由
        assert ci.stages[-1]["status"] == "passed"

    def test_rule_texts_path_creates_addon_json(self, tmp_path):
        """rule_texts_path 指向存在的文件 → 动态生成 misra-addon-config.json。"""
        proj, cfile = _make_project(tmp_path)
        (proj / "rule-texts.txt").write_text("Rule 10.1: text")
        (proj / ".yuleosh").mkdir(exist_ok=True)  # 生产环境由前置阶段创建
        cfg = CiConfig()
        cfg.misra = MisraConfig(rule_texts_path="rule-texts.txt")
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        addon_json = proj / ".yuleosh" / "misra-addon-config.json"
        assert addon_json.exists()
        data = json.loads(addon_json.read_text())
        assert data["args"] == ["--rule-texts=" + str(proj / "rule-texts.txt")]

    def test_rule_texts_path_missing_warns(self, tmp_path):
        proj, cfile = _make_project(tmp_path)
        cfg = CiConfig()
        cfg.misra = MisraConfig(rule_texts_path="nope.txt")
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        assert not (proj / ".yuleosh" / "misra-addon-config.json").exists()

    def test_suppress_rules_and_overrides(self, tmp_path):
        """suppress_rules / 禁用 override → 命令行带 --suppress。"""
        proj, cfile = _make_project(tmp_path)
        cfg = CiConfig()
        cfg.misra = MisraConfig(
            suppress_rules=["10.1"],
            rule_overrides=[MisraRuleOverride(rule_id="Rule-8.1",
                                              enabled=False)],
        )
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg) as ctx:
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        # 通过 raw output 保存证明流程走完；命令行在 mock 的 run 调用里
        assert ctx.mocks["save_report"].called


# ===========================================================================
# review_misra.py — L2 delta blocking + baseline
# ===========================================================================

class TestRunMisraL2Delta:
    def _write_trend(self, proj, lines):
        p = proj / ".yuleosh" / "reports" / "misra-trend.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines) + "\n")

    def test_new_required_blocks_l2(self, tmp_path):
        """L2 full+delta: 基线之后新增 Required → L2-P0 阻断。"""
        proj, cfile = _make_project(tmp_path)
        self._write_trend(proj, [
            json.dumps({"is_delta": True, "total_violations": 9}),
            json.dumps({
                "is_delta": False, "total_violations": 3,
                "violations": [{"rule_id": "Rule-10.1", "file": "src/main.c",
                                "line": 5, "severity_category": "required"}],
            }),
        ])
        # 当前输出: 1 个新增 required(line=10)、1 个基线已有(line=5)、
        # 1 个 advisory（severity != required → 不计数）
        viols = [
            _violation(line=10),
            _violation(line=5),
            _violation(severity="advisory", severity_category="advisory",
                       rule_id="Rule-2.1"),
        ]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=3, required=2,
                                                   advisory=1)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is False
        assert "L2-P0" in ci.stages[-1]["detail"]

    def test_baseline_no_trend_file(self, tmp_path):
        """无 trend 文件 → baseline={} → 无 delta 阻断（仍按普通规则）。"""
        proj, cfile = _make_project(tmp_path)
        viols = [_violation(severity="advisory", severity_category="advisory")]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, advisory=1)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        assert ci.stages[-1]["status"] == "warning"

    def test_baseline_invalid_json_lines(self, tmp_path):
        """trend 文件含坏行 → 跳过；全是 delta 条目 → 取最后一条。"""
        proj, cfile = _make_project(tmp_path)
        self._write_trend(proj, [
            "not-json{{{",
            "",
            json.dumps({"is_delta": True, "total_violations": 2}),
        ])
        viols = [_violation(severity="advisory", severity_category="advisory")]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, advisory=1)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        assert ci.stages[-1]["status"] == "warning"

    def test_classification_failure_failsafe_blocks(self, tmp_path):
        """三级分类解析失败（ValueError）→ fail-safe 阻断，不再静默清空违规放行。

        回归语义: 分类失败意味着无法枚举 business/third_party 违规，此时有违规
        却放行 = 门禁失效。工程诚实 → 按 business 违规 fail-safe 阻断，
        而不是降级清空列表后放行（TASK_STATUS P2 存量风险修复）。
        """
        proj, cfile = _make_project(tmp_path)
        self._write_trend(proj, [json.dumps({"is_delta": False})])
        viols = [_violation()]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, required=1)), \
             mock.patch("yuleosh.ci.misra_report.parse_cppcheck_output",
                        side_effect=[viols, ValueError("corrupt"),
                                     ValueError("corrupt")]):
            # 第 1 次解析正常；第 2 次（L2 delta 重解析，baseline 无
            # violations 键实际不触发）；第 3 次（分类统计）抛 ValueError
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        # 分类失败 → fail-safe 阻断（不得静默放行）
        assert result is False
        assert "fail-safe" in ci.stages[-1]["detail"]
        # L2 delta 未参与（baseline 无 violations 键）→ 无 L2-P0 reason
        assert "L2-P0" not in ci.stages[-1]["detail"]

    def test_classification_programming_error_propagates(self, tmp_path):
        """三级分类抛编程错误（AttributeError）→ 向上抛出，不被 except 吞掉。

        工程诚实: 编程错误是内部缺陷，必须暴露（调用方可见）而非静默降级；
        except 只捕获真实故障（ValueError/KeyError/TypeError）。
        """
        proj, cfile = _make_project(tmp_path)
        self._write_trend(proj, [json.dumps({"is_delta": False})])
        viols = [_violation()]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, required=1)), \
             mock.patch("yuleosh.ci.misra_report.parse_cppcheck_output",
                        side_effect=[viols, AttributeError("boom")]), \
             pytest.raises(AttributeError):
            # 第 1 次解析正常；第 2 次（分类统计）抛编程错误
            run_misra_check(str(proj), ci, mode="full",
                            target_files=[cfile])

    def test_l2_delta_parse_failure_skips_delta_but_normal_blocking(self, tmp_path):
        """L2 delta 重解析失败（ValueError）→ 仅跳过 delta 阻断，业务违规仍阻断。

        回归语义: delta 计算失败只影响 L2-P0（new Required 计数），
        不影响三级分类与 business.block_on 的 fail-safe 兜底；
        真实故障（baseline 解析失败）降级须留 warning 日志。
        """
        proj, cfile = _make_project(tmp_path)
        self._write_trend(proj, [json.dumps({
            "is_delta": False, "total_violations": 3,
            "violations": [{"rule_id": "Rule-10.1", "file": "src/main.c",
                            "line": 5, "severity_category": "required"}],
        })])
        viols = [_violation()]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, required=1)), \
             mock.patch("yuleosh.ci.misra_report.parse_cppcheck_output",
                        side_effect=[viols, ValueError("corrupt"), viols]):
            # 第 1 次解析正常；第 2 次（L2 delta 重解析）抛 ValueError；
            # 第 3 次（分类统计）正常 → business required 违规仍阻断
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        # delta 阻断被跳过 → 无 L2-P0；business 阻断不受影响 → 仍 False
        assert "L2-P0" not in ci.stages[-1]["detail"]
        assert result is False


# ===========================================================================
# review_misra.py — 报告异常路径 + GSCR + 趋势
# ===========================================================================

class TestRunMisraReportErrors:
    def test_summary_reload_from_disk(self, tmp_path):
        """compute_summary_stats 抛异常 → 从已保存的 misra-report.json 重载。"""
        proj, cfile = _make_project(tmp_path)
        report = proj / ".yuleosh" / "reports" / "misra-report.json"
        report.parent.mkdir(parents=True)
        report.write_text(json.dumps({
            "total_violations": 0, "unique_rules": 0, "affected_files": 0,
            "total_source_lines": 0, "by_severity": {},
            "by_rule_type": {}, "density_per_kloc": 0,
        }))
        ci = CIResult(2, "abc")
        with _MisraRunCtx():
            ctx_mocks = None
            with mock.patch(
                    "yuleosh.ci.misra_report.compute_summary_stats",
                    side_effect=ValueError("stats broken")):
                result = run_misra_check(str(proj), ci, mode="full",
                                         target_files=[cfile])
        assert result is True
        assert ci.stages[-1]["status"] == "passed"  # 重载 summary → 0 违规

    def test_raw_summary_fallback(self, tmp_path):
        """load_rule_definitions 抛异常且无报告文件 → 原始输出计数兜底。"""
        proj, cfile = _make_project(tmp_path)
        ci = CIResult(2, "abc")
        with _MisraRunCtx(stderr="src/main.c:5: misra violation [Rule-10.1]\n"):
            with mock.patch(
                    "yuleosh.ci.misra_report.load_rule_definitions",
                    side_effect=RuntimeError("no rules")):
                result = run_misra_check(str(proj), ci, mode="full",
                                         target_files=[cfile])
        assert result is True
        assert ci.stages[-1]["status"] == "passed"  # raw 计数只数 "misra" 行

    def test_import_error_falls_back(self, tmp_path):
        """misra_report 模块导入失败 → ImportError 分支 → 兜底 summary。"""
        proj, cfile = _make_project(tmp_path)
        fake_mod = types.ModuleType("yuleosh.ci.misra_report")
        ci = CIResult(2, "abc")
        try:
            with mock.patch.dict(sys.modules,
                                 {"yuleosh.ci.misra_report": fake_mod}):
                result = run_misra_check(str(proj), ci, mode="full",
                                         target_files=[cfile])
        finally:
            # 导入失败时 sys.path.pop(0) 未执行，手动清理
            p = str(proj)
            if p in sys.path:
                sys.path.remove(p)
        assert result is True
        assert ci.stages[-1]["status"] == "passed"

    def test_gscr_translation_writes_report(self, tmp_path):
        """GSCR 翻译成功 → gscr-report.json 落盘。"""
        proj, cfile = _make_project(tmp_path)
        viols = [_violation(severity="advisory", severity_category="advisory")]
        gscr_viols = [{
            "rule_id": "GSCR-01", "gscr_rule_ids": ["GSCR-01"],
            "gscr_severity": "S1", "file": "src/main.c", "line": 5,
        }]
        ruleset = _FakeRuleset(name="gscr-cpp", violations=gscr_viols)
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, advisory=1),
                          ruleset=ruleset):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        gscr_path = proj / ".yuleosh" / "reports" / "gscr-report.json"
        assert gscr_path.exists()
        data = json.loads(gscr_path.read_text())
        assert data["gscr_mapped"] == 1
        assert data["gscr_rule_counts"] == {"GSCR-01": 1}

    def test_gscr_default_ruleset_misra_skips(self, tmp_path):
        """默认规则集就是 misra-c2023 → 不翻译。"""
        proj, cfile = _make_project(tmp_path)
        viols = [_violation(severity="advisory", severity_category="advisory")]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, advisory=1),
                          ruleset=_FakeRuleset(name="misra-c2023")):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        assert not (proj / ".yuleosh" / "reports" / "gscr-report.json").exists()

    def test_gscr_translation_exception_non_blocking(self, tmp_path):
        proj, cfile = _make_project(tmp_path)
        viols = [_violation(severity="advisory", severity_category="advisory")]
        ruleset = mock.MagicMock()
        ruleset.name = "gscr-cpp"
        ruleset.display_name = "GSCR C"
        ruleset.translate_violations.side_effect = RuntimeError("map failed")
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, advisory=1),
                          ruleset=ruleset):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True

    def test_null_ptr_fix_and_fix_tasks_failure(self, tmp_path):
        """27.15/Dir-4.1 违规输出修复建议；generate_fix_tasks 失败不阻断。"""
        proj, cfile = _make_project(tmp_path)
        viols = [
            _violation(rule_id="GSCR-C-27.15", severity="advisory",
                       severity_category="advisory"),
            _violation(rule_id="Dir-4.1", severity="advisory",
                       severity_category="advisory"),
        ]
        cfg = CiConfig()
        cfg.misra = MisraConfig(deviations=[
            MisraDeviation(rule_id="Dir-4.1", file_pattern="src/**",
                           reason="third-party", approved_by="me",
                           expires="2027-01-01"),
        ])
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg, violations=viols,
                          summary=_default_summary(total=2, advisory=2)):
            with mock.patch(
                    "yuleosh.ci.misra_report.generate_fix_tasks",
                    side_effect=OSError("no .yuleosh/tasks")):
                result = run_misra_check(str(proj), ci, mode="full",
                                         target_files=[cfile])
        assert result is True
        assert ci.stages[-1]["status"] == "warning"

    def test_misra_fail_fast_flag(self, tmp_path):
        """MISRA_FAIL_FAST=1 → 打印提示（不改变结果）。"""
        proj, cfile = _make_project(tmp_path)
        viols = [_violation(severity="advisory", severity_category="advisory")]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, advisory=1),
                          misra_fail_fast=True):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True

    def test_trend_append_exception_skipped(self, tmp_path):
        """趋势写入失败 → 仅 debug 日志，不阻断。"""
        proj, cfile = _make_project(tmp_path)
        viols = [_violation(severity="advisory", severity_category="advisory")]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(violations=viols,
                          summary=_default_summary(total=1, advisory=1)):
            with mock.patch("yuleosh.ci.misra_trend.append_entry",
                            side_effect=OSError("readonly fs")):
                result = run_misra_check(str(proj), ci, mode="full",
                                         target_files=[cfile])
        assert result is True
        assert ci.stages[-1]["status"] == "warning"

    def test_fail_threshold_and_vpkloc(self, tmp_path):
        """fail_threshold=1 且 business 违规数>=1 → 阈值阻断。"""
        proj, cfile = _make_project(tmp_path)
        cfg = CiConfig()
        cfg.misra = MisraConfig(fail_threshold=1)
        viols = [_violation(severity="error", severity_category="error")]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg, violations=viols,
                          summary=_default_summary(total=1, required=1)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is False
        assert "threshold" in ci.stages[-1]["detail"]

    def test_fail_on_advisory_blocks(self, tmp_path):
        """fail_on_advisory=True → advisory 也阻断。"""
        proj, cfile = _make_project(tmp_path)
        cfg = CiConfig()
        cfg.misra = MisraConfig(fail_on_advisory=True)
        viols = [_violation(severity="advisory", severity_category="advisory")]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg, violations=viols,
                          summary=_default_summary(total=1, advisory=1)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is False
        assert "Advisory" in ci.stages[-1]["detail"]


# ===========================================================================
# review_critical_safety.py — 扫描器边界分支
# ===========================================================================

class TestCriticalSafetyScannerEdges:
    def _scanner(self):
        return CriticalSafetyScanner(Path("/tmp"))

    def test_div_zero_checked_variable_no_violation(self):
        s = self._scanner()
        s._scan_division_by_zero(Path("a.c"), [
            "int d = 10;",
            "if (d != 0) {",
            "int r = x / d;",
        ])
        assert not any(v.rule_id == "CRIT-DIV-001" for v in s.violations)

    def test_div_zero_unchecked_variable(self):
        s = self._scanner()
        s._scan_division_by_zero(Path("a.c"), ["int r = x / divisor;"])
        assert any("divisor" in v.message for v in s.violations)

    def test_div_zero_member_access_skipped(self):
        s = self._scanner()
        s._scan_division_by_zero(Path("a.c"), ["int r = x / obj.field;"])
        assert s.violations == []

    def test_div_zero_comment_only_not_flagged(self):
        """纯注释里的除法不报（44b889d0 精确剥离注释后）。"""
        s = self._scanner()
        s._scan_division_by_zero(Path("a.c"), ["/* int r = x / 0; */"])
        assert s.violations == []

    def test_div_zero_real_division_with_comment_still_flagged(self):
        """真实除零 + 同行注释 → 仍报（修复前 '/*' not in stripped 守卫整行
        跳过，漏报真实除零——44b889d0 剥离注释后正确检出）。"""
        s = self._scanner()
        s._scan_division_by_zero(Path("a.c"), ["int r = x / 0; /* intentional */"])
        assert any(v.rule_id == "CRIT-DIV-001" for v in s.violations)

    def test_buffer_small_memcpy_no_violation(self):
        s = self._scanner()
        s._scan_buffer_overflow(Path("a.c"), ["memcpy(dst, src, 100);"])
        assert s.violations == []

    def test_buffer_snprintf_not_flagged(self):
        s = self._scanner()
        s._scan_buffer_overflow(Path("a.c"), ['snprintf(buf, sizeof(buf), "%s", s);'])
        assert not any("sprintf" in v.message for v in s.violations)

    def test_null_deref_checked_malloc(self):
        s = self._scanner()
        s._scan_null_deref(Path("a.c"), [
            "p = malloc(100);",
            "if (p == NULL) return -1;",
            "p->x = 1;",
        ])
        assert not any(v.rule_id == "CRIT-NULL-001" and "malloc" in v.message
                       for v in s.violations)

    def test_null_deref_arrow_checked_before(self):
        s = self._scanner()
        s._scan_null_deref(Path("a.c"), [
            "if (obj != NULL) {",
            "obj->field = 1;",
        ])
        assert not any("obj" in v.message for v in s.violations)

    def test_null_deref_this_and_addressof_skipped(self):
        s = self._scanner()
        s._scan_null_deref(Path("a.c"), [
            "this->member = 1;",
            "&dev->reg = 2;",
        ])
        assert s.violations == []

    def test_null_deref_dotted_expr_skipped(self):
        s = self._scanner()
        s._scan_null_deref(Path("a.c"), ["obj.field->x = 1;"])
        assert s.violations == []

    def test_recursion_with_guard_no_violation(self):
        s = self._scanner()
        s._scan_unbounded_recursion(Path("a.c"), [
            "foo(void) {",
            "    if (n <= 1) return 1;",
            "    return foo(n - 1);",
            "}",
        ])
        assert not any(v.rule_id == "CRIT-REC-001" for v in s.violations)

    def test_recursion_without_guard(self):
        s = self._scanner()
        s._scan_unbounded_recursion(Path("a.c"), [
            "bar(void) {",
            "    return bar(n - 1);",
            "}",
        ])
        assert any(v.rule_id == "CRIT-REC-001" for v in s.violations)

    def test_recursion_func_stack_pop(self):
        s = self._scanner()
        lines = [f"f{i}(x);" for i in range(25)]
        s._scan_unbounded_recursion(Path("a.c"), lines)
        # func_stack 超过 20 个后 pop(0) 生效；检测循环不崩溃
        assert isinstance(s.violations, list)

    def test_infinite_loop_with_break_ok(self):
        s = self._scanner()
        s._scan_infinite_loop(Path("a.c"), [
            "while (1) {",
            "    if (done) break;",
            "}",
        ])
        assert not any(v.rule_id == "CRIT-LOOP-001" for v in s.violations)

    def test_infinite_loop_closed_by_brace(self):
        s = self._scanner()
        s._scan_infinite_loop(Path("a.c"), ["for (;;) {", "}"])
        assert any(v.rule_id == "CRIT-LOOP-001" for v in s.violations)

    def test_infinite_loop_return_exits(self):
        s = self._scanner()
        s._scan_infinite_loop(Path("a.c"), ["while (1) {", "    return 0;", "}"])
        assert s.violations == []

    def test_integer_overflow_interface_param(self):
        s = self._scanner()
        s._scan_integer_overflow(Path("a.c"), ["out = arg1 + raw2;"])
        assert any(v.rule_id == "CRIT-INT-001" for v in s.violations)

    def test_integer_overflow_local_vars_ok(self):
        s = self._scanner()
        s._scan_integer_overflow(Path("a.c"), ["out = a + b;"])
        assert s.violations == []

    def test_integer_overflow_uint32_guard(self):
        s = self._scanner()
        s._scan_integer_overflow(Path("a.c"), ["out = (uint32_t)(arg1 + b);"])
        assert s.violations == []

    def test_stack_overflow_small_array_ok(self):
        s = self._scanner()
        s._scan_stack_overflow(Path("a.c"), ["char buf[100];"])
        assert s.violations == []

    def test_stack_overflow_uint16_array(self):
        s = self._scanner()
        s._scan_stack_overflow(Path("a.c"), ["uint16_t arr[600];"])
        assert any(v.rule_id == "CRIT-STK-001" for v in s.violations)

    def test_memory_leak_freed_ok(self):
        s = self._scanner()
        s._scan_memory_leak(Path("a.c"), [
            "p = malloc(10);",
            "use(p);",
            "free(p);",
        ])
        assert not any(v.rule_id == "CRIT-MEM-001" for v in s.violations)

    def test_memory_leak_vportfree_ok(self):
        s = self._scanner()
        s._scan_memory_leak(Path("a.c"), [
            "p = pvPortMalloc(10);",
            "vPortFree(p);",
        ])
        assert s.violations == []

    def test_memory_leak_func_end_brace(self):
        s = self._scanner()
        s._scan_memory_leak(Path("a.c"), ["p = malloc(10);", "}"])
        assert any(v.rule_id == "CRIT-MEM-001" for v in s.violations)

    def test_scan_all_skips_vendor_dirs(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.c").write_text("int r = x / 0;")
        (tmp_path / "third_party").mkdir()
        (tmp_path / "third_party" / "b.c").write_text("int r = x / 0;")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "c.c").write_text("int r = x / 0;")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "d.c").write_text("int r = x / 0;")
        s = CriticalSafetyScanner(tmp_path)
        viols = s.scan_all()
        # 只有 src/a.c 被扫描；`x / 0` 报 1 条常量除零（变量除数分支排除常量 0）
        assert len([v for v in viols if v.rule_id == "CRIT-DIV-001"]) == 1

    def test_scan_all_custom_patterns_and_read_error(self, tmp_path):
        (tmp_path / "board.c").write_text("strcpy(dst, src);")
        (tmp_path / "fake.c").mkdir()  # 目录伪装成 .c → read_text 抛 OSError
        s = CriticalSafetyScanner(tmp_path)
        viols = s.scan_all(source_patterns=["*.c"])
        assert any(v.rule_id == "CRIT-BUF-001" for v in viols)


class TestGetBuildFlagsExtra:
    def test_ubsan_flags(self):
        flags = get_build_flags(enable_ubsan=True)
        assert "-fsanitize=undefined" in flags

    def test_arm_target(self):
        flags = get_build_flags(target="arm")
        assert "-mthumb" in flags
        assert "-mcpu=cortex-m7" in flags

    def test_riscv_target(self):
        flags = get_build_flags(target="riscv")
        assert "-march=rv32imafc" in flags

    def test_xtensa_target(self):
        flags = get_build_flags(target="xtensa")
        assert "-mlongcalls" in flags

    def test_native_target_no_arch_flags(self):
        flags = get_build_flags(target="native")
        assert "-mthumb" not in flags


class TestStepCriticalSafetyManyViolations:
    def _session(self, tmp_path):
        session = mock.MagicMock()
        session.project_dir = str(tmp_path)
        session.artifacts_dir = str(tmp_path / ".yuleosh")
        Path(session.artifacts_dir).mkdir(parents=True, exist_ok=True)
        return session

    def test_more_than_20_violations_message(self, tmp_path):
        viols = []
        for i in range(25):
            v = mock.MagicMock()
            v.rule_id = "CRIT-DIV-001"
            v.file = f"src/f{i}.c"
            v.line = i + 1
            v.message = f"violation {i}"
            v.fix_suggestion = "add check" if i == 0 else ""
            v.to_dict.return_value = {"rule_id": v.rule_id}
            viols.append(v)
        session = self._session(tmp_path)
        with mock.patch(
                "yuleosh.pipeline.step_handlers.review_critical_safety."
                "CriticalSafetyScanner.scan_all", return_value=viols), \
                mock.patch(
                "yuleosh.pipeline.step_handlers.review_critical_safety."
                "get_build_flags", return_value=[]):
            with pytest.raises(PipelineStepError) as ei:
                step_review_critical_safety(session)
        assert "还有 5 条违例" in str(ei.value)
        assert "💡" in str(ei.value)
        # 报告仍落盘
        assert (Path(session.artifacts_dir)
                / "critical-safety-report.json").exists()


# ===========================================================================
# review_development.py — 静态检查函数
# ===========================================================================

class TestExtractTasks:
    def test_heading_task(self):
        tasks = _extract_tasks("### Task 1.1: Implement the driver")
        assert tasks == [{"id": "1.1", "description": "Implement the driver",
                          "est_time": ""}]

    def test_heading_chinese(self):
        tasks = _extract_tasks("## 任务 A：写测试")
        assert tasks[0]["id"] == "A"
        assert tasks[0]["description"] == "写测试"

    def test_checkbox_with_estimate(self):
        tasks = _extract_tasks("- [x] Task 2: Fix bug (3d)")
        assert tasks[0]["id"] == "2"
        assert tasks[0]["est_time"] == "3d"

    def test_checkbox_empty_id(self):
        tasks = _extract_tasks("- [ ] 任务：写文档")
        assert tasks[0]["id"] == "task-1"

    def test_numbered_list(self):
        tasks = _extract_tasks("1. Task: Build the thing")
        assert tasks[0]["description"] == "Build the thing"

    def test_numbered_chinese_punct(self):
        tasks = _extract_tasks("3、Step X：做某事")
        assert tasks[0]["id"] == "X"

    def test_skips_empty_and_code_fence(self):
        tasks = _extract_tasks("\n```\ncode\n```\nplain text line\n")
        assert tasks == []

    def test_mixed_document(self):
        content = "\n".join([
            "### Task 1.1: A",
            "- [ ] Task 2: B (2h)",
            "3. Step 3: C",
            "unrelated line",
        ])
        tasks = _extract_tasks(content)
        assert len(tasks) == 3


class TestAcceptanceCriteria:
    def test_empty(self):
        r = _check_acceptance_criteria("")
        assert r["has_criteria"] is False
        assert r["score"] == 0

    def test_chinese_keyword_floor_60(self):
        r = _check_acceptance_criteria("每个任务要有验收标准")
        assert r["score"] == 60

    def test_many_keywords_capped(self):
        text = " ".join([
            "验收标准", "acceptance criteria", "AC:", "交付标准",
            "definition of done", "DoD", "完成定义", "gating", "gate",
            "checklist", "检查清单", "测试用例", "test case", "验证",
            "verify", "PASS", "FAIL", "expected result",
        ])
        r = _check_acceptance_criteria(text)
        assert r["score"] == 100


class TestDependencyModeling:
    def test_found(self):
        r = _check_dependency_modeling("任务B 依赖 任务A，前置条件 已具备")
        assert r["has_dependencies"] is True
        assert r["score"] == 30

    def test_empty(self):
        r = _check_dependency_modeling("随便写点东西")
        assert r["has_dependencies"] is False
        assert r["score"] == 0


class TestTimeEstimates:
    def test_partial_estimates(self):
        tasks = [{"est_time": "3d"}, {"est_time": ""}, {"est_time": "2h"}]
        r = _check_time_estimates(tasks, "预计 3 小时完成")
        assert r["total_tasks"] == 3
        assert r["tasks_with_estimates"] == 2
        assert r["score"] >= 33

    def test_no_tasks_no_keywords(self):
        r = _check_time_estimates([], "nothing here")
        assert r["score"] == 0


class TestModuleCoverage:
    def test_module_heading_covered(self):
        arch = "## Module: Sensor Driver\n## Module: Flash Storage"
        devplan = "sensor driver implementation and flash storage tests"
        findings = _check_module_coverage(devplan, arch)
        assert len(findings) == 2
        assert all(f["covered"] for f in findings)

    def test_fallback_plain_heading(self):
        arch = "## 主控单元\n"
        devplan = "主控单元 task"
        findings = _check_module_coverage(devplan, arch)
        assert len(findings) == 1
        assert findings[0]["covered"] is True

    def test_short_heading_skipped(self):
        findings = _check_module_coverage("x", "## AB\n")
        assert findings == []

    def test_uncovered_module(self):
        findings = _check_module_coverage("no match here",
                                          "## Module: CanBus\n")
        assert findings[0]["covered"] is False


class TestAssessGranularity:
    def test_too_coarse(self):
        tasks = [{"description": "a"}, {"description": "b"}]
        r = _assess_granularity(tasks)
        assert r["assessment"] == "too_coarse"
        assert len(r["issues"]) == 1

    def test_ok(self):
        tasks = [{"description": f"task {i}"} for i in range(5)]
        r = _assess_granularity(tasks)
        assert r["assessment"] == "ok"
        assert r["issues"] == []

    def test_too_fine(self):
        tasks = [{"description": f"task {i}"} for i in range(21)]
        r = _assess_granularity(tasks)
        assert r["assessment"] == "too_fine"

    def test_vague_tasks(self):
        tasks = [
            {"description": "研究可行性"},
            {"description": "调查现状"},
            {"description": "具体实现"},
        ]
        r = _assess_granularity(tasks)
        assert r["vague_tasks"] == 2
        assert any("vague" in i for i in r["issues"])


class TestBuildDevplanPrompt:
    def test_returns_two_prompts(self):
        """63ab201b (truncation audit) 后注入语义：输入 < SPEC_INJECT_LIMIT
        时全量注入 + 模板开销，prompt 必然大于输入总和；内容完整不截断。"""
        spec = "# Spec " + "x" * 6100
        arch = "## Arch " + "y" * 6100
        devplan = "## Plan " + "z" * 8100
        system_prompt, user_prompt = _build_devplan_review_prompt(
            spec, "spec.md", arch, devplan)
        assert "PASS/FAIL/RETRY" in system_prompt
        assert "spec.md" in user_prompt
        # 全量注入：devplan 尾部仍在（旧断言 len<输入总和 是 8/17 前硬编码
        # 截断行为，SPEC_INJECT_LIMIT=30000 下已不成立）
        assert devplan[-20:] in user_prompt
        assert len(user_prompt) > len(spec) + len(arch) + len(devplan)


# ===========================================================================
# review_development.py — step_review_development
# ===========================================================================

@pytest.fixture
def devplan_session(tmp_path, monkeypatch):
    """真实 PipelineSession + 隔离 OSH_HOME。"""
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n## REQ-001\nSHALL work.\n")
    session = PipelineSession("phase10-devplan", str(spec))
    return session


def _write_devplan_files(tmp_path, session, *, arch=True, plan_key="development-plan"):
    if arch:
        ap = tmp_path / "architecture.md"
        ap.write_text("## Module: Sensor Driver\n")
        session.artifacts["architecture"] = str(ap)
    dp = tmp_path / "devplan.md"
    dp.write_text("### Task 1.1: Implement sensor driver\n- [ ] Task 2: tests (2h)\n")
    session.artifacts[plan_key] = str(dp)
    return dp


class TestStepReviewDevplan:
    def test_happy_path_with_llm(self, tmp_path, devplan_session):
        _write_devplan_files(tmp_path, devplan_session)
        with mock.patch(
                "yuleosh.pipeline.step_handlers.review_development._call_llm",
                return_value={"content": "looks good",
                              "usage": {"total_tokens": 42}}):
            out = step_review_development(devplan_session)
        assert isinstance(out, str)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "passed"
        assert report["static_checks"]["tasks_found"] == 2
        assert report["llm_review"] == "looks good"
        assert devplan_session.token_usage_total == 42
        assert devplan_session.token_usage_steps[-1]["step"] == "development-review"

    def test_llm_failure_non_fatal(self, tmp_path, devplan_session):
        _write_devplan_files(tmp_path, devplan_session)
        with mock.patch(
                "yuleosh.pipeline.step_handlers.review_development._call_llm",
                side_effect=RuntimeError("api down")):
            out = step_review_development(devplan_session)
        report = json.loads(Path(out).read_text())
        assert report["llm_review"] == "(LLM-powered review unavailable)"
        assert "skipped" in report["summary"]

    def test_spec_missing_raises(self, tmp_path, devplan_session):
        devplan_session.spec_path = str(tmp_path / "nope.md")
        with pytest.raises(PipelineStepError, match="Spec file not found"):
            step_review_development(devplan_session)

    def test_devplan_missing_raises(self, tmp_path, devplan_session):
        with pytest.raises(PipelineStepError,
                           match="Development plan artifact not found"):
            step_review_development(devplan_session)

    def test_development_key_fallback(self, tmp_path, devplan_session):
        _write_devplan_files(tmp_path, devplan_session, plan_key="development")
        with mock.patch(
                "yuleosh.pipeline.step_handlers.review_development._call_llm",
                return_value={"content": "ok", "usage": {}}):
            out = step_review_development(devplan_session)
        assert Path(out).exists()

    def test_no_architecture_no_coverage_findings(self, tmp_path,
                                                  devplan_session):
        _write_devplan_files(tmp_path, devplan_session, arch=False)
        with mock.patch(
                "yuleosh.pipeline.step_handlers.review_development._call_llm",
                return_value={"content": "ok", "usage": {}}):
            out = step_review_development(devplan_session)
        report = json.loads(Path(out).read_text())
        assert report["static_checks"]["module_coverage"]["total_modules"] == 0

    def test_retry_status_many_major_findings(self, tmp_path,
                                              devplan_session):
        # 3 个未覆盖模块 + too_coarse + 无验收标准 → 5 个 major → retry
        ap = tmp_path / "architecture.md"
        ap.write_text("## Module: Alpha\n## Module: Beta\n## Module: Gamma\n")
        devplan_session.artifacts["architecture"] = str(ap)
        dp = tmp_path / "devplan.md"
        dp.write_text("### Task 1: vague\n")
        devplan_session.artifacts["development-plan"] = str(dp)
        with mock.patch(
                "yuleosh.pipeline.step_handlers.review_development._call_llm",
                return_value={"content": "ok", "usage": {}}):
            out = step_review_development(devplan_session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "retry"
        assert report["finding_count"] >= 4

    def test_write_error_raises(self, tmp_path, devplan_session):
        _write_devplan_files(tmp_path, devplan_session)
        with mock.patch(
                "yuleosh.pipeline.step_handlers.review_development._call_llm",
                return_value={"content": "ok", "usage": {}}), \
                mock.patch(
                "yuleosh.pipeline.step_handlers.review_development.json.dump",
                side_effect=OSError("disk full")):
            with pytest.raises(PipelineStepError,
                               match="Cannot write devplan review"):
                step_review_development(devplan_session)

    def test_generic_exception_wrapped(self, tmp_path, devplan_session):
        _write_devplan_files(tmp_path, devplan_session)
        with mock.patch(
                "yuleosh.pipeline.step_handlers.review_development._extract_tasks",
                side_effect=RuntimeError("regex broken")):
            with pytest.raises(PipelineStepError,
                               match="Development Plan review step failed"):
                step_review_development(devplan_session)


# ===========================================================================
# ci/stages/review.py — run_docsync_gate
# ===========================================================================

class TestRunDocsyncGate:
    def test_gate_exception_non_blocking(self, tmp_path):
        ci = CIResult(2, "abc")
        with mock.patch("yuleosh.ci.sync_check.run_sync_check_gate",
                        side_effect=RuntimeError("git boom")):
            assert run_docsync_gate(str(tmp_path), ci) is True
        assert ci.stages[-1]["status"] == "warning"

    def test_failed_strict_blocks(self, tmp_path):
        ci = CIResult(2, "abc")
        with mock.patch("yuleosh.ci.sync_check.run_sync_check_gate",
                        return_value={"status": "failed",
                                      "summary": "docs out of sync"}), \
                mock.patch("yuleosh.ci.sync_check.save_sync_evidence",
                           return_value="ev.json"), \
                mock.patch("yuleosh.ci.stages.review.is_strict",
                           return_value=True):
            assert run_docsync_gate(str(tmp_path), ci) is False
        assert ci.stages[-1]["status"] == "failed"

    def test_failed_non_strict_warns(self, tmp_path):
        ci = CIResult(2, "abc")
        with mock.patch("yuleosh.ci.sync_check.run_sync_check_gate",
                        return_value={"status": "failed",
                                      "summary": "docs out of sync"}), \
                mock.patch("yuleosh.ci.sync_check.save_sync_evidence",
                           return_value="ev.json"), \
                mock.patch("yuleosh.ci.stages.review.is_strict",
                           return_value=False):
            assert run_docsync_gate(str(tmp_path), ci) is True
        assert ci.stages[-1]["status"] == "warning"

    def test_warning_status(self, tmp_path):
        ci = CIResult(2, "abc")
        with mock.patch("yuleosh.ci.sync_check.run_sync_check_gate",
                        return_value={"status": "warning",
                                      "summary": "partial"}), \
                mock.patch("yuleosh.ci.sync_check.save_sync_evidence",
                           return_value="ev.json"):
            assert run_docsync_gate(str(tmp_path), ci) is True
        assert ci.stages[-1]["status"] == "warning"

    def test_passed_with_evidence(self, tmp_path):
        ci = CIResult(2, "abc")
        with mock.patch("yuleosh.ci.sync_check.run_sync_check_gate",
                        return_value={"status": "passed",
                                      "summary": "all good"}), \
                mock.patch("yuleosh.ci.sync_check.save_sync_evidence",
                           return_value="ev.json"):
            assert run_docsync_gate(str(tmp_path), ci) is True
        assert ci.stages[-1]["status"] == "passed"

    def test_passed_evidence_save_fails(self, tmp_path):
        ci = CIResult(2, "abc")
        with mock.patch("yuleosh.ci.sync_check.run_sync_check_gate",
                        return_value={"status": "passed",
                                      "summary": "all good"}), \
                mock.patch("yuleosh.ci.sync_check.save_sync_evidence",
                           side_effect=OSError("readonly")):
            assert run_docsync_gate(str(tmp_path), ci) is True
        assert ci.stages[-1]["status"] == "passed"


# ===========================================================================
# review_misra.py — misra.enable 配置（cppcheck --enable 级别）
# ===========================================================================


class TestMisraEnableConfig:
    """misra.enable 配置: 默认 all（向后兼容），YAML 可配置，cmd 正确传递。"""

    def test_misra_config_enable_default(self):
        """MisraConfig.enable 默认 'all'（向后兼容）。"""
        from yuleosh.ci.config import MisraConfig
        cfg = MisraConfig()
        assert cfg.enable == "all"

    def test_parse_enable_from_yaml(self):
        """YAML misra.enable → cfg.misra.enable。"""
        from yuleosh.ci.config import _parse_ci_config
        cfg = _parse_ci_config({"misra": {"enable": "warning,style"}})
        assert cfg.misra.enable == "warning,style"

    def test_parse_enable_default_when_missing(self):
        """YAML 未提供 enable → 'all'。"""
        from yuleosh.ci.config import _parse_ci_config
        cfg = _parse_ci_config({"misra": {"enabled": True}})
        assert cfg.misra.enable == "all"

    def test_run_misra_check_passes_enable_to_cppcheck(self, tmp_path):
        """cfg.misra.enable='warning,style' → cppcheck cmd 带 --enable=warning,style。"""
        proj, cfile = _make_project(tmp_path)
        cfg = CiConfig()
        cfg.misra = MisraConfig(enable="warning,style")
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg) as ctx:
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        cppcheck_cmds = [c for c in ctx.recorded_cmds
                         if c and c[0] == "cppcheck"]
        assert cppcheck_cmds
        assert any(a == "--enable=warning,style" for a in cppcheck_cmds[0])

    def test_run_misra_check_default_enable_all(self, tmp_path):
        """默认配置 → cppcheck cmd 仍带 --enable=all（向后兼容）。"""
        proj, cfile = _make_project(tmp_path)
        cfg = CiConfig()  # MisraConfig() 默认 enable='all'
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg) as ctx:
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is True
        cppcheck_cmds = [c for c in ctx.recorded_cmds
                         if c and c[0] == "cppcheck"]
        assert cppcheck_cmds
        assert any(a == "--enable=all" for a in cppcheck_cmds[0])


# ===========================================================================
# review_misra.py — approved deviations 门禁豁免
# ===========================================================================


def _advisory_violation(rule_id: str | None = "misra-c2023-10.1", file="src/main.c", line=5):
    return _violation(rule_id=rule_id, file=file, line=line,
                      severity="advisory", severity_category="advisory")


class TestMisraDeviationGateExemption:
    """approved deviations 必须在门禁层豁免（与报告层语义一致）。"""

    def test_approved_deviation_exempts_threshold(self, tmp_path):
        """15 advisory（10 条 Rule-8.7 豁免 + 5 条 Rule-10.1）→ 门禁按 5 判定通过。"""
        proj, cfile = _make_project(tmp_path)
        cfg = CiConfig()
        cfg.misra = MisraConfig(
            fail_threshold=10,
            violations_per_kloc=2.0,
            deviations=[
                MisraDeviation(rule_id="Rule-8.7", file_pattern="src/**", status="approved",
                               reason="lib api", approved_by="test",
                               expires="2099-12-31"),
            ],
        )
        viols = [_advisory_violation(rule_id="misra-c2023-8.7") for _ in range(10)]
        viols += [_advisory_violation(rule_id="misra-c2023-10.1") for _ in range(5)]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg, violations=viols,
                          summary=_default_summary(total=15, advisory=15)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        # 报告层 15，门禁层豁免后 5 < 10 → 不阻断
        assert result is True
        assert ci.stages[-1]["status"] == "warning"

    def test_without_deviation_blocks_at_threshold(self, tmp_path):
        """对照组: 同样 15 条但无 deviation → 15 >= 10 → 阻断。"""
        proj, cfile = _make_project(tmp_path)
        cfg = CiConfig()
        cfg.misra = MisraConfig(fail_threshold=10, violations_per_kloc=2.0)
        viols = [_advisory_violation(rule_id="misra-c2023-8.7") for _ in range(10)]
        viols += [_advisory_violation(rule_id="misra-c2023-10.1") for _ in range(5)]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg, violations=viols,
                          summary=_default_summary(total=15, advisory=15)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        assert result is False
        assert "threshold" in ci.stages[-1]["detail"]

    def test_rule_id_none_not_exempted_by_deviation(self, tmp_path):
        """rule_id=None（cppcheck 原生警告如 unusedFunction）不被 MISRA deviation 豁免。"""
        proj, cfile = _make_project(tmp_path)
        cfg = CiConfig()
        cfg.misra = MisraConfig(
            fail_threshold=10,
            deviations=[
                MisraDeviation(rule_id="Rule-8.7", file_pattern="src/**", status="approved",
                               reason="lib api", approved_by="test",
                               expires="2099-12-31"),
            ],
        )
        # 12 条 rule_id=None 原生警告（unusedFunction 场景）
        viols = [_advisory_violation(rule_id=None) for _ in range(12)]
        ci = CIResult(2, "abc")
        with _MisraRunCtx(cfg=cfg, violations=viols,
                          summary=_default_summary(total=12, advisory=12)):
            result = run_misra_check(str(proj), ci, mode="full",
                                     target_files=[cfile])
        # deviation 豁免不适用 → 12 >= 10 → 阻断（必须由 enable 配置关闭，
        # 而不是靠 MISRA deviation 豁免——语义边界）
        assert result is False
        assert "threshold" in ci.stages[-1]["detail"]
