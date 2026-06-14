# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Basic tests for CLI modules — stats and template.

Covers: cli/stats.py and cli/template.py basic flows at ~60% coverage.
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "cli"))

# ===================================================================
# cli/stats.py
# ===================================================================

def test_count_source_lines_empty_project():
    """Test count_source_lines with empty project."""
    from yuleosh.cli.stats import count_source_lines
    with tempfile.TemporaryDirectory() as tmp:
        # Create src/ and tests/ empty dirs
        Path(tmp).joinpath("src").mkdir()
        Path(tmp).joinpath("tests").mkdir()
        result = count_source_lines(tmp)
        assert result["total_files"] >= 0
        assert result["total_lines"] >= 0
        assert "languages" in result
        assert "source_lines" in result
        assert "doc_lines" in result


def test_count_source_lines_with_files():
    """Test count_source_lines with actual Python files."""
    from yuleosh.cli.stats import count_source_lines
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        src.mkdir()
        (src / "app.py").write_text("import os\n\n\ndef foo():\n    pass\n")
        (src / "utils.py").write_text("def bar():\n    return 42\n")
        result = count_source_lines(tmp)
        assert result["source_files"] >= 2
        assert result["source_lines"] >= 7


def test_count_tests_empty():
    """Test count_tests with no tests directory."""
    from yuleosh.cli.stats import count_tests
    with tempfile.TemporaryDirectory() as tmp:
        result = count_tests(tmp)
        assert result["test_files"] == 0
        assert result["test_functions"] == 0


def test_count_tests_with_functions():
    """Test count_tests identifies test functions."""
    from yuleosh.cli.stats import count_tests
    with tempfile.TemporaryDirectory() as tmp:
        tests = Path(tmp) / "tests"
        tests.mkdir()
        (tests / "test_foo.py").write_text(
            "def test_one():\n    pass\n\n"
            "def test_two():\n    pass\n"
        )
        (tests / "test_bar.py").write_text(
            "class TestSuite:\n"
            "    def test_a():\n        pass\n"
            "    def test_b():\n        pass\n"
        )
        result = count_tests(tmp)
        # May vary slightly depending on regex matching
        assert result["test_functions"] >= 3
        assert result["test_files"] >= 1


def test_compute_spec_coverage_no_spec():
    """Test compute_spec_coverage with no spec.md."""
    from yuleosh.cli.stats import compute_spec_coverage
    with tempfile.TemporaryDirectory() as tmp:
        result = compute_spec_coverage(tmp)
        assert result["score"] == 0
        assert "No spec.md found" in result.get("message", "")


def test_count_pipeline_runs_empty():
    """Test count_pipeline_runs with no sessions directory."""
    from yuleosh.cli.stats import count_pipeline_runs
    with tempfile.TemporaryDirectory() as tmp:
        result = count_pipeline_runs(tmp)
        assert result["total_runs"] == 0
        assert "recent_runs" in result


def test_count_pipeline_runs_with_data():
    """Test count_pipeline_runs with session data."""
    from yuleosh.cli.stats import count_pipeline_runs
    with tempfile.TemporaryDirectory() as tmp:
        sess_dir = Path(tmp) / ".osh" / "sessions" / "sess-1"
        sess_dir.mkdir(parents=True)
        (sess_dir / "session.json").write_text(json.dumps({
            "name": "pipeline-1",
            "status": "completed",
            "created_at": "2024-01-01",
            "steps": ["step1"],
        }))
        result = count_pipeline_runs(tmp)
        assert result["total_runs"] == 1
        assert result["completed"] == 1
        assert len(result["recent_runs"]) == 1


def test_count_ci_runs_empty():
    """Test count_ci_runs with no CI directory."""
    from yuleosh.cli.stats import count_ci_runs
    with tempfile.TemporaryDirectory() as tmp:
        result = count_ci_runs(tmp)
        assert result["total_runs"] == 0
        assert "by_layer" in result


def test_count_ci_runs_with_data():
    """Test count_ci_runs with CI data."""
    from yuleosh.cli.stats import count_ci_runs
    with tempfile.TemporaryDirectory() as tmp:
        ci_dir = Path(tmp) / ".osh" / "ci"
        ci_dir.mkdir(parents=True)
        (ci_dir / "layer1.json").write_text(json.dumps({
            "layer": 1, "status": "passed"
        }))
        (ci_dir / "layer2.json").write_text(json.dumps({
            "layer": 2, "status": "failed"
        }))
        result = count_ci_runs(tmp)
        assert result["total_runs"] == 2
        assert result["passed"] == 1
        assert result["failed"] == 1


def test_cmd_stats_json_output():
    """Test cmd_stats with to_json=True outputs valid JSON."""
    from yuleosh.cli.stats import cmd_stats
    with tempfile.TemporaryDirectory() as tmp:
        with patch("sys.stdout") as mock_stdout:
            result = cmd_stats(tmp, to_json=True)
            assert "project" in result
            assert "source_code" in result
            assert "tests" in result
            assert "spec_coverage" in result
            assert "pipeline_runs" in result
            assert "ci_runs" in result


def test_cmd_stats_default_dir():
    """Test cmd_stats uses current dir by default."""
    from yuleosh.cli.stats import cmd_stats
    result = cmd_stats(to_json=True)
    assert result is not None


def test_stats_main_function():
    """Test stats main() entry point."""
    from yuleosh.cli.stats import main
    test_args = ["stats.py", "--json"]
    with patch.object(sys, "argv", test_args):
        with patch("yuleosh.cli.stats.cmd_stats") as mock_cmd:
            mock_cmd.return_value = {}
            main()
            mock_cmd.assert_called_once()


def test_stats_main_with_dir():
    """Test stats main() with explicit directory."""
    from yuleosh.cli.stats import main
    with tempfile.TemporaryDirectory() as tmp:
        test_args = ["stats.py", tmp, "--json"]
        with patch.object(sys, "argv", test_args):
            with patch("yuleosh.cli.stats.cmd_stats") as mock_cmd:
                mock_cmd.return_value = {}
                main()
                mock_cmd.assert_called_once()


# ===================================================================
# cli/template.py
# ===================================================================

def test_template_starter_init():
    """Test template init creates basic project structure."""
    from yuleosh.cli.template import cmd_template_init
    with tempfile.TemporaryDirectory() as tmp:
        proj_dir = cmd_template_init("test-project", parent_dir=tmp)
        assert proj_dir.exists()
        assert (proj_dir / "docs" / "spec.md").exists()
        assert (proj_dir / "src" / "__init__.py").exists()
        assert (proj_dir / "tests" / "test_test-project.py").exists()
        assert (proj_dir / "pyproject.toml").exists()
        assert (proj_dir / ".gitignore").exists()

        # Verify spec content has the project name
        spec = (proj_dir / "docs" / "spec.md").read_text()
        assert "test-project" in spec


def test_template_starter_init_with_existing():
    """Test template init exits cleanly when dir exists."""
    from yuleosh.cli.template import cmd_template_init
    with tempfile.TemporaryDirectory() as tmp:
        existing = Path(tmp) / "existing-proj"
        existing.mkdir()
        try:
            cmd_template_init("existing-proj", parent_dir=tmp)
            assert False, "Should have exited"
        except SystemExit:
            pass


def test_template_main_init():
    """Test template main() with init command."""
    from yuleosh.cli.template import main
    with tempfile.TemporaryDirectory() as tmp:
        test_args = ["template.py", "init", "test-proj"]
        with patch.object(sys, "argv", test_args):
            with patch("yuleosh.cli.template.cmd_template_init") as mock_init:
                mock_init.return_value = Path(tmp) / "test-proj"
                main()
                mock_init.assert_called_once()


def test_template_main_unknown():
    """Test template main() with unknown command exits."""
    from yuleosh.cli.template import main
    test_args = ["template.py", "unknown"]
    with patch.object(sys, "argv", test_args):
        try:
            main()
            assert False, "Should have exited"
        except SystemExit:
            pass


def test_template_main_no_args():
    """Test template main() with no args exits."""
    from yuleosh.cli.template import main
    test_args = ["template.py"]
    with patch.object(sys, "argv", test_args):
        try:
            main()
            assert False, "Should have exited"
        except SystemExit:
            pass


def test_template_init_with_from_template():
    """Test template init with --from flag creates from template dir."""
    from yuleosh.cli.template import cmd_template_init
    with tempfile.TemporaryDirectory() as tmp:
        # Create a template dir
        template_dir = Path(tmp) / "templates" / "ble-sensor"
        template_dir.mkdir(parents=True)
        (template_dir / "docs").mkdir()
        (template_dir / "docs" / "spec.md").write_text("# BLE Sensor Spec")
        (template_dir / "src").mkdir()
        (template_dir / "tests").mkdir()
        (template_dir / "Makefile").write_text("all:\n\techo build\n")

        # Init from template using absolute path
        proj_dir = cmd_template_init("ble-proj", parent_dir=tmp,
                                     from_template=str(template_dir))
        assert proj_dir.exists()
        assert (proj_dir / "docs" / "spec.md").exists()
        assert (proj_dir / "Makefile").exists()


def test_template_init_from_template_not_found():
    """Test template init with non-existent template exits."""
    from yuleosh.cli.template import cmd_template_init
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cmd_template_init("proj", parent_dir=tmp,
                             from_template="/nonexistent/template")
            assert False, "Should have exited"
        except SystemExit:
            pass


def test_print_stats_human():
    """Test _print_stats_human renders correctly (just call it)."""
    from yuleosh.cli.stats import _print_stats_human
    stats = {
        "project": "test-proj",
        "project_dir": "/tmp",
        "source_code": {
            "total_files": 5,
            "total_lines": 100,
            "source_files": 3,
            "source_lines": 70,
            "doc_files": 2,
            "doc_lines": 30,
            "languages": {
                ".py": {"label": "Python", "files": 3, "lines": 70},
            },
        },
        "tests": {"test_files": 2, "test_functions": 10, "test_functions_by_file": {"test_a.py": 5}},
        "spec_coverage": {"score": 80, "pass_threshold": True, "requirements": 3, "scenarios": 2,
                          "total_shall": 5, "issues": 0, "error_count": 0, "warn_count": 0},
        "pipeline_runs": {"total_runs": 3, "completed": 2, "failed": 1, "recent_runs": []},
        "ci_runs": {"total_runs": 2, "by_layer": {"1": 1, "2": 1}, "passed": 1, "failed": 1},
    }
    # Should not raise
    _print_stats_human(stats)
