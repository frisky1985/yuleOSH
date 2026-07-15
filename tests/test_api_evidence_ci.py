#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for api/evidence.py and api/ci.py — evidence and CI endpoints.

Target: 90%+ statement + branch coverage.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.api.evidence import (
    handle_evidence,
    _generate_evidence,
    _list_evidence_files,
    _download_pack,
)
from yuleosh.api.ci import (
    handle_ci,
    _run_ci_layer,
    _list_ci_runs,
)


# ==================================================================
# api/evidence.py
# ==================================================================


class TestHandleEvidence:
    @mock.patch("yuleosh.api.evidence._generate_evidence")
    def test_generate_route(self, mock_gen):
        mock_gen.return_value = ({"status": "ok"}, 200)
        result = handle_evidence("POST", "generate", {}, {})
        assert result == ({"status": "ok"}, 200)
        mock_gen.assert_called_once()

    @mock.patch("yuleosh.api.evidence._list_evidence_files")
    def test_files_route(self, mock_list):
        mock_list.return_value = ({"files": []}, 200)
        result = handle_evidence("GET", "files", {}, {})
        assert result[1] == 200
        mock_list.assert_called_once()

    @mock.patch("yuleosh.api.evidence._download_pack")
    def test_pack_route(self, mock_dl):
        mock_dl.return_value = ({"path": "/tmp/zip"}, 200)
        result = handle_evidence("GET", "pack", {}, {}, handler=None)
        assert result[1] == 200
        mock_dl.assert_called_once()

    def test_unknown_route(self):
        result = handle_evidence("GET", "unknown", {}, {})
        assert result[1] == 404
        assert "error" in result[0]

    def test_generate_non_post(self):
        result = handle_evidence("GET", "generate", {}, {})
        assert result[1] == 404


class TestGenerateEvidence:
    @mock.patch("yuleosh.api.evidence.subprocess.run")
    def test_success(self, mock_run):
        proc = mock.Mock()
        proc.returncode = 0
        proc.stdout = "Evidence generated successfully"
        proc.stderr = ""
        mock_run.return_value = proc

        result = _generate_evidence({"project_dir": "/tmp/test"})
        assert result[1] == 200
        assert result[0]["data"]["status"] == "completed"
        assert "Evidence" in result[0]["data"]["stdout"]

    @mock.patch("yuleosh.api.evidence.subprocess.run")
    def test_subprocess_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 120)
        result = _generate_evidence({"project_dir": "/tmp/test"})
        assert result[1] == 504
        assert "timed out" in result[0]["error"]

    @mock.patch("yuleosh.api.evidence.subprocess.run")
    def test_os_error(self, mock_run):
        mock_run.side_effect = OSError("Permission denied")
        result = _generate_evidence({"project_dir": "/tmp/test"})
        assert result[1] == 500

    @mock.patch("yuleosh.api.evidence.os.environ.get")
    @mock.patch("yuleosh.api.evidence.subprocess.run")
    def test_default_project_dir(self, mock_run, mock_env_get):
        proc = mock.Mock()
        proc.returncode = 0
        proc.stdout = "ok"
        proc.stderr = ""
        mock_run.return_value = proc
        mock_env_get.return_value = None  # OSH_HOME not set

        result = _generate_evidence({})
        assert result[1] == 200
        # Should use the default path
        mock_run.assert_called_once()
        assert "src/evidence/pack.py" in str(mock_run.call_args[0])


class TestListEvidenceFiles:
    def test_no_evidence_dir(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)
            result = _list_evidence_files()
        assert result[1] == 200
        assert result[0]["data"]["files"] == []
        assert result[0]["data"]["count"] == 0

    def test_with_files(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            osh_dir = Path(tmpdir) / ".osh" / "evidence"
            osh_dir.mkdir(parents=True)
            (osh_dir / "report.json").write_text("{}")
            (osh_dir / "trace.xml").write_text("<data/>")
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)

            result = _list_evidence_files()
        assert result[1] == 200
        assert result[0]["data"]["count"] == 2
        names = [f["name"] for f in result[0]["data"]["files"]]
        assert "report.json" in names
        assert "trace.xml" in names

    def test_skips_dirs(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            osh_dir = Path(tmpdir) / ".osh" / "evidence"
            osh_dir.mkdir(parents=True)
            (osh_dir / "report.json").write_text("{}")
            (osh_dir / "subdir").mkdir()
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)

            result = _list_evidence_files()
        assert result[0]["data"]["count"] == 1
        assert "report.json" in [f["name"] for f in result[0]["data"]["files"]]


class TestDownloadPack:
    def test_pack_not_found(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)
            result = _download_pack(handler=None)
        assert result[1] == 404
        assert "not found" in result[0]["error"]

    def test_pack_exists_return_json(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            osh_dir = Path(tmpdir) / ".osh" / "evidence"
            osh_dir.mkdir(parents=True)
            zip_content = b"fake zip content"
            (osh_dir / "compliance-pack.zip").write_bytes(zip_content)
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)

            result = _download_pack(handler=None)
        assert result[1] == 200
        assert result[0]["data"]["status"] == "ready"
        assert result[0]["data"]["size"] == len(zip_content)

    def test_pack_exists_with_handler(self, monkeypatch):
        """Sends ZIP via handler.send_response."""
        with tempfile.TemporaryDirectory() as tmpdir:
            osh_dir = Path(tmpdir) / ".osh" / "evidence"
            osh_dir.mkdir(parents=True)
            zip_content = b"fake zip content"
            (osh_dir / "compliance-pack.zip").write_bytes(zip_content)
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)

            mock_handler = mock.Mock()
            result = _download_pack(handler=mock_handler)
        assert result is None
        mock_handler.send_response.assert_called_once_with(200)
        mock_handler.send_header.assert_any_call("Content-Type", "application/zip")
        mock_handler.send_header.assert_any_call("Content-Disposition",
                                                   'attachment; filename="compliance-pack.zip"')
        mock_handler.end_headers.assert_called_once()
        mock_handler.wfile.write.assert_called_once_with(zip_content)


# ==================================================================
# api/ci.py
# ==================================================================


class TestHandleCi:
    @mock.patch("yuleosh.api.ci._list_ci_runs")
    def test_list_runs(self, mock_list):
        mock_list.return_value = ({"results": []}, 200)
        result = handle_ci("GET", "runs", {}, {})
        assert result[1] == 200

    @mock.patch("yuleosh.api.ci._run_ci_layer")
    def test_run_layer(self, mock_run):
        mock_run.return_value = ({"layer": 1, "status": "passed"}, 200)
        result = handle_ci("POST", "run/1", {}, {})
        assert result[1] == 200
        mock_run.assert_called_with("1")

    def test_run_layer_wrong_method(self):
        result = handle_ci("GET", "run/1", {}, {})
        assert result[1] == 405

    def test_unknown_resource(self):
        result = handle_ci("GET", "unknown", {}, {})
        assert result[1] == 404


class TestRunCiLayer:
    @mock.patch("yuleosh.api.ci.subprocess.run")
    def test_layer_1_success(self, mock_run):
        proc = mock.Mock()
        proc.returncode = 0
        proc.stdout = "layer 1 passed"
        proc.stderr = ""
        mock_run.return_value = proc

        result = _run_ci_layer("1")
        assert result[1] == 200
        assert result[0]["data"]["layer"] == 1
        assert result[0]["data"]["status"] == "passed"

    @mock.patch("yuleosh.api.ci.subprocess.run")
    def test_layer_2_failure(self, mock_run):
        proc = mock.Mock()
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "error: failed"
        mock_run.return_value = proc

        result = _run_ci_layer("2")
        assert result[0]["data"]["status"] == "failed"
        assert result[0]["data"]["exit_code"] == 1

    def test_invalid_layer(self):
        result = _run_ci_layer("4")
        assert result[1] == 400
        assert "Invalid CI layer" in result[0]["error"]

    @mock.patch("yuleosh.api.ci.subprocess.run",
                side_effect=subprocess.TimeoutExpired("cmd", 180))
    def test_timeout(self, mock_run):
        result = _run_ci_layer("1")
        assert result[1] == 504
        assert "timed out" in result[0]["error"]

    @mock.patch("yuleosh.api.ci.subprocess.run",
                side_effect=Exception("generic error"))
    def test_generic_exception(self, mock_run):
        result = _run_ci_layer("1")
        assert result[1] == 500
        assert "generic error" in result[0]["error"]


class TestListCiRuns:
    def test_no_ci_dir(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)
            result = _list_ci_runs()
        assert result[1] == 200
        assert result[0]["data"]["count"] == 0
        assert result[0]["data"]["results"] == []

    def test_with_layer_results(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            ci_dir = Path(tmpdir) / ".osh" / "ci"
            ci_dir.mkdir(parents=True)
            (ci_dir / "layer1.json").write_text(
                json.dumps({"layer": 1, "status": "passed"})
            )
            (ci_dir / "layer2.json").write_text(
                json.dumps({"layer": 2, "status": "failed"})
            )
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)

            result = _list_ci_runs()
        assert result[1] == 200
        assert result[0]["data"]["count"] == 2
        # Results sorted in reverse
        statuses = [r["status"] for r in result[0]["data"]["results"]]
        assert "passed" in statuses
        assert "failed" in statuses

    def test_ignores_non_json_files(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            ci_dir = Path(tmpdir) / ".osh" / "ci"
            ci_dir.mkdir(parents=True)
            (ci_dir / "layer1.json").write_text(
                json.dumps({"layer": 1, "status": "passed"})
            )
            (ci_dir / "notes.txt").write_text("hello")
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)

            result = _list_ci_runs()
        assert result[0]["data"]["count"] == 1

    def test_glob_json_files_only(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            ci_dir = Path(tmpdir) / ".osh" / "ci"
            ci_dir.mkdir(parents=True)
            (ci_dir / "layer1.json").write_text(
                json.dumps({"layer": 1, "status": "passed"})
            )
            (ci_dir / "layer2.json").write_text(
                json.dumps({"layer": 2, "status": "failed"})
            )
            (ci_dir / "notes.txt").write_text("not json")
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)

            result = _list_ci_runs()
        assert result[0]["data"]["count"] == 2
