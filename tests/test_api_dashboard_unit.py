"""Unit tests for yuleosh.api.dashboard (v3.4.2b Wave 2a; P0-2 revised).

Covers the dashboard API routes offline:
  - handle_dashboard routing (all 7 routes + unknown -> 404)
  - projects (P0-2: real org-scoped data only — org filter, 503 on store
    failure, 401 fail-closed without org_id, 404 for unknown project_id;
    NO mock fallback)
  - swe-status (manifest path / mock fallback / corrupt manifest)
  - gap-analysis (real manifest items / pagination / severity filter)
  - evidence generate (subprocess success/failure/timeout/FileNotFound)
  - evidence status (missing/not-found/found)
  - coverage (real c-coverage.json + trend / corrupt / mock fallback)
  - misra-trend (real jsonl / KB articles / mock fallback)
  - helpers (_get_query_param / _find_latest_manifest / _build_swe_from_manifest
    / _estimate_swe_completed / _simulate_evidence_completion / _mock_note)
"""

# @tests src/yuleosh/api/dashboard.py

import json
import os
import sys
import subprocess

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.api import dashboard as D

# The auth wrapper injects current_user as a kwarg, but handle_dashboard
# has no **kwargs; unit tests call the wrapped original directly.
_handle = D.handle_dashboard.__wrapped__


def _req(method="GET", path="projects", body=None, query=None, org_id=1,
         current_user=None):
    """Call the wrapped handler with an authenticated current_user (P0-2)."""
    if current_user is None:
        current_user = {"user_id": 42, "org_id": org_id,
                        "email": "t@example.com", "role": "admin"}
    return _handle(method, path, body or {}, query or {}, handler=None,
                   current_user=current_user)


def _fake_store(projects):
    """Build a fake Store emulating list_org_projects (WHERE org_id=?)."""
    class FakeStore:
        def list_org_projects(self, org_id):
            return [dict(p) for p in projects if p.get("org_id") == org_id]
    return FakeStore


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Point OSH_HOME at tmp_path, reset global task state, and force the
    dashboard to skip the real SQLite-backed store (offline unit tests)."""
    monkeypatch.setattr(D, "OSH_HOME", str(tmp_path))
    D._ev_tasks.clear()

    class _NoStore:
        def __init__(self):
            raise RuntimeError("offline: no real store in unit tests")

    monkeypatch.setattr("yuleosh.store.Store", _NoStore)
    yield tmp_path


def _write(monkeypatch, tmp_path, relpath, content):
    p = tmp_path / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if isinstance(content, str) else json.dumps(content),
                 encoding="utf-8")
    return p


def _resp(result):
    """Unwrap (payload, status) tuple from json_ok/json_error."""
    return result


# ── handle_dashboard routing ───────────────────────────────────────────

class TestRouting:
    def test_projects_route(self):
        """GIVEN GET projects WHEN handle THEN explicit error (no mock, P0-2)."""
        payload, status = _req("GET", "projects")
        # Offline unit env has no real store — endpoint must fail explicitly
        # (503), never silently fall back to demo data.
        assert status == 503 and payload["ok"] is False
        assert "加载失败" in payload["error"]

    def test_swe_status_route(self):
        """GIVEN GET swe-status WHEN handle THEN swe dict + pct."""
        payload, _ = _handle("GET", "swe-status", {}, {}, handler=None)
        assert set(payload["data"]["swe"]) >= {"SWE1", "SWE6"}
        assert payload["data"]["overall_pct"] == 50.0

    def test_gap_analysis_route(self):
        """GIVEN GET gap-analysis WHEN handle THEN items + summary."""
        payload, _ = _handle("GET", "gap-analysis", {}, {}, handler=None)
        assert payload["data"]["summary"]["total"] == 13
        assert payload["data"]["has_more"] is True

    def test_evidence_generate_route(self, tmp_path):
        """GIVEN POST evidence/generate WHEN handle THEN task response.

        T11-SSE：生成在后台线程跑，POST 立即返回 running（不再阻塞最长
        300s）；join 工作线程后应落到 completed。
        """
        payload, _ = _handle("POST", "evidence/generate",
                                        {"project_id": "p1"}, {}, handler=None)
        assert payload["ok"] is True
        assert payload["data"]["status"] == "running"
        task = _wait_evidence_task(payload["data"]["task_id"])
        assert task["status"] == "completed"  # simulation succeeds

    def test_evidence_generate_rejects_outside_osh_home(self, tmp_path):
        """SEC-C1: dashboard evidence project_dir escaping OSH_HOME → 403,
        and no task record is created."""
        payload, status = _handle("POST", "evidence/generate",
                                  {"project_id": "p1", "project_dir": "/etc"},
                                  {}, handler=None)
        assert status == 403
        assert "inside OSH_HOME" in payload["error"]
        assert D._ev_tasks == {}  # fail fast before task creation

    def test_evidence_generate_rejects_traversal(self, tmp_path):
        """SEC-C1: ../ traversal in project_dir → 403."""
        payload, status = _handle("POST", "evidence/generate",
                                  {"project_dir": str(tmp_path / "..")},
                                  {}, handler=None)
        assert status == 403
        assert "inside OSH_HOME" in payload["error"]

    def test_evidence_status_route(self):
        """GIVEN GET evidence/status WHEN handle THEN task lookup."""
        D._ev_tasks["ev-task-abc"] = {"task_id": "ev-task-abc", "status": "running"}
        payload, _ = _handle(
            "GET", "evidence/status", {}, {"task_id": "ev-task-abc"}, None)
        assert payload["data"]["status"] == "running"

    def test_coverage_route(self):
        """GIVEN GET coverage WHEN handle THEN mock fallback."""
        payload, _ = _handle("GET", "coverage", {}, {}, handler=None)
        assert payload["data"]["line_pct"] == 58.3
        assert payload["data"]["display_mode"] == "absolute"

    def test_misra_trend_route(self):
        """GIVEN GET misra-trend WHEN handle THEN mock fallback."""
        payload, _ = _handle("GET", "misra-trend", {}, {}, handler=None)
        assert len(payload["data"]["weekly_trend"]) == 5
        assert payload["data"]["distribution"]["required"] == 218

    def test_unknown_route(self):
        """GIVEN unknown sub-path WHEN handle THEN 404."""
        payload, status = _handle("GET", "nope", {}, {}, handler=None)
        assert status == 404 and payload["ok"] is False

    def test_method_not_allowed(self):
        """GIVEN DELETE on projects WHEN handle THEN 404."""
        payload, status = _handle("DELETE", "projects", {}, {}, handler=None)
        assert status == 404


# ── projects (P0-2: real org-scoped data only, no mock fallback) ───────

class TestProjects:
    def test_store_unavailable_returns_503(self):
        """GIVEN store raising WHEN projects THEN 503, never mock fallback."""
        payload, status = _req("GET", "projects")
        assert status == 503
        assert payload["ok"] is False
        assert "加载失败" in payload["error"]
        # No demo-data note / no fabricated project rows
        assert "count" not in payload.get("data", {})

    def test_missing_org_id_fails_closed(self):
        """GIVEN no current_user.org_id WHEN projects THEN 401 (fail closed)."""
        payload, status = _req("GET", "projects",
                               current_user={"user_id": 1, "email": "x@y"})
        assert status == 401
        assert "org_id" in payload["error"]

    def test_project_id_filter(self, monkeypatch):
        """GIVEN project_id WHEN projects THEN single project from real data."""
        monkeypatch.setattr("yuleosh.store.Store", _fake_store([
            {"id": 1, "org_id": 1, "name": "Alpha", "slug": "alpha",
             "description": "d", "created_at": "2026-01-01"},
            {"id": 2, "org_id": 1, "name": "Beta", "slug": "beta",
             "description": "d", "created_at": "2026-01-02"},
        ]))
        payload, _ = _req("GET", "projects", query={"project_id": "2"})
        assert payload["data"]["count"] == 1
        assert payload["data"]["projects"][0]["name"] == "Beta"

    def test_project_id_not_found(self, monkeypatch):
        """GIVEN unknown project_id WHEN projects THEN 404."""
        monkeypatch.setattr("yuleosh.store.Store", _fake_store([
            {"id": 1, "org_id": 1, "name": "Alpha", "slug": "alpha",
             "description": "d", "created_at": "2026-01-01"},
        ]))
        payload, status = _req("GET", "projects", query={"project_id": "nope"})
        assert status == 404
        assert "not found" in payload["error"].lower()

    def test_real_projects_from_store(self, monkeypatch):
        """GIVEN real org_projects rows WHEN projects THEN real data used."""
        monkeypatch.setattr("yuleosh.store.Store", _fake_store([
            {"id": 1, "org_id": 1, "name": "RealProj", "slug": "real-proj",
             "description": "d", "created_at": "2026-01-01"},
        ]))
        payload, _ = _req("GET", "projects")
        assert payload["data"]["count"] == 1
        assert payload["data"]["projects"][0]["name"] == "RealProj"
        assert payload["data"]["note"] is None
        assert payload["data"]["projects"][0]["swe_total"] == 6

    def test_org_filtering_isolates_orgs(self, monkeypatch):
        """GIVEN projects in two orgs WHEN projects THEN only current org's."""
        monkeypatch.setattr("yuleosh.store.Store", _fake_store([
            {"id": 1, "org_id": 1, "name": "Org1Proj", "slug": "o1",
             "description": "d", "created_at": "2026-01-01"},
            {"id": 2, "org_id": 2, "name": "Org2Proj", "slug": "o2",
             "description": "d", "created_at": "2026-01-02"},
        ]))
        payload, _ = _req("GET", "projects", org_id=1)
        names = [p["name"] for p in payload["data"]["projects"]]
        assert names == ["Org1Proj"]  # Org2's project must NOT leak

    def test_org_with_zero_projects_returns_empty(self, monkeypatch):
        """GIVEN org with no projects WHEN projects THEN 200 empty (real state)."""
        monkeypatch.setattr("yuleosh.store.Store", _fake_store([]))
        payload, status = _req("GET", "projects", org_id=9)
        assert status == 200
        assert payload["data"]["count"] == 0
        assert payload["data"]["projects"] == []
        assert payload["data"]["note"] is None  # not demo data

    def test_store_error_returns_503(self, monkeypatch):
        """GIVEN store raising WHEN projects THEN 503, no fallback."""
        def boom():
            raise RuntimeError("db down")

        monkeypatch.setattr("yuleosh.store.Store", boom)
        payload, status = _req("GET", "projects")
        assert status == 503
        assert "count" not in payload.get("data", {})


# ── swe-status ─────────────────────────────────────────────────────────

class TestSweStatus:
    def test_manifest_data(self, _isolate):
        """GIVEN audit-manifest with swe_status WHEN swe-status THEN real."""
        tmp_path = _isolate
        _write(None, tmp_path, ".osh/evidence/audit-manifest.json", {
            "swe_status": {
                "SWE1": {"status": "pass", "name": "SWE.1", "description": "d",
                         "last_updated": "2026-01-01"},
                "SWE2": {"status": "fail", "name": "SWE.2", "description": "d",
                         "last_updated": "-"},
            }
        })
        payload, _ = _handle("GET", "swe-status", {}, {}, handler=None)
        assert payload["data"]["swe"]["SWE1"]["status"] == "completed"
        assert payload["data"]["swe"]["SWE2"]["status"] == "not_started"
        assert payload["data"]["note"] is None
        assert payload["data"]["overall_pct"] == 50.0

    def test_corrupt_manifest_falls_back(self, _isolate):
        """GIVEN corrupt manifest WHEN swe-status THEN mock fallback."""
        tmp_path = _isolate
        _write(None, tmp_path, ".osh/evidence/audit-manifest.json", "not json{{{")
        payload, _ = _handle("GET", "swe-status", {}, {}, handler=None)
        assert payload["data"]["total_count"] == 6

    def test_manifest_without_swe_status_falls_back(self, _isolate):
        """GIVEN manifest without swe_status WHEN swe-status THEN mock."""
        tmp_path = _isolate
        _write(None, tmp_path, ".osh/evidence/audit-manifest.json",
               {"integrity": {"total_artifacts": 3}})
        payload, _ = _handle("GET", "swe-status", {}, {}, handler=None)
        assert payload["data"]["overall_pct"] == 50.0


# ── gap-analysis ───────────────────────────────────────────────────────

class TestGapAnalysis:
    def test_mock_default_pagination(self):
        """GIVEN default params WHEN gap-analysis THEN page 1 of 10."""
        payload, _ = _handle("GET", "gap-analysis", {}, {}, handler=None)
        data = payload["data"]
        assert len(data["items"]) == 10
        assert data["page"] == 1 and data["limit"] == 10
        assert data["has_more"] is True
        # NOTE: computed from items; mock item list has 4 critical entries
        # (the hardcoded MOCK_GAP_ANALYSIS["summary"] says 3 — dead data)
        assert data["summary"]["critical"] == 4

    def test_page_2(self):
        """GIVEN page 2 WHEN gap-analysis THEN remaining items."""
        payload, _ = _handle(
            "GET", "gap-analysis", {}, {"page": "2"}, None)
        data = payload["data"]
        assert len(data["items"]) == 3
        assert data["has_more"] is False

    def test_severity_filter(self):
        """GIVEN severity=critical WHEN gap-analysis THEN only critical."""
        payload, _ = _handle(
            "GET", "gap-analysis", {}, {"severity": "critical"}, None)
        data = payload["data"]
        assert all(i["severity"] == "critical" for i in data["items"])
        assert data["summary"]["critical"] == 4

    def test_manifest_items(self, _isolate):
        """GIVEN manifest with gaps WHEN gap-analysis THEN real items."""
        tmp_path = _isolate
        _write(None, tmp_path, ".yuleosh/evidence-bundle/audit-manifest.json", {
            "gap_analysis": [
                {"id": "g1", "swe_area": "SWE.1", "description": "desc1",
                 "severity": "major", "status": "open",
                 "suggestion": "fix"},
                {"gap_id": "g2", "spec_ref": "SWE.2", "issue": "issue2",
                 "risk_level": "bogus", "status": "open",
                 "recommendation": "rec"},
            ]
        })
        payload, _ = _handle("GET", "gap-analysis", {}, {}, handler=None)
        data = payload["data"]
        assert data["note"] is None
        assert data["summary"]["total"] == 2
        severities = {i["severity"] for i in data["items"]}
        assert "major" in severities and "minor" in severities  # bogus -> minor

    def test_manifest_gaps_via_assessment(self, _isolate):
        """GIVEN assessment.gaps WHEN gap-analysis THEN items parsed."""
        tmp_path = _isolate
        _write(None, tmp_path, ".osh/evidence/audit-manifest.json", {
            "assessment": {"gaps": [
                {"id": "a1", "swe_area": "SWE.3", "description": "d3",
                 "severity": "minor", "status": "open", "suggestion": "s"},
            ]}
        })
        payload, _ = _handle("GET", "gap-analysis", {}, {}, handler=None)
        assert payload["data"]["summary"]["total"] == 1
        assert payload["data"]["items"][0]["swe_area"] == "SWE.3"


# ── evidence generate / status ─────────────────────────────────────────

class _FakeCompleted:
    def __init__(self, returncode=0, stderr="", stdout=""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


def _wait_evidence_task(task_id, timeout=10.0):
    """Wait for the background evidence worker to settle, then return the task.

    T11-SSE：证据包生成已从「POST 内同步阻塞」改为后台线程执行，POST 立即
    返回 status=running。断言终态前必须 join 工作线程，否则测出的是竞态。
    """
    import time as _t

    task = D._ev_tasks[task_id]
    thread = task.get("_thread")
    if thread is not None:
        thread.join(timeout)
    deadline = _t.time() + 1.0
    while _t.time() < deadline and task.get("status") == "running":
        _t.sleep(0.01)
    return task


class TestEvidenceGenerate:
    def test_success_with_manifest(self, monkeypatch, _isolate):
        """GIVEN CLI success + manifest WHEN generate THEN completed."""
        tmp_path = _isolate
        _write(None, tmp_path, ".yuleosh/evidence-bundle/audit-manifest.json", {
            "integrity": {"total_artifacts": 7},
        })
        monkeypatch.setattr(D.subprocess, "run",
                            lambda *a, **kw: _FakeCompleted(0))
        payload, status = _handle(
            "POST", "evidence/generate", {"project_id": "p1"}, {}, handler=None)
        assert payload["ok"] is True
        task_id = payload["data"]["task_id"]
        task = _wait_evidence_task(task_id)
        assert task["status"] == "completed"
        assert task["valid"] is True
        assert task["total_artifacts"] == 7

    def test_success_without_manifest(self, monkeypatch, _isolate):
        """GIVEN CLI success but no manifest WHEN generate THEN failed."""
        monkeypatch.setattr(D.subprocess, "run",
                            lambda *a, **kw: _FakeCompleted(0))
        payload, _ = _handle(
            "POST", "evidence/generate", {"project_id": "p1"}, {}, handler=None)
        task = _wait_evidence_task(payload["data"]["task_id"])
        assert task["status"] == "failed"
        assert "no manifest" in task["error"]

    def test_cli_failure(self, monkeypatch, _isolate):
        """GIVEN CLI returncode != 0 WHEN generate THEN failed with stderr."""
        monkeypatch.setattr(D.subprocess, "run",
                            lambda *a, **kw: _FakeCompleted(1, stderr="boom"))
        payload, _ = _handle(
            "POST", "evidence/generate", {"project_id": "p1"}, {}, handler=None)
        task = _wait_evidence_task(payload["data"]["task_id"])
        assert task["status"] == "failed"
        assert "boom" in task["error"]

    def test_timeout(self, monkeypatch, _isolate):
        """GIVEN TimeoutExpired WHEN generate THEN failed timeout msg."""

        def timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="x", timeout=300)

        monkeypatch.setattr(D.subprocess, "run", timeout)
        payload, _ = _handle(
            "POST", "evidence/generate", {"project_id": "p1"}, {}, handler=None)
        task = _wait_evidence_task(payload["data"]["task_id"])
        assert task["status"] == "failed"
        assert "timed out" in task["error"]

    def test_file_not_found_simulates(self, monkeypatch, _isolate):
        """GIVEN FileNotFoundError WHEN generate THEN simulated completion."""

        def nf(*a, **kw):
            raise FileNotFoundError("no cli")

        monkeypatch.setattr(D.subprocess, "run", nf)
        payload, _ = _handle(
            "POST", "evidence/generate", {"project_id": "p1"}, {}, handler=None)
        task = _wait_evidence_task(payload["data"]["task_id"])
        assert task["status"] == "completed"
        assert task["valid"] is True
        assert "演示" in task["note"]

    def test_generic_exception(self, monkeypatch, _isolate):
        """GIVEN unexpected exception WHEN generate THEN failed with message."""

        def boom(*a, **kw):
            raise ValueError("weird")

        monkeypatch.setattr(D.subprocess, "run", boom)
        payload, _ = _handle(
            "POST", "evidence/generate", {"project_id": "p1"}, {}, handler=None)
        task = _wait_evidence_task(payload["data"]["task_id"])
        assert task["status"] == "failed"
        assert "weird" in task["error"]

    def test_simulate_evidence_completion(self):
        """GIVEN task id WHEN simulate THEN completed + progress 100."""
        D._ev_tasks["t1"] = {"task_id": "t1", "status": "running",
                             "progress_pct": 0, "valid": False}
        D._simulate_evidence_completion("t1")
        task = D._ev_tasks["t1"]
        assert task["status"] == "completed"
        assert task["progress_pct"] == 100
        assert task["valid"] is True


class TestEvidenceStatus:
    def test_missing_task_id(self):
        """GIVEN no task_id WHEN status THEN 400."""
        payload, status = _handle(
            "GET", "evidence/status", {}, {}, handler=None)
        assert status == 400

    def test_task_not_found(self):
        """GIVEN unknown task WHEN status THEN 404."""
        payload, status = _handle(
            "GET", "evidence/status", {}, {"task_id": "nope"}, None)
        assert status == 404

    def test_found(self):
        """GIVEN existing task WHEN status THEN task dict returned."""
        D._ev_tasks["t9"] = {"task_id": "t9", "status": "running",
                             "progress_pct": 10, "valid": False}
        payload, status = _handle(
            "GET", "evidence/status", {}, {"task_id": "t9"}, None)
        assert status == 200
        assert payload["data"]["progress_pct"] == 10

    def test_status_excludes_private_keys(self):
        """GIVEN task with _thread WHEN status THEN private key stripped.

        T11-SSE：任务记录里挂了 Thread 对象，直接 json.dumps 整个 dict 会抛
        TypeError —— status 端点必须先过滤下划线前缀字段。
        """
        D._ev_tasks["t-th"] = {"task_id": "t-th", "status": "running",
                               "progress_pct": 10, "_thread": None}
        payload, status = _handle(
            "GET", "evidence/status", {}, {"task_id": "t-th"}, None)
        assert status == 200
        assert "_thread" not in payload["data"]
        assert payload["data"]["progress_pct"] == 10


# ── SSE streams (T11) ──────────────────────────────────────────────────

class _FakeWFile:
    def __init__(self):
        self.chunks: list = []

    def write(self, data):
        self.chunks.append(data)


class _FakeSSEHandler:
    """Minimal stand-in for OSHHandler that records what the SSE pump writes."""

    def __init__(self):
        self.wfile = _FakeWFile()
        self.headers: list = []
        self.status = None
        self.ended = False

    def send_response(self, code):
        self.status = code

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        self.ended = True

    def frames(self) -> str:
        return b"".join(self.wfile.chunks).decode("utf-8")


class TestSSEStream:
    """Unit tests for the shared SSE pump ``_sse_stream`` (T11-SSE)."""

    def test_emits_event_stream_headers(self):
        h = _FakeSSEHandler()
        D._sse_stream(h, "status", lambda: {"pct": 100}, lambda s: True)
        assert h.status == 200
        assert ("Content-Type", "text/event-stream; charset=utf-8") in h.headers
        assert ("Cache-Control", "no-cache, no-transform") in h.headers
        # X-Accel-Buffering 禁止反向代理缓冲 SSE
        assert ("X-Accel-Buffering", "no") in h.headers
        assert h.ended is True

    def test_deduplicates_identical_snapshots(self):
        """GIVEN unchanged snapshot WHEN pump THEN no duplicate event frames."""
        h = _FakeSSEHandler()
        state = {"n": 0}

        def snap():
            state["n"] += 1
            return {"pct": 1} if state["n"] < 3 else {"pct": 2}

        D._sse_stream(h, "status", snap, lambda s: s["pct"] == 2, interval=0.0)
        frames = h.frames()
        # pct=1 连来两次（去重后只推一帧），pct=2 一帧 → 共 2 帧
        assert frames.count("event: status") == 2
        assert frames.count(": keep-alive") == 2
        assert '"pct": 2' in frames

    def test_gone_event_when_resource_vanishes(self):
        """GIVEN snapshot None WHEN pump THEN gone event + stream closed."""
        h = _FakeSSEHandler()
        D._sse_stream(h, "status", lambda: None, lambda s: False)
        assert "event: gone" in h.frames()

    def test_terminal_state_closes_without_keepalive(self):
        """GIVEN already-terminal snapshot WHEN pump THEN one frame, no heartbeat."""
        h = _FakeSSEHandler()
        D._sse_stream(h, "status", lambda: {"status": "completed"},
                      lambda s: s.get("status") in ("completed", "failed"))
        frames = h.frames()
        assert frames.count("event: status") == 1
        assert "keep-alive" not in frames


class TestEvidenceStream:
    """GET /api/v1/dashboard/evidence/stream (T11-SSE)."""

    def test_missing_task_id(self):
        """GIVEN no task_id WHEN stream THEN 400."""
        payload, status = _handle(
            "GET", "evidence/stream", {}, {}, handler=_FakeSSEHandler())
        assert status == 400

    def test_task_not_found(self):
        """GIVEN unknown task WHEN stream THEN 404."""
        payload, status = _handle(
            "GET", "evidence/stream", {}, {"task_id": "nope"},
            handler=_FakeSSEHandler())
        assert status == 404

    def test_handler_required(self):
        """GIVEN no handler WHEN stream THEN 500 (cannot write a live stream)."""
        D._ev_tasks["ev-nh"] = {"task_id": "ev-nh", "status": "running"}
        payload, status = _handle(
            "GET", "evidence/stream", {}, {"task_id": "ev-nh"}, handler=None)
        assert status == 500

    def test_pushes_status_and_closes_on_terminal(self):
        """GIVEN completed task WHEN stream THEN status frame, then close."""
        D._ev_tasks["ev-sse"] = {
            "task_id": "ev-sse", "status": "completed", "progress_pct": 100,
            "_thread": None,
        }
        h = _FakeSSEHandler()
        result = _handle(
            "GET", "evidence/stream", {}, {"task_id": "ev-sse"}, handler=h)
        assert result is None  # 自行写响应，router 不得再补一次 JSON
        frames = h.frames()
        assert "event: status" in frames
        assert '"status": "completed"' in frames
        assert "_thread" not in frames  # 私有字段不上线
        assert "keep-alive" not in frames


class TestGapBatchStream:
    """GET /api/v1/dashboard/gap-analysis/batch/{id}/stream (T11-SSE)."""

    def test_batch_not_found(self):
        """GIVEN unknown batch WHEN stream THEN 404."""
        payload, status = _handle(
            "GET", "gap-analysis/batch/nope/stream", {}, {},
            handler=_FakeSSEHandler())
        assert status == 404

    def test_pushes_batch_and_closes_on_terminal(self):
        """GIVEN completed batch WHEN stream THEN batch frame, then close."""
        D._gap_batches["gb-sse"] = {
            "batch_id": "gb-sse", "status": "completed", "total": 1,
            "done": 1, "failed": 0, "started_at": "t0", "finished_at": "t1",
            "items": {"g1": {"gap_id": "g1", "status": "completed",
                             "progress_pct": 100, "run_id": "r1"}},
        }
        h = _FakeSSEHandler()
        result = _handle(
            "GET", "gap-analysis/batch/gb-sse/stream", {}, {}, handler=h)
        assert result is None
        frames = h.frames()
        assert "event: batch" in frames
        assert '"status": "completed"' in frames
        assert '"done": 1' in frames

    def test_plain_status_route_still_works(self):
        """GIVEN batch id WHEN GET without /stream THEN JSON status (回归)."""
        D._gap_batches["gb-plain"] = {
            "batch_id": "gb-plain", "status": "running", "total": 2,
            "done": 0, "failed": 0, "started_at": "t0", "finished_at": None,
            "items": {},
        }
        payload, status = _handle(
            "GET", "gap-analysis/batch/gb-plain", {}, {}, handler=None)
        assert status == 200
        assert payload["data"]["batch_id"] == "gb-plain"


class TestGapRunStream:
    """GET /api/v1/dashboard/gap-analysis/{gap_id}/status/stream (T11-SSE)."""

    def test_handler_required(self):
        """GIVEN no handler WHEN stream THEN 500 (cannot write a live stream)."""
        payload, status = _handle(
            "GET", "gap-analysis/g1/status/stream", {}, {}, handler=None)
        assert status == 500

    def test_unknown_run_id(self):
        """GIVEN unknown run_id WHEN stream THEN 404."""
        payload, status = _handle(
            "GET", "gap-analysis/g1/status/stream", {}, {"run_id": "nope"},
            handler=_FakeSSEHandler())
        assert status == 404

    def test_pushes_run_and_closes_on_terminal(self):
        """GIVEN completed run WHEN stream THEN run frame, then close."""
        D._gap_runs["run-sse"] = {
            "run_id": "run-sse", "gap_id": "g1", "status": "completed",
            "progress_pct": 100, "started_at": "t0", "finished_at": "t1",
            "log": ["done"],
        }
        h = _FakeSSEHandler()
        result = _handle(
            "GET", "gap-analysis/g1/status/stream", {}, {"run_id": "run-sse"},
            handler=h)
        assert result is None
        frames = h.frames()
        assert "event: run" in frames
        assert '"status": "completed"' in frames
        assert "keep-alive" not in frames

    def test_plain_status_route_still_works(self):
        """GIVEN run_id WHEN GET status (no /stream) THEN JSON (回归)."""
        D._gap_runs["run-plain"] = {
            "run_id": "run-plain", "gap_id": "g1", "status": "running",
            "progress_pct": 20, "started_at": "t0", "finished_at": None,
            "log": [],
        }
        payload, status = _handle(
            "GET", "gap-analysis/g1/status", {}, {"run_id": "run-plain"},
            handler=None)
        assert status == 200
        assert payload["data"]["progress_pct"] == 20


# ── coverage ───────────────────────────────────────────────────────────

class TestCoverage:
    def test_real_c_coverage(self, _isolate):
        """GIVEN c-coverage.json WHEN coverage THEN real numbers."""
        tmp_path = _isolate
        _write(None, tmp_path, ".yuleosh/reports/c-coverage.json", {
            "line_rate": 80.5, "branch_rate": 60.0, "function_rate": 90.0,
            "files": [
                {"file": "src/drivers/can.c", "line_rate": 70.0,
                 "branch_rate": 50.0},
                {"file": "src/foo_mock.h", "line_rate": 10.0,
                 "branch_rate": 5.0},
            ],
        })
        payload, _ = _handle("GET", "coverage", {}, {}, handler=None)
        data = payload["data"]
        assert data["line_pct"] == 80.5
        assert data["note"] is None
        names = [m["name"] for m in data["modules"]]
        assert names == ["drivers", "foo"]  # dir name / filename with _mock.h stripped
        assert data["display_mode"] == "absolute"

    def test_real_coverage_with_trend(self, _isolate):
        """GIVEN trend jsonl WHEN coverage THEN trend parsed."""
        tmp_path = _isolate
        _write(None, tmp_path, ".yuleosh/reports/c-coverage.json", {
            "line_rate": 50.0, "branch_rate": 0.0, "function_rate": 0.0,
            "files": [],
        })
        _write(None, tmp_path, ".yuleosh/reports/coverage-trend.jsonl",
               '{"timestamp": "2026-07-01T00:00:00", "line_pct": 45.5}\n'
               '{"timestamp": "2026-07-08T00:00:00", "line_pct": 50.0}\n')
        payload, _ = _handle("GET", "coverage", {}, {}, handler=None)
        trend = payload["data"]["trend"]
        assert len(trend) == 2
        assert trend[0]["date"] == "2026-07-01"
        assert trend[1]["line_pct"] == 50.0

    def test_corrupt_trend_lines_skipped(self, _isolate):
        """GIVEN bad jsonl line WHEN coverage THEN line skipped."""
        tmp_path = _isolate
        _write(None, tmp_path, ".yuleosh/reports/c-coverage.json", {
            "line_rate": 1.0, "branch_rate": 0.0, "function_rate": 0.0,
            "files": [],
        })
        _write(None, tmp_path, ".yuleosh/reports/coverage-trend.jsonl",
               'not-json\n{"timestamp": "2026-07-01T00:00:00", "line_pct": 1.0}\n')
        payload, _ = _handle("GET", "coverage", {}, {}, handler=None)
        assert len(payload["data"]["trend"]) == 1

    def test_corrupt_report_falls_back(self, _isolate):
        """GIVEN corrupt c-coverage WHEN coverage THEN mock fallback."""
        tmp_path = _isolate
        _write(None, tmp_path, ".yuleosh/reports/c-coverage.json", "{{{{bad")
        payload, _ = _handle("GET", "coverage", {}, {}, handler=None)
        assert payload["data"]["line_pct"] == 58.3
        assert payload["data"]["note"] == "⚠️ 演示数据 — 需连接实际项目"

    def test_mock_fallback_display_modes(self, monkeypatch, _isolate):
        """GIVEN mock coverage <30% WHEN coverage THEN trend mode."""
        monkeypatch.setattr(D, "MOCK_COVERAGE", {"line_pct": 12.0,
                                                 "branch_pct": 0,
                                                 "function_pct": 0})
        payload, _ = _handle("GET", "coverage", {}, {}, handler=None)
        assert payload["data"]["display_mode"] == "trend"


# ── misra-trend ────────────────────────────────────────────────────────

class TestMisraTrend:
    def test_real_trend_data(self, _isolate, monkeypatch):
        """GIVEN misra-trend.jsonl WHEN misra-trend THEN weekly trend."""
        tmp_path = _isolate
        _write(None, tmp_path, ".yuleosh/reports/misra-trend.jsonl",
               '{"timestamp": "2026-07-01", "total_violations": 10, '
               '"required": 7, "advisory": 3}\n'
               '{"timestamp": "2026-07-01", "total_violations": 5, '
               '"required": 4, "advisory": 1}\n')

        class _EmptyKb:
            def list_articles(self, search="", limit=10, offset=0):
                return []

        monkeypatch.setattr("yuleosh.kb.store.KbStore", _EmptyKb)
        payload, _ = _handle("GET", "misra-trend", {}, {}, handler=None)
        data = payload["data"]
        assert data["note"] is None
        assert data["weekly_trend"][0]["violations"] == 15
        assert data["distribution"] == {"required": 11, "advisory": 4}
        # no KB articles -> fallback recent from entries
        assert len(data["recent_violations"]) == 2

    def test_kb_articles_used(self, _isolate, monkeypatch):
        """GIVEN KB articles WHEN misra-trend THEN recent from KB."""
        tmp_path = _isolate
        _write(None, tmp_path, ".yuleosh/reports/misra-trend.jsonl",
               '{"timestamp": "2026-07-01", "total_violations": 1, '
               '"required": 1, "advisory": 0}\n')

        class Art:
            source = "misra_analysis"
            title = "MISRA-Rule-10.1 xyz"
            tags = "required"
            source_ref = "src/a.c:42"
            content = "## message line"

        class FakeKb:
            def list_articles(self, search="", limit=10, offset=0):
                return [Art()]

        monkeypatch.setattr("yuleosh.kb.store.KbStore", FakeKb)
        payload, _ = _handle("GET", "misra-trend", {}, {}, handler=None)
        recent = payload["data"]["recent_violations"]
        assert recent[0]["rule_id"] == "MISRA-Rule-10.1"
        assert recent[0]["category"] == "Required"
        assert recent[0]["file"] == "src/a.c"
        assert recent[0]["line"] == 42
        assert recent[0]["severity"] == "high"

    def test_kb_exception_falls_back(self, _isolate, monkeypatch):
        """GIVEN KB store raising WHEN misra-trend THEN fallback recent."""
        tmp_path = _isolate
        _write(None, tmp_path, ".yuleosh/reports/misra-trend.jsonl",
               '{"timestamp": "2026-07-01", "total_violations": 2, '
               '"required": 2, "advisory": 0, "commit": "abcd"}\n')

        def boom(*a, **kw):
            raise RuntimeError("kb down")

        monkeypatch.setattr("yuleosh.kb.store.KbStore", boom)
        payload, _ = _handle("GET", "misra-trend", {}, {}, handler=None)
        recent = payload["data"]["recent_violations"]
        assert len(recent) == 1
        assert recent[0]["rule_id"] == "misra-c2023-abcd"

    def test_mock_fallback(self):
        """GIVEN no trend file WHEN misra-trend THEN mock data."""
        payload, _ = _handle("GET", "misra-trend", {}, {}, handler=None)
        data = payload["data"]
        assert len(data["weekly_trend"]) == 5
        assert data["note"] == "⚠️ 演示数据 — 需连接实际项目"


# ── Helpers ────────────────────────────────────────────────────────────

class TestHelpers:
    def test_get_query_param_list(self):
        """GIVEN list value WHEN _get_query_param THEN first element."""
        assert D._get_query_param({"k": ["a", "b"]}, "k") == "a"
        assert D._get_query_param({"k": []}, "k") == ""
        assert D._get_query_param({}, "k", "def") == "def"

    def test_find_latest_manifest(self, _isolate):
        """GIVEN manifest present WHEN find_latest THEN path returned."""
        tmp_path = _isolate
        p = _write(None, tmp_path, "reports/audit-manifest.json", {})
        assert D._find_latest_manifest() == str(p)

    def test_find_latest_manifest_missing(self, _isolate):
        """GIVEN no manifests WHEN find_latest THEN None."""
        assert D._find_latest_manifest() is None

    def test_build_swe_from_manifest_statuses(self):
        """GIVEN mixed statuses WHEN build_swe THEN mapped + counts."""
        swe_data = {
            "SWE1": {"status": "pass", "name": "A"},
            "SWE2": {"status": "partial", "name": "B"},
            "SWE3": {"status": "unknown", "name": "C"},
        }
        payload, status = D._build_swe_from_manifest(swe_data)
        assert status == 200
        data = payload["data"]
        assert data["swe"]["SWE1"]["status"] == "completed"
        assert data["swe"]["SWE2"]["status"] == "partial"
        assert data["swe"]["SWE3"]["status"] == "not_started"
        assert data["swe"]["SWE1"]["color"] == "#10b981"
        assert data["swe"]["SWE2"]["color"] == "#faad14"
        assert data["swe"]["SWE3"]["color"] == "#ff4d4f"
        assert data["completed_count"] == 1
        assert data["overall_pct"] == round(1 / 3 * 100, 1)
        assert data["swe"]["SWE1"]["details_url"] == "/dashboard/swe/swe1"

    def test_estimate_swe_completed_manifest(self, _isolate):
        """GIVEN manifest with completed WHEN estimate THEN manifest count."""
        tmp_path = _isolate
        _write(None, tmp_path, ".osh/evidence/audit-manifest.json", {
            "swe_status": {
                "SWE1": {"status": "completed"},
                "SWE2": {"status": "completed"},
                "SWE3": {"status": "fail"},
            }
        })
        assert D._estimate_swe_completed({"id": "p", "name": "Core Firmware"}) == 2

    @pytest.mark.parametrize("name,expected", [
        ("Core Firmware", 4),
        ("Bootloader", 2),
        ("CAN Stack", 5),
        ("Anything Else", 3),
    ])
    def test_estimate_swe_completed_heuristic(self, name, expected):
        """GIVEN project name WHEN estimate THEN heuristic count."""
        assert D._estimate_swe_completed({"id": "p", "name": name}) == expected

    def test_mock_note(self):
        """GIVEN _mock_note WHEN called THEN demo annotation."""
        assert D._mock_note() == "⚠️ 演示数据 — 需连接实际项目"
