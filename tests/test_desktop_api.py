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


# ── Artifact classification ───────────────────────────────────────────────

class TestClassifyArtifact:
    """产物 → 五分区：目录语义 > 文件名语义 > 扩展名 > 待归类。"""

    @pytest.mark.parametrize(
        "rel_path,expected",
        [
            # RTE 生成代码固定进 code/rte
            ("rte/Rte.c", ("code", "code/rte", "rte")),
            ("rte/Rte.h", ("code", "code/rte", "rte")),
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

        # Now audit auto-closes.
        audit = d.handle_desktop("GET", f"projects/{pid}/qa/{aid}", None, {})[0]["audit"]
        assert audit["status"] == "closed"

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

        # Close from mitigated.
        resp, s = d.handle_desktop(
            "POST", f"projects/{pid}/risks/{rid}/transition",
            _body({"status": "closed"}), {},
        )
        assert s == 200
        assert resp["risk"]["status"] == "closed"

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





