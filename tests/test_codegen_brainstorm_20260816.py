#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""老板指令 (2026-08-16): 框住 LLM 行为 + 3 次失败头脑风暴。

背景: codegen repair 轮里 LLM 可以随意重发/重写任意文件, 同一错误反复
3+ 轮修不好 (window-anti-pinch set_all 4 连败实证)。两个新机制:

C1. 白名单硬过滤 (框住 LLM): repair 轮引擎计算"允许修改文件集"
    (错误文本涉及文件 + seed_contract 文件 + 行为失败时上轮输出文件),
    LLM 输出白名单外的文件 → 引擎直接丢弃 + 记录, 不靠 prompt 自觉。

A1. 3 次失败 → 头脑风暴: 连续失败达到阈值 (默认 3) 时, 引擎做失败
    模式分析 (同一错误/错误增加/行为失败主导), 强制恢复 seed 基线,
    下一轮用头脑风暴指令 (恢复基线 vs 最小修复 vs 停止恶化)。
"""

import os
from pathlib import Path
from unittest import mock

from yuleosh.codegen import CodegenEngine, GeneratedFile
from yuleosh.pipeline.session import PipelineSession


def _session(tmp_path, name="brainstorm-test"):
    with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
        return PipelineSession(
            name=name,
            spec_path=str(tmp_path / "spec.md"),
            development_mode="generate-code",
        )


def _marker_output(path: str = "src/foo.py", lang: str = "python",
                   body: str = "def foo():\n    return 1\n"):
    return f"### FILE: {path}\n```{lang}\n{body}```\n"


# ==================================================================
# C1: 白名单硬过滤 — 框住 LLM 不能随意修改
# ==================================================================

class TestScopeFilter:
    def test_extract_error_files_from_gcc_output(self):
        errors = (
            "src/app.c:12:5: error: 'pinchZone' undeclared (first use in this function)\n"
            "In file included from src/app.c:5:\n"
            "src/hal/include/hal_motor.h:3:1: error: expected ';'\n"
        )
        files = CodegenEngine._extract_error_files(errors)
        assert "src/app.c" in files
        assert "src/hal/include/hal_motor.h" in files

    def test_extract_error_files_empty(self):
        assert CodegenEngine._extract_error_files("") == set()
        assert CodegenEngine._extract_error_files("(no output)") == set()

    def test_build_allowlist_includes_error_and_seed_contract(self):
        errors = "src/app.c:3: error: syntax error"
        allow = CodegenEngine._build_allowlist(
            errors,
            round_files=[GeneratedFile(path="src/other.c", content="x")],
            seed_contract={"src/hal.c": {"hal_init"}},
        )
        assert "src/app.c" in allow          # 错误文件
        assert "src/hal.c" in allow          # seed_contract 文件
        assert "src/other.c" not in allow    # 无关文件不在白名单

    def test_build_allowlist_behavior_fail_adds_round_files(self):
        # 行为失败时错误文本只有测试文件, 允许修改上轮输出过的文件
        errors = "FAIL test.c:20: state == IDLE\nrunner=ctest passed=0 failed=1"
        allow = CodegenEngine._build_allowlist(
            errors,
            round_files=[GeneratedFile(path="src/window.c", content="x")],
            seed_contract=None,
        )
        assert "src/window.c" in allow

    def test_filter_drops_out_of_scope_files(self):
        engine = CodegenEngine(max_retries=1)
        files = [
            GeneratedFile(path="src/app.c", content="a"),
            GeneratedFile(path="src/unrelated.c", content="b"),
        ]
        kept, dropped = engine._filter_out_of_scope(files, {"src/app.c"})
        assert [f.path for f in kept] == ["src/app.c"]
        assert dropped == ["src/unrelated.c"]


# ==================================================================
# A1: 3 次失败 → 头脑风暴
# ==================================================================

class TestBrainstorm:
    def test_error_signature_ignores_line_numbers(self):
        e1 = "src/app.c:12:5: error: 'x' undeclared"
        e2 = "src/app.c:99:7: error: 'x' undeclared"
        assert CodegenEngine._error_signature(e1) == CodegenEngine._error_signature(e2)

    def test_error_signature_distinguishes_error_type(self):
        e1 = "src/app.c:1: error: syntax error"
        e2 = "src/app.c:1: error: undeclared identifier"
        assert CodegenEngine._error_signature(e1) != CodegenEngine._error_signature(e2)

    def test_brainstorm_strategy_same_behavior_error(self):
        from yuleosh.codegen.engine import RoundFailure

        failures = [
            RoundFailure(round_idx=1, error_signature="FAIL state==IDLE",
                         err_count=2, is_behavior=True, files=["src/a.c"]),
            RoundFailure(round_idx=2, error_signature="FAIL state==IDLE",
                         err_count=2, is_behavior=True, files=["src/a.c"]),
            RoundFailure(round_idx=3, error_signature="FAIL state==IDLE",
                         err_count=2, is_behavior=True, files=["src/a.c"]),
        ]
        analysis = CodegenEngine._brainstorm(failures)
        assert analysis["same_error"] is True
        assert analysis["strategy"] == "restore_baseline"

    def test_brainstorm_strategy_worsening(self):
        from yuleosh.codegen.engine import RoundFailure

        failures = [
            RoundFailure(round_idx=1, error_signature="e1",
                         err_count=1, is_behavior=False, files=["src/a.c"]),
            RoundFailure(round_idx=2, error_signature="e2",
                         err_count=3, is_behavior=False, files=["src/a.c"]),
            RoundFailure(round_idx=3, error_signature="e3",
                         err_count=5, is_behavior=False, files=["src/a.c"]),
        ]
        analysis = CodegenEngine._brainstorm(failures)
        assert analysis["worsening"] is True
        assert analysis["strategy"] == "stop_worsening"

    def test_format_brainstorm_context_restore_baseline(self):
        analysis = {
            "strategy": "restore_baseline",
            "rounds": 3,
            "same_error": True,
            "reason": "同一行为回归反复出现",
        }
        ctx = CodegenEngine._format_brainstorm_context(
            analysis, "FAIL test.c:1: state == IDLE",
            [GeneratedFile(path="src/window.c", content="x")],
        )
        assert "头脑风暴" in ctx
        assert "恢复基线" in ctx
        assert "3 轮" in ctx


# ==================================================================
# E2E: 3 次失败 → 头脑风暴 → 恢复
# ==================================================================

class TestBrainstormE2E:
    def test_generate_three_failures_then_brainstorm_recovers(self, tmp_path):
        """GIVEN LLM 连续 3 轮输出同一坏文件 (删 guard 的行为回归)
           WHEN 第 4 轮前触发头脑风暴 (引擎恢复 seed 基线 + 脑暴指令)
           THEN 第 4 轮 LLM 恢复基线实现 → verified"""
        calls = []

        def llm(system, user, **kw):
            calls.append(user)
            if len(calls) <= 3:
                # 前三轮: 输出坏文件 (删掉 guard)
                return {"content": _marker_output(
                    "src/ok.py", "python", "def f():\n    return 0\n")}
            # 第 4 轮: 收到头脑风暴指令后恢复基线
            assert "头脑风暴" in user
            return {"content": _marker_output(
                "src/ok.py", "python", "def f():\n    return 1\n")}

        session = _session(tmp_path)
        out_dir = Path(session.session_dir) / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "src").mkdir(parents=True, exist_ok=True)
        # seed 基线 = 正确实现
        (out_dir / "src" / "ok.py").write_text("def f():\n    return 1\n")

        def behavior_verify(out_dir_arg):
            content = (Path(out_dir_arg) / "src" / "ok.py").read_text()
            if "return 1" in content:
                return ""
            return "FAIL ok.py:2: f() == 1\nrunner=ctest passed=0 failed=1"

        engine = CodegenEngine(
            llm_client=llm,
            max_retries=4,
            seed_dir=out_dir,
            behavior_verify=behavior_verify,
            brainstorm_after_failures=3,
        )
        engine.seed_dir = out_dir
        result = engine.generate(session, "sys", "user")

        assert result.status == "verified"
        # 第 4 轮 prompt 必须含头脑风暴标记
        assert "头脑风暴" in calls[3]
        # 前 3 轮 prompt 不应含头脑风暴标记
        for i in range(3):
            assert "头脑风暴" not in calls[i]
        # 头脑风暴分析已记录
        assert result.brainstorm.get("strategy") == "restore_baseline"

    def test_generate_out_of_scope_files_dropped(self, tmp_path):
        """GIVEN repair 轮 LLM 同时输出错误文件 + 无关文件
           THEN 无关文件被丢弃, 只有白名单内文件写盘"""
        calls = []

        def llm(system, user, **kw):
            calls.append(user)
            if len(calls) == 1:
                return {"content": _marker_output(
                    "src/ok.py", "python", "def f():\n    return 0\n")}
            # round 2: 输出错误文件 + 一个无关文件
            return {"content": (
                _marker_output("src/ok.py", "python", "def f():\n    return 1\n")
                + _marker_output("src/unrelated.py", "python",
                                 "def evil():\n    return 1\n"))}

        session = _session(tmp_path)
        out_dir = Path(session.session_dir) / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "src").mkdir(parents=True, exist_ok=True)
        (out_dir / "src" / "ok.py").write_text("def f():\n    return 1\n")

        def behavior_verify(out_dir_arg):
            content = (Path(out_dir_arg) / "src" / "ok.py").read_text()
            if "return 1" in content:
                return ""
            return "FAIL ok.py:2: f() == 1\nrunner=ctest passed=0 failed=1"

        engine = CodegenEngine(
            llm_client=llm,
            max_retries=2,
            seed_dir=out_dir,
            behavior_verify=behavior_verify,
            brainstorm_after_failures=99,  # 不触发脑暴, 只看过滤
        )
        engine.seed_dir = out_dir
        result = engine.generate(session, "sys", "user")

        assert result.status == "verified"
        # 无关文件被丢弃且记录
        assert "src/unrelated.py" in result.dropped_files
        # 无关文件没有写盘
        assert not (out_dir / "src" / "unrelated.py").exists()
