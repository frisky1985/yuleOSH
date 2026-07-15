"""Extended tests for evidence.generator — covering uncovered paths."""

import sys
import os
import json
import tempfile
import ast

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.evidence.generator import EvidenceCollector


class TestEvidenceCollector:
    """Cover EvidenceCollector uncovered paths."""

    def test_init_creates_evidence_dir(self):
        """__init__: creates evidence directory."""
        with tempfile.TemporaryDirectory() as tmp:
            c = EvidenceCollector(tmp, "1.0.0")
            expected_dir = os.path.join(tmp, ".osh", "evidence")
            assert os.path.exists(expected_dir)

    def test_init_sets_defaults(self):
        """__init__: sets default values correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            c = EvidenceCollector(tmp, "1.0.0")
            assert c.version == "1.0.0"
            assert c.project_dir == tmp
            assert c.requirements == []
            assert c.scenarios == []
            assert c.reviews == []
            assert c.ci_results == []
            assert c.coverage_data is None
            assert c.sil_reports == []
            assert c.test_coverage == {}
            assert c.req_to_tests == {}
            assert c.test_to_reqs == {}
            assert c.scenario_refs == {}
            assert c.match_modes == {}
            assert c.match_confidences == {}

    def test_static_parse_scenario_refs(self):
        """_parse_scenario_refs static method."""
        text = "Scenario-Ref: REF-001"
        result = EvidenceCollector._parse_scenario_refs(text)
        assert "REF-001" in result

    def test_static_parse_module_covers(self):
        """_parse_module_covers static method."""
        tree = ast.parse('"""Covers: feature-x"""')
        result = EvidenceCollector._parse_module_covers(tree)
        assert "feature-x" in result

    def test_static_parse_comment_covers(self):
        """_parse_comment_covers static method."""
        result = EvidenceCollector._parse_comment_covers("# Covers: feature-y")
        assert "feature-y" in result

    def test_parse_function_covers(self):
        """_parse_function_covers instance method."""
        source = 'def test_feature():\n    """Covers: fn-z"""\n    pass\n'
        tree = ast.parse(source)
        c = EvidenceCollector(tempfile.mkdtemp())
        result = c._parse_function_covers(tree)
        assert "fn-z" in result

    def test_static_infer_covers(self):
        """_infer_covers_from_function_names static method."""
        source = 'def test_pipeline():\n    pass\n'
        tree = ast.parse(source)
        result = EvidenceCollector._infer_covers_from_function_names(tree)
        assert "pipeline" in result

    def test_static_categorize_uncovered(self):
        """_categorize_uncovered static method."""
        uncovered = [{"shall": "SHALL process", "req_name": "REQ-001"}]
        critical, warn = EvidenceCollector._categorize_uncovered(uncovered)
        assert len(critical) == 1
        assert len(warn) == 0

    def test_collect_scenario_refs_from_file(self):
        """_collect_scenario_refs_from_file: reads Scenario-Ref from file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Scenario-Ref: REF-TEST"""\ndef test_x(): pass\n')
            f.flush()
            c = EvidenceCollector(tempfile.mkdtemp())
            result = c._collect_scenario_refs_from_file(f.name)
            assert "REF-TEST" in result or len(result) > 0
            os.unlink(f.name)

    def test_collect_scenario_refs_not_found(self):
        """_collect_scenario_refs_from_file: file not found."""
        c = EvidenceCollector(tempfile.mkdtemp())
        result = c._collect_scenario_refs_from_file("/nonexistent/test.py")
        assert result == []

    def test_collect_test_coverage_no_tests_dir(self):
        """_collect_test_coverage: no tests/ directory."""
        with tempfile.TemporaryDirectory() as tmp:
            c = EvidenceCollector(tmp)
            result = c._collect_test_coverage()
            assert result == {}

    def test_collect_test_coverage_empty_tests_dir(self):
        """_collect_test_coverage: tests/ dir exists but no test_*.py files."""
        with tempfile.TemporaryDirectory() as tmp:
            tests_dir = os.path.join(tmp, "tests")
            os.makedirs(tests_dir)
            c = EvidenceCollector(tmp)
            result = c._collect_test_coverage()
            assert result == {}

    def test_collect_test_coverage_with_files(self):
        """_collect_test_coverage: covers files with markers."""
        with tempfile.TemporaryDirectory() as tmp:
            tests_dir = os.path.join(tmp, "tests")
            os.makedirs(tests_dir)
            with open(os.path.join(tests_dir, "test_feature.py"), "w") as f:
                f.write('"""Covers: feature-x, feature-y"""\ndef test_x(): pass\n')
            c = EvidenceCollector(tmp)
            result = c._collect_test_coverage()
            assert "test_feature.py" in result

    def test_find_latest_pipeline_spec_no_store(self):
        """_find_latest_pipeline_spec: no store available."""
        with tempfile.TemporaryDirectory() as tmp:
            c = EvidenceCollector(tmp)
            # No store.db, no sessions → should return None
            result = c._find_latest_pipeline_spec()
            assert result is None

    def test_find_latest_pipeline_spec_with_sessions(self):
        """_find_latest_pipeline_spec: finds spec from session files."""
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = os.path.join(tmp, ".osh", "sessions")
            os.makedirs(sessions_dir)

            spec_path = os.path.join(tmp, "spec.md")
            with open(spec_path, "w") as f:
                f.write("# Test\n")

            session_file = os.path.join(sessions_dir, "session.json")
            with open(session_file, "w") as f:
                json.dump({"spec_path": spec_path}, f)

            c = EvidenceCollector(tmp)
            result = c._find_latest_pipeline_spec()
            assert result == spec_path

    def test_find_latest_pipeline_spec_session_no_spec(self):
        """_find_latest_pipeline_spec: session file has no spec_path."""
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = os.path.join(tmp, ".osh", "sessions")
            os.makedirs(sessions_dir)

            # Session file without spec_path
            session_file = os.path.join(sessions_dir, "session.json")
            with open(session_file, "w") as f:
                json.dump({}, f)

            c = EvidenceCollector(tmp)
            result = c._find_latest_pipeline_spec()
            assert result is None
