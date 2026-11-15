# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for yuleosh.api.desktop — project management + pipeline + sync.

Tests the HTTP handler functions directly (no server). The workspace is
pointed at a temp dir via YULEOSH_DESKTOP_HOME.
"""

import json
import os
import shutil
from pathlib import Path
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

    def test_rename_project(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "Old"}), {})[0]["project"]["id"]

        resp, status = d.handle_desktop(
            "PATCH", f"projects/{pid}", _body({"name": "  New  ", "description": "d"}), {})
        assert status == 200
        assert resp["project"]["name"] == "New"
        assert resp["project"]["description"] == "d"

        resp, _ = d.handle_desktop("GET", f"projects/{pid}", None, {})
        assert resp["project"]["name"] == "New"

    def test_rename_blank_name_400(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        _, status = d.handle_desktop("PATCH", f"projects/{pid}", _body({"name": "   "}), {})
        assert status == 400

    def test_rename_missing_404(self, desktop_api):
        _, status = desktop_api.handle_desktop(
            "PATCH", "projects/nope", _body({"name": "X"}), {})
        assert status == 404

    def test_rename_no_fields_400(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        _, status = d.handle_desktop("PATCH", f"projects/{pid}", _body({}), {})
        assert status == 400


# ── Project templates (new-project wizard) ────────────────────────────────

class TestProjectTemplates:
    def test_list_project_templates(self, desktop_api):
        resp, status = desktop_api.handle_desktop("GET", "project-templates", None, {})
        assert status == 200
        ids = {t["id"] for t in resp["templates"]}
        assert {"blank", "aspice-lite", "automotive", "web-app"} <= ids
        blank = next(t for t in resp["templates"] if t["id"] == "blank")
        assert blank["doc_templates"] == []
        assert blank["has_requirements_seed"] is False
        # The wizard only needs metadata — seed bodies must not leak.
        assert "requirements_seed" not in blank

    def test_create_with_template_seeds_docs_and_requirements(
            self, desktop_api, tmp_path, monkeypatch):
        monkeypatch.setenv("YULEOSH_DESKTOP_HOME", str(tmp_path / "ws"))
        d = desktop_api
        resp, status = d.handle_desktop(
            "POST", "projects", _body({"name": "Auto", "template": "aspice-lite"}), {})
        assert status == 201
        pid = resp["project"]["id"]
        applied = resp["template"]
        assert applied["template"] == "aspice-lite"
        assert applied["requirements_saved"] is True
        assert sorted(applied["created_docs"]) == [
            "docs/project-plan.md", "docs/qa-plan.md", "docs/risk-register.md",
        ]
        for rel in applied["created_docs"]:
            assert (Path(tmp_path) / "ws" / pid / rel).is_file()

        req, status = d.handle_desktop("GET", f"projects/{pid}/requirements", None, {})
        assert status == 200
        assert "SYS-001" in req["content"]

    def test_create_with_blank_template(self, desktop_api):
        d = desktop_api
        resp, status = d.handle_desktop(
            "POST", "projects", _body({"name": "Empty", "template": "blank"}), {})
        assert status == 201
        assert resp["template"]["created_docs"] == []
        assert resp["template"]["requirements_saved"] is False

    def test_create_with_unknown_template_400(self, desktop_api):
        d = desktop_api
        resp, status = d.handle_desktop(
            "POST", "projects", _body({"name": "Bad", "template": "nope"}), {})
        assert status == 400
        assert "template" in resp["error"].lower()
        # A rejected preset must not leave an orphan project behind.
        listing, _ = d.handle_desktop("GET", "projects", None, {})
        assert listing["projects"] == []


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

        # Artifact tree should preserve the AUTOSAR Classic layer directories.
        tree_resp, _ = d.handle_desktop("GET", f"projects/{pid}/artifacts", None, {})
        tree = tree_resp["tree"]
        all_paths = []
        def walk(n):
            all_paths.append(n["path"])
            for c in n.get("children", []):
                walk(c)
        walk(tree)
        assert "code/src/application/HeadlightSwc.c" in all_paths
        assert "code/src/rte/Rte.c" in all_paths
        assert "code/src/bsw/ecu_abstraction/IoHwAb.c" in all_paths
        assert "code/src/bsw/mcal/Adc.c" in all_paths
        assert "tests/test_headlight_swc.c" in all_paths
        assert "design/sdd.md" in all_paths

    def test_list_runs(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        d.handle_desktop("POST", f"projects/{pid}/pipeline/run", _body({"type": "full"}), {})
        resp, status = d.handle_desktop("GET", f"projects/{pid}/pipeline/runs", None, {})
        assert status == 200
        assert len(resp["runs"]) >= 1

    def test_status_disk_fallback_includes_logs(self, desktop_api):
        """重启后从 result.json 读取运行详情时，日志与失败原因不能丢。"""
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        run_dir = d.workspace._project_dir(pid) / "pipeline" / "runs" / "job-disk-logs"
        run_dir.mkdir(parents=True)
        (run_dir / "result.json").write_text(
            json.dumps({
                "status": "failed",
                "started_at": "2026-11-15T10:00:00",
                "completed_at": "2026-11-15T10:01:00",
                "current_stage": "ci_compile",
                "stages": [{"key": "ci_compile", "name": "编译", "status": "failed"}],
                "logs": ["step a", "step b"],
                "result": {"error": "boom"},
            }),
            encoding="utf-8",
        )

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/pipeline/status/job-disk-logs", None, {},
        )

        assert status == 200
        assert resp["source"] == "disk"
        assert resp["logs"] == ["step a", "step b"]
        assert resp["logs_total"] == 2
        assert resp["result"]["error"] == "boom"
        assert resp["stages"][0]["status"] == "failed"

    def test_status_disk_logs_capped_at_500(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        run_dir = d.workspace._project_dir(pid) / "pipeline" / "runs" / "job-disk-many"
        run_dir.mkdir(parents=True)
        logs = [f"line {i}" for i in range(600)]
        (run_dir / "result.json").write_text(
            json.dumps({"status": "passed", "logs": logs}), encoding="utf-8",
        )

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/pipeline/status/job-disk-many", None, {},
        )

        assert status == 200
        assert len(resp["logs"]) == 500
        assert resp["logs"][0] == "line 100"
        assert resp["logs_total"] == 600

    def test_status_memory_reports_total_logs(self, desktop_api):
        """内存中的运行也要给出日志总数，便于详情页显示进度。"""
        from yuleosh.pipeline import async_runner

        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        job_id = "job-mem-many"
        async_runner._PIPELINE_JOBS[job_id] = {
            "job_id": job_id,
            "status": "running",
            "progress": 40,
            "stages": [{"key": "arxml_parse", "name": "解析", "status": "passed"}],
            "logs": [f"l{i}" for i in range(520)],
            "started_at": "2026-11-15T10:00:00",
            "completed_at": None,
            "result": None,
        }
        try:
            resp, status = d.handle_desktop(
                "GET", f"projects/{pid}/pipeline/status/{job_id}", None, {},
            )
        finally:
            async_runner._PIPELINE_JOBS.pop(job_id, None)

        assert status == 200
        assert len(resp["logs"]) == 500
        assert resp["logs_total"] == 520
        assert resp["stages"][0]["status"] == "passed"



# ── Artifacts ─────────────────────────────────────────────────────────────

class TestArtifacts:
    def test_read_artifact(self, desktop_api):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        d.handle_desktop("POST", f"projects/{pid}/pipeline/run", _body({"type": "full"}), {})
        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/artifacts/code/src/application/HeadlightSwc.c", None, {},
        )
        assert status == 200
        assert resp["binary"] is False
        assert "HeadlightSwc_Run" in resp["content"]

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

    def test_sync_status_unconfigured(self, desktop_api, monkeypatch):
        monkeypatch.delenv("YULEOSH_CLOUD_URL", raising=False)
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        resp, status = d.handle_desktop("GET", f"projects/{pid}/sync", None, {})
        assert status == 200
        assert resp["configured"] is False
        assert resp["synced"] is False
        assert resp["pending"] is True
        assert resp["total_files"] == 0

    def test_sync_status_after_sync(self, desktop_api, monkeypatch):
        d = desktop_api
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        d.handle_desktop("POST", f"projects/{pid}/pipeline/run", _body({"type": "full"}), {})
        monkeypatch.setenv("YULEOSH_CLOUD_URL", "http://localhost:9999")

        class FakeResp:
            def read(self):
                return b'{"ok":true}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            d.handle_desktop("POST", f"projects/{pid}/sync", _body({}), {})

        resp, status = d.handle_desktop("GET", f"projects/{pid}/sync", None, {})
        assert status == 200
        assert resp["configured"] is True
        assert resp["synced"] is True
        assert resp["pending"] is False
        assert resp["last_synced_at"]

    def test_sync_status_missing_404(self, desktop_api):
        _, status = desktop_api.handle_desktop("GET", "projects/nope/sync", None, {})
        assert status == 404


# ── Artifact classification ───────────────────────────────────────────────

class TestClassifyArtifact:
    """产物 → 五分区：目录语义 > 文件名语义 > 扩展名 > 待归类。"""

    @pytest.mark.parametrize(
        "rel_path,expected",
        [
            # RTE 生成代码固定进 code/rte
            ("rte/Rte.c", ("code", "code/rte", "rte")),
            ("rte/Rte.h", ("code", "code/rte", "rte")),
            # AUTOSAR Classic 分层目录原样保留
            ("src/application/HeadlightSwc.c", ("code", "code/src/application", "autosar:application")),
            ("src/rte/Rte.c", ("code", "code/src/rte", "autosar:rte")),
            ("src/bsw/services/EcuM.c", ("code", "code/src/bsw/services", "autosar:services")),
            ("src/bsw/ecu_abstraction/IoHwAb.c", ("code", "code/src/bsw/ecu_abstraction", "autosar:ecu-abstraction")),
            ("src/bsw/mcal/Dio.c", ("code", "code/src/bsw/mcal", "autosar:mcal")),
            # 目录语义
            ("design/sdd.md", ("design", "design", "dir:design")),
            ("tests/report_lamp.json", ("tests", "tests", "dir:tests")),
            ("reports/coverage.json", ("evidence", "evidence", "dir:evidence")),
            ("requirements/requirements.md", ("requirements", "requirements", "dir:requirements")),
            # 文件名语义
            ("test_lamp.c", ("tests", "tests", "name:test")),
            ("docs/system-requirements.md", ("requirements", "requirements", "name:requirements")),
            ("docs/sdd.md", ("design", "design", "name:design")),
            ("misra_result.json", ("evidence", "evidence", "name:evidence")),
            # 扩展名
            ("src/main.c", ("code", "code", "suffix:code")),
            ("scripts/build.py", ("code", "code", "suffix:code")),
            # 无法判定 → 不猜，进待归类
            ("misc/board.png", ("_unclassified", "_unclassified", "unclassified")),
            # 流水线内部文件不收集
            ("config.json", None),
            ("config.arxml", None),
        ],
    )
    def test_classify(self, desktop_api, rel_path, expected):
        assert desktop_api.classify_artifact(Path(rel_path)) == expected


class TestCollectRealArtifacts:
    def _make_job(self, tmp_path):
        proj = tmp_path / "proj"
        job = proj / ".yuleosh" / "pipeline" / "job-1"
        files = {
            "rte/Rte.c": "// rte",
            "docs/sdd.md": "# design",
            "docs/system-requirements.md": "# req",
            "tests/test_lamp.c": "// test",
            "reports/coverage.json": "{}",
            "src/main.c": "int main(void){}",
            "src/application/HeadlightSwc.c": "// swc",
            "src/bsw/mcal/Dio.c": "// mcal",
            "misc/board.png": "png",
            "config.json": "{}",
            "config.arxml": "<xml/>",
        }
        for rel, content in files.items():
            p = job / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return proj

    def test_collect_routes_files_to_sections(self, desktop_api, tmp_path):
        proj = self._make_job(tmp_path)
        collected = desktop_api._collect_real_artifacts(str(proj))

        assert sorted(collected) == sorted([
            "code/rte/Rte.c",
            "design/sdd.md",
            "requirements/system-requirements.md",
            "tests/test_lamp.c",
            "evidence/coverage.json",
            "code/main.c",
            "code/src/application/HeadlightSwc.c",
            "code/src/bsw/mcal/Dio.c",
            "_unclassified/board.png",
        ])
        for rel in collected:
            assert (proj / rel).is_file(), rel
        # 内部文件不应被当成产物复制出来
        assert not (proj / "code" / "config.json").exists()
        assert not (proj / "config.json").exists()

    def test_collect_writes_manifest_with_rule_and_section(self, desktop_api, tmp_path):
        proj = self._make_job(tmp_path)
        desktop_api._collect_real_artifacts(str(proj))

        manifest_path = proj / "pipeline" / "runs" / "job-1" / "artifact-manifest.json"
        assert manifest_path.is_file()
        artifacts = json.loads(manifest_path.read_text(encoding="utf-8"))["artifacts"]
        by_path = {a["path"]: a for a in artifacts}

        assert by_path["design/sdd.md"]["section"] == "design"
        assert by_path["design/sdd.md"]["source"] == "docs/sdd.md"
        assert by_path["design/sdd.md"]["rule"] == "name:design"
        assert by_path["tests/test_lamp.c"]["section"] == "tests"
        assert by_path["code/rte/Rte.c"]["rule"] == "rte"
        assert by_path["code/src/application/HeadlightSwc.c"]["rule"] == "autosar:application"
        assert by_path["code/src/bsw/mcal/Dio.c"]["rule"] == "autosar:mcal"
        assert by_path["_unclassified/board.png"]["section"] == "_unclassified"

    def test_collect_is_idempotent_and_keeps_newer_destination(self, desktop_api, tmp_path):
        proj = self._make_job(tmp_path)
        desktop_api._collect_real_artifacts(str(proj))
        # 第二次收集不应重复登记
        collected = desktop_api._collect_real_artifacts(str(proj))
        assert collected.count("design/sdd.md") == 1

    def test_collect_without_pipeline_dir_returns_empty(self, desktop_api, tmp_path):
        proj = tmp_path / "empty"
        proj.mkdir()
        assert desktop_api._collect_real_artifacts(str(proj)) == []


# ── Change requests (SUP.10) ──────────────────────────────────────────────

class TestChangeRequests:
    def _project(self, d):
        return d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]

    def _create(self, d, pid, **overrides):
        payload = {"title": "Add lamp control", "reason": "new requirement", "requirements": ["REQ-001"]}
        payload.update(overrides)
        return d.handle_desktop("POST", f"projects/{pid}/change-requests", _body(payload), {})

    def test_full_lifecycle_with_impact_evidence(self, desktop_api):
        d = desktop_api
        pid = self._project(d)

        # 准备带 @req 注解的代码与测试产物
        from yuleosh.desktop import workspace
        proj_dir = workspace._project_dir(pid)
        src = proj_dir / "code" / "src" / "main.c"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("// @req REQ-001\nint main(void){return 0;}\n", encoding="utf-8")
        test = proj_dir / "tests" / "test_main.c"
        test.write_text("// REQ-001 covers lamp switching\n", encoding="utf-8")

        resp, status = self._create(d, pid, author="alice")
        assert status == 201
        cr_id = resp["change_request"]["id"]
        assert resp["change_request"]["status"] == "draft"

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/change-requests/{cr_id}/analyze", _body({}), {},
        )
        assert status == 200
        impact = resp["impact"]
        assert resp["change_request"]["status"] == "analyzed"
        assert impact["summary"]["requirements"] == 1
        assert impact["summary"]["code_files"] == 1
        assert impact["summary"]["test_files"] == 1

        evidence = proj_dir / ".osh" / "evidence" / f"impact-analysis-{cr_id}.json"
        assert evidence.is_file()

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/change-requests/{cr_id}/transition",
            _body({"status": "approved", "author": "ccb", "comment": "ok"}), {},
        )
        assert status == 200
        assert resp["change_request"]["status"] == "approved"

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/change-requests/{cr_id}/transition",
            _body({"status": "closed"}), {},
        )
        assert status == 200
        assert resp["change_request"]["status"] == "closed"
        assert [h["to"] for h in resp["change_request"]["history"]] == [
            "draft", "analyzed", "approved", "closed",
        ]

        # 列表与详情
        resp, status = d.handle_desktop("GET", f"projects/{pid}/change-requests", None, {})
        assert status == 200
        assert [c["id"] for c in resp["change_requests"]] == [cr_id]

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/change-requests/{cr_id}", None, {},
        )
        assert status == 200
        assert resp["change_request"]["impact"]["summary"]["requirements"] == 1

    def test_illegal_transition_returns_409(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        cr_id = self._create(d, pid)[0]["change_request"]["id"]

        # draft 不能直接 approved
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/change-requests/{cr_id}/transition",
            _body({"status": "approved"}), {},
        )
        assert status == 409

    def test_analyze_twice_returns_409(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        cr_id = self._create(d, pid)[0]["change_request"]["id"]

        assert d.handle_desktop(
            "POST", f"projects/{pid}/change-requests/{cr_id}/analyze", _body({}), {},
        )[1] == 200
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/change-requests/{cr_id}/analyze", _body({}), {},
        )
        assert status == 409
        assert resp["ok"] is False

    def test_create_requires_title(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/change-requests", _body({"reason": "x"}), {},
        )
        assert status == 400

    def test_missing_project_or_cr_404(self, desktop_api):
        d = desktop_api
        resp, status = d.handle_desktop("GET", "projects/nope/change-requests", None, {})
        assert status == 404

        pid = self._project(d)
        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/change-requests/CR-20260101-abcdef", None, {},
        )
        assert status == 404

    def test_cr_id_path_traversal_rejected(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/change-requests/../project.json", None, {},
        )
        assert status == 400
        assert resp["ok"] is False


# ── Document templates (P4) ──────────────────────────────────────────────

class TestTemplates:
    def _project(self, d):
        return d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]

    def test_list_and_generate(self, desktop_api):
        d = desktop_api
        pid = self._project(d)

        resp, status = d.handle_desktop("GET", f"projects/{pid}/templates", None, {})
        assert status == 200
        assert "qa-plan" in resp["templates"]
        assert "known-issues" in resp["templates"]

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/templates",
            _body({"templates": ["qa-plan", "known-issues"]}), {},
        )
        assert status == 201
        assert set(resp["created"]) == {"docs/qa-plan.md", "docs/known-issues.md"}

    def test_existing_file_skipped_unless_overwrite(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        d.handle_desktop(
            "POST", f"projects/{pid}/templates",
            _body({"templates": ["risk-register"]}), {},
        )
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/templates",
            _body({"templates": ["risk-register"]}), {},
        )
        assert status == 201
        assert resp["skipped"] == ["docs/risk-register.md"]
        assert resp["created"] == []

        from yuleosh.desktop import workspace
        content = (workspace._project_dir(pid) / "docs" / "risk-register.md").read_text()
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/templates",
            _body({"templates": ["risk-register"], "overwrite": True}), {},
        )
        assert status == 201
        assert resp["created"] == ["docs/risk-register.md"]

    def test_generates_compliance_recognized_docs(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        d.handle_desktop(
            "POST", f"projects/{pid}/templates",
            _body({"templates": ["qa-plan", "known-issues"]}), {},
        )
        from yuleosh.compliance.compliance_checker import ComplianceChecker
        from yuleosh.desktop import workspace
        cc = ComplianceChecker(str(workspace._project_dir(pid)))
        assert cc._has_qa_records() is True
        assert cc._has_issue_records() is True

    def test_process_capability_map_generation(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        from yuleosh.compliance.bp_gp_mapping import write_process_capability_map
        from yuleosh.desktop import workspace
        proj = workspace._project_dir(pid)
        out = write_process_capability_map(proj)
        assert Path(out["capability_statement"]).is_file()
        assert Path(out["json"]).is_file()

        data = json.loads(Path(out["json"]).read_text(encoding="utf-8"))
        assert data["capability_boundary"]["CL3"]["supported"] is False
        assert data["capability_boundary"]["CL1"]["supported"] is True
        # 每个 BP 至少有 CL1 的三个 GP
        swe1 = next(a for a in data["areas"] if a["id"] == "SWE.1")
        bp = swe1["bps"][0]
        assert {"GP1.1", "GP1.2", "GP1.3"}.issubset(set(bp["gps"]))


# ── Traceability (P3) ─────────────────────────────────────────────────────

class TestTraceability:
    def _project_with_requirements(self, d):
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        content = (
            "# Reqs\n\n## REQ-001\n- The system SHALL switch the lamp on request.\n\n"
            "## REQ-002\n- The system SHALL report fault status.\n"
        )
        d.handle_desktop("POST", f"projects/{pid}/requirements",
                         _body({"content": content}), {})
        return pid

    def _write(self, pid, rel, content):
        from yuleosh.desktop import workspace
        p = workspace._project_dir(pid) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_refresh_builds_matrix_and_gate(self, desktop_api):
        d = desktop_api
        pid = self._project_with_requirements(d)
        self._write(pid, "code/src/main.c", "// @req REQ-001\nint main(void){return 0;}\n")
        self._write(pid, "tests/test_main.c", "// REQ-001\nvoid test_lamp(void){}\n")

        # 未刷新时读取 → 404
        resp, status = d.handle_desktop("GET", f"projects/{pid}/traceability", None, {})
        assert status == 404

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/traceability/refresh", _body({}), {},
        )
        assert status == 201
        summary = resp["summary"]
        assert summary["total_requirements"] == 2
        assert summary["with_test_coverage"] == 1
        assert summary["coverage_pct"] == 50.0
        # 50% < 60% 默认阈值 → 门禁失败
        assert resp["gate"]["status"] == "failed"

        # 阈值可显式放宽
        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/traceability", None, {"threshold": ["50"]},
        )
        assert status == 200
        assert resp["gate"]["status"] == "passed"

    def test_matrix_rows_expose_design_code_test_links(self, desktop_api):
        d = desktop_api
        pid = self._project_with_requirements(d)
        self._write(pid, "design/sdd.md", "# REQ-001 design\n")
        self._write(pid, "code/main.c", "// @req REQ-001\n")
        self._write(pid, "tests/test_main.c", "// REQ-001\n")
        self._write(pid, "tests/test_orphan.c", "// unrelated\n")

        assert d.handle_desktop(
            "POST", f"projects/{pid}/traceability/refresh", _body({}), {},
        )[1] == 201

        resp, status = d.handle_desktop("GET", f"projects/{pid}/traceability", None, {})
        assert status == 200
        summary = resp["summary"]
        assert summary["with_design_coverage"] == 1
        assert summary["with_implementation"] == 1
        assert summary["design_coverage_pct"] == 50.0

        rows = {r["req_id"]: r for r in resp["requirements"]}
        assert rows["REQ-001"]["design_files"] == ["design/sdd.md"]
        assert rows["REQ-001"]["code_files"] == ["code/main.c"]
        assert rows["REQ-001"]["test_files"] == ["tests/test_main.c"]
        assert rows["REQ-001"]["has_design"] is True
        assert rows["REQ-001"]["match_method"] == "annotation"
        assert rows["REQ-001"]["status"] == "Covered"
        assert rows["REQ-002"]["design_files"] == []
        assert rows["REQ-002"]["status"] == "Not Covered"
        assert resp["orphaned_test_files"] == ["tests/test_orphan.c"]

    def test_refresh_bound_to_baseline(self, desktop_api):
        d = desktop_api
        pid = self._project_with_requirements(d)
        assert d.handle_desktop(
            "POST", f"projects/{pid}/baselines", _body({"name": "B1"}), {},
        )[1] == 201

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/traceability/refresh",
            _body({"baseline": "B1"}), {},
        )
        assert status == 201
        assert resp["baseline"] == "B1"
        assert resp["snapshot"] == ".osh/evidence/traceability-B1.json"

        from yuleosh.desktop import workspace
        assert (workspace._project_dir(pid) / resp["snapshot"]).is_file()

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/traceability/refresh",
            _body({"baseline": "missing"}), {},
        )
        assert status == 404

    def test_reverse_lookup_file_to_requirements(self, desktop_api):
        d = desktop_api
        pid = self._project_with_requirements(d)
        self._write(pid, "code/src/main.c", "// @req REQ-001\nint main(void){return 0;}\n")

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/traceability/reverse",
            None, {"file": ["code/src/main.c"]},
        )
        assert status == 200
        assert resp["requirement_ids"] == ["REQ-001"]

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/traceability/reverse", None, {},
        )
        assert status == 400

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/traceability/reverse",
            None, {"file": ["code/src/nope.c"]},
        )
        assert status == 404

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/traceability/reverse",
            None, {"file": ["../project.json"]},
        )
        assert status == 400

    def test_trace_gate_blocks_green(self):
        from yuleosh.pipeline.gates import classify_run_outcome, traceability_gate

        assert traceability_gate({
            "summary": {"total_requirements": 4, "with_test_coverage": 2,
                        "coverage_pct": 50.0},
        })["status"] == "failed"
        assert traceability_gate({
            "summary": {"total_requirements": 0, "with_test_coverage": 0,
                        "coverage_pct": 0.0},
        })["status"] == "not-run"

        summary = {"worst_gate_status": "passed",
                   "gates": [{"gate": "G1", "status": "passed"}]}
        verdict = classify_run_outcome(
            "completed", [], summary,
            traceability={"summary": {"total_requirements": 4,
                                      "with_test_coverage": 2,
                                      "coverage_pct": 50.0}},
        )
        assert verdict["outcome"] == "unverified"
        assert {"gate": "TRACE", "status": "failed"} in verdict["blocking_gates"]


# ── Evidence chain verification (audit chain) ─────────────────────────────

class TestEvidenceChain:
    def _project(self, d, with_artifacts=True):
        pid = d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]
        content = (
            "# Reqs\n\n## REQ-001\n- The system SHALL switch the lamp on request.\n"
        )
        d.handle_desktop("POST", f"projects/{pid}/requirements",
                         _body({"content": content}), {})
        if with_artifacts:
            from yuleosh.desktop import workspace
            proj = workspace._project_dir(pid)
            for rel, text in (
                ("design/sdd.md", "# REQ-001 design\n"),
                ("code/main.c", "// @req REQ-001\n"),
                ("tests/test_main.c", "// REQ-001\n"),
            ):
                p = proj / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
        return pid

    def test_chain_verdict_uses_desktop_matrix(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop("GET", f"projects/{pid}/evidence-chain", None, {})
        assert status == 200
        assert resp["status"] in ("PASS", "FAIL")
        assert resp["source"] == "traceability-matrix.json"
        assert resp["summary"]["requirements"] == 1
        assert resp["summary"]["nodes"] >= 3
        ids = {g["id"] for g in resp["gates"]}
        assert {"G-REQ", "G-CODE", "G-TEST"} <= ids
        assert isinstance(resp["problems"], list)
        assert resp["v_model"]["required_pairs"] >= 0

    def test_chain_autogenerates_matrix_when_missing(self, desktop_api):
        d = desktop_api
        pid = self._project(d, with_artifacts=False)
        resp, status = d.handle_desktop("GET", f"projects/{pid}/evidence-chain", None, {})
        assert status == 200
        # 未手动刷新时也应先落盘矩阵再校验
        from yuleosh.desktop import workspace
        assert (workspace._project_dir(pid)
                / ".osh/evidence/traceability-matrix.json").is_file()
        assert resp["summary"]["requirements"] == 1

    def test_chain_missing_project_404(self, desktop_api):
        _, status = desktop_api.handle_desktop(
            "GET", "projects/nope/evidence-chain", None, {})
        assert status == 404

    def test_chain_method_not_allowed(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        _, status = d.handle_desktop(
            "POST", f"projects/{pid}/evidence-chain", _body({}), {})
        assert status == 405


# ── Baselines (SUP.8) ─────────────────────────────────────────────────────

class TestBaselines:
    def _project(self, d):
        return d.handle_desktop("POST", "projects", _body({"name": "P"}), {})[0]["project"]["id"]

    def test_snapshot_and_diff_archives_evidence(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        from yuleosh.desktop import workspace
        proj_dir = workspace._project_dir(pid)

        src = proj_dir / "code" / "src" / "main.c"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("int main(void){return 0;}\n", encoding="utf-8")
        obsolete = proj_dir / "evidence" / "obsolete.txt"
        obsolete.write_text("old evidence\n", encoding="utf-8")

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/baselines",
            _body({"name": "B1", "label": "initial", "pipeline_run": "job-1"}), {},
        )
        assert status == 201
        b1 = resp["baseline"]
        assert b1["file_count"] >= 2
        assert b1["pipeline_run"] == "job-1"
        assert len(b1["manifest_sha256"]) == 64
        main_entry = next(f for f in b1["files"] if f["path"] == "code/src/main.c")
        assert len(main_entry["sha256"]) == 64

        # 第二次基线前：修改、增加、删除文件
        src.write_text("int main(void){return 1;}\n", encoding="utf-8")
        (proj_dir / "tests" / "test_new.c").write_text("// new test\n", encoding="utf-8")
        obsolete.unlink()

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/baselines", _body({"name": "B2"}), {},
        )
        assert status == 201

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/baselines/diff",
            None, {"from": ["B1"], "to": ["B2"]},
        )
        assert status == 200
        diff = resp["diff"]
        assert "code/src/main.c" in [m["path"] for m in diff["modified"]]
        assert "tests/test_new.c" in diff["added"]
        assert "evidence/obsolete.txt" in diff["removed"]
        assert diff["summary"]["total_changes"] == 3

        evidence = proj_dir / ".osh" / "evidence" / "baseline-diff-B1--B2.json"
        assert evidence.is_file()
        assert diff["evidence_path"] == ".osh/evidence/baseline-diff-B1--B2.json"

    def test_list_and_detail(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/baselines", _body({"name": "release-1.0"}), {},
        )
        assert status == 201

        resp, status = d.handle_desktop("GET", f"projects/{pid}/baselines", None, {})
        assert status == 200
        assert resp["baselines"][0]["name"] == "release-1.0"
        assert "files" not in resp["baselines"][0]

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/baselines/release-1.0", None, {},
        )
        assert status == 200
        assert "files" in resp["baseline"]

    def test_auto_name_when_omitted(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/baselines", _body({}), {},
        )
        assert status == 201
        assert resp["baseline"]["name"].startswith("BSL-")

    def test_duplicate_name_conflict(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        payload = _body({"name": "B1"})
        assert d.handle_desktop("POST", f"projects/{pid}/baselines", payload, {})[1] == 201
        resp, status = d.handle_desktop("POST", f"projects/{pid}/baselines", payload, {})
        assert status == 409

    def test_diff_missing_params_and_baseline(self, desktop_api):
        d = desktop_api
        pid = self._project(d)

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/baselines/diff", None, {"from": ["B1"]},
        )
        assert status == 400

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/baselines/diff", None,
            {"from": ["nope"], "to": ["nope2"]},
        )
        assert status == 404

    def test_invalid_baseline_name_rejected(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/baselines/../project.json", None, {},
        )
        assert status == 400
        assert resp["ok"] is False


# ── Compliance audit (P5) ──────────────────────────────────────────────────

class TestComplianceAudit:
    def _project(self, d):
        return d.handle_desktop("POST", "projects", _body({"name": "P5"}), {})[0]["project"]["id"]

    def _write(self, pid, rel, content):
        from yuleosh.desktop import workspace
        p = workspace._project_dir(pid) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def _seed_evidence(self, pid):
        """Drop a few substantive passed-evidence JSON files so the audit
        report can compute non-NI evidence-coverage grades."""
        ev = self._write(pid, ".osh/evidence/swe1-req.json", json.dumps({
            "type": "requirement",
            "status": "passed",
            "title": "REQ-001 夜间自动开启车灯",
            "details": "Requirements specification parsed and validated.",
            "id": "REQ-001",
        }))
        self._write(pid, ".osh/evidence/swe3-code.json", json.dumps({
            "type": "code",
            "status": "passed",
            "title": "main.c implementation",
            "details": "Source code present with requirement references.",
            "id": "CODE-001",
        }))
        self._write(pid, ".osh/evidence/swe4-unit-test.json", json.dumps({
            "type": "unit_test",
            "status": "passed",
            "title": "test_main.c unit tests",
            "details": "2/2 tests passed, 100% coverage.",
            "id": "TC-001",
        }))
        return ev

    def test_run_produces_pack_and_report(self, desktop_api):
        d = desktop_api
        pid = self._project(d)

        # Seed project artifacts so evidence collection has something to scan.
        self._write(pid, "docs/spec.md",
                    "# Spec\n\n## REQ-001\n- The system SHALL switch the lamp on.\n")
        self._write(pid, "code/src/main.c", "// @req REQ-001\nint main(void){return 0;}\n")
        self._write(pid, "tests/test_main.c", "// REQ-001\nvoid test_lamp(void){}\n")
        self._seed_evidence(pid)

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/compliance/run", _body({}), {},
        )
        assert status == 200
        summary = resp["summary"]
        assert summary["pack_path"] is not None
        assert summary["audit_report_path"] is not None
        assert summary["bp_summary"]["total"] > 0

        from yuleosh.desktop import workspace
        proj = workspace._project_dir(pid)
        assert (proj / ".osh" / "evidence" / "compliance-pack.zip").is_file()
        assert (proj / ".osh" / "reports" / "aspice-report.html").is_file()
        assert (proj / ".osh" / "reports" / "aspice-report.json").is_file()
        assert (proj / ".osh" / "reports" / "aspice-report.txt").is_file()
        # Compliance check report is also bundled into evidence.
        assert (proj / ".osh" / "evidence" / "compliance-check-report.md").is_file()

    def test_scores_are_evidence_coverage_not_cl(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        self._write(pid, "docs/spec.md", "# Spec\n## REQ-001\n- SHALL do X.\n")
        self._seed_evidence(pid)

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/compliance/run", _body({}), {},
        )
        assert status == 200
        summary = resp["summary"]

        # Scores keyed by process id; values carry a score token from the
        # evidence-coverage set {E1,E2,E3,NI} — never "CL1"/"CL2".
        assert isinstance(summary["scores"], dict)
        valid = {"E1", "E2", "E3", "NI"}
        for pid_dim, dim in summary["scores"].items():
            assert dim["score"] in valid, f"{pid_dim} score {dim['score']} not in {valid}"
            # No ASPICE capability-level leakage.
            assert not dim["score"].startswith("CL")

        # Disclaimer is always present in the response.
        assert "E1" in summary["disclaimer"]
        assert "NOT Automotive SPICE capability" in summary["disclaimer"]

        # The generated HTML report also carries the disclaimer.
        from yuleosh.desktop import workspace
        html = (workspace._project_dir(pid) / ".osh" / "reports" /
                "aspice-report.html").read_text(encoding="utf-8")
        assert "非 ASPICE 能力等级" in html or "NOT Automotive SPICE" in html

    def test_compliance_run_keeps_authoritative_traceability_matrix(self, desktop_api):
        """合规审计不得用旧版 LRT 导出覆盖桌面追溯矩阵。"""
        d = desktop_api
        pid = self._project(d)
        self._write(
            pid, "requirements/requirements.md",
            "# Spec\n\n## REQ-001\n- The system SHALL do X.\n"
            "## REQ-002\n- The system SHALL do Y.\n",
        )
        self._write(pid, "code/main.c", "// @req REQ-001\nint main(void){return 0;}\n")
        self._write(pid, "tests/test_main.c", "// @req REQ-001\nvoid test_x(void){}\n")

        assert d.handle_desktop(
            "POST", f"projects/{pid}/traceability/refresh", _body({}), {},
        )[1] == 201
        assert d.handle_desktop(
            "POST", f"projects/{pid}/compliance/run", _body({}), {},
        )[1] == 200

        resp, status = d.handle_desktop("GET", f"projects/{pid}/traceability", None, {})
        assert status == 200
        assert resp["summary"]["total_requirements"] == 2
        assert resp["summary"]["with_test_coverage"] == 1
        assert resp["gate"]["total_requirements"] == 2

    def test_get_before_run_returns_404(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop("GET", f"projects/{pid}/compliance", None, {})
        assert status == 404

    def test_get_after_run_returns_summary(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        self._write(pid, "docs/spec.md", "# Spec\n## REQ-001\n- SHALL do X.\n")
        self._seed_evidence(pid)

        assert d.handle_desktop(
            "POST", f"projects/{pid}/compliance/run", _body({}), {},
        )[1] == 200

        resp, status = d.handle_desktop("GET", f"projects/{pid}/compliance", None, {})
        assert status == 200
        assert resp["summary"]["pack_path"] is not None

    def test_empty_project_reports_not_run(self, desktop_api):
        """Fail-closed: an empty project must NOT silently pass."""
        d = desktop_api
        pid = self._project(d)
        # No requirements, no evidence.
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/compliance/run", _body({}), {},
        )
        assert status == 200
        summary = resp["summary"]
        assert summary["status"] in ("not_run", "partial")
        # No fake-green: overall evidence-coverage should be NI.
        assert summary.get("overall_score") == "NI"

    def test_summary_carries_dashboard_fields(self, desktop_api):
        """The compliance dashboard needs titles, aggregate counters and
        document status alongside the existing summary."""
        d = desktop_api
        pid = self._project(d)
        self._write(pid, "docs/spec.md", "# Spec\n## REQ-001\n- SHALL do X.\n")
        self._seed_evidence(pid)

        d.handle_desktop("POST", f"projects/{pid}/compliance/run", _body({}), {})

        resp, status = d.handle_desktop("GET", f"projects/{pid}/compliance", None, {})
        assert status == 200
        summary = resp["summary"]
        assert summary["overall_coverage_pct"] >= 0
        assert summary["total_gaps"] == len(summary["gaps"])
        assert summary["total_evidences"] >= 1
        assert summary["scores"]
        for process_id, score in summary["scores"].items():
            assert score["title"], process_id

        docs = {doc["name"]: doc for doc in resp["documents"]}
        assert docs["qa-plan"]["path"] == "docs/qa-plan.md"
        assert docs["qa-plan"]["exists"] is False

    def test_documents_list_missing_evidence_templates(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        self._write(pid, "docs/qa-plan.md", "# QA Plan\n## 1. Scope\n")

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/compliance/documents", None, {},
        )
        assert status == 200
        docs = {doc["name"]: doc for doc in resp["documents"]}
        assert docs["qa-plan"]["exists"] is True
        assert docs["risk-register"]["exists"] is False
        assert "risk-register" in resp["missing"]
        assert "qa-plan" not in resp["missing"]

    def test_documents_endpoint_rejects_unknown_project(self, desktop_api):
        resp, status = desktop_api.handle_desktop(
            "GET", "projects/does-not-exist/compliance/documents", None, {},
        )
        assert status == 404

    def test_documents_endpoint_rejects_non_get(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/compliance/documents", _body({}), {},
        )
        assert status == 405


# ── Audit visualisation (P6) ───────────────────────────────────────────────

class TestAuditVisualization:
    def _project(self, d):
        return d.handle_desktop("POST", "projects", _body({"name": "P6"}), {})[0]["project"]["id"]

    def _write(self, pid, rel, content):
        from yuleosh.desktop import workspace
        p = workspace._project_dir(pid) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def _seed_evidence(self, pid):
        self._write(pid, ".osh/evidence/swe1-req.json", json.dumps({
            "type": "requirement", "status": "passed",
            "title": "REQ-001", "details": "Parsed and validated.", "id": "REQ-001",
        }))
        self._write(pid, ".osh/evidence/swe4-unit.json", json.dumps({
            "type": "unit_test", "status": "passed",
            "title": "test_main", "details": "2/2 passed.", "id": "TC-001",
        }))

    def test_run_produces_dashboard_with_svg(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        self._write(pid, "docs/spec.md", "# Spec\n## REQ-001\n- SHALL do X.\n")
        self._seed_evidence(pid)

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/compliance/run", _body({}), {},
        )
        assert status == 200
        summary = resp["summary"]
        assert summary["dashboard_path"] is not None

        from yuleosh.desktop import workspace
        dash = workspace._project_dir(pid) / ".osh" / "reports" / "aspice-dashboard.html"
        assert dash.is_file()
        html = dash.read_text(encoding="utf-8")

        # Self-contained SVG charts are embedded (no external CDN).
        assert "<svg" in html
        assert "coverage_bar" not in html  # function name must not leak
        # Donut + coverage bar + gap heatmap present.
        assert html.count("<svg") >= 3

    def test_dashboard_disclaimer_preserved(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        self._write(pid, "docs/spec.md", "# Spec\n## REQ-001\n- SHALL do X.\n")
        self._seed_evidence(pid)

        d.handle_desktop("POST", f"projects/{pid}/compliance/run", _body({}), {})
        from yuleosh.desktop import workspace
        html = (workspace._project_dir(pid) / ".osh" / "reports" /
                "aspice-dashboard.html").read_text(encoding="utf-8")
        # E1–E3 ≠ ASPICE CL disclaimer must survive into the dashboard.
        assert "非 ASPICE 能力等级" in html or "NOT Automotive SPICE" in html

    def test_get_dashboard_endpoint(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        self._write(pid, "docs/spec.md", "# Spec\n## REQ-001\n- SHALL do X.\n")
        self._seed_evidence(pid)

        # Before run → 404.
        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/compliance/dashboard", None, {},
        )
        assert status == 404

        d.handle_desktop("POST", f"projects/{pid}/compliance/run", _body({}), {})

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/compliance/dashboard", None, {},
        )
        assert status == 200
        assert resp["ok"] is True
        assert "<svg" in resp["html"]
        assert "非 ASPICE 能力等级" in resp["html"] or "NOT Automotive SPICE" in resp["html"]

    def test_visualization_module_unit(self):
        """Direct unit test of the SVG chart generators."""
        from yuleosh.report.visualization import (
            coverage_bar, bp_pass_donut, score_distribution, gap_heatmap,
            render_dashboard,
        )
        domains = [
            {"id": "SWE.1", "title": "Req Analysis", "score": "E3",
             "coverage_pct": 95.0, "evidence_count": 4, "gap_count": 0},
            {"id": "SWE.2", "title": "Arch Design", "score": "E1",
             "coverage_pct": 40.0, "evidence_count": 2, "gap_count": 1},
            {"id": "SWE.3", "title": "Detailed Design", "score": "NI",
             "coverage_pct": 0.0, "evidence_count": 0, "gap_count": 1},
        ]
        assert "<svg" in coverage_bar(domains)
        assert "SWE.1" in coverage_bar(domains)
        assert "<svg" in bp_pass_donut(8, 10)
        assert "80%" in bp_pass_donut(8, 10)
        # Empty total → no donut (fail-closed, no fake 0%).
        assert bp_pass_donut(0, 0) == ""
        dist = score_distribution(["E3", "E1", "NI", "E3"])
        for grade in ("E3", "E1", "NI"):
            assert grade in dist
        assert "<svg" in gap_heatmap(domains)

        dash = render_dashboard(
            project_name="P", version="1.0", generated_at="2026-01-01",
            overall_score="E2", overall_coverage_pct=55.0, domains=domains,
            bp_passed=8, bp_total=10,
        )
        assert "非 ASPICE 能力等级" in dash or "NOT Automotive SPICE" in dash
        assert dash.count("<svg") >= 3


# ── QA audit workflow (SUP.1 / P7) ─────────────────────────────────────────

class TestQAWorkflow:
    def _project(self, d):
        return d.handle_desktop("POST", "projects", _body({"name": "P7"}), {})[0]["project"]["id"]

    def test_create_list_get_audit(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/qa",
            _body({"title": "SWE.1 requirements review", "auditor": "qa",
                   "scope": "SWE.1"}), {},
        )
        assert status == 201
        aid = resp["audit"]["id"]
        assert resp["audit"]["status"] == "open"

        resp, status = d.handle_desktop("GET", f"projects/{pid}/qa", None, {})
        assert status == 200
        assert any(a["id"] == aid for a in resp["audits"])

        resp, status = d.handle_desktop("GET", f"projects/{pid}/qa/{aid}", None, {})
        assert status == 200
        assert resp["audit"]["title"] == "SWE.1 requirements review"

    def test_finding_lifecycle_and_audit_closure(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        aid = d.handle_desktop(
            "POST", f"projects/{pid}/qa",
            _body({"title": "Audit"}), {},
        )[0]["audit"]["id"]

        # Add a finding.
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/qa/{aid}/findings",
            _body({"description": "Missing traceability", "severity": "high"}), {},
        )
        assert status == 201
        fid = resp["finding"]["id"]
        assert resp["finding"]["status"] == "open"

        # Audit stays open while finding is open (fail-closed).
        audit = d.handle_desktop("GET", f"projects/{pid}/qa/{aid}", None, {})[0]["audit"]
        assert audit["status"] == "open"

        # Close the finding.
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/qa/{aid}/findings/{fid}/transition",
            _body({"status": "closed", "resolution": "Fixed", "verifier": "qa"}), {},
        )
        assert status == 200
        assert resp["finding"]["status"] == "closed"

        # All findings closed → audit awaits management approval (no fake-green).
        audit = d.handle_desktop("GET", f"projects/{pid}/qa/{aid}", None, {})[0]["audit"]
        assert audit["status"] == "pending_approval"
        assert audit["approval"] is None

        # Approval without an approver is rejected.
        _, s = d.handle_desktop(
            "POST", f"projects/{pid}/qa/{aid}/approve", _body({}), {},
        )
        assert s == 400

        # Explicit management sign-off closes the audit.
        resp, s = d.handle_desktop(
            "POST", f"projects/{pid}/qa/{aid}/approve",
            _body({"approver": "qa-lead", "role": "qa_lead"}), {},
        )
        assert s == 200
        assert resp["audit"]["status"] == "closed"
        assert resp["audit"]["approval"]["approved_by"] == "qa-lead"

    def test_invalid_finding_transition_rejected(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        aid = d.handle_desktop(
            "POST", f"projects/{pid}/qa", _body({"title": "A"}), {},
        )[0]["audit"]["id"]
        fid = d.handle_desktop(
            "POST", f"projects/{pid}/qa/{aid}/findings",
            _body({"description": "x"}), {},
        )[0]["finding"]["id"]
        # closed -> open is not allowed.
        d.handle_desktop(
            "POST", f"projects/{pid}/qa/{aid}/findings/{fid}/transition",
            _body({"status": "closed"}), {},
        )
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/qa/{aid}/findings/{fid}/transition",
            _body({"status": "open"}), {},
        )
        assert status == 400

    def test_qa_records_satisfy_compliance_check(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        d.handle_desktop(
            "POST", f"projects/{pid}/qa",
            _body({"title": "Process audit"}), {},
        )
        from yuleosh.compliance.compliance_checker import ComplianceChecker
        from yuleosh.desktop import workspace
        cc = ComplianceChecker(str(workspace._project_dir(pid)))
        assert cc._has_qa_records() is True

    def test_export_report(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        aid = d.handle_desktop(
            "POST", f"projects/{pid}/qa", _body({"title": "A"}), {},
        )[0]["audit"]["id"]
        resp, status = d.handle_desktop("GET", f"projects/{pid}/qa/export", None, {})
        assert status == 200
        from yuleosh.desktop import workspace
        assert Path(resp["path"]).is_file()
        content = Path(resp["path"]).read_text(encoding="utf-8")
        assert aid in content


# ── Issue / problem-resolution workflow (SUP.9 / P8) ───────────────────────

class TestIssues:
    def _project(self, d):
        return d.handle_desktop("POST", "projects", _body({"name": "P8"}), {})[0]["project"]["id"]

    def test_create_list_get_issue(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/issues",
            _body({"title": "NULL pointer in init", "severity": "high",
                   "owner": "dev"}), {},
        )
        assert status == 201
        iid = resp["issue"]["id"]
        assert resp["issue"]["status"] == "open"

        resp, status = d.handle_desktop("GET", f"projects/{pid}/issues", None, {})
        assert status == 200
        assert any(i["id"] == iid for i in resp["issues"])

        resp, status = d.handle_desktop("GET", f"projects/{pid}/issues/{iid}", None, {})
        assert status == 200
        assert resp["issue"]["severity"] == "high"

    def test_full_lifecycle_with_rca_and_verification(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        iid = d.handle_desktop(
            "POST", f"projects/{pid}/issues",
            _body({"title": "Defect"}), {},
        )[0]["issue"]["id"]

        # open -> analyzed (root cause)
        _, s = d.handle_desktop(
            "POST", f"projects/{pid}/issues/{iid}/transition",
            _body({"status": "analyzed", "root_cause": "Uninitialized pointer"}), {},
        )
        assert s == 200

        # analyzed -> resolved
        _, s = d.handle_desktop(
            "POST", f"projects/{pid}/issues/{iid}/transition",
            _body({"status": "resolved", "resolution": "Added init"}), {},
        )
        assert s == 200

        # resolved -> verified
        _, s = d.handle_desktop(
            "POST", f"projects/{pid}/issues/{iid}/transition",
            _body({"status": "verified", "verification": "Retest passed"}), {},
        )
        assert s == 200

        # verified -> closed
        resp, s = d.handle_desktop(
            "POST", f"projects/{pid}/issues/{iid}/transition",
            _body({"status": "closed"}), {},
        )
        assert s == 200
        assert resp["issue"]["status"] == "closed"
        assert resp["issue"]["closed_at"] is not None

    def test_close_without_verification_blocked(self, desktop_api):
        """Fail-closed: an issue cannot close without verification."""
        d = desktop_api
        pid = self._project(d)
        iid = d.handle_desktop(
            "POST", f"projects/{pid}/issues", _body({"title": "D"}), {},
        )[0]["issue"]["id"]
        # Skip verified, try to close directly from resolved.
        d.handle_desktop(
            "POST", f"projects/{pid}/issues/{iid}/transition",
            _body({"status": "analyzed", "root_cause": "x"}), {},
        )
        d.handle_desktop(
            "POST", f"projects/{pid}/issues/{iid}/transition",
            _body({"status": "resolved", "resolution": "y"}), {},
        )
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/issues/{iid}/transition",
            _body({"status": "closed"}), {},
        )
        assert status == 409

    def test_issues_satisfy_compliance_check(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        d.handle_desktop(
            "POST", f"projects/{pid}/issues", _body({"title": "Defect"}), {},
        )
        from yuleosh.compliance.compliance_checker import ComplianceChecker
        from yuleosh.desktop import workspace
        cc = ComplianceChecker(str(workspace._project_dir(pid)))
        assert cc._has_issue_records() is True


# ── Project management (MAN.3 / P9) ────────────────────────────────────────

class TestProjectMgmt:
    def _project(self, d):
        return d.handle_desktop("POST", "projects", _body({"name": "P9"}), {})[0]["project"]["id"]

    def test_risk_lifecycle(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/risks",
            _body({"description": "Schedule slip", "likelihood": "high",
                   "impact": "high", "owner": "pm"}), {},
        )
        assert status == 201
        rid = resp["risk"]["id"]
        # high × high = critical
        assert resp["risk"]["level"] == "critical"
        assert resp["risk"]["status"] == "open"

        # Mitigate requires a mitigation plan.
        _, s = d.handle_desktop(
            "POST", f"projects/{pid}/risks/{rid}/transition",
            _body({"status": "mitigated", "mitigation": "Buffer added"}), {},
        )
        assert s == 200

        # Close from mitigated requires management acceptance.
        _, s = d.handle_desktop(
            "POST", f"projects/{pid}/risks/{rid}/transition",
            _body({"status": "closed"}), {},
        )
        assert s == 400

        resp, s = d.handle_desktop(
            "POST", f"projects/{pid}/risks/{rid}/transition",
            _body({"status": "closed", "accepted_by": "pm"}), {},
        )
        assert s == 200
        assert resp["risk"]["status"] == "closed"
        assert resp["risk"]["acceptance"]["accepted_by"] == "pm"

    def test_risk_close_without_mitigation_blocked(self, desktop_api):
        """Fail-closed: a risk cannot close without mitigation."""
        d = desktop_api
        pid = self._project(d)
        rid = d.handle_desktop(
            "POST", f"projects/{pid}/risks",
            _body({"description": "R"}), {},
        )[0]["risk"]["id"]
        # open -> mitigated without mitigation plan should fail.
        _, s = d.handle_desktop(
            "POST", f"projects/{pid}/risks/{rid}/transition",
            _body({"status": "mitigated"}), {},
        )
        assert s == 400

    def test_risk_level_matrix(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        # low × low = low
        r = d.handle_desktop(
            "POST", f"projects/{pid}/risks",
            _body({"description": "r1", "likelihood": "low", "impact": "low"}), {},
        )[0]["risk"]
        assert r["level"] == "low"
        # high × medium = high
        r = d.handle_desktop(
            "POST", f"projects/{pid}/risks",
            _body({"description": "r2", "likelihood": "high", "impact": "medium"}), {},
        )[0]["risk"]
        assert r["level"] == "high"

    def test_milestones_crud(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/milestones",
            _body({"title": "M1", "target_date": "2026-12-01",
                   "deliverable": "Spec"}), {},
        )
        assert status == 201
        mid = resp["milestone"]["id"]

        resp, status = d.handle_desktop("GET", f"projects/{pid}/milestones", None, {})
        assert status == 200
        assert len(resp["milestones"]) == 1

        # Update status to completed.
        resp, status = d.handle_desktop(
            "PATCH", f"projects/{pid}/milestones/{mid}",
            _body({"status": "completed"}), {},
        )
        assert status == 200
        assert resp["milestone"]["status"] == "completed"

    def test_risk_and_milestones_satisfy_compliance(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        d.handle_desktop(
            "POST", f"projects/{pid}/risks", _body({"description": "R"}), {},
        )
        d.handle_desktop(
            "POST", f"projects/{pid}/milestones", _body({"title": "M"}), {},
        )
        from yuleosh.compliance.compliance_checker import ComplianceChecker
        from yuleosh.desktop import workspace
        cc = ComplianceChecker(str(workspace._project_dir(pid)))
        assert cc._has_risk_records() is True
        assert cc._has_milestone_records() is True


# ── Compliance audit ↔ workflow integration (优化项 1/2) ────────────────────

class TestComplianceWorkflowIntegration:
    def _project(self, d):
        return d.handle_desktop(
            "POST", "projects", _body({"name": "INT"}), {},
        )[0]["project"]["id"]

    def _write(self, pid, rel, content):
        from yuleosh.desktop import workspace
        p = workspace._project_dir(pid) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def _seed(self, pid):
        self._write(pid, "docs/spec.md", "# Spec\n## REQ-001\n- SHALL do X.\n")
        self._write(pid, ".osh/evidence/swe1-req.json", json.dumps({
            "type": "requirement", "status": "passed",
            "title": "REQ-001", "details": "Parsed.", "id": "REQ-001",
        }))

    def _seed_workflows(self, d, pid):
        d.handle_desktop("POST", f"projects/{pid}/qa",
                         _body({"title": "Process audit"}), {})
        d.handle_desktop("POST", f"projects/{pid}/issues",
                         _body({"title": "Defect"}), {})
        d.handle_desktop("POST", f"projects/{pid}/risks",
                         _body({"description": "Schedule slip",
                                "likelihood": "high", "impact": "high"}), {})
        d.handle_desktop("POST", f"projects/{pid}/milestones",
                         _body({"title": "M1"}), {})

    def test_workflow_exports_bundled_into_pack(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        self._seed(pid)
        self._seed_workflows(d, pid)

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/compliance/run", _body({}), {},
        )
        assert status == 200
        summary = resp["summary"]

        # Workflow counts surface in the summary.
        assert summary["workflow"]["qa"]["total"] == 1
        assert summary["workflow"]["issues"]["total"] == 1
        assert summary["workflow"]["risks"]["total"] == 1
        assert summary["workflow"]["risks"]["critical"] == 1
        assert summary["workflow"]["milestones"]["total"] == 1

        from yuleosh.desktop import workspace
        import zipfile
        proj = workspace._project_dir(pid)
        for name in ("qa-audit-report.md", "issue-report.md", "project-mgmt-report.md"):
            assert (proj / ".osh" / "evidence" / name).is_file(), name

        with zipfile.ZipFile(proj / ".osh" / "evidence" / "compliance-pack.zip") as zf:
            names = zf.namelist()
            for name in ("qa-audit-report.md", "issue-report.md", "project-mgmt-report.md"):
                assert name in names, f"{name} not bundled in pack"

    def test_dashboard_shows_workflow_status(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        self._seed(pid)
        self._seed_workflows(d, pid)

        d.handle_desktop("POST", f"projects/{pid}/compliance/run", _body({}), {})
        from yuleosh.desktop import workspace
        html = (workspace._project_dir(pid) / ".osh" / "reports" /
                "aspice-dashboard.html").read_text(encoding="utf-8")
        assert "Workflow Status" in html
        assert "SUP.1" in html and "SUP.9" in html and "MAN.3" in html
        # Disclaimer must still be present (E1–E3 ≠ CL).
        assert "非 ASPICE 能力等级" in html or "NOT Automotive SPICE" in html

    def test_workflow_section_omitted_when_empty(self, desktop_api):
        """Fail-closed: no workflow records → no status section at all."""
        d = desktop_api
        pid = self._project(d)
        self._seed(pid)

        resp, status = d.handle_desktop(
            "POST", f"projects/{pid}/compliance/run", _body({}), {},
        )
        assert status == 200
        assert resp["summary"]["workflow"] == {}

        from yuleosh.desktop import workspace
        html = (workspace._project_dir(pid) / ".osh" / "reports" /
                "aspice-dashboard.html").read_text(encoding="utf-8")
        assert "Workflow Status" not in html


# ── 角色字段与审批链 ──────────────────────────────────────────────────────

class TestRolesAndApprovalChain:
    def _project(self, d):
        return d.handle_desktop(
            "POST", "projects", _body({"name": "ROLE"}), {},
        )[0]["project"]["id"]

    def test_roles_recorded_on_records(self, desktop_api):
        d = desktop_api
        pid = self._project(d)

        audit = d.handle_desktop(
            "POST", f"projects/{pid}/qa",
            _body({"title": "A", "auditor": "alice", "auditor_role": "qa_engineer"}),
            {},
        )[0]["audit"]
        assert audit["auditor_role"] == "qa_engineer"

        fid = d.handle_desktop(
            "POST", f"projects/{pid}/qa/{audit['id']}/findings",
            _body({"description": "x", "assigned_to": "bob"}), {},
        )[0]["finding"]["id"]
        full = d.handle_desktop(
            "GET", f"projects/{pid}/qa/{audit['id']}", None, {},
        )[0]["audit"]
        finding = [f for f in full["findings"] if f["id"] == fid][0]
        assert finding["assigned_to"] == "bob"

        issue = d.handle_desktop(
            "POST", f"projects/{pid}/issues",
            _body({"title": "Defect", "reported_by": "alice"}), {},
        )[0]["issue"]
        assert issue["reported_by"] == "alice"
        assert issue["verified_by"] == ""

        d.handle_desktop(
            "POST", f"projects/{pid}/issues/{issue['id']}/transition",
            _body({"status": "analyzed", "root_cause": "x"}), {},
        )
        d.handle_desktop(
            "POST", f"projects/{pid}/issues/{issue['id']}/transition",
            _body({"status": "resolved", "resolution": "y"}), {},
        )
        ver = d.handle_desktop(
            "POST", f"projects/{pid}/issues/{issue['id']}/transition",
            _body({"status": "verified", "verification": "z",
                   "verified_by": "carol"}), {},
        )[0]["issue"]
        assert ver["verified_by"] == "carol"

        risk = d.handle_desktop(
            "POST", f"projects/{pid}/risks",
            _body({"description": "R", "owner_role": "risk_owner"}), {},
        )[0]["risk"]
        assert risk["owner_role"] == "risk_owner"
        assert risk["acceptance"] is None

    def test_audit_without_findings_requires_approval(self, desktop_api):
        """Fail-closed: an empty audit is not evidence of quality."""
        d = desktop_api
        pid = self._project(d)
        aid = d.handle_desktop(
            "POST", f"projects/{pid}/qa", _body({"title": "A"}), {},
        )[0]["audit"]["id"]
        audit = d.handle_desktop("GET", f"projects/{pid}/qa/{aid}", None, {})[0]["audit"]
        assert audit["status"] == "open"

        _, s = d.handle_desktop(
            "POST", f"projects/{pid}/qa/{aid}/approve", _body({}), {},
        )
        assert s == 400

        resp, s = d.handle_desktop(
            "POST", f"projects/{pid}/qa/{aid}/approve",
            _body({"approver": "lead"}), {},
        )
        assert s == 200
        assert resp["audit"]["status"] == "closed"

    def test_approval_blocked_while_findings_open(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        aid = d.handle_desktop(
            "POST", f"projects/{pid}/qa", _body({"title": "A"}), {},
        )[0]["audit"]["id"]
        d.handle_desktop(
            "POST", f"projects/{pid}/qa/{aid}/findings",
            _body({"description": "open finding"}), {},
        )
        _, s = d.handle_desktop(
            "POST", f"projects/{pid}/qa/{aid}/approve",
            _body({"approver": "lead"}), {},
        )
        assert s == 400


# ── OpenAPI 描述 ──────────────────────────────────────────────────────────

class TestOpenAPISpec:
    def test_spec_is_served(self, desktop_api):
        spec, status = desktop_api.handle_desktop("GET", "openapi.json", None, {})
        assert status == 200
        assert spec["openapi"].startswith("3.0")
        assert spec["servers"][0]["url"] == "/api/v1/desktop"
        for path in (
            "/projects",
            "/projects/{project_id}/compliance/run",
            "/projects/{project_id}/qa/{audit_id}/approve",
            "/projects/{project_id}/risks/{risk_id}/transition",
        ):
            assert path in spec["paths"], path

    def test_spec_carries_evidence_coverage_disclaimer(self, desktop_api):
        spec, status = desktop_api.handle_desktop("GET", "openapi.json", None, {})
        assert status == 200
        assert "NOT Automotive SPICE" in spec["info"]["description"]

    def test_non_get_method_rejected(self, desktop_api):
        _, status = desktop_api.handle_desktop("POST", "openapi.json", _body({}), {})
        assert status == 405


# ── LLM settings ──────────────────────────────────────────────────────────

_LLM_ENV_VARS = (
    "YULEOSH_LLM_PROVIDER",
    "YULEOSH_DESKTOP_MODE",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture
def llm_env(monkeypatch):
    """Isolate LLM-related env vars so tests see a deterministic state."""
    for env in _LLM_ENV_VARS:
        monkeypatch.delenv(env, raising=False)
    return monkeypatch


class TestLLMSettings:
    def test_get_defaults(self, desktop_api, llm_env):
        resp, status = desktop_api.handle_desktop("GET", "settings/llm", None, {})

        assert status == 200
        assert resp["ok"] is True
        assert resp["provider"] == "deepseek"
        assert resp["model"] == ""
        assert resp["base_url"] == ""
        assert resp["default_model"] == "deepseek-v4"
        assert resp["providers"] == ["deepseek", "openai", "anthropic", "mock"]
        assert resp["api_key_set"] is False
        assert resp["api_key_masked"] == ""

    def test_save_persists_masks_and_applies_env(self, desktop_api, llm_env):
        resp, status = desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "openai",
            "model": "qwen2.5-coder",
            "base_url": "http://127.0.0.1:11434/v1",
            "api_key": "sk-test-123456",
        }), {})

        assert status == 200
        assert resp["api_key_set"] is True
        assert resp["api_key_masked"] == "••••3456"
        assert resp["api_key_source"] == "settings"
        # The plaintext key must never leak through the API response.
        assert "sk-test-123456" not in json.dumps(resp)

        # Applied to the process env (read per-call by the LLM providers).
        assert os.environ["YULEOSH_LLM_PROVIDER"] == "openai"
        assert os.environ["LLM_MODEL"] == "qwen2.5-coder"
        assert os.environ["LLM_BASE_URL"] == "http://127.0.0.1:11434/v1"
        assert os.environ["OPENAI_API_KEY"] == "sk-test-123456"

        # Persisted privately on disk.
        path = desktop_api._settings_path()
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8"))["llm"]["api_key"] == "sk-test-123456"
        assert (path.stat().st_mode & 0o777) == 0o600

    def test_omitted_key_keeps_previous(self, desktop_api, llm_env):
        desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "deepseek", "api_key": "sk-keep-9999",
        }), {})

        resp, status = desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "deepseek", "model": "deepseek-v4",
        }), {})

        assert status == 200
        assert resp["api_key_masked"] == "••••9999"
        assert os.environ["DEEPSEEK_API_KEY"] == "sk-keep-9999"

    def test_clear_api_key(self, desktop_api, llm_env):
        desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "openai", "api_key": "sk-clear-8888",
        }), {})
        assert os.environ["OPENAI_API_KEY"] == "sk-clear-8888"

        resp, status = desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "openai", "clear_api_key": True,
        }), {})

        assert status == 200
        assert resp["api_key_set"] is False
        assert resp["api_key_masked"] == ""
        assert "OPENAI_API_KEY" not in os.environ
        assert "LLM_API_KEY" not in os.environ

    def test_mock_provider_reports_no_key(self, desktop_api, llm_env):
        desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "openai", "api_key": "sk-mock-7777",
        }), {})

        resp, status = desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "mock",
        }), {})

        assert status == 200
        assert resp["provider"] == "mock"
        assert resp["api_key_set"] is False

    def test_empty_model_and_base_url_clear_env(self, desktop_api, llm_env):
        desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "deepseek",
            "model": "deepseek-v4",
            "base_url": "https://api.deepseek.com",
        }), {})
        assert os.environ["LLM_MODEL"] == "deepseek-v4"
        assert os.environ["LLM_BASE_URL"] == "https://api.deepseek.com"

        resp, status = desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "deepseek", "model": "", "base_url": "",
        }), {})

        assert status == 200
        assert resp["model"] == ""
        assert "LLM_MODEL" not in os.environ
        assert "LLM_BASE_URL" not in os.environ

    def test_invalid_provider_rejected(self, desktop_api, llm_env):
        resp, status = desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "not-a-provider",
        }), {})

        assert status == 400
        assert resp["ok"] is False
        assert not desktop_api._settings_path().exists()

    def test_invalid_base_url_rejected(self, desktop_api, llm_env):
        resp, status = desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "openai", "base_url": "127.0.0.1:11434",
        }), {})

        assert status == 400
        assert resp["ok"] is False

    def test_bootstrap_restores_saved_settings(self, desktop_api, llm_env):
        desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "anthropic",
            "model": "claude-4-sonnet",
            "base_url": "https://api.anthropic.com",
            "api_key": "sk-ant-1111",
        }), {})

        # Simulate a fresh process: env is empty, settings remain on disk.
        for env in ("YULEOSH_LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "ANTHROPIC_API_KEY"):
            os.environ.pop(env, None)
        llm_env.setenv("YULEOSH_DESKTOP_MODE", "1")

        desktop_api._bootstrap_llm_settings()

        assert os.environ["YULEOSH_LLM_PROVIDER"] == "anthropic"
        assert os.environ["LLM_MODEL"] == "claude-4-sonnet"
        assert os.environ["LLM_BASE_URL"] == "https://api.anthropic.com"
        assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-1111"

    def test_bootstrap_skipped_outside_desktop_mode(self, desktop_api, llm_env):
        desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "deepseek", "model": "deepseek-v4", "api_key": "sk-skip-2222",
        }), {})
        os.environ.pop("LLM_MODEL", None)
        os.environ.pop("DEEPSEEK_API_KEY", None)

        desktop_api._bootstrap_llm_settings()

        assert "LLM_MODEL" not in os.environ
        assert "DEEPSEEK_API_KEY" not in os.environ

    def test_method_not_allowed(self, desktop_api, llm_env):
        _, status = desktop_api.handle_desktop("DELETE", "settings/llm", None, {})
        assert status == 405

    def test_unknown_settings_resource_404(self, desktop_api, llm_env):
        _, status = desktop_api.handle_desktop("GET", "settings/other", None, {})
        assert status == 404

    # ── 生效配置回显 ─────────────────────────────────────────────────────

    def test_get_reports_effective_config_with_defaults(self, desktop_api, llm_env):
        """未显式配置模型 / 地址时，生效配置回落到服务商默认值。"""
        resp, status = desktop_api.handle_desktop("GET", "settings/llm", None, {})

        assert status == 200
        effective = resp["effective"]
        assert effective["provider"] == "deepseek"
        assert effective["model"] == "deepseek-v4"
        assert effective["model_is_default"] is True
        assert effective["base_url"] == "https://api.deepseek.com"
        assert effective["base_url_is_default"] is True
        assert effective["api_key_set"] is False

    def test_effective_config_tracks_saved_values(self, desktop_api, llm_env):
        desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "openai",
            "model": "qwen2.5-coder",
            "base_url": "http://127.0.0.1:11434/v1",
            "api_key": "sk-eff-4321",
        }), {})

        resp, _ = desktop_api.handle_desktop("GET", "settings/llm", None, {})

        effective = resp["effective"]
        assert effective["model"] == "qwen2.5-coder"
        assert effective["model_is_default"] is False
        assert effective["base_url"] == "http://127.0.0.1:11434/v1"
        assert effective["base_url_is_default"] is False
        assert effective["api_key_set"] is True
        assert effective["api_key_source"] == "settings"

    def test_mock_effective_config_needs_no_key(self, desktop_api, llm_env):
        desktop_api.handle_desktop("PUT", "settings/llm", _body({"provider": "mock"}), {})

        resp, _ = desktop_api.handle_desktop("GET", "settings/llm", None, {})

        assert resp["effective"]["api_key_set"] is True
        assert resp["effective"]["api_key_source"] == ""

    # ── 测试连接 ─────────────────────────────────────────────────────────

    def test_connection_test_mock_succeeds_and_counts(self, desktop_api, llm_env):
        resp, status = desktop_api.handle_desktop(
            "POST", "settings/llm/test", _body({"provider": "mock"}), {},
        )

        assert status == 200
        assert resp["ok"] is True
        assert resp["model"] == "deepseek-v4"
        assert resp["latency_ms"] >= 0
        assert resp["stats"]["success"] == 1
        assert resp["stats"]["failure"] == 0
        assert resp["stats"]["last_ok"] is True
        assert resp["tested_at"]

        # 计数持久化，重新读取设置时仍然可见。
        again, _ = desktop_api.handle_desktop("GET", "settings/llm", None, {})
        assert again["stats"]["success"] == 1

    def test_connection_test_requires_api_key(self, desktop_api, llm_env):
        resp, status = desktop_api.handle_desktop(
            "POST", "settings/llm/test", _body({"provider": "openai"}), {},
        )

        assert status == 400
        assert resp["ok"] is False
        assert "API Key" in resp["error"]
        # 未发起请求，不计入成功/失败统计。
        assert resp["stats"]["success"] == 0
        assert resp["stats"]["failure"] == 0

    def test_connection_test_failure_records_error(self, desktop_api, llm_env):
        # 127.0.0.1:9 上没有服务监听，连接会立即被拒绝。
        resp, status = desktop_api.handle_desktop(
            "POST", "settings/llm/test",
            _body({
                "provider": "openai",
                "model": "gpt-4o",
                "base_url": "http://127.0.0.1:9/v1",
                "api_key": "sk-fail-0001",
            }),
            {},
        )

        assert status == 200
        assert resp["ok"] is False
        assert resp["error"]
        assert "127.0.0.1:9" in resp["endpoint"]
        assert resp["stats"]["failure"] == 1
        assert resp["stats"]["success"] == 0
        assert resp["stats"]["last_ok"] is False

        stored = desktop_api._read_settings()
        assert stored["llm_stats"]["failure"] == 1
        # 明文 Key 不应写进统计信息。
        assert "sk-fail-0001" not in json.dumps(stored["llm_stats"])

    def test_connection_test_uses_saved_key(self, desktop_api, llm_env):
        desktop_api.handle_desktop("PUT", "settings/llm", _body({
            "provider": "openai",
            "model": "gpt-4o",
            "base_url": "http://127.0.0.1:9/v1",
            "api_key": "sk-saved-5555",
        }), {})

        # 未在测试请求里传 Key，应复用已保存的 Key 并通过缺 Key 校验。
        resp, status = desktop_api.handle_desktop(
            "POST", "settings/llm/test", _body({"provider": "openai"}), {},
        )

        assert status == 200
        assert "API Key" not in resp["error"]
        assert resp["stats"]["failure"] == 1

    def test_connection_test_defaults_endpoint_by_provider(self, desktop_api, llm_env):
        # 指向本地空闲端口，避免测试访问真实服务商网络。
        resp, _ = desktop_api.handle_desktop(
            "POST", "settings/llm/test",
            _body({
                "provider": "anthropic",
                "base_url": "http://127.0.0.1:9",
                "api_key": "sk-ant-test",
            }),
            {},
        )

        # Anthropic 使用 /v1/messages 协议，默认模型来自路由表。
        assert resp["model"] == "claude-4-sonnet"
        assert resp["endpoint"] == "http://127.0.0.1:9/v1/messages"

    def test_connection_test_accepts_v1_base_url(self, desktop_api, llm_env):
        resp, _ = desktop_api.handle_desktop(
            "POST", "settings/llm/test",
            _body({
                "provider": "openai",
                "base_url": "http://127.0.0.1:9/v1/",
                "api_key": "sk-v1-1111",
            }),
            {},
        )

        # 不应重复拼接 /v1/v1。
        assert resp["endpoint"] == "http://127.0.0.1:9/v1/chat/completions"

    def test_connection_test_rejects_invalid_input(self, desktop_api, llm_env):
        resp, status = desktop_api.handle_desktop(
            "POST", "settings/llm/test", _body({"provider": "nope"}), {},
        )
        assert status == 400
        assert resp["ok"] is False

        resp, status = desktop_api.handle_desktop(
            "POST", "settings/llm/test",
            _body({"provider": "openai", "base_url": "127.0.0.1:9"}),
            {},
        )
        assert status == 400
        assert "base_url" in resp["error"]

    def test_connection_test_method_not_allowed(self, desktop_api, llm_env):
        _, status = desktop_api.handle_desktop("GET", "settings/llm/test", None, {})
        assert status == 405



# ── Quality gate board (traceability / review / CI / test) ────────────────

class TestQualityGates:
    def _project(self, d):
        return d.handle_desktop("POST", "projects", _body({"name": "QG"}), {})[
            0]["project"]["id"]

    def _write(self, pid, rel, content):
        from yuleosh.desktop import workspace
        p = workspace._project_dir(pid) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def _gate(self, resp, key):
        return next(c for c in resp["categories"] if c["key"] == key)

    def _green_project(self, d):
        """Project whose four gates all verify green."""
        pid = self._project(d)
        d.handle_desktop("POST", f"projects/{pid}/requirements", _body({
            "content": "# Reqs\n\n## REQ-001\n- The system SHALL switch on.\n",
        }), {})
        self._write(pid, "code/main.c", "// @req REQ-001\nint main(void){return 0;}\n")
        self._write(pid, "tests/test_main.c", "// @req REQ-001\n")
        self._write(pid, "tests/report.json",
                    json.dumps({"passed": 3, "failed": 0, "coverage": "82%"}))
        d.handle_desktop("POST", f"projects/{pid}/review", _body({
            "artifact": "code/main.c", "status": "approved", "author": "qa",
        }), {})

        from yuleosh.desktop import workspace
        workspace.record_pipeline_run(pid, "job-20261115")
        workspace.save_pipeline_result(pid, "job-20261115", {
            "status": "passed",
            "started_at": "2026-11-15T10:00:00",
            "completed_at": "2026-11-15T10:05:00",
        })
        self._write(pid, ".osh/sessions/s1/gate-summary.json", json.dumps({
            "schema": "gate-summary-v1",
            "session": "s1",
            "timestamp": "2026-11-15T10:05:00",
            "worst_gate_status": "passed",
            "gates": [
                {"gate": "G1", "name": "SWE.1 需求 Gate", "status": "passed",
                 "step_keys": ["spec-check", "prd"], "advisory": False},
                {"gate": "G4", "name": "方案评审 Gate", "status": "passed",
                 "step_keys": ["claude-review"], "advisory": True},
            ],
            "not_run_gates": [],
            "stale_gates": [],
        }))
        return pid

    def test_empty_project_is_unverified_not_green(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/quality-gates", None, {},
        )
        assert status == 200
        assert resp["overall"] == "unverified"
        assert {c["key"] for c in resp["categories"]} == {
            "traceability", "review", "ci", "test"}
        for category in resp["categories"]:
            assert category["status"] == "not-run", category["key"]
        assert resp["latest_run"]["source"] == "none"
        assert resp["latest_run"]["gates"] == []

    def test_all_gates_green_with_pipeline_gate_summary(self, desktop_api):
        d = desktop_api
        pid = self._green_project(d)

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/quality-gates", None, {},
        )
        assert status == 200
        assert resp["overall"] == "green"
        assert resp["worst_status"] == "passed"
        assert self._gate(resp, "traceability")["status"] == "passed"
        assert self._gate(resp, "review")["status"] == "passed"
        assert self._gate(resp, "ci")["status"] == "passed"
        assert self._gate(resp, "test")["status"] == "passed"

        latest = resp["latest_run"]
        assert latest["job_id"] == "job-20261115"
        assert latest["source"] == "gate-summary"
        assert latest["session"] == "s1"
        assert latest["worst_gate_status"] == "passed"
        assert [g["gate"] for g in latest["gates"]] == ["G1", "G4"]
        assert latest["gates"][1]["advisory"] is True

    def test_rejected_review_turns_overall_red(self, desktop_api):
        d = desktop_api
        pid = self._green_project(d)
        d.handle_desktop("POST", f"projects/{pid}/review", _body({
            "artifact": "code/main.c", "status": "rejected", "author": "qa",
        }), {})

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/quality-gates", None, {},
        )
        assert status == 200
        assert resp["overall"] == "red"
        review = self._gate(resp, "review")
        assert review["status"] == "failed"
        assert "驳回 1" in review["detail"]

    def test_failed_test_report_fails_test_gate(self, desktop_api):
        d = desktop_api
        pid = self._green_project(d)
        self._write(pid, "tests/report.json",
                    json.dumps({"passed": 2, "failed": 1, "coverage": "70%"}))

        resp, _ = d.handle_desktop("GET", f"projects/{pid}/quality-gates", None, {})
        test_gate = self._gate(resp, "test")
        assert test_gate["status"] == "failed"
        assert "失败 1" in test_gate["detail"]
        assert resp["overall"] == "red"

    def test_run_without_gate_summary_uses_run_record(self, desktop_api):
        d = desktop_api
        pid = self._project(d)
        from yuleosh.desktop import workspace
        workspace.record_pipeline_run(pid, "job-run-only")
        workspace.save_pipeline_result(pid, "job-run-only", {
            "status": "running", "started_at": "2026-11-15T11:00:00",
        })

        resp, _ = d.handle_desktop("GET", f"projects/{pid}/quality-gates", None, {})
        assert self._gate(resp, "ci")["status"] == "warning"
        assert resp["latest_run"]["source"] == "run-record"
        assert resp["latest_run"]["gates"] == []
        # 运行中不等于验证通过
        assert resp["overall"] == "unverified"

    def test_unknown_project_and_bad_method(self, desktop_api):
        d = desktop_api
        _, status = d.handle_desktop(
            "GET", "projects/nope/quality-gates", None, {},
        )
        assert status == 404
        pid = self._project(d)
        _, status = d.handle_desktop(
            "POST", f"projects/{pid}/quality-gates", _body({}), {},
        )
        assert status == 405


# ── Review center (cross-artifact list / bulk tagging / export) ────────────

class TestReviewCenter:
    def _project(self, d):
        return d.handle_desktop("POST", "projects", _body({"name": "RV"}), {})[
            0]["project"]["id"]

    def _write(self, pid, rel, content):
        from yuleosh.desktop import workspace
        p = workspace._project_dir(pid) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def _seed(self, d):
        pid = self._project(d)
        self._write(pid, "requirements/requirements.md", "# Req\n")
        self._write(pid, "code/main.c", "int main(void){return 0;}\n")
        self._write(pid, "code/util.c", "int add(int a,int b){return a+b;}\n")
        self._write(pid, "tests/test_main.c", "int main(void){return 0;}\n")
        return pid

    def _artifacts(self, d, pid):
        resp, status = d.handle_desktop("GET", f"projects/{pid}/review", None, {})
        assert status == 200
        return {a["artifact"]: a for a in resp["artifacts"]}

    def test_list_shows_unreviewed_artifacts_and_counts(self, desktop_api):
        d = desktop_api
        pid = self._seed(d)
        d.handle_desktop("POST", f"projects/{pid}/review", _body({
            "artifact": "code/main.c", "status": "approved", "author": "qa",
        }), {})

        resp, status = d.handle_desktop("GET", f"projects/{pid}/review", None, {})
        assert status == 200
        arts = {a["artifact"]: a for a in resp["artifacts"]}
        assert set(arts) == {
            "requirements/requirements.md", "code/main.c",
            "code/util.c", "tests/test_main.c",
        }
        assert arts["code/main.c"]["status"] == "approved"
        assert arts["code/main.c"]["review_id"]
        assert arts["code/util.c"]["status"] == "unreviewed"
        # review.json / review-report.md 不能被当成待评审产物
        assert "evidence/review.json" not in arts
        assert resp["counts"] == {
            "total_files": 4, "approved": 1, "rejected": 0,
            "needs_revision": 0, "unreviewed": 3,
        }
        sections = {s["section"]: s for s in resp["sections"]}
        assert sections["code"]["total"] == 2
        assert sections["code"]["approved"] == 1
        assert sections["code"]["unreviewed"] == 1

    def test_bulk_by_section_updates_and_creates(self, desktop_api):
        d = desktop_api
        pid = self._seed(d)
        d.handle_desktop("POST", f"projects/{pid}/review", _body({
            "artifact": "code/main.c", "status": "approved",
        }), {})

        resp, status = d.handle_desktop("POST", f"projects/{pid}/review/bulk", _body({
            "scope": "section", "section": "code",
            "status": "needs_revision", "comment": "缺少注释",
        }), {})
        assert status == 200
        assert resp["matched"] == 2
        assert resp["created"] == 1
        assert resp["updated"] == 1

        arts = self._artifacts(d, pid)
        assert arts["code/main.c"]["status"] == "needs_revision"
        assert arts["code/main.c"]["comment"] == "缺少注释"
        assert arts["code/util.c"]["status"] == "needs_revision"
        assert arts["tests/test_main.c"]["status"] == "unreviewed"

    def test_bulk_by_glob_only_matches_pattern(self, desktop_api):
        d = desktop_api
        pid = self._seed(d)

        resp, status = d.handle_desktop("POST", f"projects/{pid}/review/bulk", _body({
            "scope": "glob", "pattern": "code/*.c", "status": "approved",
        }), {})
        assert status == 200
        assert resp == {
            "ok": True, "scope": "glob", "matched": 2, "created": 2, "updated": 0,
        }
        arts = self._artifacts(d, pid)
        assert arts["code/main.c"]["status"] == "approved"
        assert arts["code/util.c"]["status"] == "approved"
        assert arts["requirements/requirements.md"]["status"] == "unreviewed"
        assert arts["tests/test_main.c"]["status"] == "unreviewed"

        # 支持逗号分隔的多条模式
        resp, status = d.handle_desktop("POST", f"projects/{pid}/review/bulk", _body({
            "scope": "glob", "pattern": "requirements/*, tests/*",
            "status": "rejected",
        }), {})
        assert status == 200
        assert resp["matched"] == 2
        assert resp["created"] == 2

    def test_bulk_rejects_invalid_input(self, desktop_api):
        d = desktop_api
        pid = self._seed(d)

        cases = [
            ({"scope": "glob", "pattern": "", "status": "approved"}, "pattern"),
            ({"scope": "glob", "pattern": "/etc/passwd", "status": "approved"},
             "project-relative"),
            ({"scope": "glob", "pattern": "../secret/*", "status": "approved"},
             "project-relative"),
            ({"scope": "section", "section": "", "status": "approved"}, "section"),
            ({"scope": "section", "section": "code", "status": "ok"}, "status"),
        ]
        for body, keyword in cases:
            resp, status = d.handle_desktop(
                "POST", f"projects/{pid}/review/bulk", _body(body), {},
            )
            assert status == 400, body
            assert keyword in resp["error"], body

    def test_export_report_lists_unreviewed_and_coverage(self, desktop_api):
        d = desktop_api
        pid = self._seed(d)
        d.handle_desktop("POST", f"projects/{pid}/review/bulk", _body({
            "scope": "section", "section": "code", "status": "approved",
        }), {})

        resp, status = d.handle_desktop(
            "GET", f"projects/{pid}/review/export", None, {},
        )
        assert status == 200
        assert resp["path"] == "evidence/review-report.md"
        assert resp["reviewed_files"] == 2
        assert resp["unreviewed_files"] == 2
        assert resp["total_files"] == 4
        assert "## 未评审产物" in resp["content"]
        assert "tests/test_main.c" in resp["content"]
        assert "覆盖：已评审 2/4" in resp["content"]

        from yuleosh.desktop import workspace
        path = workspace._project_dir(pid) / "evidence" / "review-report.md"
        assert path.exists()

    def test_delete_review_restores_unreviewed(self, desktop_api):
        d = desktop_api
        pid = self._seed(d)
        created, _ = d.handle_desktop("POST", f"projects/{pid}/review", _body({
            "artifact": "code/main.c", "status": "approved",
        }), {})
        rid = created["review"]["id"]

        _, status = d.handle_desktop(
            "DELETE", f"projects/{pid}/review/{rid}", None, {},
        )
        assert status == 200
        assert self._artifacts(d, pid)["code/main.c"]["status"] == "unreviewed"

        _, status = d.handle_desktop(
            "DELETE", f"projects/{pid}/review/{rid}", None, {},
        )
        assert status == 404
