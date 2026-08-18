"""Tests for OpenSpec directory mode in step_spec_check."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.spec import step_spec_check


def _make_session(tmp_path, spec_path: str) -> PipelineSession:
    session = PipelineSession(
        name="test-spec-check-dir",
        spec_path=spec_path,
    )
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-spec-check-dir"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


def _write_openspec_dir(root: Path) -> Path:
    specs = root / ".osh" / "specs"
    (specs / "window").mkdir(parents=True, exist_ok=True)
    (specs / "window" / "spec.md").write_text(
        "# Window\n\n## SR-001: Window\n\n- The system SHALL open\n\n### Reason\n\nNeeded\n"
    )
    (specs / "light").mkdir(parents=True, exist_ok=True)
    (specs / "light" / "spec.md").write_text(
        "# Light\n\n## SR-002: Light\n\n- The system SHALL light\n\n### Reason\n\nNeeded\n"
    )
    return specs


def _valid_dir_payload():
    return {
        "file": ".osh/specs",
        "requirements": 2,
        "scenarios": 0,
        "total_shall": 2,
        "issues": [],
        "issue_count": 0,
        "error_count": 0,
        "coverage": {"score": 85.0},
        "files": ["a", "b"],
    }


class TestStepSpecCheckDirMode:
    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.spec.contracts_check_dir")
    def test_directory_mode_aggregates(self, mock_ccd, mock_run, tmp_path):
        """GIVEN spec_path points at .osh/specs directory
           WHEN step_spec_check runs
           THEN it validates the dir and writes contracts + spec-files index."""
        specs = _write_openspec_dir(tmp_path)
        session = _make_session(tmp_path, str(specs))

        # validate subprocess returns clean
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = json.dumps(_valid_dir_payload())
        proc.stderr = ""
        mock_run.return_value = proc

        # contracts_check_dir returns passed
        mock_ccd.return_value = {
            "contracts": {"files": [str(specs / "window" / "spec.md"), str(specs / "light" / "spec.md")]},
            "validation": {"passed": True, "missing": [], "details": {}},
            "mode": "directory",
        }

        out = step_spec_check(session)

        # subprocess invoked with directory target
        args = mock_run.call_args[0][0]
        assert str(specs) in args

        # contracts written
        contracts_path = session.session_dir / "contracts.json"
        assert contracts_path.exists()

        # spec-files index written + registered
        idx = session.session_dir / "spec-files.json"
        assert idx.exists()
        assert session.artifacts.get("spec_files") == str(idx)
        assert out is not None

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.spec.contracts_check")
    def test_file_mode_uses_contracts_check(self, mock_cc, mock_run, tmp_path):
        """GIVEN spec_path points at a single file
           WHEN step_spec_check runs
           THEN it uses the single-file contracts_check path."""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec\n")
        session = _make_session(tmp_path, str(spec_file))

        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = json.dumps({
            "coverage": {"score": 85.0},
            "error_count": 0,
            "issues": [],
        })
        proc.stderr = ""
        mock_run.return_value = proc

        mock_cc.return_value = {
            "contracts": {},
            "validation": {"passed": True, "missing": [], "details": {}},
        }

        step_spec_check(session)
        mock_cc.assert_called_once_with(str(spec_file))
        # no spec-files index for single-file mode
        assert not (session.session_dir / "spec-files.json").exists()
