#!/usr/bin/env python3

# @tests src/yuleosh/evidence/generator.py
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""C 项目测试覆盖收集 — codex-verify 2026-08-16 缺陷 4 的引擎根因。

window-anti-pinch (C 项目) 的 acceptance-matrix 全 ❌: _collect_test_coverage
只扫 test_*.py (Python AST + # Covers:), C 测试文件 (test_*.c) 被完全忽略
→ req_to_tests 全空 → 验收矩阵假红, 与真实 ctest 3/3 全绿矛盾。

修复 (2026-08-16):
- analysis.py: parse_covers_from_file 支持 C 注释 (// Covers: 与 /* */ 块)
  + C 函数名推断 (static void test_xxx(...))
- generator.py: _collect_test_coverage / _collect_scenario_refs_from_file
  同时扫 test_*.c / test_*.cpp
"""

from pathlib import Path

from yuleosh.evidence.analysis import (
    infer_covers_from_c_function_names,
    parse_c_comment_covers,
    parse_covers_from_file,
)
from yuleosh.evidence.generator import EvidenceCollector


def _write(tmp_path, name, content):
    p = Path(tmp_path) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


C_TEST_SAMPLE = """\
#include "window_control.h"

/*
 * Covers: pinch, reversal, stall
 * Scenario-Ref: SC-001, SC-002
 */
static void test_config_validate(void)
{
    CHECK(window_config_validate(&cfg));
}

// Covers: calibration, zone
static void test_position_calibrate_zone(void)
{
    CHECK(window_position_is_calibrated(&pos));
}
"""


class TestCCommentCovers:
    def test_parse_c_comment_covers_block(self):
        kw = parse_c_comment_covers(C_TEST_SAMPLE)
        assert "pinch" in kw
        assert "reversal" in kw
        assert "stall" in kw

    def test_parse_c_comment_covers_line(self):
        kw = parse_c_comment_covers(C_TEST_SAMPLE)
        assert "calibration" in kw
        assert "zone" in kw

    def test_infer_covers_from_c_function_names(self):
        kw = infer_covers_from_c_function_names(C_TEST_SAMPLE)
        assert "config" in kw
        assert "validate" in kw
        assert "position" in kw
        assert "calibrate" in kw


class TestParseCoversFromFileC:
    def test_parse_covers_from_c_file(self, tmp_path):
        f = _write(tmp_path, "tests/test_window_control.c", C_TEST_SAMPLE)
        kw = parse_covers_from_file(str(f))
        # 块注释 Covers + 行注释 Covers + 函数名推断 合并
        assert "pinch" in kw
        assert "calibration" in kw
        assert "validate" in kw

    def test_parse_covers_python_still_works(self, tmp_path):
        f = _write(
            tmp_path, "tests/test_something.py",
            '"""Covers: pipeline, processing"""\n'
            "def test_pipeline_processing():\n    assert True\n",
        )
        kw = parse_covers_from_file(str(f))
        assert "pipeline" in kw


class TestCollectTestCoverageC:
    def test_collects_c_test_files(self, tmp_path):
        collector = EvidenceCollector(project_dir=str(tmp_path))
        _write(tmp_path, "tests/test_window_control.c", C_TEST_SAMPLE)
        coverage = collector._collect_test_coverage()
        assert "test_window_control.c" in coverage
        assert "pinch" in coverage["test_window_control.c"]

    def test_collects_both_py_and_c(self, tmp_path):
        collector = EvidenceCollector(project_dir=str(tmp_path))
        _write(tmp_path, "tests/test_window_control.c", C_TEST_SAMPLE)
        _write(
            tmp_path, "tests/test_pipeline.py",
            '"""Covers: pipeline"""\ndef test_pipeline():\n    assert True\n',
        )
        coverage = collector._collect_test_coverage()
        assert "test_window_control.c" in coverage
        assert "test_pipeline.py" in coverage

    def test_no_test_dir_returns_empty(self, tmp_path):
        collector = EvidenceCollector(project_dir=str(tmp_path))
        assert collector._collect_test_coverage() == {}
