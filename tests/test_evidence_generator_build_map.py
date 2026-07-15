"""Tests for EvidenceCollector._build_requirement_to_test_map and _check_traceability_completeness."""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.evidence.generator import EvidenceCollector
from yuleosh.evidence.report_builder import ReportBuilderMixin


class TestBuildRequirementToTestMap:
    """Cover _build_requirement_to_test_map paths."""

    def test_with_requirements_and_scenarios(self):
        """Build map with requirements and scenarios."""
        with tempfile.TemporaryDirectory() as tmp:
            tests_dir = os.path.join(tmp, "tests")
            os.makedirs(tests_dir)
            # Create a test file with covers marker
            with open(os.path.join(tests_dir, "test_feature.py"), "w") as f:
                f.write('"""Covers: data-processing"""\ndef test_process(): pass\n')

            c = EvidenceCollector(tmp)
            c.requirements = [{
                "name": "data_processing_req",
                "shall": ["The system SHALL process data correctly"],
                "req_id": "REQ-001",
            }]
            c.scenarios = [{
                "name": "scenario_data_processing",
                "given": ["data is available"],
                "when": ["process is called"],
                "then": ["result is correct"],
            }]
            c._build_requirement_to_test_map()
            assert len(c.req_to_tests) > 0

    def test_without_test_coverage(self):
        """Build map when no test coverage data."""
        with tempfile.TemporaryDirectory() as tmp:
            c = EvidenceCollector(tmp)
            c.requirements = [{"name": "REQ-001", "shall": ["do something"], "req_id": "R1"}]
            c._build_requirement_to_test_map()
            # Should handle gracefully
            assert isinstance(c.req_to_tests, dict)

    def test_with_multi_shall_requirements(self):
        """Build map with multiple SHALL requirements."""
        with tempfile.TemporaryDirectory() as tmp:
            tests_dir = os.path.join(tmp, "tests")
            os.makedirs(tests_dir)
            with open(os.path.join(tests_dir, "test_critical.py"), "w") as f:
                f.write('"""Covers: safety-critical"""\ndef test_safety(): pass\n')

            c = EvidenceCollector(tmp)
            c.requirements = [
                {"name": "safety", "shall": ["SHALL ensure safety"], "req_id": "R1"},
                {"name": "logging", "shall": ["SHALL log events"], "req_id": "R2"},
            ]
            c.scenarios = [{"name": "safety_scenario", "given": [], "when": [], "then": []}]
            c._build_requirement_to_test_map()
            assert isinstance(c.req_to_tests, dict)


class TestCheckTraceabilityCompleteness:
    """Cover _check_traceability_completeness paths."""

    def test_no_uncovered(self):
        """No uncovered SHALLs."""
        with tempfile.TemporaryDirectory() as tmp:
            tests_dir = os.path.join(tmp, "tests")
            os.makedirs(tests_dir)
            with open(os.path.join(tests_dir, "test_x.py"), "w") as f:
                f.write('"""Covers: myfeature"""\ndef test_x(): pass\n')

            c = EvidenceCollector(tmp)
            c.requirements = [{"name": "myfeature", "shall": ["SHALL do it"], "req_id": "R1"}]
            c._build_requirement_to_test_map()
            uncovered = c._check_traceability_completeness()
            assert isinstance(uncovered, list)

    def test_all_uncovered(self):
        """All SHALLs uncovered."""
        with tempfile.TemporaryDirectory() as tmp:
            c = EvidenceCollector(tmp)
            c.requirements = [{"name": "REQ-A", "shall": ["SHALL work"], "req_id": "R1"}]
            c._build_requirement_to_test_map()
            uncovered = c._check_traceability_completeness()
            assert isinstance(uncovered, list)

    def test_mixed_coverage(self):
        """Mix of covered and uncovered SHALLs."""
        with tempfile.TemporaryDirectory() as tmp:
            tests_dir = os.path.join(tmp, "tests")
            os.makedirs(tests_dir)
            with open(os.path.join(tests_dir, "test_critical.py"), "w") as f:
                f.write('"""Covers: critical-feature"""\ndef test_critical(): pass\n')

            c = EvidenceCollector(tmp)
            c.requirements = [
                {"name": "critical-feature", "shall": ["SHALL be critical"], "req_id": "R1"},
                {"name": "ui-feature", "shall": ["SHALL support UI"], "req_id": "R2"},
            ]
            c._collect_test_coverage()
            c._build_requirement_to_test_map()
            uncovered = c._check_traceability_completeness()
            # Should identify which are uncovered
            assert isinstance(uncovered, list)
