#!/usr/bin/env python3

# @tests src/yuleosh/codegen/engine.py
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for src/yuleosh/codegen — parse / write / verify / retry loop.

Covers: LLM output parsing (marker + JSON formats), file writing with path
sanitization, language detection, Python & C compile verification, the
generate → verify → fix retry loop (success, repair, exhausted, no-files),
and the report builder.
"""

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.codegen import (
    CodegenEngine,
    CodegenResult,
    GeneratedFile,
    build_codegen_report,
    build_codegen_prompt,
    compile_verify,
    default_output_dir,
    detect_language,
    parse_generated_files,
    verify_c,
    verify_python,
)
from yuleosh.pipeline.session import PipelineSession


def _session(tmp_path, name="codegen-test", dev_mode=None):
    with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
        return PipelineSession(
            name=name,
            spec_path=str(tmp_path / "spec.md"),
            development_mode=dev_mode,
        )


def _marker_output(path: str = "src/foo.py", lang: str = "python",
                   body: str = "def foo():\n    return 1\n"):
    return f"### FILE: {path}\n```{lang}\n{body}```\n"


# ==================================================================
# Parsing
# ==================================================================


class TestParseGeneratedFiles:
    def test_parse_marker_format(self):
        files = parse_generated_files(_marker_output())
        assert len(files) == 1
        assert files[0].path == "src/foo.py"
        assert files[0].language == "python"
        assert "def foo()" in files[0].content

    def test_parse_multiple_files(self):
        out = (_marker_output("a.py", "python", "x = 1\n")
               + "\n" + _marker_output("b.c", "c", "int main(void){return 0;}\n"))
        files = parse_generated_files(out)
        assert [f.path for f in files] == ["a.py", "b.c"]

    def test_parse_json_payload(self):
        out = json.dumps({"files": [
            {"path": "src/a.py", "content": "print(1)", "language": "python"},
            {"path": "src/b.c", "content": "int main(void){return 0;}"},
        ]})
        files = parse_generated_files(out)
        assert len(files) == 2
        assert files[0].path == "src/a.py"
        assert files[1].language == ""

    def test_parse_json_empty_list_falls_back(self):
        out = json.dumps({"files": []}) + "\n" + _marker_output()
        files = parse_generated_files(out)
        assert len(files) == 1
        assert files[0].path == "src/foo.py"

    def test_parse_empty_and_garbage(self):
        assert parse_generated_files("") == []
        assert parse_generated_files("no markers at all") == []

    def test_parse_marker_without_fence(self):
        out = "### FILE: src/plain.py\njust some text, no fence\n"
        files = parse_generated_files(out)
        assert len(files) == 1
        assert "just some text" in files[0].content


# ==================================================================
# Language detection & compile verification
# ==================================================================


class TestLanguageDetection:
    def test_detect_python(self):
        assert detect_language(["a.py", "b.pyw"]) == "python"

    def test_detect_c(self):
        assert detect_language(["a.c", "b.h"]) == "c"

    def test_detect_cpp_maps_to_c(self):
        assert detect_language(["a.cpp", "b.hpp"]) == "c"

    def test_detect_unknown(self):
        assert detect_language(["a.md", "b.txt"]) == "unknown"

    def test_detect_c_project_with_stray_py(self):
        """C 项目 (CMakeLists + .c 主导) 里混入生成器 .py 时不得误判 python。

        Regression: 2026-08-14 headlamp dogfood — LLM 生成 Python 文件到 C 项目,
        detect_language 见 .py 就返回 python → py_compile 验证通过 → 假绿部署。
        """
        assert detect_language(["a.c", "b.h", "tools/gen.py"]) == "c"

    def test_detect_pure_python_still_python(self):
        assert detect_language(["a.py", "b.py"]) == "python"


class TestCompileVerification:
    def test_verify_python_ok(self, tmp_path):
        f = tmp_path / "ok.py"
        f.write_text("def f():\n    return 42\n")
        result = verify_python([f])
        assert result["ok"] is True
        assert result["language"] == "python"

    def test_verify_python_failure(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(:\n")
        result = verify_python([f])
        assert result["ok"] is False
        assert result["errors"]

    def test_verify_c_ok(self, tmp_path):
        if not (os.environ.get("HAS_CC") == "0"):  # pragma: no cover
            pytest.importorskip("shutil")
        import shutil
        if not (shutil.which("gcc") or shutil.which("cc")):
            pytest.skip("no C compiler available")
        f = tmp_path / "ok.c"
        f.write_text("int add(int a, int b) { return a + b; }\n")
        result = verify_c([f])
        assert result["ok"] is True

    def test_verify_c_cross_dir_include(self, tmp_path):
        """E2E fix (2026-08-11): 跨目录 #include 必须能通过验证。

        修复前 verify_c 不带 -I，src/hal/src/*.c 包含 src/hal/include/*.h
        时必然 "file not found" 误报失败；修复后自动收集 include 目录。
        """
        import shutil
        if not (shutil.which("gcc") or shutil.which("cc")):
            pytest.skip("no C compiler available")
        inc = tmp_path / "src" / "hal" / "include"
        src = tmp_path / "src" / "hal" / "src"
        inc.mkdir(parents=True)
        src.mkdir(parents=True)
        (inc / "hal_motor.h").write_text(
            "#ifndef HAL_MOTOR_H\n#define HAL_MOTOR_H\nvoid motor_on(void);\n#endif\n",
            encoding="utf-8",
        )
        (src / "hal_motor_stm32.c").write_text(
            '#include "hal_motor.h"\nvoid motor_on(void) {}\n',
            encoding="utf-8",
        )
        # 混入非 C 文件（CMakeLists/README）—— 应被过滤，不参与编译
        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.16)\n")
        (tmp_path / "README.md").write_text("# readme\n")
        result = verify_c([src / "hal_motor_stm32.c", tmp_path / "CMakeLists.txt",
                           tmp_path / "README.md"])
        assert result["ok"] is True, result["errors"]

    def test_verify_c_only_non_c_sources(self, tmp_path):
        """只传非 C 文件 → 无需编译即通过（无可验证源码）。"""
        f = tmp_path / "CMakeLists.txt"
        f.write_text("cmake_minimum_required(VERSION 3.16)\n", encoding="utf-8")
        result = verify_c([f])
        assert result["ok"] is True

    def test_verify_c_failure(self, tmp_path):
        import shutil
        if not (shutil.which("gcc") or shutil.which("cc")):
            pytest.skip("no C compiler available")
        f = tmp_path / "bad.c"
        f.write_text("int add(int a, int b) { return a + }\n")
        result = verify_c([f])
        assert result["ok"] is False
        assert result["errors"]

    def test_compile_verify_empty_files(self):
        result = compile_verify([])
        assert result["ok"] is True

    def test_compile_verify_unknown_language(self, tmp_path):
        f = tmp_path / "a.md"
        f.write_text("# hi")
        result = compile_verify([f])
        assert result["ok"] is False

    def test_compile_verify_build_cmd(self, tmp_path):
        shell = os.environ.get("SHELL", "/bin/sh")
        result = compile_verify([tmp_path / "ignored.c"],
                                build_cmd=[shell, "-c", "exit 0"])
        assert result["ok"] is True
        # 平台敏感：macOS SHELL=/bin/zsh、CI 为 /bin/sh —— 后缀匹配实际 shell 而非硬编码
        assert result["command"].endswith(f"{os.path.basename(shell)} -c exit 0")


# ==================================================================
# Engine — write + retry loop
# ==================================================================


class TestEngineWrite:
    def test_write_files(self, tmp_path):
        engine = CodegenEngine(output_dir=tmp_path / "out")
        files = [GeneratedFile("src/a.py", "x = 1", "python"),
                 GeneratedFile("nested/dir/b.c", "int main(void){return 0;}", "c")]
        written = engine.write_files(files, tmp_path / "out")
        assert len(written) == 2
        assert (tmp_path / "out" / "src" / "a.py").read_text() == "x = 1"
        assert (tmp_path / "out" / "nested" / "dir" / "b.c").exists()

    def test_write_files_blocks_path_traversal(self, tmp_path):
        engine = CodegenEngine(output_dir=tmp_path / "out")
        files = [GeneratedFile("../../evil.py", "x = 1", "python")]
        written = engine.write_files(files, tmp_path / "out")
        # Sanitized: written INSIDE the output dir, never escaping it.
        assert len(written) == 1
        assert written[0].resolve() == (tmp_path / "out" / "evil.py").resolve()
        assert not (tmp_path / "evil.py").exists()

    def test_default_output_dir_layout(self, tmp_path):
        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            out = default_output_dir(tmp_path, "sess-1")
        assert out == (tmp_path / "artifacts" / "generated-code" / "sess-1").resolve()


class TestEngineLoop:
    def _ok_llm(self, system, user, **kw):
        return {"content": _marker_output("src/ok.py", "python",
                                          "def ok():\n    return 1\n"),
                "usage": {"total_tokens": 10}}

    def test_generate_success_first_try(self, tmp_path):
        session = _session(tmp_path)
        engine = CodegenEngine(llm_client=self._ok_llm, max_retries=3)
        result = engine.generate(session, "sys", "user")
        assert result.status == "verified"
        assert result.rounds == 1
        assert len(result.files) == 1
        assert (Path(result.output_dir) / "src" / "ok.py").exists()
        assert (Path(result.output_dir) / "codegen-report.md").exists()

    def test_generate_repair_loop_succeeds(self, tmp_path):
        """First attempt fails compile, second attempt fixes it."""
        calls = {"n": 0}
        prompts = []

        def flaky_llm(system, user, **kw):
            calls["n"] += 1
            prompts.append(user)
            if calls["n"] == 1:
                return {"content": _marker_output("src/ok.py", "python",
                                                  "def broken(:\n")}
            return {"content": _marker_output("src/ok.py", "python",
                                              "def fixed():\n    return 1\n")}

        session = _session(tmp_path)
        engine = CodegenEngine(llm_client=flaky_llm, max_retries=3)
        result = engine.generate(session, "sys", "user")
        assert result.status == "verified"
        assert result.rounds == 2
        assert calls["n"] == 2
        # The repair context (compiler feedback) must be appended to the
        # second prompt so the model can fix the errors.
        assert "编译验证失败" in prompts[1]
        assert "SyntaxError" in prompts[1] or "error" in prompts[1].lower()

    def test_generate_retries_exhausted(self, tmp_path):
        """Always-broken code → max_retries exhausted → status failed."""
        def bad_llm(system, user, **kw):
            return {"content": _marker_output("src/bad.py", "python",
                                              "def broken(:\n")}

        session = _session(tmp_path)
        engine = CodegenEngine(llm_client=bad_llm, max_retries=3)
        result = engine.generate(session, "sys", "user")
        assert result.status == "failed"
        assert result.rounds == 4  # 1 initial + 3 retries
        assert result.last_errors
        assert result.verify.get("ok") is False

    def test_generate_max_retries_zero(self, tmp_path):
        def bad_llm(system, user, **kw):
            return {"content": _marker_output("src/bad.py", "python",
                                              "def broken(:\n")}

        session = _session(tmp_path)
        engine = CodegenEngine(llm_client=bad_llm, max_retries=0)
        result = engine.generate(session, "sys", "user")
        assert result.rounds == 1
        assert result.status == "failed"

    def test_generate_no_parseable_files(self, tmp_path):
        def empty_llm(system, user, **kw):
            return {"content": "I will only plan, no code."}

        session = _session(tmp_path)
        engine = CodegenEngine(llm_client=empty_llm, max_retries=3)
        result = engine.generate(session, "sys", "user")
        assert result.status == "no-files"
        assert "no parseable files" in result.last_errors

    def test_generate_respects_custom_verifier(self, tmp_path):
        def custom_verifier(files, **kw):
            return {"ok": True, "language": "python", "command": "fake",
                    "output": "", "errors": "", "returncode": 0}

        session = _session(tmp_path)
        engine = CodegenEngine(llm_client=self._ok_llm, max_retries=3,
                               verifier=custom_verifier)
        result = engine.generate(session, "sys", "user")
        assert result.status == "verified"

    def test_generate_llm_transport_error_raises(self, tmp_path):
        def boom(system, user, **kw):
            raise RuntimeError("connection refused")

        session = _session(tmp_path)
        engine = CodegenEngine(llm_client=boom)
        with pytest.raises(Exception):
            engine.generate(session, "sys", "user")

    def test_call_llm_passes_long_timeout(self, tmp_path):
        """Codegen prompts (spec+PRD+arch+seed) exceed the 60s chat_completion
        default; the engine must pass an explicit timeout (120s default,
        YULEOSH_CODEGEN_LLM_TIMEOUT override) to the LLM client."""
        seen = {}

        def spy(system, user, **kw):
            seen["timeout"] = kw.get("timeout")
            seen["max_tokens"] = kw.get("max_tokens")
            return {"content": _marker_output("src/ok.py", "python", "x = 1\n")}

        session = _session(tmp_path)
        engine = CodegenEngine(llm_client=spy, max_retries=0, max_tokens=8192)
        engine.generate(session, "sys", "user")

        assert seen["timeout"] == 120, (
            "codegen must not rely on the 60s chat_completion default "
            "(real runs time out on long outputs)"
        )
        assert seen["max_tokens"] == 8192

    def test_call_llm_timeout_env_override(self, tmp_path, monkeypatch):
        seen = {}

        def spy(system, user, **kw):
            seen["timeout"] = kw.get("timeout")
            return {"content": _marker_output("src/ok.py", "python", "x = 1\n")}

        monkeypatch.setenv("YULEOSH_CODEGEN_LLM_TIMEOUT", "300")
        session = _session(tmp_path)
        engine = CodegenEngine(llm_client=spy, max_retries=0)
        engine.generate(session, "sys", "user")

        assert seen["timeout"] == 300


class TestBehaviorRegressionRepair:
    """2026-08-16 window-anti-pinch run 11: codegen 4 连败根因。

    LLM 编译通过但行为回归 (删掉 RESET 清 cooldown / set_all clamp) 时,
    repair 提示仍说"修复编译错误" → LLM 在坏代码上继续改 → 越修越坏。
    必须: 1) behavior FAIL 也计错误数 (best-state 回滚生效);
    2) repair 提示明确"恢复基线实现, 不要重写"。
    """

    def test_error_count_counts_behavior_fail(self):
        errors = (
            "Test project ...\n"
            "1/2 Test #1: window_control_tests ***Failed\n"
            "FAIL test.c:200: state == IDLE\n"
            "FAIL test.c:201: !motor\n"
        )
        assert CodegenEngine._error_count(errors) == 2

    def test_error_count_counts_compile_errors(self):
        errors = "src/x.c:12:5: error: undeclared identifier 'foo'\n"
        assert CodegenEngine._error_count(errors) == 1

    def test_error_count_empty(self):
        assert CodegenEngine._error_count("") == 0
        assert CodegenEngine._error_count("(no output)\n") == 0

    def test_repair_context_behavior_fail_hints_restore(self):
        ctx = CodegenEngine._format_repair_context(
            errors="FAIL test.c:1: state == IDLE\nrunner=ctest passed=1 failed=1",
            files=[GeneratedFile(path="src/app.c", content="x")],
        )
        assert "行为测试失败" in ctx
        assert "恢复基线实现" in ctx
        assert "不要整体重写" in ctx

    def test_repair_context_compile_fail_no_behavior_hint(self):
        ctx = CodegenEngine._format_repair_context(
            errors="src/x.c:1:1: error: syntax error",
            files=[GeneratedFile(path="src/app.c", content="x")],
        )
        assert "行为测试失败" not in ctx
        assert "编译错误" in ctx

    def test_generate_behavior_regression_rolls_back_to_best(self, tmp_path):
        """Round 1 breaks behavior (no compile error); round 2 must receive a
        repair prompt pointing at the seed baseline, and best-state rollback
        must keep the baseline (0 FAIL) rather than the broken round-1 edit."""
        calls = []

        def llm(system, user, **kw):
            calls.append(user)
            if len(calls) == 1:
                # Round 1: compile-valid file that breaks behavior (removes
                # the guard that tests assert on).
                return {"content": _marker_output(
                    "src/ok.py", "python", "def f():\n    return 0\n")}
            # Round 2: model follows the restore hint and re-emits baseline.
            return {"content": _marker_output(
                "src/ok.py", "python", "def f():\n    return 1\n")}

        session = _session(tmp_path)
        out_dir = Path(session.session_dir) / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        # Seed baseline on disk: correct implementation.
        (out_dir / "src").mkdir(parents=True, exist_ok=True)
        (out_dir / "src" / "ok.py").write_text("def f():\n    return 1\n")

        def behavior_verify(out_dir_arg):
            # Round 1 disk has the broken version → FAIL; round 2 restored.
            content = (Path(out_dir_arg) / "src" / "ok.py").read_text()
            if "return 1" in content:
                return ""
            return "FAIL ok.py:2: f() == 1\nrunner=ctest passed=0 failed=1"

        engine = CodegenEngine(
            llm_client=llm,
            max_retries=2,
            seed_dir=session.project_dir,
            behavior_verify=behavior_verify,
        )
        # seed_dir points at the repo; point it at our temp tree instead.
        engine.seed_dir = out_dir
        result = engine.generate(session, "sys", "user")

        assert result.status == "verified"
        # Round-2 prompt must carry the behavior-regression restore hint.
        assert "行为测试失败" in calls[1]
        assert "恢复基线实现" in calls[1]
        # Final disk state = restored baseline.
        final = (out_dir / "src" / "ok.py").read_text()
        assert "return 1" in final

    def test_generate_structural_feature_missing_triggers_repair(self, tmp_path):
        """r21 (window-anti-pinch): LLM 全量重写删掉核心功能路径 (防夹检测
        调用/反转状态入口), 编译通过但行为验证可能因 ARM 链接环境无法执行
        → 结构性 smoke 特征必须在编译后、链接前拦截, 给 LLM 明确修复指令。"""
        calls = []

        def llm(system, user, **kw):
            calls.append(user)
            if len(calls) == 1:
                # Round 1: 编译有效但删了 window_modes_check_pinch 调用
                return {"content": _marker_output(
                    "src/win.py", "python",
                    "def window_control_process():\n"
                    "    return 0\n")}
            # Round 2: LLM 按修复指令恢复特征
            return {"content": _marker_output(
                "src/win.py", "python",
                "def window_control_process():\n"
                "    window_modes_check_pinch(0, 0, 0)\n"
                "    return WINDOW_CONTROL_PINCH_REVERSAL\n")}

        session = _session(tmp_path)
        out_dir = Path(session.session_dir) / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "src").mkdir(parents=True, exist_ok=True)
        # seed 基线含核心特征
        (out_dir / "src" / "win.py").write_text(
            "def window_control_process():\n"
            "    window_modes_check_pinch(0, 0, 0)\n"
            "    return WINDOW_CONTROL_PINCH_REVERSAL\n")

        engine = CodegenEngine(
            llm_client=llm,
            max_retries=2,
            seed_dir=session.project_dir,
            structural_features={
                "src/win.py": [
                    "window_modes_check_pinch",
                    "WINDOW_CONTROL_PINCH_REVERSAL",
                ],
            },
        )
        engine.seed_dir = out_dir
        result = engine.generate(session, "sys", "user")

        assert result.status == "verified"
        # Round-2 prompt 必须带结构性 smoke 缺失修复指令
        assert "结构性 smoke 特征缺失" in calls[1]
        assert "window_modes_check_pinch" in calls[1]
        # 最终磁盘 = 恢复特征后的实现
        final = (out_dir / "src" / "win.py").read_text()
        assert "window_modes_check_pinch" in final
        assert "WINDOW_CONTROL_PINCH_REVERSAL" in final

    def test_generate_forbidden_feature_blocks_repair(self, tmp_path):
        """r21b: LLM 生成 int64 除法 (ARM __aeabi_ldivmod 链接失败), 行为验证
        报链接错误但不指代码行 → 禁止特征在链接前直接点名子串, LLM 收到明确
        修复指令后移除。"""
        calls = []

        def llm(system, user, **kw):
            calls.append(user)
            if len(calls) == 1:
                # Round 1: 编译有效但用 int64 除法 (ARM 会链接失败)
                return {"content": _marker_output(
                    "src/pos.py", "python",
                    "def get_mm(pos, mm_per_pulse):\n"
                    "    return (int64_t)(pos * mm_per_pulse) // 1000\n")}
            # Round 2: LLM 按禁止特征指令移除 int64
            return {"content": _marker_output(
                "src/pos.py", "python",
                "def get_mm(pos, mm_per_pulse):\n"
                "    return (pos * mm_per_pulse) // 1000\n")}

        session = _session(tmp_path)
        out_dir = Path(session.session_dir) / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "src").mkdir(parents=True, exist_ok=True)
        # seed 基线是 32 位实现
        (out_dir / "src" / "pos.py").write_text(
            "def get_mm(pos, mm_per_pulse):\n"
            "    return (pos * mm_per_pulse) // 1000\n")

        engine = CodegenEngine(
            llm_client=llm,
            max_retries=2,
            output_dir=out_dir,
            seed_dir=session.project_dir,
            forbidden_features={
                "src/pos.py": ["(int64_t)"],
            },
        )
        engine.seed_dir = out_dir
        result = engine.generate(session, "sys", "user")

        assert result.status == "verified"
        # Round-2 prompt 必须带禁止特征移除指令
        assert "禁止特征出现" in calls[1]
        assert "(int64_t)" in calls[1]
        # 最终磁盘 = 移除 int64 后的实现
        final = (out_dir / "src" / "pos.py").read_text()
        assert "(int64_t)" not in final

    def test_forbidden_feature_message_includes_seed_baseline(self, tmp_path):
        """2026-08-18 r21g: repair 消息必须贴 seed 基线实现 — '参考 seed 基线'
        无具体代码时 LLM 无从下手 (r21g 4 轮 repair 全重写回 int64)。"""
        calls = []

        def llm(system, user, **kw):
            calls.append(user)
            return {"content": _marker_output(
                "src/pos.py", "python",
                "def get_mm(pos, mm_per_pulse):\n"
                "    return (int64_t)(pos * mm_per_pulse) // 1000\n")}

        session = _session(tmp_path)
        out_dir = Path(session.session_dir) / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "src").mkdir(parents=True, exist_ok=True)
        # seed 基线是 32 位实现 (禁止特征的正确形态)
        (out_dir / "src" / "pos.py").write_text(
            "def get_mm(pos, mm_per_pulse):\n"
            "    return (pos * mm_per_pulse) // 1000\n")

        engine = CodegenEngine(
            llm_client=llm,
            max_retries=1,
            output_dir=out_dir,
            seed_dir=session.project_dir,
            forbidden_features={
                "src/pos.py": ["(int64_t)"],
            },
        )
        engine.seed_dir = out_dir
        result = engine.generate(session, "sys", "user")

        assert result.status == "failed"
        # 第二轮 (repair) 消息包含 seed 基线代码块, 且标注不可重写回反模式
        assert "seed 基线实现" in calls[1]
        assert "src/pos.py" in calls[1]
        assert "禁止重写回反模式" in calls[1]
        # seed 基线里的正确实现 (无 int64) 出现在消息中, 且该实现本身无 int64
        seed_block = calls[1].split("seed 基线实现")[1]
        assert "(pos * mm_per_pulse) // 1000" in seed_block

    def test_compile_error_repair_includes_seed_baseline(self):
        """2026-08-18 r21h: compile-error repair 路径也必须贴 seed 基线 —
        r21h window_modes.c (void) 抑制 4 轮丢失 (G-17 -Werror), 只给编译器
        输出不贴基线实现时 LLM 无从下手。"""
        from yuleosh.codegen.engine import CodegenEngine, GeneratedFile

        errors = (
            "window_modes.c:122:57: error: unused parameter 'lastCheckTimeMs' "
            "[-Werror,-Wunused-parameter]"
        )
        files = [GeneratedFile(path="src/app/src/window_modes.c", content="")]
        seed_baseline = {
            "src/app/src/window_modes.c": (
                "int check_pinch(uint32_t positionPulses, uint32_t timeMs, "
                "uint32_t lastCheckTimeMs)\n{\n"
                "    (void)lastCheckTimeMs;\n"
                "    return positionPulses > 100 ? 1 : 0;\n}\n"
            ),
        }
        ctx = CodegenEngine._format_repair_context(
            errors, files, seed_baseline=seed_baseline,
        )
        assert "seed 基线实现" in ctx
        assert "src/app/src/window_modes.c" in ctx
        assert "(void)lastCheckTimeMs" in ctx
        assert "禁止整体重写" in ctx

    def test_brainstorm_context_includes_seed_baseline(self):
        """2026-08-18 r21h: brainstorm 策略路径同样贴 seed 基线。"""
        from yuleosh.codegen.engine import CodegenEngine, GeneratedFile

        files = [GeneratedFile(path="src/app/src/window_control.c", content="")]
        seed_baseline = {
            "src/app/src/window_control.c": (
                "void window_control_process(...) {\n"
                "    if (window_modes_check_pinch(...)) { ... }\n}\n"
            ),
        }
        ctx = CodegenEngine._format_brainstorm_context(
            {"rounds": 3, "strategy": "minimal_fix", "reason": "test"},
            "compile error",
            files,
            seed_baseline=seed_baseline,
        )
        assert "seed 基线实现" in ctx
        assert "window_modes_check_pinch" in ctx
        assert "禁止整体重写" in ctx


class TestTruncationDetection:
    """headlamp dogfood #4: LLM 输出截断 (大项目超 max_tokens)."""

    def test_detect_truncated_c_file_brace_imbalance(self):
        """GIVEN a .c file with unbalanced braces (truncated mid-function)
           WHEN _detect_truncated_files runs
           THEN the file is flagged."""
        files = [
            GeneratedFile(path="src/app.c", content="void f(void) {\n    int x;\n"),
            GeneratedFile(path="src/ok.c", content="void f(void) {\n    int x;\n}\n"),
            GeneratedFile(path="src/util.py", content="def f():\n    pass\n"),
        ]
        truncated = CodegenEngine._detect_truncated_files(files)
        assert truncated == ["src/app.c"]

    def test_detect_truncated_last_line_no_newline(self):
        """GIVEN a .c file ending mid-expression without trailing newline
           WHEN _detect_truncated_files runs
           THEN the file is flagged (content cut off)."""
        files = [
            GeneratedFile(path="src/app.c",
                          content="void f(void) {\n    if (resp_len"),
        ]
        truncated = CodegenEngine._detect_truncated_files(files)
        assert truncated == ["src/app.c"]

    def test_complete_c_file_not_flagged(self):
        """GIVEN a complete .c file ending with closing brace
           WHEN _detect_truncated_files runs
           THEN no truncation is reported."""
        files = [
            GeneratedFile(path="src/app.c",
                          content="void f(void) {\n    int x;\n}\n"),
        ]
        truncated = CodegenEngine._detect_truncated_files(files)
        assert truncated == []

    def test_repair_context_includes_truncation_warning(self):
        """GIVEN truncated files detected
           WHEN _format_repair_context builds the repair prompt
           THEN the prompt warns about truncation and tells the model
           to only resend those files."""
        files = [GeneratedFile(path="src/app.c", content="void f() {\n")]
        ctx = CodegenEngine._format_repair_context(
            "error: expected '}'", files,
            truncated_files=["src/app.c"],
        )
        assert "输出截断警告" in ctx
        assert "src/app.c" in ctx
        assert "一次只输出这些文件" in ctx

    def test_generate_loop_detects_truncation_and_repairs(self, tmp_path):
        """GIVEN first C output is truncated and second is complete
           WHEN generate runs
           THEN truncation is detected, repair context warns, and the
           repaired (complete) file passes verification."""
        calls = {"n": 0}
        prompts = []

        def truncating_llm(system, user, **kw):
            calls["n"] += 1
            prompts.append(user)
            if calls["n"] == 1:
                # 截断: 花括号不平衡 (模拟 max_tokens 截断)
                return {"content": _marker_output(
                    "src/app.c", "c",
                    "void f(void) {\n    int x;\n")}
            return {"content": _marker_output(
                "src/app.c", "c",
                "void f(void) {\n    int x;\n}\n")}

        session = _session(tmp_path)
        engine = CodegenEngine(llm_client=truncating_llm, max_retries=3)
        result = engine.generate(session, "sys", "user")
        assert result.status == "verified"
        assert result.rounds == 2
        # repair prompt 必须包含截断警告
        assert "输出截断警告" in prompts[1]


class TestEngineReport:
    def test_report_contains_files_and_verification(self, tmp_path):
        session = _session(tmp_path)
        result = CodegenResult(status="verified", rounds=2, max_retries=3,
                               files=["/tmp/a.py", "/tmp/b.c"],
                               verify={"ok": True, "language": "python",
                                       "command": "py_compile", "output": "",
                                       "errors": "", "returncode": 0})
        report = build_codegen_report(result, session)
        assert "Code Generation Report" in report
        assert "✅ verified" in report
        assert "/tmp/a.py" in report
        assert "py_compile" in report
        assert session.spec_path in report

    def test_report_records_failure_errors(self, tmp_path):
        session = _session(tmp_path)
        result = CodegenResult(status="failed", rounds=4, max_retries=3,
                               files=["/tmp/bad.py"],
                               verify={"ok": False, "language": "python",
                                       "command": "py_compile",
                                       "output": "SyntaxError: x",
                                       "errors": "SyntaxError: x",
                                       "returncode": 1},
                               last_errors="SyntaxError: x")
        report = build_codegen_report(result, session)
        assert "❌ failed" in report
        assert "SyntaxError: x" in report
        assert "Repair Rounds" in report

    def test_report_records_behavior_verify_result(self, tmp_path):
        """Regression (2026-08-17, claude-review run-175442 blocker 1):
        dev 报告必须呈现 behavior_verify 结果 — 否则评审只看 -fsyntax-only
        误判"护栏测试从未执行", 真回归被掩盖."""
        session = _session(tmp_path)
        result = CodegenResult(status="verified", rounds=2, max_retries=3,
                               verify={"ok": True, "language": "c",
                                       "command": "gcc -fsyntax-only", "output": "",
                                       "errors": "", "returncode": 0},
                               behavior_verify_result=(
                                   "PASS (临时部署验证: 生成代码暂替 src/ 跑真实测试套件, "
                                   "验证后恢复原代码, 0 失败)"
                               ))
        report = build_codegen_report(result, session)
        assert "Behavior Verification" in report
        assert "PASS" in report


class TestFinalVerify:
    """终验机制 (2026-08-18, r21j blocker 2/3): report 必须对应最终磁盘产物。

    循环内 verify 记录的是最后一次 verify 时刻的状态; best-state 回滚 /
    brainstorm seed 恢复可能覆盖磁盘 → report 失步。_final_verify 对最终
    产物重跑完整验证链, report 以此为准。
    """

    def _engine(self, behavior_verify=None, **kw):
        def llm(system, user, **kw2):
            return {"content": _marker_output()}

        return CodegenEngine(
            llm_client=llm, max_retries=1, behavior_verify=behavior_verify, **kw
        )

    def _session_outdir(self, tmp_path):
        session = _session(tmp_path)
        out_dir = Path(session.session_dir) / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "src").mkdir(parents=True, exist_ok=True)
        return session, out_dir

    def test_compile_fail_sets_failed_and_skips_behavior(self, tmp_path):
        """终验编译失败 → status=failed, last_errors 指向最终产物, behavior SKIPPED。"""
        session, out_dir = self._session_outdir(tmp_path)
        (out_dir / "src" / "bad.py").write_text("def broken(:\n")
        engine = self._engine()
        result = CodegenResult(max_retries=1, output_dir=str(out_dir))
        engine._final_verify(result, session, out_dir, "python", None, None)
        assert result.status == "failed"
        assert "SyntaxError" in result.last_errors or "error" in result.last_errors.lower()
        assert "SKIPPED" in result.behavior_verify_result

    def test_behavior_fail_keeps_full_text(self, tmp_path):
        """终验行为失败 → behavior_verify_result 保留全量失败清单 (不截断 500)。"""
        session, out_dir = self._session_outdir(tmp_path)
        (out_dir / "src" / "ok.py").write_text("def f():\n    return 1\n")

        long_fail = "FAIL ok.py:1: cond A\n" + ("FAIL ok.py:%d: cond\n" * 55)

        def behavior_verify(out_dir_arg):
            return long_fail

        engine = self._engine(behavior_verify=behavior_verify)
        result = CodegenResult(max_retries=1, output_dir=str(out_dir))
        engine._final_verify(result, session, out_dir, "python", None, None)
        assert result.status == "failed"
        assert result.behavior_verify_result == f"FAIL ({long_fail})"
        # last_errors 必须包含完整 55 条, 不是截断的前 2 条
        assert result.last_errors.count("FAIL ok.py:") == 56
        assert "cond A" in result.last_errors

    def test_all_pass_promotes_to_verified(self, tmp_path):
        """终验全过 (编译 + 契约 + 行为) → 惊喜晋级 verified。"""
        session, out_dir = self._session_outdir(tmp_path)
        (out_dir / "src" / "ok.py").write_text("def f():\n    return 1\n")

        def behavior_verify(out_dir_arg):
            return ""

        engine = self._engine(behavior_verify=behavior_verify)
        result = CodegenResult(max_retries=1, output_dir=str(out_dir))
        engine._final_verify(result, session, out_dir, "python", None, None)
        assert result.status == "verified"
        assert result.last_errors == ""
        assert "PASS" in result.behavior_verify_result

    def test_integration_failed_run_report_matches_final_disk(self, tmp_path):
        """集成: 循环耗尽失败 → report 的 Verification 标注终验且对应最终产物。"""
        calls = {"n": 0}

        def llm(system, user, **kw):
            calls["n"] += 1
            # 每轮都输出编译通过但行为失败的代码
            return {"content": _marker_output(
                "src/ok.py", "python", "def f():\n    return 0\n")}

        def behavior_verify(out_dir_arg):
            content = (Path(out_dir_arg) / "src" / "ok.py").read_text()
            if "return 1" in content:
                return ""
            return "FAIL ok.py:2: f() == 1\nrunner=ctest passed=0 failed=1"

        session = _session(tmp_path)
        out_dir = Path(session.session_dir) / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "src").mkdir(parents=True, exist_ok=True)
        # seed 基线 = 正确实现 (行为通过)
        (out_dir / "src" / "ok.py").write_text("def f():\n    return 1\n")

        engine = CodegenEngine(
            llm_client=llm, max_retries=2,
            seed_dir=session.project_dir,
            behavior_verify=behavior_verify,
        )
        engine.seed_dir = out_dir
        result = engine.generate(session, "sys", "user")
        # 循环内所有轮都行为失败 → failed; 终验对最终磁盘产物跑行为也失败
        assert result.status == "failed"
        # report 必须可复现: Verification 段标注最终产物终验
        report = build_codegen_report(result, session)
        assert "最终产物终验" in report
        assert "FAIL" in report


class TestEnginePrompt:
    def test_codegen_prompt_embeds_spec_and_skills(self):
        sys_p, user_p = build_codegen_prompt("SPEC BODY", "spec.md",
                                             skills=["autosar-coding"])
        assert "SPEC BODY" in user_p
        assert "### FILE:" in sys_p
        assert "AUTOSAR C 编码规范要点" in user_p  # skills spliced in

    def test_codegen_prompt_default_skills(self):
        _, user_p = build_codegen_prompt("S", "s.md")
        assert "autosar-coding" in user_p

    def test_codegen_prompt_target_language_hint(self):
        _, user_p = build_codegen_prompt("S", "s.md", target_language="C")
        assert "目标语言" in user_p and "C" in user_p

    def test_codegen_prompt_keeps_prd_tail_contracts(self):
        """Regression (2026-08-16, run-20260816-174313): codegen prompt
        truncated PRD at 4000 chars — the behavioral contract tail (FR-044
        |delta|, G-01..G-12 guardrail map, SW-005..008 FRs) was invisible to
        the codegen LLM, so it regenerated signed-delta/raw-memcpy code every
        round. The full PRD must reach the codegen prompt."""
        prd = "# PRD\n" + ("FR row\n" * 600) + "\n## 护栏映射\nG-12 window_control_reset(NULL) 安全 tail_marker\n"
        assert len(prd) > 4000
        _, user_p = build_codegen_prompt("SPEC", "spec.md", prd_content=prd)
        assert "tail_marker" in user_p, (
            "PRD tail contract must survive codegen prompt injection "
            "(PRD truncation regression)"
        )
