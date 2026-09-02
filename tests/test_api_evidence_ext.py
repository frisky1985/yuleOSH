"""Tests for api/evidence.py — Evidence endpoints."""

# @tests src/yuleosh/api/evidence.py

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


_USER = {"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"}


def _auth_patch():
    """Bypass real JWT verification for the HTTP-handler path."""
    return patch("yuleosh.api.middleware.verify_token", return_value=dict(_USER))


def _fake_handler():
    """Minimal stand-in for the HTTP handler (records what was written).

    Carries a Bearer token so the request clears ``require_auth``; a real
    browser download via <a href> relies on the cookie fallback instead,
    which middleware._extract_token also accepts (T1 v3.9.0).
    """
    h = MagicMock()
    h.headers = MagicMock()
    h.headers.get.side_effect = lambda k, d=None: (
        "Bearer test-token" if k == "Authorization" else (d or "")
    )
    h.sent_headers = {}

    def _send_header(k, v):
        h.sent_headers[k] = v

    h.send_header.side_effect = _send_header
    h.written = b""

    def _write(b):
        h.written += b

    h.wfile.write.side_effect = _write
    return h


class TestEvidenceFileDownload:
    """GET /api/v1/evidence/file?name=<bare> — single-file download."""

    def _ev_dir(self, tmp_path):
        d = tmp_path / ".osh" / "evidence"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_download_markdown_file(self, tmp_path):
        """A listed evidence file is streamed with markdown content type."""
        ev = self._ev_dir(tmp_path)
        (ev / "traceability-matrix.md").write_text("# matrix\n", encoding="utf-8")
        h = _fake_handler()
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)), _auth_patch():
            out = handle_evidence(
                "GET", "file", {}, {"name": "traceability-matrix.md"},
                handler=h, current_user=_USER,
            )
        assert out is None  # response already sent
        h.send_response.assert_called_once_with(200)
        assert h.sent_headers["Content-Type"] == "text/markdown; charset=utf-8"
        assert h.sent_headers["Content-Disposition"] == (
            'attachment; filename="traceability-matrix.md"'
        )
        assert h.sent_headers["Content-Length"] == str(len("# matrix\n".encode()))
        assert h.written == b"# matrix\n"

    def test_download_json_and_unknown_type(self, tmp_path):
        """.json → application/json; unknown extension → octet-stream."""
        ev = self._ev_dir(tmp_path)
        (ev / "review-log.json").write_text("{}", encoding="utf-8")
        (ev / "blob.bin").write_bytes(b"\x00\x01")
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)), _auth_patch():
            h = _fake_handler()
            handle_evidence("GET", "file", {}, {"name": "review-log.json"},
                            handler=h, current_user=_USER)
            assert h.sent_headers["Content-Type"] == "application/json; charset=utf-8"

            h2 = _fake_handler()
            handle_evidence("GET", "file", {}, {"name": "blob.bin"},
                            handler=h2, current_user=_USER)
            assert h2.sent_headers["Content-Type"] == "application/octet-stream"

    def test_no_handler_returns_metadata(self, tmp_path):
        """Without a handler we return JSON metadata (used by tests/clients)."""
        ev = self._ev_dir(tmp_path)
        (ev / "aspice.md").write_text("x", encoding="utf-8")
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence(
                "GET", "file", {}, {"name": "aspice.md"},
                handler=None, current_user=_USER,
            )
        assert code == 200
        assert result["data"]["name"] == "aspice.md"
        assert result["data"]["content_type"] == "text/markdown; charset=utf-8"
        assert result["data"]["size"] == 1

    @pytest.mark.parametrize("bad", [
        "../secret.txt", "..", ".", "sub/file.md", "..\\secret.txt",
        ".hidden", "file\nname.md", 'file"name.md', "", "   ",
    ])
    def test_rejects_traversal_and_bad_names(self, bad, tmp_path):
        """Path traversal / dot-segments / quote-injection names → 400."""
        self._ev_dir(tmp_path)
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence(
                "GET", "file", {}, {"name": bad},
                handler=None, current_user=_USER,
            )
        assert code == 400, f"expected 400 for {bad!r}"
        assert "Invalid file name" in result["error"]

    def test_missing_file_returns_404(self, tmp_path):
        """Well-formed but non-existent name → 404 (not 400, not 500)."""
        self._ev_dir(tmp_path)
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence(
                "GET", "file", {}, {"name": "nope.md"},
                handler=None, current_user=_USER,
            )
        assert code == 404
        assert "not found" in result["error"].lower()

    def test_rejects_symlink_escape(self, tmp_path):
        """A symlink inside evidence/ pointing outside is refused."""
        ev = self._ev_dir(tmp_path)
        outside = tmp_path / "outside-secret.txt"
        outside.write_text("top secret", encoding="utf-8")
        try:
            (ev / "escape.md").symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unsupported on this platform")
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence(
                "GET", "file", {}, {"name": "escape.md"},
                handler=None, current_user=_USER,
            )
        assert code == 400
        assert "Invalid file name" in result["error"]

    def test_directory_name_rejected(self, tmp_path):
        """A sub-directory name resolves but is not a file → 404."""
        ev = self._ev_dir(tmp_path)
        (ev / "subdir").mkdir()
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, code = handle_evidence(
                "GET", "file", {}, {"name": "subdir"},
                handler=None, current_user=_USER,
            )
        assert code == 404
