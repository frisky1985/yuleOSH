# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for yuleosh.api.desktop — project management + pipeline + sync.

Tests the HTTP handler functions directly (no server). The workspace is
pointed at a temp dir via YULEOSH_DESKTOP_HOME.
"""

import json
import os
import shutil
from unittest.mock import patch

import pytest


@pytest.fixture
def desktop_api(tmp_path, monkeypatch):
    """Set up an isolated workspace and import the desktop API module."""
    monkeypatch.setenv("YULEOSH_DESKTOP_HOME", str(tmp_path / "ws"))
    import importlib
    from yuleosh.desktop import workspace
    importlib.reload(workspace)
    from yuleosh.api import desktop
    importlib.reload(desktop)
    yield desktop


def _body(data):
    return data


# ── Projects ──────────────────────────────────────────────────────────────

class TestProjects:
    def test_create_and_list(self, desktop_api):
        d = desktop_api
        resp, status = d.handle_desktop("POST", "projects", _body({"name": "P1"}), {})
        assert status == 201
        assert resp["ok"] is True
        pid = resp["project"]["id"]

        resp, status = d.handle_desktop("GET", "projects", None, {})
        assert status == 200
        assert any(p["id"] == pid for p in resp["projects"])

    def test_create_no_name_400(self, desktop_api):
        resp, status = desktop_api.handle_desktop("POST", "projects", _body({"name": ""}), {})
        assert status == 400

    def test_get_project(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        resp, status = d.handle_desktop("GET", f"projects/{pid}", None, {})
        assert status == 200
        assert resp["project"]["name"] == "P"

    def test_get_missing_404(self, desktop_api):
        resp, status = desktop_api.handle_desktop("GET", "projects/nope", None, {})
        assert status == 404

    def test_delete_project(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        resp, status = d.handle_desktop("DELETE", f"projects/{pid}", None, {})
        assert status == 200
        assert resp["ok"] is True
        # Should be gone.
        _, status = d.handle_desktop("GET", f"projects/{pid}", None, {})
        assert status == 404


# ── Requirements ──────────────────────────────────────────────────────────

class TestRequirements:
    def test_import_and_get(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        content = "# Reqs\n- REQ-001"
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/requirements",
            _body({"content": content, "source": "cli"}), {},
        )
        assert status == 201
        assert resp["manifest"]["source"] == "cli"

        resp, status = d.handle_desktop("GET", f"projects/{pid}/requirements", None, {})
        assert status == 200
        assert resp["content"] == content

    def test_import_empty_400(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/requirements", _body({"content": ""}), {},
        )
        assert status == 400


# ── Pipeline run ──────────────────────────────────────────────────────────

class TestPipeline:
    def test_run_creates_artifacts(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        d.handle_desktop(
            "POST", f"projects/{pid}/requirements",
            _body({"content": "# R"}), {},
        )
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/pipeline/run", _body({"type": "full"}), {},
        )
        assert status == 202
        assert resp["job_id"]

        # Artifact tree should contain code/src/main.c etc.
        tree_resp, _ = d.handle_desktop("GET", f"projects/{pid}/artifacts", None, {})
        tree = tree_resp["tree"]
        all_paths = []
        def walk(n):
            all_paths.append(n["path"])
            for c in n.get("children", []):
                walk(c)
        walk(tree)
        assert "code/src/main.c" in all_paths
        assert "tests/test_main.c" in all_paths
        assert "design/sdd.md" in all_paths

    def test_list_runs(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        d.handle_desktop("POST", f"projects/{pid}/pipeline/run", _body({"type": "full"}), {})
        resp, status = d.handle_desktop("GET", f"projects/{pid}/pipeline/runs", None, {})
        assert status == 200
        assert len(resp["runs"]) >= 1


# ── Artifacts ─────────────────────────────────────────────────────────────

class TestArtifacts:
    def test_read_artifact(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        d.handle_desktop("POST", f"projects/{pid}/pipeline/run", _body({"type": "full"}), {})
        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/artifacts/code/src/main.c", None, {},
        )
        assert status == 200
        assert resp["binary"] is False
        assert "main" in resp["content"]

    def test_read_missing_artifact_404(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        resp, status = d.handle_desktop("GET", f"projects/{pid}/artifacts/nope.c", None, {})
        assert status == 404


# ── Cloud sync ────────────────────────────────────────────────────────────

class TestSync:
    def test_sync_no_cloud_url_pending(self, desktop_api, monkeypatch):
        monkeypatch.delenv("YULEOSH_CLOUD_URL", raising=False)
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        resp, status = d.handle_desktop("POST", f"projects/{pid}/sync", _body({}), {})
        assert status == 202
        assert resp["pending"] is True
        assert resp["synced"] is False

    def test_sync_with_cloud_url(self, desktop_api, monkeypatch):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        d.handle_desktop("POST", f"projects/{pid}/pipeline/run", _body({"type": "full"}), {})
        monkeypatch.setenv("YULEOSH_CLOUD_URL", "http://localhost:9999")

        # Mock the HTTP upload to succeed.
        class FakeResp:
            def read(self):
                return b'{"ok":true}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            resp, status = d.handle_desktop("POST", f"projects/{pid}/sync", _body({}), {})
        assert status == 200
        assert resp["synced"] is True
