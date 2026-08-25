#!/usr/bin/env python3
"""Regression tests for codegen seed-contract + behavior-verify (2026-08-16).

C: CodegenEngine._check_seed_contract — 生成代码删除既有公共函数 → 判定回归
A: _make_behavior_verify — 编译通过后跑真实测试, 失败反馈给 repair 轮
"""

# @tests src/yuleosh/codegen/engine.py

import sys
from pathlib import Path

import pytest

from yuleosh.codegen.engine import CodegenEngine  # noqa: E402
from yuleosh.pipeline.step_classes import (  # noqa: E402
    _collect_seed_contract,
)


# ── C: seed contract ─────────────────────────────────────────────────


class TestCheckSeedContract:
    def _engine(self, contract=None):
        e = CodegenEngine.__new__(CodegenEngine)
        e.seed_contract = contract
        return e

    def test_no_contract_no_op(self, tmp_path):
        e = self._engine(None)
        assert e._check_seed_contract(tmp_path) == ""

    def test_missing_function_detected(self, tmp_path):
        (tmp_path / "src" / "app" / "src").mkdir(parents=True)
        gen = tmp_path / "src" / "app" / "src" / "window_control.c"
        gen.write_text(
            "void window_control_init(void) {}\n"          # kept
            "void window_control_process(void) {}\n"        # kept
            "/* PINCH_REVERSAL 启动序列被删 */\n"
        )
        e = self._engine({
            "src/app/src/window_control.c": {
                "window_control_init",
                "window_control_process",
                "window_control_command",   # 缺失
            },
        })
        err = e._check_seed_contract(tmp_path)
        assert "window_control_command" in err
        assert "seed 契约破坏" in err

    def test_all_functions_present_ok(self, tmp_path):
        (tmp_path / "src" / "app" / "src").mkdir(parents=True)
        (tmp_path / "src" / "app" / "src" / "window_control.c").write_text(
            "void window_control_init(void) {}\n"
            "void window_control_process(void) {}\n"
            "void window_control_command(void) {}\n"
        )
        e = self._engine({
            "src/app/src/window_control.c": {
                "window_control_init",
                "window_control_process",
                "window_control_command",
            },
        })
        assert e._check_seed_contract(tmp_path) == ""

    def test_missing_whole_file(self, tmp_path):
        (tmp_path / "src" / "app" / "src").mkdir(parents=True)
        e = self._engine({
            "src/app/src/window_control.c": {"window_control_process"},
        })
        err = e._check_seed_contract(tmp_path)
        assert "整个文件缺失" in err


# ── contract collection ──────────────────────────────────────────────


class TestCollectSeedContract:
    def test_maps_header_funcs_to_impl(self, tmp_path):
        inc = tmp_path / "src" / "app" / "include"
        impl = tmp_path / "src" / "app" / "src"
        inc.mkdir(parents=True)
        impl.mkdir(parents=True)
        (inc / "window_control.h").write_text(
            "#ifndef W\n#define W\n"
            "void window_control_init(void);\n"
            "void window_control_process(void);\n"
            "static void helper(void);\n"   # static → still captured by regex
            "#endif\n"
        )
        (impl / "window_control.c").write_text(
            "void window_control_init(void) {}\n"
        )
        c = _collect_seed_contract(tmp_path)
        assert "src/app/src/window_control.c" in c
        funcs = c["src/app/src/window_control.c"]
        assert "window_control_init" in funcs
        assert "window_control_process" in funcs

    def test_real_window_anti_pinch(self):
        proj = Path(
            "/Users/stefan/workspace/window-anti-pinch/window-anti-pinch"
        )
        if not proj.exists():
            pytest.skip("window-anti-pinch not present")
        c = _collect_seed_contract(proj)
        assert "src/app/src/window_control.c" in c
        assert "window_control_process" in c["src/app/src/window_control.c"]
        # 全部实现文件都有契约。8/16 hal_nvm.h 加入 (SW-006 NVM) 后为 8 个
        # (window_config/control/modes/position + hal_hall/motor/nvm/timer)；
        # 2026-08-17 全量回归暴露旧断言 7 未同步。
        assert len(c) == 8
