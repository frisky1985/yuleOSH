"""Portal 方案 B (2026-08-10): pipeline usage API + 消费计量接通测试。

覆盖:
- GET /api/v1/pipeline/usage 角色分层（admin 全量 / member 本 org / 无认证 / 坏 json 容错）
- PipelineSession org_id/token_usage 持久化（to_dict）
- 消费计量链路: record_pipeline_run → usage_log → get_monthly_usage 聚合
- async_runner org_id 传递 + _record_pipeline_usage（org_id=0 跳过）
"""

import json
import os
from unittest import mock

from yuleosh.pipeline.session import PipelineSession
from yuleosh.ui.routes.pipeline_routes import handle_pipeline_usage


class TestPipelineUsageAPI:
    """GET /api/v1/pipeline/usage — 角色分层消费明细。"""

    def _make_user(self, role="admin", org_id=1):
        return {"user_id": 1, "org_id": org_id, "email": "t@t.com", "role": role}

    def _write_session(self, root, name, org_id, token_total, status="completed"):
        sdir = root / ".osh" / "sessions" / name
        sdir.mkdir(parents=True, exist_ok=True)
        data = {
            "name": name,
            "status": status,
            "created_at": "2026-08-10T12:00:00",
            "org_id": org_id,
            "token_usage_total": token_total,
            "token_usage_steps": [
                {"step": "architecture", "usage": {"total_tokens": token_total}}
            ],
        }
        (sdir / "session.json").write_text(json.dumps(data))

    def _call(self, user, root):
        with (
            mock.patch("yuleosh.ui.routes.tenant_routes._require_auth", return_value=user),
            mock.patch.dict(os.environ, {"OSH_HOME": str(root)}),
        ):
            return handle_pipeline_usage(mock.MagicMock(), "/api/v1/pipeline/usage")

    def test_admin_sees_all_runs(self, tmp_path):
        self._write_session(tmp_path, "run-a", org_id=1, token_total=100)
        self._write_session(tmp_path, "run-b", org_id=2, token_total=200)
        self._write_session(tmp_path, "legacy", org_id=0, token_total=50)
        resp = self._call(self._make_user("admin", 1), tmp_path)
        assert resp["ok"] is True
        assert len(resp["runs"]) == 3
        assert resp["total_tokens"] == 350
        assert resp["total_llm_calls"] == 3

    def test_member_sees_only_own_org(self, tmp_path):
        self._write_session(tmp_path, "run-a", org_id=1, token_total=100)
        self._write_session(tmp_path, "run-b", org_id=2, token_total=200)
        resp = self._call(self._make_user("member", 1), tmp_path)
        assert resp["ok"] is True
        assert len(resp["runs"]) == 1
        assert resp["runs"][0]["name"] == "run-a"
        assert resp["total_tokens"] == 100

    def test_member_excludes_legacy_org0(self, tmp_path):
        self._write_session(tmp_path, "legacy", org_id=0, token_total=50)
        resp = self._call(self._make_user("member", 1), tmp_path)
        assert len(resp["runs"]) == 0

    def test_no_auth_returns_error(self, tmp_path):
        with mock.patch("yuleosh.ui.routes.tenant_routes._require_auth", return_value=None):
            resp = handle_pipeline_usage(mock.MagicMock(), "/api/v1/pipeline/usage")
        assert resp["ok"] is False

    def test_corrupt_json_skipped(self, tmp_path):
        self._write_session(tmp_path, "good", org_id=1, token_total=10)
        bad = tmp_path / ".osh" / "sessions" / "bad"
        bad.mkdir(parents=True)
        (bad / "session.json").write_text("{not json")
        resp = self._call(self._make_user("admin", 1), tmp_path)
        assert len(resp["runs"]) == 1
        assert resp["total_tokens"] == 10


class TestSessionUsagePersistence:
    """PipelineSession to_dict 持久化 org_id/token_usage（session.json + store 来源）。"""

    def test_to_dict_includes_usage(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        s = PipelineSession("persist-test", str(tmp_path / "spec.md"), org_id=7)
        s.token_usage_total = 123
        s.token_usage_steps = [{"step": "arch", "usage": {"total_tokens": 123}}]
        d = s.to_dict()
        assert d["org_id"] == 7
        assert d["token_usage_total"] == 123
        assert d["token_usage_steps"][0]["step"] == "arch"


class TestUsageRecording:
    """消费计量链路: record_pipeline_run → usage_log → get_monthly_usage。"""

    def test_record_pipeline_run_writes_usage_log(self, tmp_path):
        from yuleosh.store import Store
        from yuleosh.usage import record_pipeline_run

        store = Store(str(tmp_path / "store.db"))
        store.reset()
        record_pipeline_run(store, org_id=5, project_id=0, llm_tokens=500)
        monthly = store.get_monthly_usage(5)
        assert monthly["pipeline_runs"] == 1
        assert monthly["llm_tokens"] == 500

    def test_get_usage_summary_includes_llm_tokens(self, tmp_path):
        from yuleosh.store import Store
        from yuleosh.usage import get_usage_summary, record_pipeline_run

        store = Store(str(tmp_path / "store2.db"))
        store.reset()
        record_pipeline_run(store, org_id=5, project_id=0, llm_tokens=1200)
        summary = get_usage_summary(store, org_id=5)
        assert summary["usage"]["llm_tokens"]["used"] == 1200
        assert summary["usage"]["pipeline_runs"]["used"] == 1

    def test_async_runner_record_usage_skips_org0(self):
        from yuleosh.pipeline.async_runner import _record_pipeline_usage
        # _record_pipeline_usage 函数内 import record_pipeline_run → patch 源头模块
        with mock.patch(
            "yuleosh.usage.record_pipeline_run"
        ) as m_record:
            _record_pipeline_usage(0)
            m_record.assert_not_called()

    def test_async_runner_record_usage_records(self):
        from yuleosh.pipeline.async_runner import _record_pipeline_usage
        with mock.patch(
            "yuleosh.usage.record_pipeline_run"
        ) as m_record:
            _record_pipeline_usage(5)
            m_record.assert_called_once()
            args = m_record.call_args
            assert args[0][1] == 5  # org_id

    def test_async_runner_submit_passes_org_id(self):
        from yuleosh.pipeline import async_runner
        with mock.patch.object(async_runner, "_get_pool") as m_pool:
            job_id = async_runner.submit_full_pipeline(
                "/tmp/proj", config_json=None, arxml_content=None, org_id=3
            )
            job = async_runner._PIPELINE_JOBS[job_id]
            assert job["org_id"] == 3
            # pool.submit 传了 org_id 给 _run_full_pipeline
            submit_args = m_pool.return_value.submit.call_args[0]
            assert submit_args[-1] == 3
