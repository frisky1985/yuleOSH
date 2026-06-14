# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for cli/stats.py and cli/template.py.

Target: 80%+ branch coverage for stats, 80%+ for template.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ======================================================================
# cli/stats.py — count_source_lines edge cases
# ======================================================================

class TestCountSourceLines:
    def test_no_src_dir(self):
        from yuleosh.cli.stats import count_source_lines
        with tempfile.TemporaryDirectory() as tmp:
            result = count_source_lines(tmp)
            assert result["total_files"] == 0

    def test_exception_during_read(self):
        from yuleosh.cli.stats import count_source_lines
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "broken.py").write_text("x = 1\n")
            with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
                result = count_source_lines(tmp)
                assert "languages" in result

    def test_excluded_dirs_skipped(self):
        from yuleosh.cli.stats import count_source_lines
        with tempfile.TemporaryDirectory() as tmp:
            for d in [".osh", "__pycache__", "node_modules", ".git", "venv"]:
                p = Path(tmp) / "src" / d
                p.mkdir(parents=True)
                (p / "test.py").write_text("x = 1\n")
            result = count_source_lines(tmp)
            assert result["source_files"] == 0

    def test_docs_directory(self):
        from yuleosh.cli.stats import count_source_lines
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            docs.mkdir()
            (docs / "readme.md").write_text("# Hello\n\nWorld\n")
            result = count_source_lines(tmp)
            assert result["doc_files"] >= 1
            assert result["doc_lines"] >= 2

    def test_no_ext_match(self):
        from yuleosh.cli.stats import count_source_lines
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "data.xyz").write_text("binary garbage")
            result = count_source_lines(tmp)
            assert result["source_files"] == 0

    def test_doc_read_exception(self):
        from yuleosh.cli.stats import count_source_lines
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            docs.mkdir()
            (docs / "readme.md").write_text("hello")
            with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
                result = count_source_lines(tmp)
                assert "doc_files" in result

    def test_cpp_and_hpp(self):
        from yuleosh.cli.stats import count_source_lines
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "main.cpp").write_text("int main() {}\n")
            (src / "header.hpp").write_text("#pragma once\nint x = 1;\n")
            result = count_source_lines(tmp)
            assert result["source_lines"] >= 3

    def test_yaml_toml_json(self):
        from yuleosh.cli.stats import count_source_lines
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "config.yml").write_text("key: value\n")
            (src / "config.yaml").write_text("key2: value2\n")
            (src / "config.toml").write_text("key3 = 3\n")
            (src / "data.json").write_text('{"a": 1}\n')
            result = count_source_lines(tmp)
            assert result["source_files"] >= 4


# ======================================================================
# cli/stats.py — count_tests edge cases
# ======================================================================

class TestCountTests:
    def test_hidden_dirs_skipped(self):
        from yuleosh.cli.stats import count_tests
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp) / "tests"
            tests.mkdir()
            hidden = tests / ".hidden"
            hidden.mkdir()
            (hidden / "test_hidden.py").write_text("def test_x(): pass\n")
            self_dir = tests / "self"
            self_dir.mkdir()
            (self_dir / "test_self.py").write_text("def test_y(): pass\n")
            (tests / "test_good.py").write_text("def test_z(): pass\n")
            result = count_tests(tmp)
            assert result["test_functions"] >= 1

    def test_non_python_files_ignored(self):
        from yuleosh.cli.stats import count_tests
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp) / "tests"
            tests.mkdir()
            (tests / "test_data.json").write_text("{}")
            (tests / "_private.py").write_text("def test_hidden(): pass\n")
            result = count_tests(tmp)
            assert result["test_files"] == 0

    def test_parse_exception(self):
        from yuleosh.cli.stats import count_tests
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp) / "tests"
            tests.mkdir()
            (tests / "test_bad.py").write_text("def test_ok(): pass\n")
            with patch.object(Path, "read_text", side_effect=UnicodeDecodeError("utf8", b"", 0, 1, "bad")):
                result = count_tests(tmp)
                assert "test_functions" in result


# ======================================================================
# cli/stats.py — compute_spec_coverage edge cases
# ======================================================================

class TestComputeSpecCoverage:
    def test_spec_no_validate_import(self):
        """Test with spec.md but validate module unavailable."""
        from yuleosh.cli.stats import compute_spec_coverage
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            docs.mkdir()
            (docs / "spec.md").write_text("# Spec\n")
            # Disable the validate module's spec subpackage
            with patch.dict("sys.modules", {"spec": None}):
                result = compute_spec_coverage(tmp)
                assert result["score"] == 0
                assert "message" in result


# ======================================================================
# cli/stats.py — count_pipeline_runs edge cases
# ======================================================================

class TestCountPipelineRuns:
    def test_not_a_directory(self):
        from yuleosh.cli.stats import count_pipeline_runs
        with tempfile.TemporaryDirectory() as tmp:
            sess_dir = Path(tmp) / ".osh" / "sessions"
            sess_dir.mkdir(parents=True)
            (sess_dir / "not-a-dir.txt").write_text("not a session")
            result = count_pipeline_runs(tmp)
            assert result["total_runs"] == 0

    def test_missing_session_json(self):
        from yuleosh.cli.stats import count_pipeline_runs
        with tempfile.TemporaryDirectory() as tmp:
            sess_dir = Path(tmp) / ".osh" / "sessions" / "sess-1"
            sess_dir.mkdir(parents=True)
            result = count_pipeline_runs(tmp)
            assert result["total_runs"] == 0

    def test_json_decode_error(self):
        from yuleosh.cli.stats import count_pipeline_runs
        with tempfile.TemporaryDirectory() as tmp:
            sess_dir = Path(tmp) / ".osh" / "sessions" / "sess-1"
            sess_dir.mkdir(parents=True)
            (sess_dir / "session.json").write_text("not valid json")
            result = count_pipeline_runs(tmp)
            assert result["total_runs"] == 0

    def test_failed_status(self):
        from yuleosh.cli.stats import count_pipeline_runs
        with tempfile.TemporaryDirectory() as tmp:
            sess_dir = Path(tmp) / ".osh" / "sessions" / "sess-1"
            sess_dir.mkdir(parents=True)
            (sess_dir / "session.json").write_text(json.dumps({
                "name": "failed-pipe", "status": "failed", "created_at": "2024-01-01", "steps": []
            }))
            result = count_pipeline_runs(tmp)
            assert result["failed"] == 1
            assert result["total_runs"] == 1

    def test_unknown_status(self):
        from yuleosh.cli.stats import count_pipeline_runs
        with tempfile.TemporaryDirectory() as tmp:
            sess_dir = Path(tmp) / ".osh" / "sessions" / "sess-1"
            sess_dir.mkdir(parents=True)
            (sess_dir / "session.json").write_text(json.dumps({
                "name": "unknown", "status": "pending"
            }))
            result = count_pipeline_runs(tmp)
            assert result["total_runs"] == 1


# ======================================================================
# cli/stats.py — count_ci_runs edge cases
# ======================================================================

class TestCountCIRuns:
    def test_invalid_json_file(self):
        from yuleosh.cli.stats import count_ci_runs
        with tempfile.TemporaryDirectory() as tmp:
            ci_dir = Path(tmp) / ".osh" / "ci"
            ci_dir.mkdir(parents=True)
            (ci_dir / "layer1-invalid.json").write_text("bad json")
            result = count_ci_runs(tmp)
            assert result["total_runs"] == 0

    def test_non_layer_files_skipped(self):
        from yuleosh.cli.stats import count_ci_runs
        with tempfile.TemporaryDirectory() as tmp:
            ci_dir = Path(tmp) / ".osh" / "ci"
            ci_dir.mkdir(parents=True)
            (ci_dir / "report.json").write_text('{"status": "passed", "layer": 1}')
            result = count_ci_runs(tmp)
            assert result["total_runs"] == 0

    def test_layer_25_runs(self):
        from yuleosh.cli.stats import count_ci_runs
        with tempfile.TemporaryDirectory() as tmp:
            ci_dir = Path(tmp) / ".osh" / "ci"
            ci_dir.mkdir(parents=True)
            (ci_dir / "layer25-pass.json").write_text(json.dumps({
                "layer": 25, "status": "passed"
            }))
            result = count_ci_runs(tmp)
            assert result["total_runs"] == 1


# ======================================================================
# cli/stats.py — cmd_stats edge cases
# ======================================================================

class TestCmdStats:
    def test_cmd_stats_with_osh_home(self):
        from yuleosh.cli.stats import cmd_stats
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"OSH_HOME": tmp}):
                result = cmd_stats(to_json=True)
                assert result["project_dir"] == tmp

    def test_cmd_stats_human_output(self):
        from yuleosh.cli.stats import cmd_stats
        with tempfile.TemporaryDirectory() as tmp:
            with patch("yuleosh.cli.stats._print_stats_human") as mock_print:
                result = cmd_stats(tmp, to_json=False)
                mock_print.assert_called_once()
                assert result is not None

    def test_cmd_stats_human_empty(self):
        from yuleosh.cli.stats import cmd_stats
        with tempfile.TemporaryDirectory() as tmp:
            result = cmd_stats(tmp, to_json=False)
            assert "project" in result


# ======================================================================
# cli/stats.py — main() edge cases
# ======================================================================

class TestStatsMain:
    def test_main_no_args(self):
        from yuleosh.cli.stats import main
        with patch.object(sys, "argv", ["stats.py"]):
            with patch("yuleosh.cli.stats.cmd_stats") as mock_cmd:
                main()
                mock_cmd.assert_called_once_with(None, False)

    def test_main_with_dir(self):
        from yuleosh.cli.stats import main
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(sys, "argv", ["stats.py", tmp]):
                with patch("yuleosh.cli.stats.cmd_stats") as mock_cmd:
                    main()
                    mock_cmd.assert_called_once_with(tmp, False)

    def test_main_with_json_only(self):
        from yuleosh.cli.stats import main
        with patch.object(sys, "argv", ["stats.py", "--json"]):
            with patch("yuleosh.cli.stats.cmd_stats") as mock_cmd:
                main()
                mock_cmd.assert_called_once_with(None, True)


# ======================================================================
# cli/template.py — cmd_template_init edge cases
# ======================================================================

class TestTemplateInit:
    def test_init_from_template_with_osh_home(self):
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates" / "mcu-firmware"
            template_dir.mkdir(parents=True)
            (template_dir / "docs").mkdir()
            (template_dir / "docs" / "spec.md").write_text("# MCU Spec")
            (template_dir / "src").mkdir()
            (template_dir / "Makefile").write_text("all:\n\techo\n")
            with patch.dict(os.environ, {"OSH_HOME": tmp}):
                proj_dir = cmd_template_init("mcu-proj", parent_dir=tmp,
                                             from_template="templates/mcu-firmware")
                assert proj_dir.exists()
                assert (proj_dir / "Makefile").exists()

    def test_init_from_template_cleanup(self):
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates" / "has-git"
            template_dir.mkdir(parents=True)
            (template_dir / "docs").mkdir()
            (template_dir / "docs" / "spec.md").write_text("# Spec")
            (template_dir / "src").mkdir()
            (template_dir / "tests").mkdir()
            (template_dir / ".git").mkdir()
            (template_dir / "build").mkdir()
            (template_dir / "build" / "output.bin").write_text("")
            (template_dir / "__pycache__").mkdir()
            (template_dir / "__pycache__" / "cache.pyc").write_text("")
            (template_dir / ".pytest_cache").mkdir()
            (template_dir / ".pytest_cache" / "README").write_text("")
            proj_dir = cmd_template_init("clean-proj", parent_dir=tmp,
                                         from_template=str(template_dir))
            assert not (proj_dir / ".git").exists()
            assert not (proj_dir / ".pytest_cache").exists()
            assert not (proj_dir / "build").exists()
            assert (proj_dir / "docs" / "spec.md").exists()

    def test_init_starter_empty(self):
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = cmd_template_init("starter-only", parent_dir=str(tmp))
            assert (proj_dir / "tests" / "test_starter-only.py").exists()
            content = (proj_dir / "src" / "__init__.py").read_text()
            assert "starter-only" in content

    def test_template_not_found_osh_home(self):
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"OSH_HOME": "/nonexistent/osh"}):
                try:
                    cmd_template_init("proj", parent_dir=tmp,
                                     from_template="templates/missing")
                    assert False, "Should have exited"
                except SystemExit:
                    pass

    def test_template_relative_path(self):
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "my-templates"
            template_dir.mkdir()
            (template_dir / "docs").mkdir()
            (template_dir / "docs" / "spec.md").write_text("# Spec")
            (template_dir / "src").mkdir()
            (template_dir / "tests").mkdir()
            proj_dir = cmd_template_init("relative-proj", parent_dir=tmp,
                                         from_template=str(template_dir))
            assert proj_dir.exists()

    def test_init_starter_src_init(self):
        from yuleosh.cli.template import _init_starter
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = Path(tmp) / "test-proj"
            result = _init_starter("test-proj", proj_dir)
            init_py = proj_dir / "src" / "__init__.py"
            assert init_py.exists()
            assert "test-proj" in init_py.read_text()


# ======================================================================
# cli/template.py — main() edge cases
# ======================================================================

class TestTemplateMain:
    def test_main_init_no_project_name(self):
        from yuleosh.cli.template import main
        with patch.object(sys, "argv", ["template.py", "init"]):
            try:
                main()
                assert False, "Should have exited"
            except SystemExit:
                pass

    def test_main_init_with_from(self):
        from yuleosh.cli.template import main
        with patch.object(sys, "argv", ["template.py", "init", "myproj", "--from", "ble"]):
            with patch("yuleosh.cli.template.cmd_template_init") as mock_init:
                mock_init.return_value = Path("/tmp/myproj")
                main()
                mock_init.assert_called_once_with("myproj", from_template="ble")

    def test_main_init_partial_flags(self):
        from yuleosh.cli.template import main
        with patch.object(sys, "argv", ["template.py", "init", "proj", "--from"]):
            with patch("yuleosh.cli.template.cmd_template_init") as mock_init:
                mock_init.return_value = Path("/tmp/proj")
                main()
                mock_init.assert_called_once_with("proj", from_template=None)


# ======================================================================
# cli/stats.py — _print_stats_human edge cases
# ======================================================================

class TestPrintStatsHuman:
    def test_print_empty(self):
        from yuleosh.cli.stats import _print_stats_human
        stats = {
            "project": "p", "project_dir": "/p",
            "source_code": {"total_files": 0, "total_lines": 0,
                          "source_files": 0, "source_lines": 0,
                          "doc_files": 0, "doc_lines": 0},
            "tests": {"test_files": 0, "test_functions": 0},
            "spec_coverage": {"score": 0, "requirements": 0, "scenarios": 0,
                            "total_shall": 0, "issues": 0},
            "pipeline_runs": {"total_runs": 0, "recent_runs": [],
                            "completed": 0, "failed": 0},
            "ci_runs": {"total_runs": 0, "by_layer": {}, "passed": 0, "failed": 0},
        }
        _print_stats_human(stats)

    def test_print_with_recent_runs(self):
        from yuleosh.cli.stats import _print_stats_human
        stats = {
            "project": "p", "project_dir": "/p",
            "source_code": {"total_files": 1, "total_lines": 5,
                          "source_files": 1, "source_lines": 5,
                          "doc_files": 0, "doc_lines": 0,
                          "languages": {".py": {"label": "Python", "files": 1, "lines": 5}}},
            "tests": {"test_files": 0, "test_functions": 0},
            "spec_coverage": {"score": 0, "pass_threshold": False},
            "pipeline_runs": {"total_runs": 2, "completed": 1, "failed": 1,
                           "recent_runs": [
                               {"name": "p1", "status": "completed", "steps": 3, "created_at": "2024-01-01"},
                               {"name": "p2", "status": "failed", "steps": 1, "created_at": "2024-01-02"},
                           ]},
            "ci_runs": {"total_runs": 1, "by_layer": {"1": 1}, "passed": 1, "failed": 0},
        }
        _print_stats_human(stats)
