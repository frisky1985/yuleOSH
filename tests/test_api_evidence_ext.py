"""Tests for api/evidence.py — Evidence endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.evidence import handle_evidence, _generate_evidence


class TestEvidence:
    """Test evidence endpoint."""

    def test_unknown_resource(self):
        """Unknown evidence resource returns 404."""
        result, code = handle_evidence("GET", "unknown", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 404

    @patch("yuleosh.api.evidence.subprocess.run")
    @patch("yuleosh.api.evidence.os.environ.get")
    def test_generate_evidence_ok(self, mock_env, mock_subproc, tmp_path):
        """POST /evidence/generate runs pack."""
        mock_env.return_value = str(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "generated"
        mock_result.stderr = ""
        mock_subproc.return_value = mock_result

        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence("POST", "generate", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 200
        assert result["data"]["status"] == "completed"

    @patch("yuleosh.api.evidence.subprocess.run")
    @patch("yuleosh.api.evidence.os.environ.get")
    def test_generate_evidence_timeout(self, mock_env, mock_subproc, tmp_path):
        """Timeout returns 504."""
        mock_env.return_value = str(tmp_path)
        mock_subproc.side_effect = __import__("subprocess").TimeoutExpired("cmd", 120)
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence("POST", "generate", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 504

    @patch("yuleosh.api.evidence.subprocess.run")
    @patch("yuleosh.api.evidence.os.environ.get")
    def test_generate_evidence_error(self, mock_env, mock_subproc, tmp_path):
        """OSError returns 500 (masked, no internal details)."""
        mock_env.return_value = str(tmp_path)
        mock_subproc.side_effect = OSError("No such file")
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence("POST", "generate", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 500
        assert "No such file" not in result.get("error", "")
        assert result["error"] == "Internal server error"

    def test_generate_evidence_rejects_outside_osh_home(self, tmp_path):
        """SEC-C1: project_dir outside OSH_HOME → 403."""
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence("POST", "generate",
                                           {"project_dir": "/etc"}, {},
                                           current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 403
        assert "inside OSH_HOME" in result["error"]

    def test_list_evidence_files_empty(self, tmp_path):
        """GET /evidence/files handles missing evidence dir."""
        # The real project may have .osh/evidence/ so patch OSH_HOME to tmp_path
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence("GET", "files", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
            assert code == 200
            assert result["data"]["count"] == 0

    def test_download_pack_not_found(self, tmp_path):
        """GET /evidence/pack when pack doesn't exist."""
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence("GET", "pack", {}, {}, handler=None,
                   current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
            assert code == 404

    @patch("yuleosh.api.evidence.subprocess.run")
    def test_generate_direct(self, mock_subproc, tmp_path):
        """Direct call to _generate_evidence."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "done"
        mock_result.stderr = ""
        mock_subproc.return_value = mock_result
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = _generate_evidence({"project_dir": str(tmp_path)})
        assert result["data"]["status"] == "completed"
