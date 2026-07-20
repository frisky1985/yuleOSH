"""Tests for api/evidence.py — Evidence endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.evidence import handle_evidence, _generate_evidence


class TestEvidence:
    """Test evidence endpoint."""

    def test_unknown_resource(self):
        """Unknown evidence resource returns 404."""
        result, code = handle_evidence("GET", "unknown", {}, {})
        assert code == 404

    @patch("yuleosh.api.evidence.subprocess.run")
    @patch("yuleosh.api.evidence.os.environ.get")
    def test_generate_evidence_ok(self, mock_env, mock_subproc):
        """POST /evidence/generate runs pack."""
        mock_env.return_value = "/tmp"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "generated"
        mock_result.stderr = ""
        mock_subproc.return_value = mock_result

        result, code = handle_evidence("POST", "generate", {}, {})
        assert code == 200
        assert result["data"]["status"] == "completed"

    @patch("yuleosh.api.evidence.subprocess.run")
    @patch("yuleosh.api.evidence.os.environ.get")
    def test_generate_evidence_timeout(self, mock_env, mock_subproc):
        """Timeout returns 504."""
        mock_env.return_value = "/tmp"
        mock_subproc.side_effect = __import__("subprocess").TimeoutExpired("cmd", 120)
        result, code = handle_evidence("POST", "generate", {}, {})
        assert code == 504

    @patch("yuleosh.api.evidence.subprocess.run")
    @patch("yuleosh.api.evidence.os.environ.get")
    def test_generate_evidence_error(self, mock_env, mock_subproc):
        """OSError returns 500."""
        mock_env.return_value = "/tmp"
        mock_subproc.side_effect = OSError("No such file")
        result, code = handle_evidence("POST", "generate", {}, {})
        assert code == 500

    def test_list_evidence_files_empty(self, tmp_path):
        """GET /evidence/files handles missing evidence dir."""
        # The real project may have .osh/evidence/ so patch OSH_HOME to tmp_path
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence("GET", "files", {}, {})
            assert code == 200
            assert result["data"]["count"] == 0

    def test_download_pack_not_found(self, tmp_path):
        """GET /evidence/pack when pack doesn't exist."""
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence("GET", "pack", {}, {}, handler=None)
            assert code == 404

    @patch("yuleosh.api.evidence.subprocess.run")
    def test_generate_direct(self, mock_subproc):
        """Direct call to _generate_evidence."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "done"
        mock_result.stderr = ""
        mock_subproc.return_value = mock_result
        result, code = _generate_evidence({"project_dir": "/tmp/proj"})
        assert result["data"]["status"] == "completed"
