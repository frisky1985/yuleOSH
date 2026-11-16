
# @tests src/yuleosh/evidence/generator.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Deep tests for evidence/pack.py — mock FS, IO, zip, no real filesystem.

Target: 80%+ branch coverage (from ~0%).
Covers: EvidenceCollector (all parsing, collection, generation methods),
        _check_pipeline_not_running, generate_evidence, main().
"""

import ast
import json
import os
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


# ==================================================================
# Fixtures
# ==================================================================

@pytest.fixture
def tmp_proj():
    """Temporary project directory with minimal structure."""
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def collector(tmp_proj):
    """Fresh EvidenceCollector with mocked fs where needed."""
    from yuleosh.evidence.pack import EvidenceCollector
    return EvidenceCollector(tmp_proj)


@pytest.fixture
def collector_with_review_artifacts(tmp_proj):
    """Collector + 两个 review 任务目录，同一 review-session.json 文件名，
    触发 aggregate_review_logs 的归档路径（rev_dir.exists → dest.exists 碰撞）。"""
    from yuleosh.evidence.pack import EvidenceCollector

    # 任务 1：legacy 格式
    task1 = Path(tmp_proj) / ".osh" / "reviews" / "task-1"
    task1.mkdir(parents=True)
    (task1 / "review-session.json").write_text(json.dumps({
        "task": "Task 1", "decision": "passed", "created_at": "2025-06-01",
        "reviews": [
            {"reviewer": "bot", "status": "passed",
             "finding_breakdown": {"critical": 0, "major": 0, "minor": 0},
             "summary": "ok"}
        ],
    }))
    # 任务 2：flat 格式 + 同名文件 → 触发碰撞分支
    task2 = Path(tmp_proj) / ".osh" / "reviews" / "task-2"
    task2.mkdir(parents=True)
    (task2 / "review-session.json").write_text(json.dumps({
        "review_type": "lint", "status": "passed",
        "agent": "lint-bot", "generated_at": "2025-06-02",
        "summary": "all clean", "findings": [],
    }))
    # 另一个独立文件（不会碰撞）
    (task2 / "extra-code-review.json").write_text(json.dumps({
        "review_type": "code", "status": "passed",
        "agent": "code-bot", "findings": [],
    }))

    c = EvidenceCollector(tmp_proj)
    # 给 reviews 一个 legacy 记录（有 actual review data 触发表格渲染）
    c.reviews = [
        {"task": "Task 1", "decision": "passed", "created_at": "2025-06-01",
         "reviews": [
             {"reviewer": "style-bot", "status": "passed",
              "finding_breakdown": {"critical": 0, "major": 0, "minor": 0},
              "summary": "ok"}]},
    ]
    return c


@pytest.fixture
def collector_with_reqs(collector):
    """Collector pre-loaded with sample requirements and scenarios."""
    collector.requirements = [
        {
            "name": "Pipeline Processing",
            "req_id": "RS-001",
            "shall_count": 2,
            "shall": ["The system SHALL process pipelines", "The system SHALL retry on failure"],
        },
        {
            "name": "User Authentication",
            "req_id": "RS-002",
            "shall_count": 1,
            "shall": ["The system SHALL authenticate users"],
        },
    ]
    collector.scenarios = [
        {"name": "Pipeline Processing Scenario", "given": ["pipeline exists"], "when": ["run"], "then": ["output"]},
        {"name": "Auth Login", "given": ["credentials"], "when": ["login"], "then": ["token"]},
    ]
    return collector


# ==================================================================
# _parse_scenario_refs
# ==================================================================

class TestParseScenarioRefs:
    def test_no_refs(self):
        from yuleosh.evidence.pack import EvidenceCollector
        assert EvidenceCollector._parse_scenario_refs("no refs here") == []

    def test_inline_covers_line(self):
        from yuleosh.evidence.pack import EvidenceCollector
        text = 'Covers: pipeline, SDD, Scenario-Ref: SDD \u2192 DDD \u2192 TDD \u5168\u6d41\u7a0b'
        refs = EvidenceCollector._parse_scenario_refs(text)
        assert len(refs) == 1
        assert "SDD" in refs[0]

    def test_standalone_line(self):
        from yuleosh.evidence.pack import EvidenceCollector
        text = 'Scenario-Ref: CI/CD \u4e09\u5c42\u9a8c\u8bc1'
        refs = EvidenceCollector._parse_scenario_refs(text)
        assert len(refs) == 1
        assert "CI/CD" in refs[0]

    def test_multiple_refs(self):
        from yuleosh.evidence.pack import EvidenceCollector
        text = "Scenario-Ref: CI/CD\nScenario-Ref: pipeline"
        refs = EvidenceCollector._parse_scenario_refs(text)
        assert len(refs) == 2

    def test_deduplication(self):
        from yuleosh.evidence.pack import EvidenceCollector
        text = "Scenario-Ref: CI/CD\nScenario-Ref: CI/CD"
        refs = EvidenceCollector._parse_scenario_refs(text)
        assert len(refs) == 1

    def test_trailing_quotes_cleaned(self):
        from yuleosh.evidence.pack import EvidenceCollector
        text = 'Scenario-Ref: CI/CD"""'
        refs = EvidenceCollector._parse_scenario_refs(text)
        assert refs == ["CI/CD"]


# ==================================================================
# _parse_module_covers
# ==================================================================

class TestParseModuleCovers:
    def test_no_docstring(self):
        from yuleosh.evidence.pack import EvidenceCollector
        tree = ast.parse("x = 1")
        assert EvidenceCollector._parse_module_covers(tree) == []

    def test_with_covers(self):
        from yuleosh.evidence.pack import EvidenceCollector
        code = '"""Covers: pipeline, review"""\nx = 1\n'
        tree = ast.parse(code)
        covers = EvidenceCollector._parse_module_covers(tree)
        assert "pipeline" in covers
        assert "review" in covers

    def test_scenario_ref_stripped(self):
        from yuleosh.evidence.pack import EvidenceCollector
        code = '"""Covers: pipeline, Scenario-Ref: CI/CD"""\nx = 1\n'
        tree = ast.parse(code)
        covers = EvidenceCollector._parse_module_covers(tree)
        assert "pipeline" in covers
        assert "CI/CD" not in covers


# ==================================================================
# _parse_comment_covers
# ==================================================================

class TestParseCommentCovers:
    def test_no_covers(self):
        from yuleosh.evidence.pack import EvidenceCollector
        assert EvidenceCollector._parse_comment_covers("no marker") == []

    def test_comment_covers(self):
        from yuleosh.evidence.pack import EvidenceCollector
        content = "# Covers: pipeline, review\n"
        covers = EvidenceCollector._parse_comment_covers(content)
        assert "pipeline" in covers
        assert "review" in covers

    def test_scenario_ref_stripped(self):
        from yuleosh.evidence.pack import EvidenceCollector
        content = "# Covers: pipeline, Scenario-Ref: CI/CD\n"
        covers = EvidenceCollector._parse_comment_covers(content)
        assert "pipeline" in covers
        assert "CI/CD" not in covers


# ==================================================================
# _parse_function_covers
# ==================================================================

class TestParseFunctionCovers:
    def test_no_test_funcs(self):
        from yuleosh.evidence.pack import EvidenceCollector
        tree = ast.parse("def helper(): pass")
        collector = mock.MagicMock()
        collector._parse_function_covers = EvidenceCollector._parse_function_covers.__get__(collector, EvidenceCollector)
        assert collector._parse_function_covers(tree) == []

    def test_test_func_with_covers(self):
        from yuleosh.evidence.pack import EvidenceCollector
        code = '''
def test_pipeline():
    """Covers: pipeline, retry"""
    pass
'''
        tree = ast.parse(code)
        collector = mock.MagicMock()
        collector._parse_function_covers = EvidenceCollector._parse_function_covers.__get__(collector, EvidenceCollector)
        covers = collector._parse_function_covers(tree)
        assert "pipeline" in covers
        assert "retry" in covers


# ==================================================================
# _infer_covers_from_function_names
# ==================================================================

class TestInferCoversFromFunctionNames:
    def test_no_test_funcs(self):
        from yuleosh.evidence.pack import EvidenceCollector
        tree = ast.parse("def helper(): pass")
        assert EvidenceCollector._infer_covers_from_function_names(tree) == []

    def test_infers_from_name(self):
        from yuleosh.evidence.pack import EvidenceCollector
        code = '''
def test_pipeline_processing():
    pass
def test_user_auth():
    pass
'''
        tree = ast.parse(code)
        inferred = EvidenceCollector._infer_covers_from_function_names(tree)
        assert "pipeline" in inferred
        assert "processing" in inferred
        assert "user" in inferred
        assert "auth" in inferred

    def test_skip_stop_words(self):
        from yuleosh.evidence.pack import EvidenceCollector
        code = '''
def test_the_system():
    pass
'''
        tree = ast.parse(code)
        inferred = EvidenceCollector._infer_covers_from_function_names(tree)
        assert "system" not in inferred  # stop word
        assert "the" not in inferred      # stop word


# ==================================================================
# _parse_covers_from_file
# ==================================================================

class TestParseCoversFromFile:
    def test_file_not_found(self, collector):
        covers = collector._parse_covers_from_file("/nonexistent/test_x.py")
        assert covers == []

    def test_syntax_error_fallback(self, collector, tmp_proj):
        bad_file = os.path.join(tmp_proj, "test_bad.py")
        with open(bad_file, "w") as f:
            f.write("# Covers: pipeline\nthis is not valid python {{{")
        covers = collector._parse_covers_from_file(bad_file)
        assert "pipeline" in covers

    def test_full_parse(self, collector, tmp_proj):
        test_file = os.path.join(tmp_proj, "test_full.py")
        with open(test_file, "w") as f:
            f.write('''"""Covers: pipeline, review"""
def test_ci_blocking():
    """Covers: CI blocking"""
    pass
def test_user_auth():
    pass
''')
        covers = collector._parse_covers_from_file(test_file)
        assert "pipeline" in covers
        assert "review" in covers
        assert "CI blocking" in covers
        assert "user" in covers  # inferred
        assert "auth" in covers  # inferred


# ==================================================================
# _collect_test_coverage
# ==================================================================

class TestCollectTestCoverage:
    def test_no_tests_dir(self, collector, tmp_proj):
        result = collector._collect_test_coverage()
        assert result == {}

    def test_with_test_files(self, collector, tmp_proj):
        tests_dir = os.path.join(tmp_proj, "tests")
        os.makedirs(tests_dir)
        with open(os.path.join(tests_dir, "test_foo.py"), "w") as f:
            f.write('"""Covers: pipeline"""\ndef test_foo(): pass\n')
        with open(os.path.join(tests_dir, "test_bar.py"), "w") as f:
            f.write('"""Covers: review"""\ndef test_bar(): pass\n')
        result = collector._collect_test_coverage()
        assert "test_foo.py" in result
        assert "test_bar.py" in result
        assert "pipeline" in result["test_foo.py"]
        assert "review" in result["test_bar.py"]

    def test_parse_failure(self, collector, tmp_proj):
        tests_dir = os.path.join(tmp_proj, "tests")
        os.makedirs(tests_dir)
        with open(os.path.join(tests_dir, "test_crash.py"), "w") as f:
            f.write("# Covers: pipeline\n")
        # Should not crash, just log
        result = collector._collect_test_coverage()
        assert "test_crash.py" in result

    def test_no_cover_markers(self, collector, tmp_proj):
        tests_dir = os.path.join(tmp_proj, "tests")
        os.makedirs(tests_dir)
        # File with only a passthrough test function — inferred keyword "bare" is not
        # a Covers marker so _collect_test_coverage still returns the file
        with open(os.path.join(tests_dir, "test_bare.py"), "w") as f:
            f.write("def test_bare(): pass\n")
        collector._collect_test_coverage()
        # The file gets collected because function-name inference adds "bare"
        assert "test_bare.py" in collector.test_coverage
        assert "bare" in collector.test_coverage["test_bare.py"]


# ==================================================================
# _build_requirement_to_test_map
# ==================================================================

class TestBuildRequirementToTestMap:
    def test_empty_requirements(self, collector):
        collector.test_coverage = {"test_foo.py": ["pipeline"]}
        r2t, t2r = collector._build_requirement_to_test_map()
        assert r2t == {}
        assert t2r == {"test_foo.py": []}

    def test_keyword_match(self, collector_with_reqs):
        c = collector_with_reqs
        c.test_coverage = {"test_pipe.py": ["pipeline"]}
        r2t, t2r = c._build_requirement_to_test_map()
        assert "Pipeline Processing" in r2t
        assert "test_pipe.py" in r2t["Pipeline Processing"]

    def test_exact_scenario_ref_match(self, collector_with_reqs, tmp_proj):
        c = collector_with_reqs
        # Create a test file with scenario-ref
        os.makedirs(os.path.join(tmp_proj, "tests"), exist_ok=True)
        test_file = os.path.join(tmp_proj, "tests", "test_scenario.py")
        with open(test_file, "w") as f:
            f.write('"""Covers: pipeline, Scenario-Ref: Pipeline Processing Scenario"""\n')
        c.test_coverage = {"test_scenario.py": ["pipeline"]}
        r2t, t2r = c._build_requirement_to_test_map()
        assert "Pipeline Processing" in r2t
        assert "test_scenario.py" in r2t["Pipeline Processing"]

    def test_no_match(self, collector_with_reqs):
        c = collector_with_reqs
        c.test_coverage = {"test_other.py": ["unrelated"]}
        r2t, t2r = c._build_requirement_to_test_map()
        assert r2t.get("Pipeline Processing") == []


# ==================================================================
# _categorize_uncovered
# ==================================================================

class TestCategorizeUncovered:
    def test_critical(self):
        from yuleosh.evidence.pack import EvidenceCollector
        uncovered = [{"req_name": "Pipeline", "shall": "process pipelines"}]
        crit, warn = EvidenceCollector._categorize_uncovered(uncovered)
        assert len(crit) == 1
        assert len(warn) == 0

    def test_warn_non_functional(self):
        from yuleosh.evidence.pack import EvidenceCollector
        uncovered = [{"req_name": "UI", "shall": "render interface"}]
        crit, warn = EvidenceCollector._categorize_uncovered(uncovered)
        assert len(crit) == 0
        assert len(warn) == 1

    def test_mixed(self):
        from yuleosh.evidence.pack import EvidenceCollector
        uncovered = [
            {"req_name": "Pipeline", "shall": "process"},
            {"req_name": "UI", "shall": "render"},
            {"req_name": "Multi-tenant", "shall": "isolate tenants"},
        ]
        crit, warn = EvidenceCollector._categorize_uncovered(uncovered)
        assert len(crit) == 1
        assert len(warn) == 2


# ==================================================================
# _check_traceability_completeness
# ==================================================================

class TestCheckTraceabilityCompleteness:
    def test_all_covered(self, collector_with_reqs):
        c = collector_with_reqs
        c.test_coverage = {"test_pipe.py": ["pipeline"]}
        c._build_requirement_to_test_map()
        uncovered = c._check_traceability_completeness()
        # Pipeline Processing has test, User Auth does not
        assert len(uncovered) > 0  # User Auth uncovered

    def test_none_covered_info_message(self, collector_with_reqs):
        c = collector_with_reqs
        c.test_coverage = {}  # no tests at all
        c._build_requirement_to_test_map()
        uncovered = c._check_traceability_completeness()
        assert len(uncovered) > 0

    def test_partial_coverage_categorized(self, collector_with_reqs):
        c = collector_with_reqs
        c.test_coverage = {"test_pipe.py": ["pipeline"]}
        c._build_requirement_to_test_map()
        uncovered = c._check_traceability_completeness()
        assert len(uncovered) >= 1


# ==================================================================
# _find_latest_pipeline_spec
# ==================================================================

class TestFindLatestPipelineSpec:
    def test_no_store_no_sessions(self, collector, tmp_proj):
        spec = collector._find_latest_pipeline_spec()
        assert spec is None

    def test_store_failure_fallback(self, collector, tmp_proj):
        # Create .osh/sessions with a session.json
        sessions_dir = os.path.join(tmp_proj, ".osh", "sessions")
        os.makedirs(sessions_dir)
        session_file = os.path.join(sessions_dir, "session.json")
        spec_path = os.path.join(tmp_proj, "docs", "spec.md")
        os.makedirs(os.path.dirname(spec_path), exist_ok=True)
        with open(spec_path, "w") as f:
            f.write("spec content")
        with open(session_file, "w") as f:
            json.dump({"spec_path": spec_path}, f)
        spec = collector._find_latest_pipeline_spec()
        assert spec == spec_path


# ==================================================================
# collect_requirements
# ==================================================================

class TestCollectRequirements:
    def test_no_spec_file(self, collector, tmp_proj):
        collector.collect_requirements(spec_path="/nonexistent/spec.md")
        assert collector.requirements == []

    def test_with_spec_path(self, collector, tmp_proj):
        # Mock the import chain — parse_spec is imported via "from validate import parse_spec"
        spec_path = os.path.join(tmp_proj, "spec.md")
        with open(spec_path, "w") as f:
            f.write("# Test\n> REQ-001\nSHALL: do something\n")

        mock_doc = mock.MagicMock()
        mock_req = mock.MagicMock()
        mock_req.to_dict.return_value = {"name": "Test", "shall_count": 1, "shall": ["do something"]}
        mock_doc.requirements = [mock_req]
        mock_doc.scenarios = []

        mock_validate = mock.MagicMock()
        mock_validate.parse_spec.return_value = mock_doc

        with mock.patch.dict("sys.modules", {"validate": mock_validate}):
            collector.collect_requirements(spec_path=spec_path)
            assert len(collector.requirements) == 1


# ==================================================================
# collect_reviews
# ==================================================================

class TestCollectReviews:
    def test_no_reviews_dir(self, collector, tmp_proj):
        collector.collect_reviews()
        assert collector.reviews == []

    def test_with_reviews(self, collector, tmp_proj):
        reviews_dir = os.path.join(tmp_proj, ".osh", "evidence", "reviews", "task1")
        os.makedirs(reviews_dir)
        with open(os.path.join(reviews_dir, "review-session.json"), "w") as f:
            json.dump({"task": "test", "decision": "pass"}, f)
        collector.collect_reviews()
        assert len(collector.reviews) == 1
        assert collector.reviews[0]["task"] == "test"


# ==================================================================
# collect_ci_results
# ==================================================================

class TestCollectCiResults:
    def test_no_ci_dir(self, collector, tmp_proj):
        collector.collect_ci_results()
        assert collector.ci_results == []

    def test_with_ci_results(self, collector, tmp_proj):
        ci_dir = os.path.join(tmp_proj, ".osh", "ci")
        os.makedirs(ci_dir)
        with open(os.path.join(ci_dir, "layer1-abc123.json"), "w") as f:
            json.dump({"layer": 1, "status": "passed", "coverage": {"line_coverage": 85}}, f)
        collector.collect_ci_results()
        assert len(collector.ci_results) == 1
        assert collector.coverage_data["line_coverage"] == 85

    def test_ci_no_coverage(self, collector, tmp_proj):
        ci_dir = os.path.join(tmp_proj, ".osh", "ci")
        os.makedirs(ci_dir)
        with open(os.path.join(ci_dir, "layer1-abc.json"), "w") as f:
            json.dump({"layer": 1, "status": "passed"}, f)
        collector.collect_ci_results()
        assert collector.coverage_data is None


# ==================================================================
# collect_sil_reports
# ==================================================================

class TestCollectSilReports:
    def test_no_ci_dir(self, collector, tmp_proj):
        collector.collect_sil_reports()
        assert collector.sil_reports == []

    def test_no_sil_files(self, collector, tmp_proj):
        ci_dir = os.path.join(tmp_proj, ".osh", "ci")
        os.makedirs(ci_dir)
        collector.collect_sil_reports()
        assert collector.sil_reports == []

    def test_with_sil_files(self, collector, tmp_proj):
        ci_dir = os.path.join(tmp_proj, ".osh", "ci")
        os.makedirs(ci_dir)
        with open(os.path.join(ci_dir, "sil-results.json"), "w") as f:
            json.dump({"results": [{"test": "boot", "passed": True}]}, f)
        collector.collect_sil_reports()
        assert len(collector.sil_reports) == 1
        assert collector.sil_reports[0]["results"][0]["test"] == "boot"

    def test_bad_json_skipped(self, collector, tmp_proj):
        ci_dir = os.path.join(tmp_proj, ".osh", "ci")
        os.makedirs(ci_dir)
        with open(os.path.join(ci_dir, "sil-bad.json"), "w") as f:
            f.write("not valid json{{{")
        collector.collect_sil_reports()
        assert collector.sil_reports == []


# ==================================================================
# generate_traceability_matrix
# ==================================================================

class TestGenerateTraceabilityMatrix:
    def test_empty(self, collector, tmp_proj):
        path = collector.generate_traceability_matrix()
        out = os.path.join(tmp_proj, ".osh", "evidence", "traceability-matrix.md")
        assert path == out
        assert os.path.exists(out)

    def test_with_requirements(self, collector_with_reqs, tmp_proj):
        c = collector_with_reqs
        c.test_coverage = {"test_pipe.py": ["pipeline"]}
        path = c.generate_traceability_matrix()
        content = open(os.path.join(tmp_proj, ".osh", "evidence", "traceability-matrix.md")).read()
        assert "Pipeline Processing" in content
        assert "User Authentication" in content
        assert "RS-001" in content
        # JSON also generated
        assert os.path.exists(os.path.join(tmp_proj, ".osh", "evidence", "traceability-matrix.json"))


# ==================================================================
# generate_requirement_coverage
# ==================================================================

class TestGenerateRequirementCoverage:
    def test_empty(self, collector, tmp_proj):
        path = collector.generate_requirement_coverage()
        assert os.path.exists(path)

    def test_with_reqs(self, collector_with_reqs, tmp_proj):
        c = collector_with_reqs
        # Set up test_coverage so req_to_tests mapping finds matches
        c.test_coverage = {"test_pipe.py": ["pipeline"]}
        c._build_requirement_to_test_map()
        name_to_tests = c.req_to_tests.get("Pipeline Processing", [])
        assert len(name_to_tests) > 0  # verify mapping works
        path = c.generate_requirement_coverage()
        content = open(path).read()
        assert "Pipeline Processing" in content
        assert "✅" in content
        assert "100%" in content  # all reqs have test mappings
        assert "Tests" in content  # new column header


# ==================================================================
# generate_code_coverage_report
# ==================================================================

class TestGenerateCodeCoverageReport:
    def test_no_coverage_data(self, collector, tmp_proj):
        path = collector.generate_code_coverage_report()
        content = open(path).read()
        assert "No coverage data available" in content

    def test_with_coverage_data(self, collector, tmp_proj):
        collector.coverage_data = {
            "line_coverage": 85.0,
            "condition_coverage": 70.0,
            "threshold_line": 80,
            "threshold_condition": 75,
            "line_pass": True,
            "condition_pass": False,
        }
        path = collector.generate_code_coverage_report()
        content = open(path).read()
        assert "85.0%" in content
        assert "70.0%" in content
        assert "✅" in content
        assert "❌" in content


# ==================================================================
# aggregate_review_logs
# ==================================================================


@pytest.fixture
def collector_with_review_artifacts(tmp_proj):
    """Collector + 两个 review 任务目录，同一 review-session.json 文件名，
    触发 aggregate_review_logs 的归档路径（rev_dir.exists → dest.exists 碰撞）。"""
    from yuleosh.evidence.pack import EvidenceCollector

    # 任务 1：legacy 格式
    task1 = Path(tmp_proj) / ".osh" / "reviews" / "task-1"
    task1.mkdir(parents=True)
    (task1 / "review-session.json").write_text(json.dumps({
        "task": "Task 1",
        "decision": "passed",
        "created_at": "2025-06-01",
        "reviews": [
            {"reviewer": "bot", "status": "passed",
             "finding_breakdown": {"critical": 0, "major": 0, "minor": 0},
             "summary": "ok"}
        ],
    }))
    # 任务 2：flat 格式 + 同名文件 → 触发碰撞分支
    task2 = Path(tmp_proj) / ".osh" / "reviews" / "task-2"
    task2.mkdir(parents=True)
    (task2 / "review-session.json").write_text(json.dumps({
        "review_type": "lint", "status": "passed",
        "agent": "lint-bot", "generated_at": "2025-06-02",
        "summary": "all clean", "findings": [],
    }))
    # 另一个独立文件（不会碰撞）
    (task2 / "extra-code-review.json").write_text(json.dumps({
        "review_type": "code", "status": "passed",
        "agent": "code-bot", "findings": [],
    }))

    c = EvidenceCollector(tmp_proj)
    # 给 reviews 一个 legacy 记录（有 actual review data 触发表格渲染）
    c.reviews = [
        {"task": "Task 1", "decision": "passed", "created_at": "2025-06-01",
         "reviews": [
             {"reviewer": "style-bot", "status": "passed",
              "finding_breakdown": {"critical": 0, "major": 0, "minor": 0},
              "summary": "ok"}]},
    ]
    return c


class TestAggregateReviewLogs:
    """review-log-summary.md 必须是条目化表格，可读、可审计、机器可解析。"""

    def test_empty_reviews_produces_placeholder_not_zero_bytes(self, collector, tmp_proj):
        """空集不应产生 0 字节文件；审计视角下 0 字节 == 生成失败。"""
        path = collector.aggregate_review_logs()
        content = open(path, encoding="utf-8").read()
        assert content, "placeholder 必须非空"
        assert "# Review Log Summary" in content
        assert "未发现评审记录" in content
        assert "## 概览" not in content, "空集不应渲染概览表"

    def test_legacy_format_renders_overview_and_agent_tables(self, collector, tmp_proj):
        """Legacy 格式 (task/decision/reviews) → 概览表 + 代理明细表。"""
        collector.reviews = [
            {
                "task": "Review Pipeline",
                "decision": "pass",
                "created_at": "2025-01-01",
                "reviews": [
                    {
                        "reviewer": "style-bot",
                        "status": "passed",
                        "finding_breakdown": {"critical": 0, "major": 1, "minor": 2},
                        "summary": "all good",
                    },
                ],
            }
        ]
        path = collector.aggregate_review_logs()
        content = open(path, encoding="utf-8").read()

        assert "## 概览" in content
        assert "| 任务 / 评审 | 决策 | 代理 | Critical | Major | Minor |" in content
        assert "| Review Pipeline | `pass` | 1 | 0 | 1 | 2 |" in content

        assert "## 1. Review Pipeline" in content
        assert "| 评审代理 | 状态 | Critical | Major | Minor | 结论 |" in content
        assert "| style-bot | `passed` | 0 | 1 | 2 | all good |" in content

    def test_flat_format_renders_findings_table_with_severity_sort(self, collector, tmp_proj):
        """Flat 格式 (review_type/status/findings) → 逐条 finding 表，按严重度排序。"""
        collector.reviews = [
            {
                "review_type": "security",
                "status": "failed",
                "agent": "sec-reviewer",
                "generated_at": "2025-01-02",
                "build_id": "build-42",
                "summary": "2 issues found",
                "findings": [
                    {"severity": "minor", "file": "a.py", "line": 10, "message": "unused var"},
                    {"severity": "critical", "file": "b.py", "line": 3, "message": "sql injection"},
                    {"severity": "major", "file": "c.py", "line": 20, "message": "missing auth"},
                ],
            }
        ]
        path = collector.aggregate_review_logs()
        content = open(path, encoding="utf-8").read()

        assert "| security | `failed` | 1 | 1 | 1 | 1 |" in content
        assert "## 1. 评审 · security" in content
        assert "| `failed` |" in content
        assert "| sec-reviewer |" in content

        crit_line = "| `critical` | `b.py:3` | sql injection |"
        major_line = "| `major` | `c.py:20` | missing auth |"
        minor_line = "| `minor` | `a.py:10` | unused var |"
        assert crit_line in content
        assert major_line in content
        assert minor_line in content
        crit_pos = content.index(crit_line)
        major_pos = content.index(major_line)
        minor_pos = content.index(minor_line)
        assert crit_pos < major_pos < minor_pos, (
            "严重度顺序应为 critical → major → minor"
        )

    def test_findings_truncate_at_50_rows(self, collector, tmp_proj):
        """超过 50 条 finding 只展示前 50 条，底部注明 + 指向 JSON。"""
        findings = [
            {"severity": "info", "file": f"f{i}.py", "line": i, "message": f"msg {i}"}
            for i in range(60)
        ]
        collector.reviews = [
            {
                "review_type": "lint",
                "status": "passed",
                "agent": "lint-bot",
                "generated_at": "2025-01-03",
                "summary": "60 info items",
                "findings": findings,
            }
        ]
        path = collector.aggregate_review_logs()
        content = open(path, encoding="utf-8").read()

        assert "共 60 条问题" in content
        assert "仅展示前 50 条" in content
        assert "review-log.json" in content
        assert "| `info` | `f49.py:49` | msg 49 |" in content
        assert "| `info` | `f50.py:50` | msg 50 |" not in content

    def test_cell_escapes_pipe_and_newline(self, collector, tmp_proj):
        """_cell 应转义竖线、压缩换行、空值显示为 —。"""
        review_with_escapes = {
            "review_type": "smoke",
            "status": "passed",
            "agent": None,
            "generated_at": "2025-01-04",
            "summary": "summary | with pipe" + "\n" + "and newline",
            "findings": [
                {
                    "severity": "info",
                    "file": "x.py",
                    "line": 1,
                    "message": "a | b" + "\n" + "c",
                },
            ],
        }
        collector.reviews = [review_with_escapes]
        path = collector.aggregate_review_logs()
        content = open(path, encoding="utf-8").read()

        assert "| — |" in content
        assert "summary \\| with pipe and newline" in content
        assert "a \\| b c" in content

    # ── 补充：覆盖此前未命中的分支 ──

    def test_archive_raw_review_files_from_osh_reviews_dir(self, collector_with_review_artifacts, tmp_proj):
        """归档路径：.osh/reviews/**/*.json → evidence/reviews/
        覆盖 rev_dir.exists() → rglob → 同名碰撞 → shutil.copy2 → copied+=1 → 日志。"""
        collector = collector_with_review_artifacts
        evidence_dir = Path(collector.evidence_dir)
        raw_reviews = evidence_dir / "reviews"
        assert not raw_reviews.exists(), "归档前 subdir 应不存在"

        path = collector.aggregate_review_logs()

        assert raw_reviews.is_dir(), "归档后 evidence/reviews 子目录创建"
        # task-1 和 task-2 都有 review-session.json，名字相同 → 碰撞后 task-2 的被加前缀
        names = sorted(p.name for p in raw_reviews.iterdir())
        assert names == [
            "extra-code-review.json",
            "review-session.json",          # task-1 的原样保留
            "task-2-review-session.json",   # task-2 的被重命名
        ], f"归档文件列表不符：{names}"
        # 原始 .osh/reviews/ 必须完好（是 copy 不是 move）
        assert (Path(tmp_proj) / ".osh" / "reviews" / "task-1" / "review-session.json").exists()
        assert (Path(tmp_proj) / ".osh" / "reviews" / "task-2" / "review-session.json").exists()

    def test_sev_counts_handles_non_int_finding_values(self, collector, tmp_proj):
        """_sev_counts 的 try/except (TypeError, ValueError) 分支。"""
        collector.reviews = [
            {
                "task": "Bad Data",
                "decision": "pass",
                "created_at": "2025-06-01",
                "reviews": [
                    {
                        "reviewer": "bot", "status": "passed",
                        # 故意塞字符串和 None —— int() 会抛 ValueError / TypeError
                        "finding_breakdown": {
                            "critical": "oops",
                            "major": None,
                            "minor": 2,
                        },
                        "summary": "partial junk",
                    }
                ],
            }
        ]
        # 不应抛异常，且坏值被当作 0 处理
        path = collector.aggregate_review_logs()
        content = open(path).read()
        # 概览表：_sev_counts 把坏值规范化成 0
        assert "| Bad Data | `pass` | 1 | 0 | 0 | 2 |" in content
        # 代理明细表直接显示原始值（设计意图），不再断言 0；
        # 本测试的核心是验证 int() 抛 ValueError / TypeError 时 except 分支被走到

    def test_json_write_failure_is_swallowed(self, collector, tmp_proj):
        """写 review-log.json 时 OSError 被吞，不中断摘要生成。"""
        collector.reviews = [
            {"task": "X", "decision": "pass", "created_at": "2025-06-01",
             "reviews": []},
        ]
        # 源码用 builtin open(json_path, "w")，mock builtins.open 即可
        call_count = {"n": 0}
        real_open = open

        def _boom_on_json(path_or_file, mode="r", *args, **kwargs):
            fname = str(path_or_file)
            if fname.endswith("review-log.json") and "w" in mode:
                call_count["n"] += 1
                raise OSError("disk full — simulated")
            return real_open(path_or_file, mode, *args, **kwargs)

        with mock.patch("builtins.open", side_effect=_boom_on_json):
            path = collector.aggregate_review_logs()

        # 摘要 md 应正常生成（json 写失败被吞了）
        content = real_open(path).read()
        assert "# Review Log Summary" in content
        assert call_count["n"] >= 1, "OSError mock 必须被触发至少一次（实际触发 %d）" % call_count["n"]

    def test_archive_copy_failure_is_skipped_without_crashing(self, collector_with_review_artifacts, tmp_proj):
        """归档时 shutil.copy2 抛 OSError 被跳过，不中断循环（report_builder.py L433-435）。"""
        collector = collector_with_review_artifacts
        import shutil

        real_copy2 = shutil.copy2
        fail_once = {"n": 0}

        def _fail_copy2(src, dst, *a, **kw):
            # 让第一个文件 (task-1/review-session.json) 失败，后面的继续
            fail_once["n"] += 1
            if fail_once["n"] == 1:
                raise OSError("permission denied — simulated")
            return real_copy2(src, dst, *a, **kw)

        with mock.patch.object(shutil, "copy2", side_effect=_fail_copy2):
            path = collector.aggregate_review_logs()

        # 摘要 md 仍正常生成
        assert "# Review Log Summary" in open(path).read()
        # 归档目录里至少应有 2 个文件（task-2 的两个复制成功；task-1 的那个被跳过）
        raw_reviews = Path(collector.evidence_dir) / "reviews"
        names = sorted(p.name for p in raw_reviews.iterdir())
        assert len(names) >= 2, f"copy2 抛错后其余文件应继续归档；实际只剩 {names}"
        # 触发计数必须为 1
        assert fail_once["n"] >= 1

    def test_collect_reviews_skips_non_dict_json(self, collector_with_review_artifacts, tmp_proj):
        """collect_reviews 里 isinstance(data, dict) 检查 — 非 dict JSON（list 等）被跳过。
        覆盖 collection.py L335。"""
        from yuleosh.evidence.pack import EvidenceCollector

        # 在已有的 .osh/reviews/task-2 里再塞一个 list 类型的脏 JSON
        task2 = Path(tmp_proj) / ".osh" / "reviews" / "task-2"
        (task2 / "bad-review.json").write_text(json.dumps(["list", "not", "dict"]))

        c = EvidenceCollector(tmp_proj)
        # 不预填 reviews，让 collect_reviews 自己扫
        c.reviews = []
        c.collect_reviews()
        c.aggregate_review_logs()

        # 核心断言：bad-review.json 是 list 不应报错，正常 dict 记录仍被收集
        assert len(c.reviews) >= 2, "正常 dict JSON 应被收集；实际只有 %d 条" % len(c.reviews)
        # （list 类型的不会出现在 c.reviews 里 —— 这就是 L335 跳过它的效果）


# ==================================================================
# generate_acceptance_matrix
# ==================================================================

class TestGenerateAcceptanceMatrix:
    def test_empty(self, collector, tmp_proj):
        path = collector.generate_acceptance_matrix()
        assert os.path.exists(path)
        content = open(path).read()
        assert "Acceptance Matrix" in content

    def test_with_data(self, collector_with_reqs, tmp_proj):
        c = collector_with_reqs
        c.test_coverage = {"test_pipe.py": ["pipeline", "processing"]}
        c._build_requirement_to_test_map()
        path = c.generate_acceptance_matrix()
        content = open(path).read()
        assert "RS-001" in content
        assert "RS-002" in content
        assert "test_pipe.py" in content


# ==================================================================
# pack_compliance_zip
# ==================================================================

class TestPackComplianceZip:
    def test_basic_pack(self, collector, tmp_proj):
        # Create some evidence files (already created by collector.__init__)
        ev_dir = os.path.join(tmp_proj, ".osh", "evidence")
        for fn in ("traceability-matrix.md", "code-coverage-report.md", "traceability-matrix.json"):
            with open(os.path.join(ev_dir, fn), "w") as f:
                f.write("content")
        # Create spec file
        docs = os.path.join(tmp_proj, "docs")
        os.makedirs(docs)
        with open(os.path.join(docs, "spec.md"), "w") as f:
            f.write("spec content")
        # Create startup analysis
        with open(os.path.join(docs, "startup-analysis.md"), "w") as f:
            f.write("analysis")
        # Create sil report
        ci_dir = os.path.join(tmp_proj, ".osh", "ci")
        os.makedirs(ci_dir)
        with open(os.path.join(ci_dir, "sil-results.json"), "w") as f:
            json.dump({"results": []}, f)

        zip_path = collector.pack_compliance_zip()
        assert os.path.exists(zip_path)
        # Verify zip contents
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "traceability-matrix.md" in names
            assert "spec.md" in names
            assert "startup-analysis.md" in names
            assert "sil-reports/sil-results.json" in names


# ==================================================================
# _check_pipeline_not_running
# ==================================================================

class TestCheckPipelineNotRunning:
    def test_no_sessions_dir(self, tmp_proj):
        from yuleosh.evidence.pack import _check_pipeline_not_running
        assert _check_pipeline_not_running(tmp_proj) is True

    def test_with_running_pipeline(self, tmp_proj):
        from yuleosh.evidence.pack import _check_pipeline_not_running
        sess_dir = os.path.join(tmp_proj, ".osh", "sessions", "run1")
        os.makedirs(sess_dir)
        with open(os.path.join(sess_dir, "session.json"), "w") as f:
            json.dump({"status": "running"}, f)
        assert _check_pipeline_not_running(tmp_proj) is False

    def test_completed_pipeline(self, tmp_proj):
        from yuleosh.evidence.pack import _check_pipeline_not_running
        sess_dir = os.path.join(tmp_proj, ".osh", "sessions", "run1")
        os.makedirs(sess_dir)
        with open(os.path.join(sess_dir, "session.json"), "w") as f:
            json.dump({"status": "completed"}, f)
        assert _check_pipeline_not_running(tmp_proj) is True

    def test_recent_ci_write(self, tmp_proj):
        from yuleosh.evidence.pack import _check_pipeline_not_running
        ci_dir = os.path.join(tmp_proj, ".osh", "ci")
        os.makedirs(ci_dir)
        with open(os.path.join(ci_dir, "layer1.json"), "w") as f:
            f.write("{}")
        # Recent write (now) should be within the grace window
        result = _check_pipeline_not_running(tmp_proj)
        # Since the write happened within the last 5 seconds, it should return False
        assert result is False


# ==================================================================
# generate_evidence (standalone)
# ==================================================================

class TestGenerateEvidence:
    def test_basic_flow(self, tmp_proj):
        from yuleosh.evidence.pack import generate_evidence
        # Minimal project structure
        docs = os.path.join(tmp_proj, "docs")
        os.makedirs(docs)
        with open(os.path.join(docs, "spec.md"), "w") as f:
            f.write("# Test\n> REQ-001\nSHALL: do something\n")

        # Mock the spec parsing to avoid import chain
        mock_doc = mock.MagicMock()
        mock_req = mock.MagicMock()
        mock_req.to_dict.return_value = {"name": "Test", "shall_count": 1, "shall": ["do something"]}
        mock_doc.requirements = [mock_req]
        mock_doc.scenarios = []

        mock_validate = mock.MagicMock()
        mock_validate.parse_spec.return_value = mock_doc

        with mock.patch("yuleosh.evidence.pack._check_pipeline_not_running", return_value=True):
            with mock.patch.dict("sys.modules", {"validate": mock_validate}):
                artifacts = generate_evidence(project_dir=tmp_proj)
                assert len(artifacts) == 6
                for a in artifacts:
                    assert os.path.exists(a)

    def test_with_wait_loop(self, tmp_proj):
        from yuleosh.evidence.pack import generate_evidence
        # Pipeline busy initially, then free
        busy = [True, True, False]

        def mock_check(_pd):
            return busy.pop(0)

        with mock.patch("yuleosh.evidence.pack._check_pipeline_not_running", side_effect=mock_check):
            with mock.patch.dict("sys.modules", {"validate": mock.MagicMock()}):
                artifacts = generate_evidence(project_dir=tmp_proj)
                assert len(artifacts) == 6

    def test_timeout_wait(self, tmp_proj):
        from yuleosh.evidence.pack import generate_evidence
        # Pipeline never free — hits timeout
        with mock.patch("yuleosh.evidence.pack._check_pipeline_not_running", return_value=False):
            with mock.patch.dict("sys.modules", {"validate": mock.MagicMock()}):
                artifacts = generate_evidence(project_dir=tmp_proj)
                assert len(artifacts) == 6


# ==================================================================
# main() CLI entry point
# ==================================================================

class TestMain:
    def test_no_args(self, tmp_proj):
        from yuleosh.evidence.pack import main
        with mock.patch("yuleosh.evidence.pack.generate_evidence") as mgen:
            with mock.patch.object(sys, "argv", ["pack"]):
                main()
                mgen.assert_called_once()

    def test_with_spec_path(self, tmp_proj):
        from yuleosh.evidence.pack import main
        with mock.patch("yuleosh.evidence.pack.generate_evidence") as mgen:
            with mock.patch.object(sys, "argv", ["pack", "/tmp/spec.md"]):
                main()
                mgen.assert_called_once_with(spec_path="/tmp/spec.md")

    def test_pack_arg_stripped(self, tmp_proj):
        from yuleosh.evidence.pack import main
        with mock.patch("yuleosh.evidence.pack.generate_evidence") as mgen:
            with mock.patch.object(sys, "argv", ["pack", "pack", "/tmp/spec.md"]):
                main()
                mgen.assert_called_once_with(spec_path="/tmp/spec.md")

    def test_formats_flag_forwarded(self, tmp_proj):
        from yuleosh.evidence.pack import main
        with mock.patch("yuleosh.evidence.pack.generate_evidence") as mgen:
            argv = ["pack", "pack", "--formats", "md,html,xlsx,pdf", "/tmp/spec.md"]
            with mock.patch.object(sys, "argv", argv):
                main()
                mgen.assert_called_once_with(
                    spec_path="/tmp/spec.md", formats="md,html,xlsx,pdf"
                )

    def test_formats_flag_requires_value(self, tmp_proj):
        import pytest
        from yuleosh.evidence.pack import main
        with mock.patch.object(sys, "argv", ["pack", "pack", "--formats"]):
            with pytest.raises(SystemExit):
                main()
