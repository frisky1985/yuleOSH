"""Phase 4 coverage boost — pipeline_routes legacy handlers + api/pipeline 委托层.

Milestone: 85.90% → 90%（2026-08-10 接力）。
Target modules:
  - src/yuleosh/ui/routes/pipeline_routes.py  (~41%) — 6 个 legacy handler 未覆盖
  - src/yuleosh/api/pipeline.py               (~79%) — 委托分支补齐

发现（Phase 4）: 真实路由 api/pipeline.py::handle_pipeline 委托到
ui/routes/pipeline_routes.py 的 legacy handlers（runs/stats/yuleasr-status/
yuleasr-notify/checkpoint/list/status）。handle_pipeline_trigger 是死代码
（真实 trigger 走 api.pipeline._trigger_pipeline），仍直测保证行为。
"""

import json
from pathlib import Path
from unittest import mock

# ── Mock handler factory ──────────────────────────────────────────────

def _make_handler(path="/", method="GET", headers=None, body=b""):
    handler = mock.MagicMock()
    handler.headers = dict(headers or {})
    handler.path = path
    handler.command = method
    handler.rfile = mock.MagicMock()
    handler.rfile.read.return_value = body
    handler.wfile = mock.MagicMock()
    handler._request_start_time = 100.0
    handler._get_client_ip = mock.MagicMock(return_value="127.0.0.1")
    handler._response_status = 200
    return handler


# =====================================================================
# handle_pipeline_trigger（死代码但保行为）
# =====================================================================

class TestTriggerHandler:
    def test_requires_auth(self):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        handler = _make_handler(method="POST")
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value=None):
            resp = handle_pipeline_trigger(handler, b"{}")
        assert resp["ok"] is False
        assert "Authentication" in resp["error"]

    def test_bad_json(self):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        handler = _make_handler(method="POST")
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value={"user_id": 1}):
            resp = handle_pipeline_trigger(handler, b"{not-json")
        assert resp["ok"] is False
        assert "Invalid JSON" in resp["error"]

    def test_missing_project_dir(self, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        monkeypatch.delenv("OSH_HOME", raising=False)
        handler = _make_handler(method="POST")
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value={"user_id": 1}):
            resp = handle_pipeline_trigger(handler, b"{}")
        assert resp["ok"] is False
        assert "project_dir" in resp["error"]

    def test_path_outside_osh_home(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        handler = _make_handler(method="POST")
        body = json.dumps({"project_dir": "/etc"}).encode()
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value={"user_id": 1}):
            resp = handle_pipeline_trigger(handler, body)
        assert resp["ok"] is False
        assert "inside OSH_HOME" in resp["error"]

    def test_bad_type(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        handler = _make_handler(method="POST")
        body = json.dumps({"project_dir": str(tmp_path), "type": "evil"}).encode()
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value={"user_id": 1}):
            resp = handle_pipeline_trigger(handler, body)
        assert resp["ok"] is False
        assert "type must be" in resp["error"]

    def test_bad_layer(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        handler = _make_handler(method="POST")
        body = json.dumps({"project_dir": str(tmp_path), "type": "ci", "layer": 99}).encode()
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value={"user_id": 1}):
            resp = handle_pipeline_trigger(handler, body)
        assert resp["ok"] is False
        assert "layer must be" in resp["error"]

    def test_arxml_too_large(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        handler = _make_handler(method="POST")
        body = json.dumps({"project_dir": str(tmp_path),
                           "arxml_content": "x" * 1_000_001}).encode()
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value={"user_id": 1}):
            resp = handle_pipeline_trigger(handler, body)
        assert resp["ok"] is False
        assert "arxml_content too large" in resp["error"]

    def test_config_too_large(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        handler = _make_handler(method="POST")
        body = json.dumps({"project_dir": str(tmp_path),
                           "config_json": "x" * 1_000_001}).encode()
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value={"user_id": 1}):
            resp = handle_pipeline_trigger(handler, body)
        assert resp["ok"] is False
        assert "config_json too large" in resp["error"]

    def test_submit_full(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        handler = _make_handler(method="POST")
        body = json.dumps({"project_dir": str(tmp_path), "type": "full"}).encode()
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value={"user_id": 1}), \
             mock.patch("yuleosh.pipeline.async_runner.submit_full_pipeline",
                        return_value="job-1"):
            resp = handle_pipeline_trigger(handler, body)
        assert resp["ok"] is True
        assert resp["job_id"] == "job-1"
        assert resp["poll_url"] == "/api/v1/pipeline/status/job-1"

    def test_submit_ci(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        handler = _make_handler(method="POST")
        body = json.dumps({"project_dir": str(tmp_path), "type": "ci",
                           "layer": 2}).encode()
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value={"user_id": 1}), \
             mock.patch("yuleosh.pipeline.async_runner.submit_pipeline",
                        return_value="job-2"):
            resp = handle_pipeline_trigger(handler, body)
        assert resp["ok"] is True
        assert resp["job_id"] == "job-2"
        assert resp["type"] == "ci"

    def test_submit_exception(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        handler = _make_handler(method="POST")
        body = json.dumps({"project_dir": str(tmp_path)}).encode()
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value={"user_id": 1}), \
             mock.patch("yuleosh.pipeline.async_runner.submit_full_pipeline",
                        side_effect=RuntimeError("boom")):
            resp = handle_pipeline_trigger(handler, body)
        assert resp["ok"] is False
        assert "boom" in resp["error"]


# =====================================================================
# handle_pipeline_status / runs / stats
# =====================================================================

class TestStatusRunsStats:
    def test_status_missing_id(self):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_status
        handler = _make_handler(path="/api/v1/pipeline/status")
        result = handle_pipeline_status(handler, "/api/v1/pipeline/status")
        # tuple: (dict, 404)
        assert isinstance(result, tuple)
        assert result[1] == 404

    def test_status_not_found(self):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_status
        handler = _make_handler(path="/api/v1/pipeline/status/job-x")
        with mock.patch("yuleosh.pipeline.async_runner.get_job_status",
                        return_value=None):
            result = handle_pipeline_status(handler, "/api/v1/pipeline/status/job-x")
        assert result[1] == 404

    def test_status_success(self):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_status
        handler = _make_handler(path="/api/v1/pipeline/status/job-1")
        status = {
            "job_id": "job-1", "status": "running", "type": "full",
            "progress": 50, "current_stage": "build", "stages": [{"id": "s1"}],
            "logs": ["log1"], "started_at": "2026-01-01T00:00:00",
            "completed_at": None, "result": None,
        }
        with mock.patch("yuleosh.pipeline.async_runner.get_job_status",
                        return_value=status):
            result = handle_pipeline_status(handler, "/api/v1/pipeline/status/job-1")
        assert result["ok"] is True
        assert result["job"]["job_id"] == "job-1"
        assert result["job"]["progress"] == 50

    def test_runs(self):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_runs
        handler = _make_handler(path="/api/v1/pipeline/runs")
        jobs = [
            {"job_id": "j1", "status": "completed", "type": "full",
             "progress": 100, "current_stage": None,
             "started_at": "2026-01-01", "completed_at": "2026-01-01 00:01"},
            {"job_id": "j2", "status": "running", "type": "ci",
             "progress": 10, "current_stage": "build",
             "started_at": "2026-01-01", "completed_at": None},
        ]
        with mock.patch("yuleosh.pipeline.async_runner.list_jobs",
                        return_value=jobs):
            result = handle_pipeline_runs(handler)
        assert result["ok"] is True
        assert result["count"] == 2
        assert result["runs"][0]["job_id"] == "j1"

    def test_stats(self):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_stats
        handler = _make_handler(path="/api/v1/pipeline/stats")
        with mock.patch("yuleosh.pipeline.async_runner.get_pipeline_stats",
                        return_value={"total": 5, "passed": 4}):
            result = handle_pipeline_stats(handler)
        assert result["ok"] is True
        assert result["total"] == 5


# =====================================================================
# handle_yuleasr_status（evidence-bundle 聚合）
# =====================================================================

class TestYuleasrStatus:
    def _make_evidence(self, root, **files):
        """构造 .yuleosh/evidence-bundle 目录树。"""
        ev = root / ".yuleosh" / "evidence-bundle"
        for rel, content in files.items():
            p = ev / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return ev

    def test_unavailable_without_home(self, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_status
        monkeypatch.delenv("YULEASR_HOME", raising=False)
        monkeypatch.delenv("OSH_HOME", raising=False)
        handler = _make_handler(path="/api/v1/pipeline/yuleasr-status")
        result = handle_yuleasr_status(handler)
        assert result["ok"] is True
        assert result["available"] is False
        assert result["errors"]

    def test_unavailable_dir_missing(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_status
        monkeypatch.setenv("YULEASR_HOME", str(tmp_path / "nope"))
        handler = _make_handler(path="/api/v1/pipeline/yuleasr-status")
        result = handle_yuleasr_status(handler)
        assert result["ok"] is True
        assert result["available"] is False

    def test_full_evidence_aggregation(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_status
        monkeypatch.setenv("YULEASR_HOME", str(tmp_path))
        self._make_evidence(tmp_path, **{
            "ci-results/ci-results.json": json.dumps({
                "pipeline": {"status": "passed", "completed_at": "2026-08-10T10:00:00"},
                "generated_at": "2026-08-10T10:00:00",
            }),
            "ci-results/sil-test-results.json": json.dumps({"all_passed": True}),
            "misra-reports/misra-report.json": json.dumps({"total_violations": 3}),
            "coverage/c-coverage.json": json.dumps({
                "summary": {
                    "lines": {"rate": 0.85, "covered": 85, "total": 100},
                    "branches": {"rate": 0.9},
                    "functions": {"rate": 0.95},
                }
            }),
        })
        handler = _make_handler(path="/api/v1/pipeline/yuleasr-status")
        with mock.patch("yuleosh.pipeline.async_runner.list_jobs",
                        return_value=[]):
            result = handle_yuleasr_status(handler)
        assert result["available"] is True
        assert result["compile_status"] == "passed"
        assert result["misra_violations"] == 3
        assert result["coverage"]["line_rate"] == 0.85
        assert result["qemu_status"] == "passed"

    def test_sil_fallback_json(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_status
        monkeypatch.setenv("YULEASR_HOME", str(tmp_path))
        self._make_evidence(tmp_path, **{
            "ci-results/ci-results.json": json.dumps({
                "pipeline": {"status": "failed"},
                "generated_at": "2026-08-10T10:00:00",
            }),
            "ci-results/sil-results.json": json.dumps({
                "generated_at": "2026-08-10T10:00:00",
                "sil_reports": [
                    {"status": "completed", "failed": 0},
                    {"status": "completed", "failed": 2},
                ],
            }),
        })
        handler = _make_handler(path="/api/v1/pipeline/yuleasr-status")
        with mock.patch("yuleosh.pipeline.async_runner.list_jobs",
                        return_value=[]):
            result = handle_yuleasr_status(handler)
        assert result["available"] is True
        assert result["qemu_status"] == "failed"  # 有 2 failed

    def test_corrupted_evidence_errors(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_status
        monkeypatch.setenv("YULEASR_HOME", str(tmp_path))
        self._make_evidence(tmp_path, **{
            "ci-results/ci-results.json": "{not-json",
            "misra-reports/misra-report.json": "{not-json",
            "coverage/c-coverage.json": "{not-json",
        })
        handler = _make_handler(path="/api/v1/pipeline/yuleasr-status")
        with mock.patch("yuleosh.pipeline.async_runner.list_jobs",
                        return_value=[]):
            result = handle_yuleasr_status(handler)
        assert result["available"] is True
        assert len(result["errors"]) >= 1  # ci-results parse error

    def test_recent_autosar_runs(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_status
        monkeypatch.setenv("YULEASR_HOME", str(tmp_path))
        handler = _make_handler(path="/api/v1/pipeline/yuleasr-status")
        jobs = [
            {"job_id": "j1", "type": "full_pipeline"},
            {"job_id": "j2", "type": "ci"},
            {"job_id": "j3", "type": "autosar"},
        ]
        with mock.patch("yuleosh.pipeline.async_runner.list_jobs",
                        return_value=jobs):
            result = handle_yuleasr_status(handler)
        assert result["available"] is True
        assert len(result["recent_autosar_runs"]) == 2  # full_pipeline + autosar


# =====================================================================
# handle_yuleasr_notify
# =====================================================================

class TestYuleasrNotify:
    def test_bad_json(self):
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_notify
        handler = _make_handler(method="POST")
        result = handle_yuleasr_notify(handler, b"{not-json")
        assert result["ok"] is False

    def test_notify_writes_file(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_notify
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        handler = _make_handler(method="POST")
        body = json.dumps({
            "project": "yuleASR", "status": "passed",
            "misra_violations": 0, "coverage": 0.9, "qemu_status": "passed",
        }).encode()
        with mock.patch("yuleosh.notify.notify_pipeline") as m_notify:
            result = handle_yuleasr_notify(handler, body)
        assert result["ok"] is True
        assert result["notify_file"]
        f = Path(result["notify_file"])
        assert f.exists()
        data = json.loads(f.read_text())
        assert data["status"] == "passed"
        assert data["channel"] == "feishu"
        m_notify.assert_called_once()

    def test_notify_feishu_failure_tolerated(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_notify
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        handler = _make_handler(method="POST")
        body = json.dumps({"project": "yuleASR", "status": "failed",
                           "errors": ["boom"]}).encode()
        with mock.patch("yuleosh.notify.notify_pipeline",
                        side_effect=RuntimeError("feishu down")):
            result = handle_yuleasr_notify(handler, body)
        assert result["ok"] is True  # 文件已写，feishu 失败仅 warning


# =====================================================================
# api/pipeline.py 委托层补齐（runs/stats/yuleasr-status/notify/list/status）
# =====================================================================

class TestApiPipelineDelegation:
    def _call(self, path_tail, method="GET", body=None, query=None, **kwargs):
        from yuleosh.api.pipeline import handle_pipeline
        # @require_auth: handler=None 时需显式注入 current_user（测试旁路）
        kwargs.setdefault("current_user", {"user_id": 1, "org_id": 1,
                                           "email": "t@t.com", "role": "admin"})
        return handle_pipeline(method, path_tail, body or {}, query or {}, **kwargs)

    def test_runs_delegates(self):
        with mock.patch("yuleosh.pipeline.async_runner.list_jobs",
                        return_value=[]):
            result = self._call("runs", "GET")
        assert result[0]["ok"] is True
        assert result[0]["runs"] == []

    def test_stats_delegates(self):
        with mock.patch("yuleosh.pipeline.async_runner.get_pipeline_stats",
                        return_value={"total": 3}):
            result = self._call("stats", "GET")
        assert result[0]["ok"] is True
        assert result[0]["total"] == 3

    def test_yuleasr_status_delegates(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YULEASR_HOME", str(tmp_path))
        with mock.patch("yuleosh.pipeline.async_runner.list_jobs",
                        return_value=[]):
            result = self._call("yuleasr-status", "GET")
        assert result[0]["available"] is True

    def test_yuleasr_notify_delegates(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        with mock.patch("yuleosh.notify.notify_pipeline"):
            result = self._call("yuleasr-notify", "POST",
                                {"project": "yuleASR", "status": "passed"})
        assert result[0]["ok"] is True

    def test_validate_delegates(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        with mock.patch("yuleosh.pipeline.config_validator.validate_pipeline_config",
                        return_value={"valid": True}):
            result = self._call("validate", "GET")
        assert result[0]["ok"] is True

    def test_status_id_delegates(self):
        with mock.patch("yuleosh.pipeline.async_runner.get_job_status",
                        return_value=None):
            result = self._call("status/job-1", "GET")
        assert result[1] == 404

    def test_list_delegates(self):
        handler = _make_handler(path="/api/v1/pipeline/list",
                                headers={"Authorization": "Bearer test-token"})
        with mock.patch("yuleosh.api.middleware.verify_token",
                        return_value={"user_id": 1, "org_id": 1}), \
             mock.patch("yuleosh.ui.routes.tenant_routes._require_auth",
                        return_value={"user_id": 1}), \
             mock.patch("yuleosh.ui.routes.pipeline_routes._scan_project_checkpoints",
                        return_value=[]):
            result = self._call("list", "GET", {}, {}, handler=handler)
        assert result[0]["ok"] is True
        assert result[0]["pipelines"] == []

    def test_unknown_resource(self):
        result = self._call("frobnicate", "GET", {}, {})
        assert result[1] == 404

    def test_run_post_without_spec(self):
        result = self._call("run", "POST", {}, {})
        assert result[0]["error"] == "'spec' is required"

    def test_run_get_method_not_allowed(self):
        result = self._call("run", "GET", {}, {})
        assert result[1] == 405

    def test_trigger_get_method_not_allowed(self):
        result = self._call("trigger", "GET", {}, {})
        assert result[1] == 405
        assert "Use POST" in result[0]["error"]

    def test_status_post_method_not_allowed(self):
        result = self._call("status", "POST", {}, {})
        assert result[1] == 405

    def test_steps_post_method_not_allowed(self):
        result = self._call("steps", "POST", {}, {})
        assert result[1] == 405
        assert "Use GET" in result[0]["error"]

    def test_list_post_method_not_allowed(self):
        result = self._call("list", "POST", {}, {})
        assert result[1] == 404  # list POST 无分支 → unknown resource
