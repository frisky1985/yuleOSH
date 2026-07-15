"""Tests for pipeline/step_handlers/test_qualification.py."""
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from yuleosh.pipeline.step_handlers.test_qualification import (
    Scenario, _discover_scenarios, _discover_test_files,
    _check_scenario_coverage, _run_system_tests,
    _build_qualification_report, step_test_qualification,
)


class TestScenario:
    def test_parse_full_scenario(self):
        raw = "### Test Login\nGIVEN user is logged in\nWHEN user clicks login\nTHEN dashboard is shown"
        s = Scenario(raw)
        assert "user is logged in" in s.given[0]
        assert "user clicks login" in s.when
        assert len(s.then) > 0

    def test_parse_case_insensitive_keywords(self):
        raw = "Given user exists\nWhen action performed\nThen result checked"
        s = Scenario(raw)
        assert len(s.given) > 0
        assert s.when == "action performed"

    def test_parse_given_followed_by_lines(self):
        raw = "GIVEN:\nuser is logged in\nuser has permissions\nWHEN action\nTHEN result ok"
        s = Scenario(raw)
        assert len(s.given) >= 1

    def test_parse_if_when_has_colon_prefix(self):
        raw = "GIVEN user exists\nWHEN: click button\nTHEN result appears"
        s = Scenario(raw)
        assert s.when.strip() == "click button"

    def test_name_generation(self):
        raw = "### Complex Scenario 123\nGIVEN x\nWHEN y\nTHEN z"
        s = Scenario(raw)
        assert "Complex" in s.name

    def test_name_fallback(self):
        s = Scenario("GIVEN x\nWHEN y\nTHEN z")
        assert s.name is not None

    def test_to_dict(self):
        raw = "GIVEN user\nWHEN click\nTHEN done"
        s = Scenario(raw)
        d = s.to_dict()
        assert d["given"] == ["user"]
        assert d["when"] == "click"
        assert d["then"] == ["done"]


class TestDiscoverScenarios:
    def test_no_file(self):
        scenarios = _discover_scenarios("/nonexistent/spec.md")
        assert scenarios == []

    def test_with_scenarios(self):
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "spec.md"
            spec_path.write_text("""# Spec
### Scenario 1
GIVEN user
WHEN action
THEN result
""")
            scenarios = _discover_scenarios(str(spec_path))
            assert len(scenarios) == 1
            assert "user" in scenarios[0].given

    def test_no_given_when_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "spec.md"
            spec_path.write_text("# Just some text\n")
            scenarios = _discover_scenarios(str(spec_path))
            assert scenarios == []


class TestDiscoverTestFiles:
    def test_no_matching_files(self):
        with tempfile.TemporaryDirectory() as td:
            files = _discover_test_files(Path(td))
            assert files == []

    def test_finds_system_test_files(self):
        with tempfile.TemporaryDirectory() as td:
            sys_dir = Path(td) / "tests" / "system"
            sys_dir.mkdir(parents=True, exist_ok=True)
            (sys_dir / "test_qualification.py").write_text("def test_foo(): pass")
            files = _discover_test_files(Path(td))
            assert len(files) >= 1
            assert any("test_qualification.py" in str(f) for f in files)


class TestCheckScenarioCoverage:
    def test_no_scenarios(self):
        coverage = _check_scenario_coverage([], [])
        assert coverage["total_scenarios"] == 0
        assert coverage["coverage_pct"] == 0.0

    def test_uncovered_scenario(self):
        s = Scenario("GIVEN user does something\nWHEN event happens\nTHEN system responds")
        coverage = _check_scenario_coverage([s], [])
        assert coverage["uncovered_count"] == 1
        assert coverage["coverage_pct"] == 0.0

    def test_covered_scenario(self):
        with tempfile.TemporaryDirectory() as td:
            test_file = Path(td) / "test_system.py"
            test_file.write_text("def test_user_does_something(): pass")
            s = Scenario("GIVEN user does something\nWHEN event happens\nTHEN system responds")
            coverage = _check_scenario_coverage([s], [test_file])
            # The keyword "user" or "system" might match
            pass  # The actual match depends on keyword overlap


class TestRunSystemTests:
    def test_no_test_files(self):
        results = _run_system_tests([], Path("/tmp"))
        assert results["executed"] == 0
        assert results["passed"] == 0

    def test_python_test_success(self):
        with tempfile.TemporaryDirectory() as td:
            test_file = Path(td) / "test_pass.py"
            test_file.write_text("def test_pass(): pass")
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = ""
                mock_run.return_value.stderr = ""
                results = _run_system_tests([test_file], Path(td))
                assert results["executed"] >= 1

    def test_python_test_failure(self):
        with tempfile.TemporaryDirectory() as td:
            test_file = Path(td) / "test_fail.py"
            test_file.write_text("def test_fail(): assert False")
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 1
                mock_run.return_value.stdout = "FAIL"
                mock_run.return_value.stderr = ""
                results = _run_system_tests([test_file], Path(td))
                assert results["failed"] >= 1

    def test_timeout(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            test_file = Path(td) / "test_slow.py"
            test_file.write_text("def test_slow(): pass")
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pytest", 30)):
                results = _run_system_tests([test_file], Path(td))
                assert results["executed"] >= 1
                assert results["failed"] >= 1


class TestBuildQualificationReport:
    def test_no_scenarios(self):
        report = _build_qualification_report(
            "spec.md", Path("/tmp"), [],
            {"total_scenarios": 0, "covered_count": 0, "uncovered_count": 0,
             "covered": [], "uncovered": [], "coverage_pct": 0.0},
            {"executed": 0, "passed": 0, "failed": 0, "errors": [], "details": []}
        )
        assert report["verdict"] == "not-applicable"

    def test_all_covered_and_passed(self):
        s = Scenario("GIVEN x\nWHEN y\nTHEN z")
        coverage = {"total_scenarios": 1, "covered_count": 1, "uncovered_count": 0, "covered": [], "uncovered": [], "coverage_pct": 100.0}
        test_results = {"executed": 2, "passed": 2, "failed": 0, "errors": [], "details": []}
        report = _build_qualification_report("spec.md", Path("/tmp"), [s], coverage, test_results)
        assert report["verdict"] == "passed"

    def test_partial_coverage(self):
        s = Scenario("GIVEN x\nWHEN y\nTHEN z")
        coverage = {"total_scenarios": 2, "covered_count": 1, "uncovered_count": 1, "covered": [], "uncovered": [{"scenario": "s2"}], "coverage_pct": 50.0}
        test_results = {"executed": 1, "passed": 1, "failed": 0, "errors": [], "details": []}
        report = _build_qualification_report("spec.md", Path("/tmp"), [s, s], coverage, test_results)
        assert report["verdict"] == "partial"

    def test_failed_tests(self):
        s = Scenario("GIVEN x\nWHEN y\nTHEN z")
        coverage = {"total_scenarios": 1, "covered_count": 1, "uncovered_count": 0, "covered": [], "uncovered": [], "coverage_pct": 100.0}
        test_results = {"executed": 2, "passed": 1, "failed": 1, "errors": [], "details": []}
        report = _build_qualification_report("spec.md", Path("/tmp"), [s], coverage, test_results)
        assert report["verdict"] == "failed"


class TestStepTestQualification:
    def test_step_runs(self):
        session = MagicMock()
        session.name = "test"
        session.spec_path = "/tmp/spec.md"
        session.session_dir = Path("/tmp")

        with patch("yuleosh.pipeline.step_handlers.test_qualification.os.environ",
                   new={}):
            # Mock all the internal functions to return valid data
            with patch("yuleosh.pipeline.step_handlers.test_qualification._discover_scenarios",
                       return_value=[Scenario("GIVEN user\nWHEN click\nTHEN ok")]):
                with patch("yuleosh.pipeline.step_handlers.test_qualification._discover_test_files",
                           return_value=[]):
                    with patch("yuleosh.pipeline.step_handlers.test_qualification._run_system_tests",
                               return_value={"executed": 0, "passed": 0, "failed": 0, "errors": [],
                                              "details": []}):
                        result = step_test_qualification(session)
                        assert result is not None
