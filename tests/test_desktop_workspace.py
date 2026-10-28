# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for yuleosh.desktop.workspace — local project + artifact folders.

These tests exercise the filesystem workspace manager directly with an
isolated temp directory (YULEOSH_DESKTOP_HOME). No backend or network
required.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def workspace_home(tmp_path, monkeypatch):
    """Point the desktop workspace at an isolated temp dir."""
    home = tmp_path / "yuleosh-workspace"
    monkeypatch.setenv("YULEOSH_DESKTOP_HOME", str(home))
    # Force re-import so workspace_root() picks up the env var.
    import importlib
    from yuleosh.desktop import workspace
    importlib.reload(workspace)
    yield workspace
    shutil.rmtree(home, ignore_errors=True)


# ── Project CRUD ──────────────────────────────────────────────────────────

class TestProjectCrud:
    def test_create_project_creates_artifact_dirs(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("车灯控制器", "描述")
        assert meta["id"]
        assert meta["name"] == "车灯控制器"
        proj_dir = ws._project_dir(meta["id"])
        for sub in ws.ARTIFACT_DIRS:
            assert (proj_dir / sub).is_dir()
        assert (proj_dir / "pipeline" / "runs").is_dir()
        assert (proj_dir / "project.json").is_file()

    def test_create_project_empty_name_raises(self, workspace_home):
        with pytest.raises(ValueError):
            workspace_home.create_project("   ")

    def test_list_projects_sorted_by_updated_desc(self, workspace_home):
        ws = workspace_home
        ws.create_project("A")
        ws.create_project("B")
        ws.create_project("C")
        projects = ws.list_projects()
        assert [p["name"] for p in projects] == ["C", "B", "A"]

    def test_get_project_includes_artifact_summary(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        proj = ws.get_project(meta["id"])
        assert "artifacts" in proj
        for sub in ws.ARTIFACT_DIRS:
            assert sub in proj["artifacts"]
            assert proj["artifacts"][sub]["exists"] is True

    def test_get_project_missing_raises(self, workspace_home):
        with pytest.raises(FileNotFoundError):
            workspace_home.get_project("nope")

    def test_delete_project(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("to-delete")
        ws.delete_project(meta["id"])
        assert not ws._project_dir(meta["id"]).exists()
        assert ws.list_projects() == []

    def test_delete_missing_raises(self, workspace_home):
        with pytest.raises(FileNotFoundError):
            workspace_home.delete_project("nope")


# ── Requirements ──────────────────────────────────────────────────────────

class TestRequirements:
    def test_save_and_get_requirements(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        content = "# 需求\n\n- REQ-001: 功能A"
        manifest = ws.save_requirements(meta["id"], content, source="chatbot")
        assert manifest["source"] == "chatbot"
        assert manifest["char_count"] == len(content)

        result = ws.get_requirements(meta["id"])
        assert result["content"] == content
        assert result["manifest"]["source"] == "chatbot"

    def test_get_requirements_empty_project(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        result = ws.get_requirements(meta["id"])
        assert result["content"] == ""
        assert result["manifest"] == {}


# ── Artifact tree & read ──────────────────────────────────────────────────

class TestArtifacts:
    def test_list_artifacts_empty_project(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        tree = ws.list_artifacts(meta["id"])
        # Top-level artifact dirs exist but are empty.
        assert tree["type"] == "dir"
        names = [c["name"] for c in tree["children"]]
        assert names == list(ws.ARTIFACT_DIRS)

    def test_unclassified_dir_listed_only_when_files_exist(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        proj_dir = ws._project_dir(meta["id"])

        # 只有空目录时不出现
        (proj_dir / ws.UNCLASSIFIED_DIR).mkdir()
        names = [c["name"] for c in ws.list_artifacts(meta["id"])["children"]]
        assert ws.UNCLASSIFIED_DIR not in names

        # 有文件时追加到树末尾
        (proj_dir / ws.UNCLASSIFIED_DIR / "pin_map.xml").write_text("<pinmap/>")
        tree = ws.list_artifacts(meta["id"])
        assert tree["children"][-1]["name"] == ws.UNCLASSIFIED_DIR
        assert tree["children"][-1]["children"][0]["path"] == "_unclassified/pin_map.xml"
        # 且不能混进正式五分区
        assert ws.UNCLASSIFIED_DIR not in ws.ARTIFACT_DIRS

    def test_read_artifact_text_file(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        proj_dir = ws._project_dir(meta["id"])
        (proj_dir / "code" / "src").mkdir(parents=True)
        (proj_dir / "code" / "src" / "main.c").write_text("int main() { return 0; }")
        result = ws.read_artifact(meta["id"], "code/src/main.c")
        assert result["binary"] is False
        assert "int main" in result["content"]

    def test_read_artifact_not_found(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        with pytest.raises(FileNotFoundError):
            ws.read_artifact(meta["id"], "nope.c")

    def test_read_artifact_path_traversal_blocked(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        with pytest.raises(PermissionError):
            ws.read_artifact(meta["id"], "../../../etc/passwd")

    def test_collect_artifact_files(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        proj_dir = ws._project_dir(meta["id"])
        (proj_dir / "code" / "src").mkdir(parents=True)
        (proj_dir / "code" / "src" / "main.c").write_text("int main(){return 0;}")
        (proj_dir / "tests").mkdir(parents=True, exist_ok=True)
        (proj_dir / "tests" / "test_main.c").write_text("void test(){}")
        files = ws.collect_artifact_files(meta["id"])
        paths = [f["path"] for f in files]
        assert "code/src/main.c" in paths
        assert "tests/test_main.c" in paths
        # All text files include content.
        for f in files:
            if not f["binary"]:
                assert "content" in f


# ── Pipeline run records ──────────────────────────────────────────────────

class TestPipelineRuns:
    def test_record_and_list_runs(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        job_id = "job-001"
        ws.record_pipeline_run(meta["id"], job_id, {"type": "full"})
        ws.save_pipeline_result(meta["id"], job_id, {"status": "passed"}, "logs here")

        runs = ws.list_pipeline_runs(meta["id"])
        assert len(runs) == 1
        assert runs[0]["job_id"] == job_id
        assert runs[0]["status"] == "passed"

        run_dir = ws._project_dir(meta["id"]) / "pipeline" / "runs" / job_id
        assert (run_dir / "result.json").is_file()
        assert (run_dir / "logs.txt").is_file()

    def test_list_runs_empty(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        assert ws.list_pipeline_runs(meta["id"]) == []

    def test_record_pipeline_increments_counter(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        ws.record_pipeline_run(meta["id"], "j1")
        ws.record_pipeline_run(meta["id"], "j2")
        updated = ws.get_project(meta["id"])
        assert updated["pipeline_runs"] == 2


# ── Cloud sync marker ─────────────────────────────────────────────────────

class TestSync:
    def test_mark_synced(self, workspace_home):
        ws = workspace_home
        meta = ws.create_project("P")
        ws.mark_synced(meta["id"], remote_url="https://cloud.example.com")
        updated = ws.get_project(meta["id"])
        assert updated["cloud_synced"] is True
        assert updated["cloud_url"] == "https://cloud.example.com"
        assert updated["last_synced_at"] is not None
