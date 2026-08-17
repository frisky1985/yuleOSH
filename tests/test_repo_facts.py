"""repo_facts 模块单测 — 2026-08-18 r21e 文档步骤仓库事实快照。

覆盖: 测试框架探测 (custom-Check vs Unity vs pytest)、测试函数统计、
ASIL 来源扩展 (yuleosh.yaml → project-context.md/README.md)、
collect_repo_facts 快照结构、format_repo_facts 注入文本。
"""

import json
from pathlib import Path

import pytest

from yuleosh.pipeline.repo_facts import (
    collect_repo_facts,
    count_test_functions,
    detect_test_framework,
    format_repo_facts,
    get_project_asil,
)


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """构造一个 C 项目骨架: src + tests (自定义 CHECK harness) + 覆盖率报告。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "window_control.c").write_text(
        "#include \"window_control.h\"\n"
        "static int clamp_speed(int v) { return v < 0 ? 0 : v; }\n"
        "void window_control_init(void) {}\n"
    )
    (tmp_path / "src" / "window_control.h").write_text(
        "#ifndef WINDOW_CONTROL_H\n#define WINDOW_CONTROL_H\n"
        "void window_control_init(void);\n#endif\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_window_control.c").write_text(
        "#define CHECK(cond) do { if (!(cond)) fail(); } while (0)\n"
        "static void test_init(void) { CHECK(1); }\n"
        "static void test_clamp(void) { CHECK(1); }\n"
        "static void test_edge(void) { CHECK(1); }\n"
    )
    (tmp_path / ".yuleosh" / "reports").mkdir(parents=True)
    (tmp_path / ".yuleosh" / "reports" / "c-coverage.json").write_text(
        json.dumps({"totals": {"line_rate": 0.9285, "branch_rate": 0.8107,
                               "functions": 42}})
    )
    return tmp_path


class TestDetectTestFramework:
    def test_custom_check_harness(self, tmp_path: Path):
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_a.c").write_text(
            "#define CHECK(cond) do { if (!(cond)) fail(); } while (0)\n"
            "static void test_a(void) { CHECK(1); }\n"
        )
        assert detect_test_framework(tmp_path / "tests") == "custom-Check"

    def test_unity(self, tmp_path: Path):
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_b.c").write_text(
            "#include \"unity.h\"\n"
            "void test_b(void) { TEST_ASSERT_EQUAL(1, 1); }\n"
        )
        assert detect_test_framework(tmp_path / "tests") == "unity"

    def test_pytest(self, tmp_path: Path):
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_c.py").write_text(
            "import pytest\n\ndef test_c():\n    assert True\n"
        )
        assert detect_test_framework(tmp_path / "tests") == "pytest"

    def test_missing_dir(self, tmp_path: Path):
        assert detect_test_framework(tmp_path / "nope") == "unknown"


class TestCountTestFunctions:
    def test_counts_test_prefix(self, tmp_path: Path):
        f = tmp_path / "test_x.c"
        f.write_text(
            "static void test_one(void) {}\n"
            "void test_two(void) {}\n"
            "static int helper(void) { return 0; }\n"
            "static void not_a_test_call() { test_one(); }\n"
        )
        # test_one + test_two; helper/not_a_test 不匹配
        assert count_test_functions(f) == 2

    def test_missing_file(self, tmp_path: Path):
        assert count_test_functions(tmp_path / "missing.c") == 0


class TestGetProjectAsil:
    def test_from_yuleosh_yaml(self, tmp_path: Path):
        (tmp_path / "yuleosh.yaml").write_text("asil: ASIL_B\n")
        assert get_project_asil(tmp_path) == "ASIL_B"

    def test_from_project_context_md(self, tmp_path: Path):
        (tmp_path / "project-context.md").write_text(
            "# Project\nSafety level: ASIL_D\n"
        )
        assert get_project_asil(tmp_path) == "ASIL_D"

    def test_from_readme(self, tmp_path: Path):
        (tmp_path / "README.md").write_text(
            "This module targets ASIL-B\n"
        )
        assert get_project_asil(tmp_path) == "ASIL_B"

    def test_not_declared(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("No safety level here.\n")
        assert get_project_asil(tmp_path) == ""


class TestCollectRepoFacts:
    def test_snapshot_structure(self, sample_project: Path):
        facts = collect_repo_facts(sample_project)
        assert facts["src_file_count"] == 2
        assert facts["test_file_count"] == 1
        assert facts["test_func_count"] == 3
        assert facts["test_framework"] == "custom-Check"
        assert facts["coverage"] != ""
        assert "line_rate=0.9285" in facts["coverage"]
        assert facts["project_asil"] == ""

    def test_no_coverage_report(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.c").write_text("int a(void) { return 1; }\n")
        facts = collect_repo_facts(tmp_path)
        assert facts["coverage"] == ""

    def test_format_contains_facts(self, sample_project: Path):
        facts = collect_repo_facts(sample_project)
        text = format_repo_facts(facts)
        assert "Repository Facts" in text
        assert "Source files: 2" in text
        assert "Test functions: 3" in text
        assert "Test framework: custom-Check" in text
        assert "Test files (1)" in text
        assert "test_window_control.c" in text
        assert "do NOT invent one" in text  # ASIL 未声明提示
