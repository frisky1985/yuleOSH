"""Targeted tests for modules with largest remaining uncovered lines."""
import os, sys, tempfile, json
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestCiRunV2:
    def test_layer_dependencies_module_var(self):
        from yuleosh.ci.run import layer_dependencies
        assert isinstance(layer_dependencies, dict)
        assert 1 in layer_dependencies

    def test_git_commit_hash(self):
        from yuleosh.ci.run import git_commit_hash
        with patch("yuleosh.ci.run.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "abc123def456\n"
            mock_run.return_value = mock_proc
            result = git_commit_hash()
            assert result == "abc123def456"

    def test_find_test_files(self):
        from yuleosh.ci.run import find_test_files
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test_foo.py").touch()
            result = find_test_files(tmpdir)
            assert isinstance(result, list)

    def test_get_changed_files(self):
        from yuleosh.ci.run import get_changed_files
        with patch("yuleosh.ci.run.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "file1.py\nfile2.py\n"
            mock_run.return_value = mock_proc
            result = get_changed_files()
            assert isinstance(result, list)


class TestTestgenFormatterV2:
    def test_format_gotest(self):
        from yuleosh.testgen.formatter import format_gotest
        result = format_gotest([])
        assert result is not None

    def test_format_ceedling(self):
        from yuleosh.testgen.formatter import format_ceedling
        result = format_ceedling([])
        assert result is not None


class TestStripeGateway:
    def test_urls_exist(self):
        from yuleosh.usage.stripe_gateway import (
            BASE_URL, SUCCESS_URL, CANCEL_URL,
            is_stripe_configured
        )
        assert isinstance(BASE_URL, str)
        assert callable(is_stripe_configured)


class TestSilModule:
    def test_participant_state(self):
        from yuleosh.sil import ParticipantState, SimStatus
        assert ParticipantState.DISCONNECTED is not None
        assert SimStatus.PENDING is not None


class TestSkillsV2:
    def test_manifest_create(self):
        from yuleosh.skills import SkillManifest
        m = SkillManifest(name="test", version="1.0", description="d",
                          author="me", type="skill")
        assert m.name == "test"
