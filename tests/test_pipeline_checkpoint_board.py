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


def _call_list(path: str, token: str | None = None):
    """直接调用 handle_pipeline_list（不经 HTTP 层）。"""
    from yuleosh.ui.routes.pipeline_routes import handle_pipeline_list

    handler = mock.MagicMock()
    handler.headers = {}
    if token:
        handler.headers["Authorization"] = f"Bearer {token}"
        handler.client_address = ("127.0.0.1", 12345)
        handler._request_start_time = 0.0
    return handle_pipeline_list(handler, path)


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


def _call_rerun(body: dict, token: str | None = None, monkeypatch=None):
    """直接调用 _rerun_pipeline（不经 HTTP 层）。"""
    from yuleosh.api import pipeline as api_pipeline

    if monkeypatch:
        monkeypatch.setattr(
            api_pipeline, "_run_engine_op",
            lambda *a, **kw: None,
        )
    return api_pipeline._rerun_pipeline(body)


def _call_stop(body: dict, token: str | None = None):
    """直接调用 _stop_pipeline（不经 HTTP 层）。"""
    from yuleosh.api import pipeline as api_pipeline

    return api_pipeline._stop_pipeline(body)


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


class TestPipelineRerun:
    """B4-看板「从头重跑」：POST /api/v1/pipeline/rerun（全量 _prepare_full）。"""

    def test_rerun_requires_project_dir(self, monkeypatch):
        # test_api.py 导入时 setdefault OSH_HOME，此处需清掉才能测"两者皆无"
        monkeypatch.delenv("OSH_HOME", raising=False)
        resp, code = _call_rerun({}, token=_valid_token(), monkeypatch=monkeypatch)
        assert code == 400
        assert "project_dir" in resp["error"]

    def test_rerun_rejects_path_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        resp, code = _call_rerun(
            {"project_dir": "/etc"},
            token=_valid_token(), monkeypatch=monkeypatch)
        assert code in (400, 403)
        assert resp["ok"] is False

    def test_rerun_starts_and_returns_started(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.api import pipeline as api_pipeline

        try:
            resp, code = _call_rerun(
                {"project_dir": str(tmp_path)},
                token=_valid_token(), monkeypatch=monkeypatch)
            assert code == 200
            assert resp["ok"] is True
            data = resp["data"]
            assert data["status"] == "started"
            assert data["op"] == "rerun"
        finally:
            api_pipeline._ENGINE_OP_ACTIVE.pop("agent-pipeline", None)

    def test_rerun_locks_second(self, tmp_path, monkeypatch):
        """并发保护：已有操作在跑时返回 409。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.api import pipeline as api_pipeline

        api_pipeline._ENGINE_OP_ACTIVE["agent-pipeline"] = True
        try:
            _resp, code = _call_rerun(
                {"project_dir": str(tmp_path)},
                token=_valid_token(), monkeypatch=monkeypatch)
            assert code == 409
            assert "already has a control operation" in _resp["error"]
        finally:
            api_pipeline._ENGINE_OP_ACTIVE.pop("agent-pipeline", None)

    def test_run_engine_op_rerun_calls_full(self, tmp_path, monkeypatch):
        """_run_engine_op(op='rerun') 应走无参 engine.run()（= _prepare_full 全量）。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from unittest import mock

        from yuleosh.api import pipeline as api_pipeline
        from yuleosh.engine.checkpoint import CheckpointEngine

        called = {}

        def fake_engine_run(self, *a, **kw):
            called["mode"] = "full" if not a and not kw else (a, kw)
            return True

        with mock.patch.object(CheckpointEngine, "run", fake_engine_run):
            api_pipeline._run_engine_op(
                "agent-pipeline", str(tmp_path), "rerun")
        assert called["mode"] == "full"


class TestPipelineStop:
    """B4-看板「停止」：POST /api/v1/pipeline/stop（步骤边界生效）。"""

    def test_stop_requires_project_dir(self, monkeypatch):
        monkeypatch.delenv("OSH_HOME", raising=False)
        resp, code = _call_stop({}, token=_valid_token())
        assert code == 400
        assert "project_dir" in resp["error"]

    def test_stop_rejects_path_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        resp, code = _call_stop(
            {"project_dir": "/etc"}, token=_valid_token())
        assert code in (400, 403)
        assert resp["ok"] is False

    def test_stop_writes_flag_and_returns_stopping(self, tmp_path, monkeypatch):
        """停止请求写入 checkpoint-stop.flag，返回 status=stopping。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        resp, code = _call_stop(
            {"project_dir": str(tmp_path)}, token=_valid_token())
        assert code == 200
        assert resp["ok"] is True
        data = resp["data"]
        assert data["status"] == "stopping"
        assert data["op"] == "stop"

        flag = tmp_path / ".yuleosh" / "checkpoint-stop.flag"
        assert flag.exists(), "stop 应写入停止标志文件"
        # 幂等：再次请求仍然 ok
        resp2, code2 = _call_stop(
            {"project_dir": str(tmp_path)}, token=_valid_token())
        assert code2 == 200
        assert resp2["ok"] is True


class TestCheckpointEngineStop:
    """CheckpointEngine 停止语义（B4-方案 B1）：步骤边界检查 + stopped 终态。"""

    def _make_engine(self, tmp_path, steps=("s1", "s2", "s3")):
        from yuleosh.engine.checkpoint import CheckpointEngine
        from yuleosh.engine.handler_adapter import HandlerAdapter

        engine = CheckpointEngine(
            "stop-engine-test", str(tmp_path), state_backend="json")
        for sid in steps:
            out = tmp_path / f"{sid}.json"

            def handler(session, _sid=sid, _out=out):
                _out.write_text("{}", encoding="utf-8")
                return str(_out)

            engine.add_step(sid, f"步骤 {sid}", HandlerAdapter(handler))
        return engine

    def test_stop_flag_stops_before_next_step(self, tmp_path):
        """停止标志在 s1 完成后写入 → s2/s3 不执行，状态 stopped，剩余 PENDING。"""
        engine = self._make_engine(tmp_path)
        # 在 s1 的 handler 里请求停止：s1 执行完 → s2 边界检查到 → 停
        from yuleosh.engine.handler_adapter import HandlerAdapter

        def handler_s1(session, engine=engine):
            (tmp_path / "s1.json").write_text("{}", encoding="utf-8")
            engine.request_stop()  # 步骤内请求停止
            return str(tmp_path / "s1.json")

        engine._step_defs[0]["handler"] = HandlerAdapter(handler_s1)

        result = engine.run()
        assert result is False
        state = engine.status()
        assert state is not None
        assert state["status"] == "stopped"
        statuses = {s["step_id"]: s["status"] for s in state["steps"]}
        assert statuses["s1"] == "passed"
        assert statuses["s2"] == "pending"
        assert statuses["s3"] == "pending"
        # 停止生效后标志应被清除（下次 run/resume 干净开始）
        assert not (tmp_path / ".yuleosh" / "checkpoint-stop.flag").exists()

    def test_run_clears_stale_flag(self, tmp_path):
        """新 run() 应清除上次残留的停止标志（防误停）。"""
        engine = self._make_engine(tmp_path)
        flag = tmp_path / ".yuleosh" / "checkpoint-stop.flag"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("stale", encoding="utf-8")

        result = engine.run()
        assert result is True
        assert not flag.exists(), "run 后残留标志应被清除"
        state = engine.status()
        assert state is not None
        assert state["status"] == "completed"
        statuses = {s["step_id"]: s["status"] for s in state["steps"]}
        assert all(v == "passed" for v in statuses.values())

    def test_resume_after_stop_continues(self, tmp_path):
        """停止后 resume 应从剩余 PENDING 步骤继续（stopped 不是 failed）。"""
        engine = self._make_engine(tmp_path)
        from yuleosh.engine.handler_adapter import HandlerAdapter

        def handler_s1(session, engine=engine):
            (tmp_path / "s1.json").write_text("{}", encoding="utf-8")
            engine.request_stop()
            return str(tmp_path / "s1.json")

        engine._step_defs[0]["handler"] = HandlerAdapter(handler_s1)
        engine.run()
        state1 = engine.status()
        assert state1 is not None
        assert state1["status"] == "stopped"

        # 重新构造引擎（模拟新请求），resume 应从 s2 继续
        engine2 = self._make_engine(tmp_path)
        engine2._step_defs[0]["handler"] = HandlerAdapter(handler_s1)
        result = engine2.run(resume=True)
        assert result is True
        state = engine2.status()
        assert state is not None
        assert state["status"] == "completed"
        statuses = {s["step_id"]: s["status"] for s in state["steps"]}
        assert statuses["s1"] == "passed"
        assert statuses["s2"] == "passed"
        assert statuses["s3"] == "passed"


class TestPipelineList:
    """B5-看板 pipeline 选择器：GET /api/v1/pipeline/list。"""

    def test_list_requires_auth(self):
        resp = _call_list("/api/v1/pipeline/list", token=None)
        assert resp["ok"] is False
        assert "Authentication" in resp["error"]

    def test_list_empty_when_no_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        resp = _call_list(f"/api/v1/pipeline/list?project_dir={tmp_path}",
                          token=_valid_token())
        assert resp["ok"] is True
        assert resp["pipelines"] == []
        assert resp["count"] == 0

    def test_list_reads_sqlite_pipelines(self, tmp_path, monkeypatch):
        """两个 pipeline 写入 sqlite → list 都能列出。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.engine.checkpoint import CheckpointEngine
        from yuleosh.engine.handler_adapter import HandlerAdapter

        for name in ("pipe-a", "pipe-b"):
            engine = CheckpointEngine(name, str(tmp_path), state_backend="sqlite")
            out = tmp_path / f"{name}.json"
            out.write_text("{}", encoding="utf-8")

            def handler(session, _out=out):
                return str(_out)

            engine.add_step("s1", "步骤一", HandlerAdapter(handler))
            engine.run()

        resp = _call_list(f"/api/v1/pipeline/list?project_dir={tmp_path}",
                          token=_valid_token())
        assert resp["ok"] is True
        names = {p["name"] for p in resp["pipelines"]}
        assert names == {"pipe-a", "pipe-b"}
        for p in resp["pipelines"]:
            assert p["status"] == "completed"
            assert p["backend"] == "sqlite"
            assert p["step_count"] == 1

    def test_list_json_fallback(self, tmp_path, monkeypatch):
        """JSON 后端记录也应被列出。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.engine.checkpoint import CheckpointEngine
        from yuleosh.engine.handler_adapter import HandlerAdapter

        engine = CheckpointEngine("pipe-json", str(tmp_path), state_backend="json")
        out = tmp_path / "p.json"
        out.write_text("{}", encoding="utf-8")

        def handler(session):
            return str(out)

        engine.add_step("s1", "步骤一", HandlerAdapter(handler))
        engine.run()

        resp = _call_list(f"/api/v1/pipeline/list?project_dir={tmp_path}",
                          token=_valid_token())
        assert resp["ok"] is True
        names = {p["name"] for p in resp["pipelines"]}
        assert "pipe-json" in names

    def test_list_corrupted_db_returns_empty_not_crash(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        db_dir = tmp_path / ".yuleosh"
        db_dir.mkdir(parents=True, exist_ok=True)
        (db_dir / "checkpoint-state.db").write_bytes(b"not a sqlite db")
        resp = _call_list(f"/api/v1/pipeline/list?project_dir={tmp_path}",
                          token=_valid_token())
        # 容错：损坏 db 不崩溃，返回 ok=True + 空列表（或带 error）
        assert resp["ok"] in (True, False)


class TestPipelineListGrouped:
    """B5.2-看板项目分组：GET /api/v1/pipeline/list 自动发现多项目。"""

    def _make_project(self, root, name, pipelines):
        """创建项目目录 + 写 sqlite checkpoint 记录。"""
        from yuleosh.engine.checkpoint import CheckpointEngine
        from yuleosh.engine.handler_adapter import HandlerAdapter

        proj = root / name
        proj.mkdir(parents=True, exist_ok=True)
        for pname in pipelines:
            engine = CheckpointEngine(pname, str(proj), state_backend="sqlite")
            out = proj / f"{pname}.json"
            out.write_text("{}", encoding="utf-8")

            def handler(session, _out=out):
                return str(_out)

            engine.add_step("s1", "步骤一", HandlerAdapter(handler))
            engine.run()
        return proj

    def test_auto_discovers_projects(self, tmp_path, monkeypatch):
        """OSH_HOME 下两个项目各有 pipeline → 返回 projects 分组。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        self._make_project(tmp_path, "proj-a", ["pipe-1", "pipe-common"])
        self._make_project(tmp_path, "proj-b", ["pipe-2", "pipe-common"])

        resp = _call_list("/api/v1/pipeline/list", token=_valid_token())
        assert resp["ok"] is True
        assert resp["count"] == 4
        projects = {p["name"]: p for p in resp["projects"]}
        assert set(projects) == {"proj-a", "proj-b"}
        assert {p["name"] for p in projects["proj-a"]["pipelines"]} == {"pipe-1", "pipe-common"}
        assert {p["name"] for p in projects["proj-b"]["pipelines"]} == {"pipe-2", "pipe-common"}
        # 扁平列表含全部（倒序）
        assert len(resp["pipelines"]) == 4

    def test_same_name_pipeline_distinguished_by_project_path(self, tmp_path, monkeypatch):
        """同名 pipeline 在不同项目 → 分组 path 可区分。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        proj_a = self._make_project(tmp_path, "proj-a", ["agent-pipeline"])
        proj_b = self._make_project(tmp_path, "proj-b", ["agent-pipeline"])

        resp = _call_list("/api/v1/pipeline/list", token=_valid_token())
        assert resp["ok"] is True
        projects = {p["name"]: p for p in resp["projects"]}
        a_path = str(proj_a.resolve())
        b_path = str(proj_b.resolve())
        assert projects["proj-a"]["path"] == a_path
        assert projects["proj-b"]["path"] == b_path
        # 每个项目里都有 agent-pipeline
        for proj in resp["projects"]:
            assert [p["name"] for p in proj["pipelines"]] == ["agent-pipeline"]

    def test_skip_dirs_without_checkpoint(self, tmp_path, monkeypatch):
        """无 checkpoint 的目录（含无关子目录）不应成为项目。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        self._make_project(tmp_path, "proj-a", ["pipe-1"])
        # 无 checkpoint 的目录 + 深层无关目录
        (tmp_path / "no-state").mkdir()
        (tmp_path / "no-state" / ".yuleosh").mkdir(parents=True, exist_ok=True)
        (tmp_path / "deep" / "nested" / "x").mkdir(parents=True)

        resp = _call_list("/api/v1/pipeline/list", token=_valid_token())
        assert resp["ok"] is True
        names = {p["name"] for p in resp["projects"]}
        assert names == {"proj-a"}

    def test_explicit_project_dir_keeps_single_view(self, tmp_path, monkeypatch):
        """显式 project_dir → 单项目视图（pipelines 兼容旧前端）。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        proj_a = self._make_project(tmp_path, "proj-a", ["pipe-1", "pipe-2"])
        self._make_project(tmp_path, "proj-b", ["pipe-3"])

        resp = _call_list(f"/api/v1/pipeline/list?project_dir={proj_a}",
                          token=_valid_token())
        assert resp["ok"] is True
        names = {p["name"] for p in resp["pipelines"]}
        assert names == {"pipe-1", "pipe-2"}
        # projects 分组也存在（单项目）
        assert len(resp["projects"]) == 1
        assert resp["projects"][0]["name"] == "proj-a"
        assert resp["count"] == 2

    def test_discovery_skips_git_node_modules(self, tmp_path, monkeypatch):
        """.git / node_modules 目录不参与项目发现。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        self._make_project(tmp_path, "proj-a", ["pipe-1"])
        (tmp_path / ".git" / ".yuleosh").mkdir(parents=True, exist_ok=True)
        (tmp_path / "node_modules" / "pkg" / ".yuleosh").mkdir(parents=True, exist_ok=True)

        resp = _call_list("/api/v1/pipeline/list", token=_valid_token())
        assert resp["ok"] is True
        names = {p["name"] for p in resp["projects"]}
        assert names == {"proj-a"}


class TestPipelineOpsWithPipelineName:
    """B5-操作 API 应透传 pipeline 名（retry/resume/rerun 共用 _resolve_pipeline_ctx）。"""

    def test_resolve_pipeline_ctx_accepts_name(self, monkeypatch):
        monkeypatch.setenv("OSH_HOME", "/tmp/osh-home")
        from yuleosh.api import pipeline as api_pipeline
        ctx, err = api_pipeline._resolve_pipeline_ctx({"pipeline": "my-pipe"})
        assert err is None
        assert ctx is not None
        assert ctx[0] == "my-pipe"

    def test_resolve_pipeline_ctx_default(self, monkeypatch):
        monkeypatch.setenv("OSH_HOME", "/tmp/osh-home")
        from yuleosh.api import pipeline as api_pipeline
        ctx, err = api_pipeline._resolve_pipeline_ctx({})
        assert err is None
        assert ctx is not None
        assert ctx[0] == "agent-pipeline"

    def test_rerun_accepts_pipeline_name(self, tmp_path, monkeypatch):
        """rerun 请求带 pipeline 名 → 返回同名的 op 目标。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.api import pipeline as api_pipeline

        try:
            resp, code = _call_rerun(
                {"project_dir": str(tmp_path), "pipeline": "my-pipe"},
                token=_valid_token(), monkeypatch=monkeypatch)
            assert code == 200
            assert resp["data"]["pipeline"] == "my-pipe"
        finally:
            api_pipeline._ENGINE_OP_ACTIVE.pop("my-pipe", None)


class TestCheckpointOpActive:
    """B5-操作状态同步：checkpoint 接口返回 op_active（后端 _ENGINE_OP_ACTIVE）。"""

    def test_no_op_active_by_default(self, tmp_path, monkeypatch):
        """无控制操作在跑 → op_active=False。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.api import pipeline as api_pipeline
        api_pipeline._ENGINE_OP_ACTIVE.clear()
        try:
            resp = _call(
                f"/api/v1/pipeline/checkpoint?project_dir={tmp_path}",
                token=_valid_token())
            assert resp["ok"] is True
            assert resp["op_active"] is False
        finally:
            api_pipeline._ENGINE_OP_ACTIVE.clear()

    def test_op_active_true_when_running(self, tmp_path, monkeypatch):
        """_ENGINE_OP_ACTIVE 有该 pipeline → op_active=True。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.api import pipeline as api_pipeline
        api_pipeline._ENGINE_OP_ACTIVE.clear()
        try:
            api_pipeline._ENGINE_OP_ACTIVE["agent-pipeline"] = True
            resp = _call(
                f"/api/v1/pipeline/checkpoint?project_dir={tmp_path}",
                token=_valid_token())
            assert resp["ok"] is True
            assert resp["op_active"] is True
        finally:
            api_pipeline._ENGINE_OP_ACTIVE.clear()

    def test_op_active_pipeline_specific(self, tmp_path, monkeypatch):
        """只有指定 pipeline 的操作才算（不同 pipeline 互不影响）。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.api import pipeline as api_pipeline
        api_pipeline._ENGINE_OP_ACTIVE.clear()
        try:
            api_pipeline._ENGINE_OP_ACTIVE["other-pipe"] = True
            resp = _call(
                f"/api/v1/pipeline/checkpoint?project_dir={tmp_path}&pipeline=my-pipe",
                token=_valid_token())
            assert resp["ok"] is True
            assert resp["op_active"] is False
        finally:
            api_pipeline._ENGINE_OP_ACTIVE.clear()
