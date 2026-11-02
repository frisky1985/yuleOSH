# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for run_c_test_suite CMock-skip semantics — 反假绿把守.

2026-11-02: c-unit-test 的 gcc-compile-check 回退路径新增「缺 CMock 的
测试跳过」逻辑。本文件锁死其边界:

* **全部**测试被跳过时 status 必须是 ``skipped`` — 0 个测试执行过的
  "passed" 是假绿 (guardrail.TestResult 四态契约, guardrail.py:238-250)。
* 部分跳过不误伤: 有测试真实执行且编译通过 → ``passed`` + skipped 计数。
* 无 CMock 跳过的既有口径不变 (skipped == 0 → passed)。
"""

import shutil
from pathlib import Path

import pytest

from yuleosh.pipeline.step_handlers.test_c_unit import run_c_test_suite

requires_gcc = pytest.mark.skipif(
    shutil.which("gcc") is None, reason="gcc not available"
)


def _make_project(tmp_path: Path, test_sources: dict[str, str]) -> Path:
    """Create a minimal C project: src/main.c + tests/<name>.c files."""
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "main.c").write_text(
        "int app_main(void) { return 0; }\n", encoding="utf-8"
    )
    tests = tmp_path / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    for name, text in test_sources.items():
        (tests / name).write_text(text, encoding="utf-8")
    return tmp_path


# 不含 Mock_ 的自包含测试 — gcc 可直接编译链接。
_CLEAN_TEST = "int main(void) { return 0; }\n"
# 引用 CMock 的测试 — 缺 Mock_*.h 时不可编译, 应被跳过。
_CMOCK_TEST = (
    "/* needs CMock */\n"
    "void Mock_Dio_WriteChannel_Expect(void);\n"
    "int main(void) { return 0; }\n"
)


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """隔离 Path.home — 开发机 ~/workspace/AUTOSAR 的 Unity 不能泄漏进测试。"""
    home = tmp_path / "fake-home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@requires_gcc
def test_all_tests_skipped_is_not_passed(tmp_path, isolated_home):
    """GIVEN 唯一测试缺 CMock WHEN 跑 suite THEN status=skipped (非 passed).

    修复前: skipped 不计入 failed → compiled_ok=True, failed=0 →
    status="passed" (0 个测试执行过的假绿)。
    """
    proj = _make_project(tmp_path / "p", {"test_cmock_only.c": _CMOCK_TEST})

    result = run_c_test_suite(proj)

    assert result["runner"] == "gcc-compile-check"
    assert result["c_test_files"] == 1
    assert result["skipped"] == 1
    assert result["skipped_tests"] == ["test_cmock_only"]
    assert result["passed"] == 0
    assert result["failed"] == 0
    # 核心断言: 全部跳过 → 不得 passed
    assert result["status"] == "skipped"
    assert "SKIPPED" in result["output"]


@requires_gcc
def test_partial_skip_still_passes_with_visible_count(tmp_path, isolated_home):
    """GIVEN 一个 CMock 测试 + 一个可编译测试 WHEN 跑 suite THEN passed 且 skipped 可见."""
    proj = _make_project(tmp_path / "p", {
        "test_cmock_one.c": _CMOCK_TEST,
        "test_clean_one.c": _CLEAN_TEST,
    })

    result = run_c_test_suite(proj)

    assert result["runner"] == "gcc-compile-check"
    assert result["c_test_files"] == 2
    assert result["skipped"] == 1
    assert result["status"] == "passed"
    assert result["failed"] == 0


@requires_gcc
def test_no_cmock_skip_keeps_legacy_semantics(tmp_path, isolated_home):
    """GIVEN 全部测试可编译 WHEN 跑 suite THEN passed, skipped=0 (既有口径不变)."""
    proj = _make_project(tmp_path / "p", {
        "test_clean_one.c": _CLEAN_TEST,
        "test_clean_two.c": _CLEAN_TEST,
    })

    result = run_c_test_suite(proj)

    assert result["status"] == "passed"
    assert result["skipped"] == 0
    assert result["skipped_tests"] == []


def test_no_c_sources_returns_skipped_with_field(tmp_path):
    """GIVEN 无 C 源码 WHEN 跑 suite THEN skipped 且 skipped 字段存在 (dict 形状稳定)."""
    proj = tmp_path / "empty"
    proj.mkdir()

    result = run_c_test_suite(proj)

    assert result["status"] == "skipped"
    assert result["skipped"] == 0


def test_cc_test_runner_passes_skipped_through(tmp_path, isolated_home, monkeypatch):
    """GIVEN 全跳过项目 WHEN CCTestRunner 包装 THEN status/skipped 透传 (证据链可见)."""
    from yuleosh.pipeline.guardrail import CCTestRunner

    proj = _make_project(tmp_path / "p", {"test_cmock_only.c": _CMOCK_TEST})

    result = CCTestRunner().run(proj)

    assert result.status == "skipped"
    assert result.extra["skipped"] == 1
    assert result.extra["c_test_files"] == 1
