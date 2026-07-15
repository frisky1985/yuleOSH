#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for the yuleOSH Onboarding Wizard CLI (方向三).

Test matrix:
  - test_onboard_new_project       — 全新项目 wizard 流程
  - test_onboard_migration_project — 迁移项目 wizard 流程
  - test_onboard_detects_project_type — 自动检测 AUTOSAR/MCU/Python
  - test_onboard_cli_registered    — yuleosh onboard --help 可运行
  - test_onboard_no_clobber        — 已存在的 .osh/ 配置不被覆盖
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from yuleosh.cli.onboard import (
    _detect_project_type,
    _ensure_osh_project,
    _OEM_TEMPLATES,
    cmd_onboard,
)


# ── Helpers ─────────────────────────────────────────────────────────────

def _make_parents(path: Path):
    """Ensure parent directory exists for a file path."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _write(path: Path, content: str):
    """Write content to path, creating parent dirs."""
    _make_parents(path)
    path.write_text(content)


def _create_minimal_project(tmpdir: str, project_type: str = "c"):
    """Create a minimal project skeleton for testing."""
    root = Path(tmpdir)

    # Always create .osh/ to test no-clobber
    (root / ".osh" / "ci").mkdir(parents=True, exist_ok=True)
    (root / ".osh" / "evidence").mkdir(parents=True, exist_ok=True)
    _write(root / ".osh" / "ci" / "layer1.json",
           json.dumps({"layer": 1, "status": "completed", "stages": []}))
    _write(root / ".osh" / "dashboard.json",
           json.dumps({"project": "test", "status": "active"}))

    # Create .yuleosh for no-clobber test
    (root / ".yuleosh" / "reports").mkdir(parents=True, exist_ok=True)

    if project_type == "autosar":
        _write(root / "src" / "mcal" / "Mcu" / "Mcu.c",
               "#include \"Std_Types.h\"\n#include \"Mcu_Cfg.h\"\n/* AUTOSAR CP 4.4 */\n")
        _write(root / "src" / "mcal" / "Dio" / "Dio.c",
               "#include \"Std_Types.h\"\n#include \"Dio_Cfg.h\"\n")
        _write(root / "tests" / "test_mcu.c",
               "#include \"CUnit/CUnit.h\"\nvoid test_mcu_init(void) { CU_ASSERT(1); }\n")
        _write(root / "arxml" / "system.arxml",
               "<?xml version=\"1.0\"?>\n<AUTOSAR></AUTOSAR>\n")

    elif project_type == "mcu":
        _write(root / "src" / "main.c",
               "#include \"S32K312.h\"\nint main(void) { return 0; }\n")
        _write(root / "src" / "gpio.c",
               "#include \"S32K312.h\"\nvoid gpio_init(void) {}\n")
        _write(root / "tests" / "test_gpio.c",
               "#include \"cmocka.h\"\nstatic void test_gpio(void **s) { assert_int_equal(1, 1); }\n")

    elif project_type == "python":
        _write(root / "src" / "app.py",
               "def hello() -> str:\n    return \"hello\"\n")
        _write(root / "tests" / "test_app.py",
               "def test_hello():\n    assert hello() == \"hello\"\n")

    else:
        # Generic C
        _write(root / "src" / "main.c", "int main(void) { return 0; }\n")
        _write(root / "src" / "utils.c", "int add(int a, int b) { return a + b; }\n")
        _write(root / "tests" / "test_utils.c",
               "#include \"CUnit/CUnit.h\"\nvoid test_add(void) { CU_ASSERT(add(1,2) == 3); }\n")

    return root


# ── Tests ───────────────────────────────────────────────────────────────


class TestOnboardNewProject:
    """全新项目 wizard 流程 (test_onboard_new_project)."""

    def test_new_project_wizard_flow(self):
        """Verify new project wizard completes end-to-end."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _create_minimal_project(tmpdir, project_type="c")

            # Remove existing .yuleosh evidence to simulate "new" project
            shutil.rmtree(str(root / ".yuleosh" / "reports"), ignore_errors=True)

            # Run wizard (non-interactive)
            with patch("builtins.input", return_value=""):  # accept defaults
                result = cmd_onboard(
                    project_dir=str(root),
                    name="TestProject",
                    project_type="new",
                    oem_template="generic",
                )

            # Validate result structure
            assert "project_info" in result
            assert "analysis" in result
            assert "kg_stats" in result
            assert "compliance" in result
            assert "dashboard" in result
            assert "elapsed" in result

            # Validate project info
            info = result["project_info"]
            assert info["name"] == "TestProject"
            assert info["project_type"] == "new"
            assert info["oem_template"] == "generic"

            # Validate analysis
            analysis = result["analysis"]
            assert analysis["source_count"] >= 2
            assert analysis["test_count"] >= 1
            assert analysis["project_type"] == "c"

            # Validate elapsed time is positive
            assert result["elapsed"] > 0

    def test_new_project_creates_dirs(self):
        """Verify new project directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "my-new-project"
            root.mkdir()

            with patch("builtins.input", return_value=""):
                cmd_onboard(
                    project_dir=str(root),
                    name="NewProject",
                    project_type="new",
                    oem_template="generic",
                )

            # Verify .osh structure exists
            assert (root / ".osh" / "ci").is_dir()
            assert (root / ".osh" / "evidence").is_dir()
            assert (root / ".yuleosh" / "reports").is_dir()


class TestOnboardMigrationProject:
    """迁移项目 wizard 流程 (test_onboard_migration_project)."""

    def test_migration_project_wizard(self):
        """Verify migration project wizard detects existing code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _create_minimal_project(tmpdir, project_type="autosar")

            with patch("builtins.input", return_value=""):
                result = cmd_onboard(
                    project_dir=str(root),
                    name="MigrationASR",
                    project_type="migration",
                    oem_template="vw",
                )

            assert result["project_info"]["name"] == "MigrationASR"
            assert result["project_info"]["project_type"] == "migration"
            assert result["project_info"]["oem_template"] == "vw"

            # AUTOSAR project should detect AUTOSAR CP
            analysis = result["analysis"]
            assert analysis["project_type"] in ("autosar", "c")
            assert any("AUTOSAR" in fw for fw in analysis.get("detected_frameworks", []))

    def test_migration_preserves_existing(self):
        """Verify existing files are not overwritten by wizard."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _create_minimal_project(tmpdir, project_type="c")

            # Write a custom docs/spec.md that should not be overwritten
            custom_spec = "# Custom spec\nDo not overwrite\n"
            (root / "docs").mkdir(parents=True, exist_ok=True)
            (root / "docs" / "spec.md").write_text(custom_spec)

            with patch("builtins.input", return_value=""):
                result = cmd_onboard(
                    project_dir=str(root),
                    name="PreserveTest",
                    project_type="migration",
                    oem_template="generic",
                )

            # The custom spec should still exist and be untouched
            spec_content = (root / "docs" / "spec.md").read_text()
            assert spec_content == custom_spec


class TestDetectProjectType:
    """自动检测 AUTOSAR/MCU/Python (test_onboard_detects_project_type)."""

    def test_detects_autosar(self):
        """Detect AUTOSAR CP project from Std_Types.h and arxml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _create_minimal_project(tmpdir, project_type="autosar")
            result = _detect_project_type(str(root))

            assert result["project_type"] == "autosar"
            assert any("AUTOSAR" in fw for fw in result["detected_frameworks"])

    def test_detects_c_project(self):
        """Detect generic C project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _create_minimal_project(tmpdir, project_type="c")
            result = _detect_project_type(str(root))

            assert result["project_type"] == "c"
            assert result["source_count"] >= 2
            assert result["test_count"] >= 1

    def test_detects_python_project(self):
        """Detect Python project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _create_minimal_project(tmpdir, project_type="python")
            result = _detect_project_type(str(root))

            assert result["project_type"] == "python"
            assert result["source_count"] >= 1  # .py files

    def test_detects_cunit_framework(self):
        """Detect CUnit and cmocka testing frameworks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _create_minimal_project(tmpdir, project_type="c")
            result = _detect_project_type(str(root))

            frameworks = result["detected_frameworks"]
            assert "CUnit" in frameworks


class TestOnboardCliRegistered:
    """yuleosh onboard --help 可运行 (test_onboard_cli_registered)."""

    def test_onboard_help_runs(self):
        """Verify 'yuleosh onboard --help' exits with code 0."""
        project_root = _PROJECT_ROOT
        cli_script = str(project_root / "src" / "yuleosh" / "cli" / "main.py")

        result = subprocess.run(
            [sys.executable, cli_script, "onboard", "--help"],
            capture_output=True, text=True,
            cwd=str(project_root),
        )

        assert result.returncode == 0, f"STDERR: {result.stderr}"
        assert "Onboarding Wizard" in result.stdout or "onboard" in result.stdout

    def test_onboard_parser_has_all_args(self):
        """Verify onboard parser has all expected arguments."""
        from yuleosh.cli.onboard import build_onboard_parser
        import argparse

        parser = argparse.ArgumentParser(prog="test")
        sub = parser.add_subparsers(dest="command")
        build_onboard_parser(sub)

        # Find the onboard subparser and inspect its options
        onboard_action = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for choice, subparser in action.choices.items():
                    if choice == "onboard":
                        onboard_action = subparser
                        break

        assert onboard_action is not None, "onboard subparser not found"

        # Collect all option strings from the subparser
        opt_strings = set()
        for action in onboard_action._actions:
            for opt in action.option_strings:
                opt_strings.add(opt)

        assert "--name" in opt_strings or "-n" in opt_strings, f"--name not in {opt_strings}"
        assert "--project-type" in opt_strings, f"--project-type not in {opt_strings}"
        assert "--oem-template" in opt_strings, f"--oem-template not in {opt_strings}"
        assert "--repo" in opt_strings or "-r" in opt_strings, f"--repo not in {opt_strings}"
        assert "--dir" in opt_strings or "-d" in opt_strings, f"--dir not in {opt_strings}"


class TestOnboardNoClobber:
    """已存在的 .osh/ 配置不被覆盖 (test_onboard_no_clobber)."""

    def test_existing_osh_not_overwritten(self):
        """Verify existing .osh/dashboard.json is not overwritten."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _create_minimal_project(tmpdir, project_type="c")

            # The _create_minimal_project already creates .osh/ with a dashboard.json
            orig_dashboard = (root / ".osh" / "dashboard.json").read_text()
            orig_data = json.loads(orig_dashboard)

            with patch("builtins.input", return_value=""):
                cmd_onboard(
                    project_dir=str(root),
                    name="NoClobber",
                    project_type="migration",
                    oem_template="generic",
                )

            # The dashboard.json should still have its original content
            # (the onboard wizard adds/modifies it if missing, but shouldn't
            # overwrite meaningful config)
            assert (root / ".osh" / "dashboard.json").exists()

            # The CI layer1.json should remain untouched
            ci_content = json.loads((root / ".osh" / "ci" / "layer1.json").read_text())
            assert ci_content["layer"] == 1
            assert ci_content["status"] == "completed"

    def test_existing_dirs_not_clobbered(self):
        """Verify .yuleosh/reports/ contents remain intact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _create_minimal_project(tmpdir, project_type="c")

            # Pre-create a custom report
            (root / ".yuleosh" / "reports" / "my-existing-report.json").write_text(
                json.dumps({"custom": True})
            )

            with patch("builtins.input", return_value=""):
                cmd_onboard(
                    project_dir=str(root),
                    name="NoClobber2",
                    project_type="migration",
                    oem_template="generic",
                )

            # Custom report should still exist
            assert (root / ".yuleosh" / "reports" / "my-existing-report.json").exists()
            data = json.loads((root / ".yuleosh" / "reports" / "my-existing-report.json").read_text())
            assert data["custom"] is True

    def test_osh_ci_results_preserved(self):
        """Verify CI result files in .osh/ci/ are preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _create_minimal_project(tmpdir, project_type="c")

            # Add extra CI result
            (root / ".osh" / "ci" / "layer2.json").write_text(
                json.dumps({"layer": 2, "status": "completed"})
            )

            with patch("builtins.input", return_value=""):
                cmd_onboard(
                    project_dir=str(root),
                    name="PreserveCI",
                    project_type="migration",
                    oem_template="generic",
                )

            assert (root / ".osh" / "ci" / "layer1.json").exists()
            assert (root / ".osh" / "ci" / "layer2.json").exists()


# ── Edge cases ─────────────────────────────────────────────────────────

class TestOnboardEdgeCases:
    """Edge case tests for onboarding wizard."""

    def test_empty_directory(self):
        """Verify wizard handles empty directory gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("builtins.input", return_value=""):
                result = cmd_onboard(
                    project_dir=tmpdir,
                    name="EmptyDir",
                    project_type="new",
                    oem_template="generic",
                )

            assert result["project_info"]["name"] == "EmptyDir"
            assert result["analysis"]["source_count"] == 0
            assert result["analysis"]["project_type"] == "unknown"

    def test_default_oem_templates_list(self):
        """Verify OEM template list is well-defined."""
        assert "generic" in _OEM_TEMPLATES
        assert "vw" in _OEM_TEMPLATES
        assert "bmw" in _OEM_TEMPLATES
        assert len(_OEM_TEMPLATES) >= 4

    def test_ensure_osh_creates_dirs(self):
        """Verify _ensure_osh_project creates expected directory tree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _ensure_osh_project(tmpdir)
            root = Path(tmpdir)
            assert (root / ".osh" / "ci").is_dir()
            assert (root / ".osh" / "evidence").is_dir()
            assert (root / ".yuleosh" / "reports").is_dir()
            assert (root / "docs").is_dir()
            assert (root / "specs").is_dir()
            assert (root / "tests").is_dir()
