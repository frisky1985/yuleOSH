# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""P0 tests for GET /api/v1/pipeline/checkpoint — CheckpointEngine 看板数据源。

Covers:
  - authentication required (401 without valid session)
  - sqlite 后端读取 33 步状态
  - JSON 后端兜底
  - 无状态记录 → ok=True, steps=[]
  - 只读视图：不写状态、不抛异常（容错）
"""

from datetime import datetime, timezone
from unittest import mock

import jwt as pyjwt
import pytest

_TEST_USER_ID = 990001
_TEST_SECRET = "test-jwt-secret-for-ci-only-not-for-production"


@pytest.fixture(autouse=True)
def _seed_user_session():
    """Seed store users + sessions so JWT auth resolves (same as trigger tests)."""
    import logging

    from yuleosh.store import Store, _session_token_hash

    store = Store()
    token = _valid_token()
    now = datetime.now(timezone.utc).isoformat()
    store.conn.execute(
        "INSERT OR IGNORE INTO organizations (id, name, slug, created_at) "
        "VALUES (?, ?, ?, ?)",
        (1, "Acme", "acme", now),
    )
    store.conn.execute(
        "INSERT OR IGNORE INTO users (id, org_id, email, role, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (_TEST_USER_ID, 1, "board@t.com", "admin", now),
    )
    store.conn.execute(
        "INSERT OR IGNORE INTO user_sessions "
        "(user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (_TEST_USER_ID, _session_token_hash(token), now, "2099-12-31"),
    )
    store.conn.commit()
    yield
    try:
        store.conn.execute("DELETE FROM users WHERE id=?", (_TEST_USER_ID,))
        store.conn.execute("DELETE FROM user_sessions WHERE user_id=?", (_TEST_USER_ID,))
        store.conn.commit()
    except Exception as e:  # noqa: BLE001 — cleanup best-effort
        logging.getLogger("test.board").warning("cleanup failed: %s", e)


def _valid_token() -> str:
    return pyjwt.encode(
        {"user_id": _TEST_USER_ID, "org_id": 1, "email": "board@t.com",
         "iat": 0, "exp": 9999999999},
        _TEST_SECRET, algorithm="HS256",
    )


def _call(path: str, token: str | None = None):
    """直接调用 handle_pipeline_checkpoint（不经 HTTP 层）。"""
    from yuleosh.ui.routes.pipeline_routes import handle_pipeline_checkpoint

    handler = mock.MagicMock()
    handler.headers = {}
    if token:
        handler.headers["Authorization"] = f"Bearer {token}"
        handler.client_address = ("127.0.0.1", 12345)
        handler._request_start_time = 0.0
    return handle_pipeline_checkpoint(handler, path)


class TestPipelineCheckpoint:
    def test_requires_auth(self):
        resp = _call("/api/v1/pipeline/checkpoint", token=None)
        assert resp["ok"] is False
        assert "Authentication" in resp["error"]

    def test_no_state_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        resp = _call(f"/api/v1/pipeline/checkpoint?project_dir={tmp_path}",
                     token=_valid_token())
        assert resp["ok"] is True
        assert resp["steps"] == []
        assert resp["state"] is None

    def test_reads_sqlite_state(self, tmp_path, monkeypatch):
        """写入 sqlite 状态 → 接口能读回步骤级状态。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.engine.checkpoint import CheckpointEngine
        from yuleosh.engine.handler_adapter import HandlerAdapter

        engine = CheckpointEngine("board-test", str(tmp_path), state_backend="sqlite")
        out = tmp_path / "out.json"
        out.write_text("{}", encoding="utf-8")

        def handler(session):
            return str(out)

        engine.add_step("s1", "步骤一", HandlerAdapter(handler))
        engine.run()

        resp = _call(
            f"/api/v1/pipeline/checkpoint?project_dir={tmp_path}&pipeline=board-test",
            token=_valid_token(),
        )
        assert resp["ok"] is True
        assert resp["count"] == 1
        step = resp["steps"][0]
        assert step["step_id"] == "s1"
        assert step["status"] == "passed"

    def test_reads_json_fallback(self, tmp_path, monkeypatch):
        """sqlite 无记录时 JSON 后端兜底。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.engine.checkpoint import CheckpointEngine
        from yuleosh.engine.handler_adapter import HandlerAdapter

        engine = CheckpointEngine("board-json", str(tmp_path), state_backend="json")
        out = tmp_path / "out.json"
        out.write_text("{}", encoding="utf-8")

        def handler(session):
            return str(out)

        engine.add_step("s1", "步骤一", HandlerAdapter(handler))
        engine.run()

        # sqlite 后端找不到（engine 写的是 json）→ 应 fallback 到 json
        resp = _call(
            f"/api/v1/pipeline/checkpoint?project_dir={tmp_path}&pipeline=board-json",
            token=_valid_token(),
        )
        assert resp["ok"] is True
        assert resp["count"] == 1
        assert resp["steps"][0]["step_id"] == "s1"

    def test_corrupted_state_returns_error_not_crash(self, tmp_path, monkeypatch):
        """损坏的 sqlite db → 返回 ok=False + error，不抛异常。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        db_dir = tmp_path / ".yuleosh"
        db_dir.mkdir(parents=True, exist_ok=True)
        (db_dir / "checkpoint-state.db").write_bytes(b"this is not a sqlite db")

        resp = _call(f"/api/v1/pipeline/checkpoint?project_dir={tmp_path}",
                     token=_valid_token())
        # 容错：要么 ok=True 空列表（fallback 也失败），要么 ok=False 带 error
        assert resp["ok"] in (True, False)
        if resp["ok"]:
            assert resp["steps"] == []
        else:
            assert "error" in resp


# ---------------------------------------------------------------------------
# B3-看板操作：POST /api/v1/pipeline/retry + resume（异步执行器）
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_engine_op_active():
    """每测试前清空 _ENGINE_OP_ACTIVE，防止跨测试/跨文件残留（模块级可变状态）。"""
    from yuleosh.api import pipeline as api_pipeline

    api_pipeline._ENGINE_OP_ACTIVE.clear()
    yield
    api_pipeline._ENGINE_OP_ACTIVE.clear()


def _call_retry(body: dict, token: str | None = None, monkeypatch=None):
    """直接调用 _retry_pipeline（不经 HTTP 层）。"""
    from yuleosh.api import pipeline as api_pipeline

    if monkeypatch:
        # 避免真实启动后台线程（测试只验证请求路径 + 参数校验）
        monkeypatch.setattr(
            api_pipeline, "_run_engine_op",
            lambda *a, **kw: None,
        )
    return api_pipeline._retry_pipeline(body)


def _call_resume(body: dict, token: str | None = None, monkeypatch=None):
    """直接调用 _resume_pipeline（不经 HTTP 层）。"""
    from yuleosh.api import pipeline as api_pipeline

    if monkeypatch:
        monkeypatch.setattr(
            api_pipeline, "_run_engine_op",
            lambda *a, **kw: None,
        )
    return api_pipeline._resume_pipeline(body)


class TestPipelineRetry:
    def test_retry_requires_step_id(self, monkeypatch):
        resp, code = _call_retry({}, token=_valid_token(), monkeypatch=monkeypatch)
        assert code == 400
        assert "step_id" in resp["error"]

    def test_retry_requires_project_dir(self, monkeypatch):
        # test_api.py 导入时 setdefault OSH_HOME，此处需清掉才能测"两者皆无"
        monkeypatch.delenv("OSH_HOME", raising=False)
        resp, code = _call_retry(
            {"step_id": "s1"}, token=_valid_token(), monkeypatch=monkeypatch)
        assert code == 400
        assert "project_dir" in resp["error"]

    def test_retry_rejects_path_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        resp, code = _call_retry(
            {"step_id": "s1", "project_dir": "/etc"},
            token=_valid_token(), monkeypatch=monkeypatch)
        assert code == 403 or code == 400
        assert resp["ok"] is False

    def test_retry_starts_and_returns_started(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.api import pipeline as api_pipeline

        try:
            resp, code = _call_retry(
                {"step_id": "s1", "project_dir": str(tmp_path)},
                token=_valid_token(), monkeypatch=monkeypatch)
            assert code == 200
            assert resp["ok"] is True
            data = resp["data"]
            assert data["status"] == "started"
            assert data["op"] == "retry"
            assert data["step_id"] == "s1"
        finally:
            # mock 掉 _run_engine_op 后线程不执行 finally pop，需手动清理
            api_pipeline._ENGINE_OP_ACTIVE.pop("agent-pipeline", None)

    def test_retry_sets_active_flag_and_locks_second(self, tmp_path, monkeypatch):
        """并发保护：同一 pipeline 第二次请求返回 409。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.api import pipeline as api_pipeline

        # 模拟已有操作在跑
        api_pipeline._ENGINE_OP_ACTIVE["agent-pipeline"] = True
        try:
            resp, code = _call_retry(
                {"step_id": "s1", "project_dir": str(tmp_path)},
                token=_valid_token(), monkeypatch=monkeypatch)
            assert code == 409
            assert "already has a control operation" in resp["error"]
        finally:
            api_pipeline._ENGINE_OP_ACTIVE.pop("agent-pipeline", None)


class TestPipelineResume:
    def test_resume_requires_project_dir(self, monkeypatch):
        # test_api.py 导入时 setdefault OSH_HOME，此处需清掉才能测"两者皆无"
        monkeypatch.delenv("OSH_HOME", raising=False)
        resp, code = _call_resume({}, token=_valid_token(), monkeypatch=monkeypatch)
        assert code == 400
        assert "project_dir" in resp["error"]

    def test_resume_starts_and_returns_started(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.api import pipeline as api_pipeline

        try:
            resp, code = _call_resume(
                {"project_dir": str(tmp_path)},
                token=_valid_token(), monkeypatch=monkeypatch)
            assert code == 200
            assert resp["ok"] is True
            data = resp["data"]
            assert data["status"] == "started"
            assert data["op"] == "resume"
        finally:
            api_pipeline._ENGINE_OP_ACTIVE.pop("agent-pipeline", None)

    def test_resume_locks_second(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.api import pipeline as api_pipeline

        api_pipeline._ENGINE_OP_ACTIVE["agent-pipeline"] = True
        try:
            _resp, code = _call_resume(
                {"project_dir": str(tmp_path)},
                token=_valid_token(), monkeypatch=monkeypatch)
            assert code == 409
        finally:
            api_pipeline._ENGINE_OP_ACTIVE.pop("agent-pipeline", None)
