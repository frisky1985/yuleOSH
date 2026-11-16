#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""test-codegen: 生成可执行 C 单元测试（SWE.4 覆盖证据）。

2026-11-16 CL2 真跑暴露: 流水线只执行测试、从不生成测试 → 覆盖率恒为 0%，
G6/G7 永远红。本套测试锁定生成 + 构建 + 运行 + 追溯注解这条链。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuleosh.pipeline.session import PipelineStepError
from yuleosh.pipeline.step_handlers.test_codegen import (
    _ensure_coverage_option,
    _ensure_test_wiring,
    step_test_codegen,
)

CMAKE = """cmake_minimum_required(VERSION 3.16)
project(demo C)
set(CMAKE_C_STANDARD 99)
file(GLOB_RECURSE SRCS CONFIGURE_DEPENDS src/*.c)
add_library(demo STATIC ${SRCS})
target_include_directories(demo PUBLIC src/include)
"""

HEADER = "int demo_value(void);\n"
SOURCE = '#include "demo.h"\nint demo_value(void) { return 42; }\n'
SPEC = """# Demo

### RS-001: demo value

- The system SHALL expose `int demo_value(void)` returning 42.
"""

GOOD_TEST = """// @req RS-001
#include <stdio.h>
#include "demo.h"

int main(void) {
    if (demo_value() != 42) {
        printf("FAIL demo_value\\n");
        return 1;
    }
    printf("PASS demo_value\\n");
    return 0;
}
"""


def _project(tmp_path: Path, *, spec: str = SPEC) -> Path:
    (tmp_path / "CMakeLists.txt").write_text(CMAKE, encoding="utf-8")
    (tmp_path / "src" / "include").mkdir(parents=True)
    (tmp_path / "src" / "include" / "demo.h").write_text(HEADER, encoding="utf-8")
    (tmp_path / "src" / "demo.c").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.md").write_text(spec, encoding="utf-8")
    return tmp_path


def _session(project: Path, llm) -> SimpleNamespace:
    session_dir = project / ".osh" / "sessions" / "S1"
    session_dir.mkdir(parents=True)
    return SimpleNamespace(
        name="S1",
        project_dir=str(project),
        spec_path=str(project / "docs" / "spec.md"),
        session_dir=session_dir,
        artifacts={},
        mock_mode=False,
        llm_client=llm,
        agent_constraints="",
        agent_constraints_by_role={},
        pipeline_knowledge_config={},
        pipeline_knowledge_step_key="",
    )


def _llm_returning(*payloads):
    calls = {"n": 0}

    def _client(system, user, **kwargs):
        idx = min(calls["n"], len(payloads) - 1)
        calls["n"] += 1
        return {"content": payloads[idx]}

    return _client, calls


def _wrap_c(path: str, body: str) -> str:
    return f"### FILE: {path}\n```c\n{body}\n```\n"


class TestWiring:
    def test_coverage_option_inserted_before_targets(self):
        text = _ensure_coverage_option(CMAKE)
        assert "ENABLE_COVERAGE" in text
        # 必须插在 add_library 之前，否则被测库没有 --coverage 插桩。
        assert text.index("add_compile_options") < text.index("add_library")

    def test_wiring_is_idempotent(self):
        once = _ensure_test_wiring(_ensure_coverage_option(CMAKE))
        twice = _ensure_test_wiring(_ensure_coverage_option(once))
        assert once == twice
        assert once.count("add_subdirectory(tests)") == 1


class TestSkip:
    def test_skip_without_cmake(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "spec.md").write_text(SPEC, encoding="utf-8")
        session = _session(tmp_path, lambda *a, **k: {"content": ""})
        report = json.loads(Path(step_test_codegen(session)).read_text())
        assert report["status"] == "skipped"
        assert "CMakeLists" in report["reason"]

    def test_existing_passing_suite_is_reused(self, tmp_path):
        project = _project(tmp_path)
        (project / "tests").mkdir()
        (project / "tests" / "test_demo.c").write_text(GOOD_TEST, encoding="utf-8")
        llm, calls = _llm_returning(_wrap_c("tests/test_demo.c", GOOD_TEST))
        session = _session(project, llm)
        report = json.loads(Path(step_test_codegen(session)).read_text())
        assert report["status"] == "passed"
        assert report["reason"] == "re-ran existing suite"
        assert calls["n"] == 0  # 已有测试通过 → 不调用 LLM 重新生成

    def test_skip_when_no_requirements(self, tmp_path):
        project = _project(tmp_path, spec="# Empty\n\nNo requirements here.\n")
        session = _session(project, lambda *a, **k: {"content": ""})
        report = json.loads(Path(step_test_codegen(session)).read_text())
        assert report["status"] == "skipped"
        assert "requirement" in report["reason"]


class TestGeneration:
    def test_generates_builds_and_passes(self, tmp_path):
        project = _project(tmp_path)
        llm, calls = _llm_returning(_wrap_c("tests/test_demo.c", GOOD_TEST))
        session = _session(project, llm)

        report = json.loads(Path(step_test_codegen(session)).read_text())

        assert report["status"] == "passed"
        assert report["covered_requirements"] == ["RS-001"]
        assert report["tests"] == ["tests/test_demo.c"]
        assert calls["n"] == 1
        # 测试文件与构建接线都落盘
        assert (project / "tests" / "test_demo.c").is_file()
        assert "add_test(NAME test_demo" in (
            project / "tests" / "CMakeLists.txt").read_text()
        root = (project / "CMakeLists.txt").read_text()
        assert "enable_testing()" in root and "ENABLE_COVERAGE" in root

    def test_untraceable_tests_are_rejected(self, tmp_path):
        project = _project(tmp_path)
        no_annotation = GOOD_TEST.replace("// @req RS-001\n", "")
        llm, _ = _llm_returning(_wrap_c("tests/test_demo.c", no_annotation))
        session = _session(project, llm)
        with pytest.raises(PipelineStepError) as exc:
            step_test_codegen(session)
        assert "@req" in str(exc.value)

    def test_repairs_after_build_failure(self, tmp_path):
        project = _project(tmp_path)
        broken = "// @req RS-001\nthis is not C;\n"
        llm, calls = _llm_returning(
            _wrap_c("tests/test_demo.c", broken),
            _wrap_c("tests/test_demo.c", GOOD_TEST),
        )
        session = _session(project, llm)
        report = json.loads(Path(step_test_codegen(session)).read_text())
        assert report["status"] == "passed"
        assert report["attempts"] == 2
        assert calls["n"] == 2

    def test_fails_after_repair_budget(self, tmp_path):
        project = _project(tmp_path)
        broken = "// @req RS-001\nthis is not C;\n"
        llm, calls = _llm_returning(_wrap_c("tests/test_demo.c", broken))
        session = _session(project, llm)
        with pytest.raises(PipelineStepError):
            step_test_codegen(session)
        assert calls["n"] == 3  # 1 次生成 + 2 次修复
