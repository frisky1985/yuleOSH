"""
Targeted coverage tests for evidence modules — covers remaining branches
in compliance.py (generate_evidence), report.py (template utilities),
and uncovered paths in generator.py (pipeline waiting, error paths).
"""

import json
import os
import sys
import time
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ==================================================================
# compliance.py — generate_evidence, pack_compliance_zip, _check_pipeline_not_running
# ==================================================================


class TestComplianceGenerateEvidence:
    """Covers compliance.generate_edge cases in compliance module."""

    def test_check_pipeline_pending_after_max_wait(self, tmp_path):
        """GIVEN pipeline stays running more than max_wait WHEN generate_evidence THEN collect anyway."""
        from yuleosh.evidence.compliance import generate_evidence

        session_dir = tmp_path / ".osh" / "sessions" / "pipe1"
        session_dir.mkdir(parents=True)
        sess_file = session_dir / "session.json"
        sess_file.write_text(json.dumps({
            "status": "running",
            "spec_path": str(tmp_path / "docs" / "spec.md"),
        }))

        docs = tmp_path / "docs"
        docs.mkdir()
        spec_file = docs / "spec.md"
        spec_file.write_text("")

        with mock.patch("yuleosh.evidence.compliance._time.sleep"):
            with mock.patch("yuleosh.evidence.generator.EvidenceCollector.collect_requirements"):
                result = generate_evidence(str(tmp_path))
        assert result is not None

    def test_generate_evidence_with_spec_path(self, tmp_path):
        """GIVEN explicit spec_path WHEN generate_evidence THEN uses it."""
        from yuleosh.evidence.compliance import generate_evidence

        docs = tmp_path / "docs"
        docs.mkdir()
        spec_file = docs / "spec.md"
        spec_file.write_text("")

        with mock.patch("yuleosh.evidence.generator.EvidenceCollector.collect_requirements"):
            result = generate_evidence(str(tmp_path), spec_path=str(spec_file))
        assert result is not None

    def test_generate_evidence_env_osh_home(self, tmp_path, monkeypatch):
        """GIVEN OSH_HOME env var WHEN generate_evidence THEN uses it."""
        from yuleosh.evidence.compliance import generate_evidence

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        with mock.patch("yuleosh.evidence.generator.EvidenceCollector.collect_requirements"):
            result = generate_evidence()
        assert result is not None

    def test_pack_compliance_zip_with_sil_reports(self, tmp_path):
        """GIVEN SIL reports exist WHEN pack_compliance_zip THEN includes them."""
        from yuleosh.evidence.compliance import pack_compliance_zip
        from yuleosh.evidence.generator import EvidenceCollector

        # Create SIL report
        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True)
        sil_report = ci_dir / "test_sil_report.json"
        sil_report.write_text(json.dumps({"results": [{"name": "test1", "passed": True}]}))

        collector = EvidenceCollector(str(tmp_path))
        result = pack_compliance_zip(collector)
        assert result is not None
        assert Path(result).exists()

    def test_check_pipeline_not_running_no_dirs(self, tmp_path):
        """GIVEN no .osh dirs WHEN check_pipeline_not_running THEN returns True."""
        from yuleosh.evidence.compliance import _check_pipeline_not_running
        assert _check_pipeline_not_running(str(tmp_path)) is True


class TestComplianceMain:
    """Covers the main() CLI entry and pack_compliance_zip."""

    def test_main_with_pack_arg(self):
        """GIVEN argv contains 'pack' WHEN main() called THEN arg stripped."""
        from yuleosh.evidence.compliance import main
        with mock.patch("yuleosh.evidence.compliance.generate_evidence") as mgen:
            with mock.patch.object(sys, "argv", ["pack", "pack", "/some/path"]):
                main()
                mgen.assert_called_once_with(spec_path="/some/path")

    def test_main_no_args(self):
        """GIVEN no extra args WHEN main() THEN calls generate_evidence with no spec."""
        from yuleosh.evidence.compliance import main
        with mock.patch("yuleosh.evidence.compliance.generate_evidence") as mgen:
            with mock.patch.object(sys, "argv", ["pack"]):
                main()
                mgen.assert_called_once_with(spec_path=None)


# ==================================================================
# report.py — template utilities
# ==================================================================


class TestReportHelpers:
    """Covers every function in report.py."""

    def test_format_maturity_label(self):
        from yuleosh.evidence.report import format_maturity_label
        assert format_maturity_label(90) == "excellent"
        assert format_maturity_label(70) == "good"
        assert format_maturity_label(50) == "fair"
        assert format_maturity_label(30) == "developing"
        assert format_maturity_label(10) == "initial"

    def test_format_status_icon(self):
        from yuleosh.evidence.report import format_status_icon
        assert format_status_icon("passed") == "✅"
        assert format_status_icon("failed") == "❌"
        assert format_status_icon("unknown") == "❓"

    def test_format_coverage_summary(self):
        from yuleosh.evidence.report import format_coverage_summary
        result = format_coverage_summary(10, 5)
        assert "50%" in result
        assert "5/10" in result

    def test_make_table_row(self):
        from yuleosh.evidence.report import make_table_row
        row = make_table_row("a", "b", "c")
        assert "a | b | c" in row

    def test_make_header_row(self):
        from yuleosh.evidence.report import make_header_row
        result = make_header_row("Req", "Status")
        assert "Req" in result

    def test_make_acceptance_row(self):
        from yuleosh.evidence.report import make_acceptance_row
        row = make_acceptance_row("R1", "name", "shall", "UT", "test.py", "exact", "1.0", "✅")
        assert "R1" in row and "test.py" in row

    def test_make_coverage_table_row(self):
        from yuleosh.evidence.report import make_coverage_table_row
        row = make_coverage_table_row("Line", "90%", "80%", "✅")
        assert "Line" in row

    def test_dedent(self):
        from yuleosh.evidence.report import dedent
        text = "  hello\n  world"
        result = dedent(text)
        assert result == "hello\nworld"

    def test_generate_timestamp(self):
        from yuleosh.evidence.report import generate_timestamp
        ts = generate_timestamp()
        assert "T" in ts  # ISO format contains T


# ==================================================================
# generator.py — remaining uncovered branches
# ==================================================================


class TestGeneratorBranches:
    """Covers remaining branch paths in EvidenceCollector."""

    def test_collect_requirements_spec_not_found(self, tmp_path):
        """GIVEN no spec file WHEN collect_requirements THEN prints skip."""
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        collector.collect_requirements(spec_path="/nonexistent/spec.md")
        assert len(collector.requirements) == 0

    def test_collect_reviews_no_dir(self, tmp_path):
        """GIVEN no reviews dir WHEN collect_reviews THEN prints skip."""
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        collector.collect_reviews()
        assert len(collector.reviews) == 0

    def test_collect_ci_no_results(self, tmp_path):
        """GIVEN no ci dir WHEN collect_ci_results THEN prints skip."""
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        collector.collect_ci_results()
        assert len(collector.ci_results) == 0

    def test_collect_sil_no_ci_dir(self, tmp_path):
        """GIVEN no ci dir WHEN collect_sil_reports THEN prints skip."""
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        collector.collect_sil_reports()
        assert len(collector.sil_reports) == 0

    def test_collect_test_coverage_no_tests_dir(self, tmp_path):
        """GIVEN no tests/ dir WHEN _collect_test_coverage THEN returns empty."""
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        result = collector._collect_test_coverage()
        assert result == {}

    def test_generate_code_coverage_no_data(self, tmp_path):
        """GIVEN no coverage_data WHEN generate_code_coverage_report THEN shows N/A."""
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        result = collector.generate_code_coverage_report()
        content = Path(result).read_text()
        assert "No coverage data available" in content

    @mock.patch("yuleosh.evidence.generator.log")
    def test_find_latest_pipeline_spec_no_sessions(self, mock_log, tmp_path):
        """GIVEN no pipeline sessions WHEN _find_latest_pipeline_spec THEN returns None."""
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        result = collector._find_latest_pipeline_spec()
        assert result is None

    def test_parse_scenario_refs_strips_triple_quotes(self):
        """GIVEN text with trailing triple quotes WHEN parse THEN strips them."""
        from yuleosh.evidence.generator import EvidenceCollector
        text = 'Scenario-Ref: SDD basic"""'
        result = EvidenceCollector._parse_scenario_refs(text)
        assert result == ["SDD basic"]

    def test_parse_scenario_refs_handles_multiple(self):
        """GIVEN multiple Scenario-Ref lines WHEN parse THEN returns all."""
        from yuleosh.evidence.generator import EvidenceCollector
        text = """Scenario-Ref: SDD basic
Covers: test, Scenario-Ref: DDD advanced
"""
        result = EvidenceCollector._parse_scenario_refs(text)
        assert "SDD basic" in result
        assert "DDD advanced" in result

    def test_infer_covers_from_function_names_with_stop_words(self):
        """GIVEN test function with stop-word names WHEN infer THEN returns empty."""
        from yuleosh.evidence.generator import EvidenceCollector
        import ast
        code = "def test_the_and(): pass"
        tree = ast.parse(code)
        result = EvidenceCollector._infer_covers_from_function_names(tree)
        assert result == []

    def test_collect_scenario_refs_from_file_io_error(self, tmp_path):
        """GIVEN unreadable file WHEN collect_refs THEN returns empty."""
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        result = collector._collect_scenario_refs_from_file("/nonexistent/test.py")
        assert result == []

    def test_generate_code_coverage_with_data(self, tmp_path):
        """GIVEN coverage_data set WHEN generate THEN shows metrics."""
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        collector.coverage_data = {
            "line_coverage": 85,
            "threshold_line": 80,
            "line_pass": True,
            "condition_coverage": 75,
            "threshold_condition": 75,
            "condition_pass": True,
        }
        result = collector.generate_code_coverage_report()
        content = Path(result).read_text()
        assert "85" in content
        assert "75" in content


# ==================================================================
# pack.py — remaining uncovered paths
# ==================================================================


class TestPackReexport:
    """Covers remaining branches in the re-export pack module."""

    def test_main_calls_generate_with_args(self):
        """GIVEN argv with spec path WHEN main THEN delegates correctly."""
        from yuleosh.evidence.pack import main
        with mock.patch("yuleosh.evidence.pack.generate_evidence") as mgen:
            with mock.patch.object(sys, "argv", ["script", "/path/spec.md"]):
                main()
                mgen.assert_called_once_with(spec_path="/path/spec.md")
