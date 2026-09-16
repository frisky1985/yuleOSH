"""G6/G7 double-main 修复验证。

回归背景：
- G6 (c-unit-test) 的 gcc 回退编译路径未定义 LED_CHASER_UNIT_TEST，而
  gpio-led-chaser 模板测试经 #include "../src/main.c" 复用实现, 其 int main
  由该宏守卫 → 重复定义 'main' → G6 假失败。
- G7 (c-coverage-gate) 用 session_dir 向上 3 层推导 project_dir, 在 .osh 不在
  project 下的布局里会落到错误目录 (CMakeLists.txt 缺失) → cmake configure 失败。

本文件验证两处修复。
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from yuleosh.pipeline.step_handlers import test_c_unit as _tcu
from yuleosh.pipeline.step_handlers import c_coverage_gate as _ccg


def test_unit_test_compile_defs_detects_macro(tmp_path):
    f = tmp_path / "test_foo.c"
    f.write_text("/* references LED_CHASER_UNIT_TEST */\nint main(void){return 0;}\n")
    assert _tcu._unit_test_compile_defs([f]) == ["-DLED_CHASER_UNIT_TEST"]


def test_unit_test_compile_defs_no_macro(tmp_path):
    f = tmp_path / "test_bar.c"
    f.write_text("int main(void){return 0;}\n")
    assert _tcu._unit_test_compile_defs([f]) == []


def test_unit_test_compile_defs_dedup(tmp_path):
    a = tmp_path / "a.c"
    b = tmp_path / "b.c"
    a.write_text("LED_CHASER_UNIT_TEST\n")
    b.write_text("LED_CHASER_UNIT_TEST\n")
    out = _tcu._unit_test_compile_defs([a, b])
    assert out == ["-DLED_CHASER_UNIT_TEST"]


def test_resolve_coverage_project_dir_from_spec():
    class S:
        spec_path = "/proj/gpio-led-chaser/docs/spec.md"
        session_dir = "/proj/.osh/sessions/x"

    assert _ccg._resolve_coverage_project_dir(S()) == "/proj/gpio-led-chaser"


def test_resolve_coverage_project_dir_fallback():
    class S:
        spec_path = None
        session_dir = "/proj/.osh/sessions/x"

    assert _ccg._resolve_coverage_project_dir(S()) == "/proj"


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")
def test_g6_gpio_template_compiles_with_macro():
    """复制 gpio-led-chaser 模板到临时目录, 直接跑 run_c_test_suite,
    断言 gcc 回退路径因定义了 LED_CHASER_UNIT_TEST 而通过 (无重复 main)。"""
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "templates" / "gpio-led-chaser"
    if not src.exists():
        pytest.skip("gpio-led-chaser template not found")
    dst = Path(__import__("tempfile").mkdtemp()) / "gpio-led-chaser"
    shutil.copytree(src, dst)
    result = _tcu.run_c_test_suite(dst)
    # gcc 回退路径: 编译成功 (returncode==0) 且 status 非 failed
    assert result["returncode"] == 0, result.get("output", "")
    assert result["status"] != "failed", result.get("output", "")
