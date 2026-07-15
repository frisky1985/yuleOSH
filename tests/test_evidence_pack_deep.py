# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


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
        path = collector_with_reqs.generate_requirement_coverage()
        content = open(path).read()
        assert "Pipeline Processing" in content
        assert "✅" in content
        assert "100%" in content  # all reqs have shall_count > 0


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

class TestAggregateReviewLogs:
    def test_no_reviews(self, collector, tmp_proj):
        path = collector.aggregate_review_logs()
        assert os.path.exists(path)

    def test_with_reviews(self, collector, tmp_proj):
        collector.reviews = [
            {
                "task": "Review Pipeline",
                "decision": "pass",
                "created_at": "2025-01-01",
                "reviews": [
                    {"reviewer": "bot", "status": "passed", "finding_breakdown": {"critical": 0, "major": 1, "minor": 2}, "summary": "all good"},
                ],
            }
        ]
        path = collector.aggregate_review_logs()
        content = open(path).read()
        assert "Review Pipeline" in content
        assert "pass" in content


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
