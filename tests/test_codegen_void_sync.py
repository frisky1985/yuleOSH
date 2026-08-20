#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Codegen 确定性 void 抑制同步测试 — G-17 (2026-08-20)。

背景: r21f/r22 反复失败 — LLM 重写 .c 文件时丢掉 seed 基线里的
``(void)param;`` 未用参数抑制 (window_modes.c 丢 (void)lastCheckTimeMs;),
项目真实 -Werror -Wunused-parameter 构建失败, 且 4 轮 LLM repair 都修不好
(worsening → 回退 seed 基线)。修复: engine 每轮 write 后确定性同步 seed
基线的 (void)param; 抑制, 不依赖 LLM。
"""

import shutil
from pathlib import Path

import pytest

from yuleosh.codegen import CodegenEngine
from yuleosh.codegen.compilers import verify_c
from yuleosh.pipeline.session import PipelineSession

pytestmark = pytest.mark.skipif(
    not (shutil.which("gcc") or shutil.which("cc")),
    reason="no C compiler available",
)

# ── 真实 window-anti-pinch 场景 (G-17) ─────────────────────────────────

SEED_WINDOW_MODES_C = (
    '#include <stdint.h>\n'
    '#include <stdbool.h>\n'
    '#include "window_modes.h"\n'
    '\n'
    'bool window_modes_check_pinch(uint32_t positionPulses, uint32_t timeMs,\n'
    '                              uint32_t lastCheckTimeMs)\n'
    '{\n'
    '    (void)lastCheckTimeMs;  /* 固定时间窗语义 (G-03): 窗口锚在 positionWindowStartMs */\n'
    '    if (timeMs > 1000) {\n'
    '        return false;\n'
    '    }\n'
    '    return positionPulses > 100;\n'
    '}\n'
)

WINDOW_MODES_H = (
    '#ifndef WINDOW_MODES_H\n'
    '#define WINDOW_MODES_H\n'
    '#include <stdint.h>\n'
    '#include <stdbool.h>\n'
    'bool window_modes_check_pinch(uint32_t positionPulses, uint32_t timeMs,\n'
    '                              uint32_t lastCheckTimeMs);\n'
    '#endif\n'
)

# LLM 重写后丢掉抑制的产物 — 与 r22 真实失败产物同构
# (timeMs 被使用, 只有 lastCheckTimeMs 未使用 → -Werror -Wunused-parameter)
GENERATED_BROKEN = (
    '#include <stdint.h>\n'
    '#include <stdbool.h>\n'
    '#include "window_modes.h"\n'
    '\n'
    'bool window_modes_check_pinch(uint32_t positionPulses, uint32_t timeMs,\n'
    '                              uint32_t lastCheckTimeMs)\n'
    '{\n'
    '    /* Pinch detection only enabled in the pinch zone (SW-004) */\n'
    '    if (timeMs > 1000) {\n'
    '        return false;\n'
    '    }\n'
    '    if (positionPulses > 100) {\n'
    '        return true;\n'
    '    }\n'
    '    return false;\n'
    '}\n'
)


def _session(tmp_path: Path, name: str = "g17-test") -> PipelineSession:
    import os
    from unittest import mock

    with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
        return PipelineSession(
            name=name,
            spec_path=str(tmp_path / "spec.md"),
            development_mode="generate-code",
        )


def _project(tmp_path: Path) -> Path:
    """Mini project with the real G-17 seed layout."""
    proj = tmp_path / "proj"
    app_src = proj / "src" / "app" / "src"
    app_inc = proj / "src" / "app" / "include"
    app_src.mkdir(parents=True)
    app_inc.mkdir(parents=True)
    (app_src / "window_modes.c").write_text(SEED_WINDOW_MODES_C, encoding="utf-8")
    (app_inc / "window_modes.h").write_text(WINDOW_MODES_H, encoding="utf-8")
    return proj


# ═══════════════════════════════════════════════════════════════════════
# _iter_void_suppressions
# ═══════════════════════════════════════════════════════════════════════

class TestIterVoidSuppressions:
    def test_extracts_real_g17_pattern(self, tmp_path):
        """多行签名 + 行尾注释: 正确归属 (lastCheckTimeMs, window_modes_check_pinch)."""
        engine = CodegenEngine(output_dir=tmp_path / "out", max_retries=0)
        pairs = engine._iter_void_suppressions(SEED_WINDOW_MODES_C)
        assert ("lastCheckTimeMs", "window_modes_check_pinch") in pairs

    def test_multiple_functions_attributed(self, tmp_path):
        src = (
            "void foo(int a)\n"
            "{\n"
            "    (void)a;\n"
            "}\n"
            "int bar(int b, int c)\n"
            "{\n"
            "    (void)b;\n"
            "    (void)c;\n"
            "    return 0;\n"
            "}\n"
        )
        engine = CodegenEngine(output_dir=tmp_path / "out", max_retries=0)
        pairs = engine._iter_void_suppressions(src)
        assert pairs == [("a", "foo"), ("b", "bar"), ("c", "bar")]

    def test_static_function_and_nested_block(self, tmp_path):
        src = (
            "static void helper(uint32_t x)\n"
            "{\n"
            "    if (x) {\n"
            "        (void)x;  /* unusual but legal */\n"
            "    }\n"
            "}\n"
        )
        engine = CodegenEngine(output_dir=tmp_path / "out", max_retries=0)
        pairs = engine._iter_void_suppressions(src)
        assert pairs == [("x", "helper")]


# ═══════════════════════════════════════════════════════════════════════
# _sync_void_suppressions
# ═══════════════════════════════════════════════════════════════════════

class TestSyncVoidSuppressions:
    def _engine_with_seed(self, tmp_path: Path) -> CodegenEngine:
        engine = CodegenEngine(output_dir=tmp_path / "out", max_retries=0)
        engine._seed_baseline = {
            "src/app/src/window_modes.c": SEED_WINDOW_MODES_C,
        }
        return engine

    def _write_generated(self, tmp_path: Path, content: str) -> Path:
        out = tmp_path / "out"
        f = out / "src" / "app" / "src" / "window_modes.c"
        f.parent.mkdir(parents=True)
        f.write_text(content, encoding="utf-8")
        # 头文件 (verify_c 需要 include 目录)
        h = out / "src" / "app" / "include" / "window_modes.h"
        h.parent.mkdir(parents=True)
        h.write_text(WINDOW_MODES_H, encoding="utf-8")
        return f

    def test_inserts_missing_suppression(self, tmp_path):
        engine = self._engine_with_seed(tmp_path)
        f = self._write_generated(tmp_path, GENERATED_BROKEN)
        applied = engine._sync_void_suppressions(tmp_path / "out", [f])
        content = f.read_text(encoding="utf-8")
        assert applied == 1
        assert "(void)lastCheckTimeMs;" in content
        # 插入在函数体开括号后
        assert "{\n    (void)lastCheckTimeMs;  /* deterministic sync" in content

    def test_noop_when_suppression_present(self, tmp_path):
        engine = self._engine_with_seed(tmp_path)
        f = self._write_generated(tmp_path, SEED_WINDOW_MODES_C)
        applied = engine._sync_void_suppressions(tmp_path / "out", [f])
        assert applied == 0
        # 不重复插入
        assert f.read_text(encoding="utf-8").count("(void)lastCheckTimeMs;") == 1

    def test_noop_when_param_not_in_signature(self, tmp_path):
        """生成代码把参数删了 (签名不含 X) → 不插 (seed_contract 会另行拦截)."""
        engine = self._engine_with_seed(tmp_path)
        rewritten = GENERATED_BROKEN.replace(
            "uint32_t timeMs,\n                              uint32_t lastCheckTimeMs)",
            "uint32_t timeMs)",
        )
        f = self._write_generated(tmp_path, rewritten)
        applied = engine._sync_void_suppressions(tmp_path / "out", [f])
        assert applied == 0
        assert "(void)lastCheckTimeMs;" not in f.read_text(encoding="utf-8")

    def test_synced_file_compiles_with_strict_flags(self, tmp_path):
        """同步后产物能过项目真实 -Wall -Wextra -Werror (G-17 验收点)."""
        engine = self._engine_with_seed(tmp_path)
        f = self._write_generated(tmp_path, GENERATED_BROKEN)
        engine._sync_void_suppressions(tmp_path / "out", [f])
        r = verify_c([f], cflags=["-Wall", "-Wextra", "-Werror"])
        assert r["ok"] is True, r.get("output")

    def test_skips_files_without_seed_baseline(self, tmp_path):
        engine = self._engine_with_seed(tmp_path)
        new_file = tmp_path / "out" / "src" / "app" / "src" / "window_new.c"
        new_file.parent.mkdir(parents=True)
        new_file.write_text(
            "int f(int x) {\n    return x;\n}\n", encoding="utf-8"
        )
        applied = engine._sync_void_suppressions(tmp_path / "out", [new_file])
        assert applied == 0


# ═══════════════════════════════════════════════════════════════════════
# engine.generate 端到端: mock LLM 丢抑制 → 引擎自动补回
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateCarriesSuppression:
    def test_generate_restores_dropped_suppression(self, tmp_path):
        proj = _project(tmp_path)
        session = _session(tmp_path)
        out_dir = tmp_path / "out"

        def llm(system, user, **kwargs):
            return {"content": (
                "### FILE: src/app/src/window_modes.c\n```c\n"
                + GENERATED_BROKEN
                + "```\n"
            )}

        engine = CodegenEngine(
            llm_client=llm,
            max_retries=0,
            seed_dir=proj,
            output_dir=out_dir,
        )
        result = engine.generate(session, "sys", "user")
        gen_file = out_dir / "src" / "app" / "src" / "window_modes.c"
        content = gen_file.read_text(encoding="utf-8")
        # 引擎确定性补回抑制, 不依赖 LLM repair
        assert "(void)lastCheckTimeMs;" in content
        # 补回后真实严格编译通过
        r = verify_c([gen_file], cflags=["-Wall", "-Wextra", "-Werror"])
        assert r["ok"] is True, r.get("output")
        assert result.status == "verified"
