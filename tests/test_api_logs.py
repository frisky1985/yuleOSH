"""Unit tests for yuleosh.api.logs (设计文档模块⑦ — 测试日志管理 API).

Covers the logs routes offline against a tmp_path-backed fake sessions tree
(OSH_HOME monkeypatched to tmp_path, .osh/sessions/<run_id>/*.log + session.json):
  - GET /api/v1/logs — keyword / project / device / pipeline / limit filters,
    level detection, empty-root and no-match notes
  - GET /api/v1/logs/pipeline?run= — full run logs (200-line preview),
    404 unknown run, 400 missing run
  - GET /api/v1/logs/summary?project= — per-run file/line/ERROR counts
  - unknown sub-path -> 404
"""

# @tests src/yuleosh/api/pipeline.py

import json

import pytest

from yuleosh.api import logs as L

# Call the wrapped original: auth wrapper injects current_user as kwarg.
_handle = L.handle_logs.__wrapped__


def _call(method, path, query=None, body=None, user=None):
    if user is None:
        user = {"user_id": 1, "org_id": 1, "email": "t@example.com",
                "role": "admin"}
    return _handle(method, path, body or {}, query or {}, handler=None,
                   current_user=user)


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    """Point OSH_HOME at tmp_path and build a two-run sessions tree."""
    monkeypatch.setattr(L, "OSH_HOME", str(tmp_path))
    root = tmp_path / ".osh" / "sessions"

    run_a = root / "run-aaaa"
    run_a.mkdir(parents=True)
    (run_a / "session.json").write_text(json.dumps({
        "name": "integration-test",
        "run_id": "run-aaaa",
        "project": "can-demo",
        "status": "completed",
        "updated_at": "2026-08-15T10:00:00",
    }), encoding="utf-8")
    (run_a / "pipeline.log").write_text(
        "2026-08-15 10:00:01 INFO starting build\n"
        "2026-08-15 10:00:02 WARN flasher retry\n"
        "2026-08-15 10:00:03 ERROR flash failed on dev-001\n"
        "2026-08-15 10:00:04 INFO recovered\n",
        encoding="utf-8")
    (run_a / "serial.log").write_text(
        "2026-08-15 10:01:00 DEBUG can frame 0x123\n"
        "2026-08-15 10:01:01 ERROR CRC mismatch\n",
        encoding="utf-8")

    run_b = root / "run-bbbb"
    run_b.mkdir(parents=True)
    (run_b / "session.json").write_text(json.dumps({
        "name": "unit-tests",
        "run_id": "run-bbbb",
        "project": "can-demo",
        "status": "failed",
    }), encoding="utf-8")
    (run_b / "pipeline.log").write_text(
        "2026-08-15 11:00:00 INFO running unit tests\n"
        "2026-08-15 11:00:05 ERROR 3 tests failed\n",
        encoding="utf-8")
    return root


def _match(results, **filters):
    """Filter search results by field values (for compact assertions)."""
    return [r for r in results if all(r[k] == v for k, v in filters.items())]


# ── search ──────────────────────────────────────────────────────────────

class TestSearch:
    def test_search_all_lines(self, sessions):
        payload, status = _call("GET", "", query={})
        assert status == 200
        data = payload["data"]
        assert data["count"] == 8  # 4 + 2 + 2
        assert data["note"] is None
        for item in data["logs"]:
            assert set(item) == {"run_id", "file", "line", "content", "level",
                                 "updated_at"}
        # 每个文件第一条记录带正确 run_id / 文件名
        assert _match(data["logs"], run_id="run-aaaa", file="run-aaaa/pipeline.log")
        assert _match(data["logs"], run_id="run-bbbb", file="run-bbbb/pipeline.log")

    def test_search_keyword(self, sessions):
        payload, status = _call("GET", "", query={"query": "ERROR"})
        assert status == 200
        logs = payload["data"]["logs"]
        assert payload["data"]["count"] == 3  # 2 in run-a + 1 in run-b
        assert all(r["level"] == "ERROR" for r in logs)
        assert all("ERROR" in r["content"] for r in logs)

    def test_search_keyword_case_insensitive(self, sessions):
        payload, _ = _call("GET", "", query={"query": "crc"})
        assert payload["data"]["count"] == 1
        assert payload["data"]["logs"][0]["line"] == 2
        assert payload["data"]["logs"][0]["file"] == "run-aaaa/serial.log"

    def test_search_project(self, sessions):
        # project=can-demo -> 两个 run 都匹配（session.json project 字段）
        payload, _ = _call("GET", "", query={"project": "can-demo"})
        assert payload["data"]["count"] == 8
        # project 也匹配 run name（integration-test）
        payload, _ = _call("GET", "", query={"project": "integration"})
        assert payload["data"]["count"] == 6
        assert all(r["run_id"] == "run-aaaa" for r in payload["data"]["logs"])

    def test_search_device(self, sessions):
        payload, _ = _call("GET", "", query={"device": "dev-001"})
        logs = payload["data"]["logs"]
        assert payload["data"]["count"] == 1
        assert "dev-001" in logs[0]["content"]

    def test_search_pipeline(self, sessions):
        # pipeline=unit-tests 匹配 run-b 的 session name
        payload, _ = _call("GET", "", query={"pipeline": "unit-tests"})
        assert payload["data"]["count"] == 2
        assert all(r["run_id"] == "run-bbbb" for r in payload["data"]["logs"])

    def test_search_limit(self, sessions):
        payload, _ = _call("GET", "", query={"limit": "3"})
        assert payload["data"]["count"] == 3

    def test_search_limit_bad_value_falls_back(self, sessions):
        payload, _ = _call("GET", "", query={"limit": "abc"})
        assert payload["data"]["count"] == 8  # default 50

    def test_search_no_match_returns_note(self, sessions):
        payload, status = _call("GET", "", query={"query": "zzz-not-there"})
        assert status == 200
        assert payload["data"]["logs"] == []
        assert payload["data"]["count"] == 0
        assert payload["data"]["note"] is not None  # 真实数据优先，无 mock

    def test_search_empty_root(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L, "OSH_HOME", str(tmp_path))  # 无 .osh/sessions
        payload, status = _call("GET", "", query={})
        assert status == 200
        assert payload["data"]["logs"] == []
        assert payload["data"]["note"] is not None

    def test_level_detection(self, sessions):
        payload, _ = _call("GET", "", query={})
        by_content = {r["content"]: r["level"] for r in payload["data"]["logs"]}
        assert by_content["2026-08-15 10:00:02 WARN flasher retry"] == "WARN"
        assert by_content["2026-08-15 10:00:03 ERROR flash failed on dev-001"] == "ERROR"
        assert by_content["2026-08-15 10:01:00 DEBUG can frame 0x123"] == "DEBUG"
        assert by_content["2026-08-15 10:00:01 INFO starting build"] == "INFO"

    def test_search_without_query_returns_all_in_run(self, sessions):
        payload, _ = _call("GET", "", query={"pipeline": "run-aaaa"})
        assert payload["data"]["count"] == 6


# ── pipeline ────────────────────────────────────────────────────────────

class TestPipeline:
    def test_pipeline_full_logs(self, sessions):
        payload, status = _call("GET", "pipeline", query={"run": "run-aaaa"})
        assert status == 200
        data = payload["data"]
        assert data["run_id"] == "run-aaaa"
        assert data["project"] == "can-demo"
        assert data["status"] == "completed"
        assert data["count"] == 2
        files = {f["file"]: f for f in data["files"]}
        pl = files["run-aaaa/pipeline.log"]
        assert pl["lines"] == 4
        assert pl["truncated"] is False
        assert pl["content"].startswith("2026-08-15 10:00:01 INFO starting build")
        assert files["run-aaaa/serial.log"]["lines"] == 2

    def test_pipeline_preview_caps_at_200_lines(self, sessions):
        big = "\n".join(f"line {i}" for i in range(250))
        (sessions / "run-bbbb" / "big.log").write_text(big, encoding="utf-8")
        payload, _ = _call("GET", "pipeline", query={"run": "run-bbbb"})
        big_file = next(f for f in payload["data"]["files"]
                        if f["file"].endswith("big.log"))
        assert big_file["lines"] == 250
        assert big_file["preview_lines"] == L.PREVIEW_LINES
        assert big_file["truncated"] is True
        assert big_file["content"].count("\n") == L.PREVIEW_LINES - 1

    def test_pipeline_run_not_found(self, sessions):
        payload, status = _call("GET", "pipeline", query={"run": "nope"})
        assert status == 404
        assert "run not found: nope" in payload["error"]

    def test_pipeline_missing_run_param(self, sessions):
        payload, status = _call("GET", "pipeline", query={})
        assert status == 400
        assert "run parameter is required" in payload["error"]

    def test_pipeline_no_log_files(self, sessions):
        empty = sessions / "run-empty"
        empty.mkdir()
        (empty / "session.json").write_text('{"name": "empty"}', encoding="utf-8")
        payload, status = _call("GET", "pipeline", query={"run": "run-empty"})
        assert status == 200
        assert payload["data"]["files"] == []
        assert payload["data"]["note"] is not None


# ── summary ─────────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_all_runs(self, sessions):
        payload, status = _call("GET", "summary", query={})
        assert status == 200
        runs = {r["run_id"]: r for r in payload["data"]["runs"]}
        assert payload["data"]["count"] == 2
        a = runs["run-aaaa"]
        assert a["log_files"] == 2
        assert a["total_lines"] == 6
        assert a["error_count"] == 2  # pipeline.log ERROR + serial.log ERROR
        b = runs["run-bbbb"]
        assert b["log_files"] == 1
        assert b["total_lines"] == 2
        assert b["error_count"] == 1
        assert b["status"] == "failed"

    def test_summary_project_filter(self, sessions):
        payload, _ = _call("GET", "summary", query={"project": "integration"})
        runs = payload["data"]["runs"]
        assert payload["data"]["count"] == 1
        assert runs[0]["run_id"] == "run-aaaa"

    def test_summary_no_data_note(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L, "OSH_HOME", str(tmp_path))
        payload, status = _call("GET", "summary", query={})
        assert status == 200
        assert payload["data"]["runs"] == []
        assert payload["data"]["count"] == 0
        assert payload["data"]["note"] is not None


# ── routing / misc ──────────────────────────────────────────────────────

class TestRouting:
    def test_unknown_sub_path(self, sessions):
        payload, status = _call("GET", "bogus")
        assert status == 404

    def test_post_to_root_not_allowed(self, sessions):
        payload, status = _call("POST", "", body={})
        assert status == 405

    def test_auth_required_without_user(self, sessions):
        """handler=None 且无 current_user -> require_auth 401（fail closed）。"""
        payload, status = L.handle_logs("GET", "", {}, {}, handler=None)
        assert status == 401
