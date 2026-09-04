"""Unit tests for yuleosh.api.projects_stats (stage-4 dashboard feed).

Covers offline (no HTTP server):
  - routing (single endpoint /projects-stats/stats + 404 on unknown)
  - require_auth enforcement (401 without authenticated context)
  - input validation: missing project → 400, illegal project name → 403
  - aggregate math: missing_requirements from gaps list length,
    pending_tests from tests summary (failed + skipped),
    evidence_count from per-session ASPICE doc file scan
  - graceful zero: missing spec files / no sessions / no project dir
"""
# @tests src/yuleosh/api/projects_stats.py

import json
import pytest

from yuleosh.api import projects_stats as P
from yuleosh.api import requirements as R
from yuleosh.api import tests as T


_handle = P.handle_projects_stats.__wrapped__


def _req(method="GET", path="stats", body=None, query=None):
    """Call the wrapped handler with an authenticated current_user."""
    return _handle(method, path, body or {}, query or {}, handler=None,
                   current_user={"user_id": 42, "org_id": 1,
                                 "email": "t@example.com", "role": "admin"})


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Point OSH_HOME at tmp_path for all three modules (requirements,
    tests, projects_stats) so sessions/spec scans stay isolated.

    Reload first (the reload resets module-level OSH_HOME to the
    OSH_HOME env var), THEN setattr — otherwise monkeypatch values get
    overwritten by the module-level init expression.
    """
    import importlib
    import yuleosh.api.requirements as R
    import yuleosh.api.tests as T
    import yuleosh.api.projects_stats as P
    importlib.reload(R)
    importlib.reload(T)
    importlib.reload(P)
    monkeypatch.setattr(P, "OSH_HOME", str(tmp_path))
    monkeypatch.setattr(R, "OSH_HOME", str(tmp_path))
    monkeypatch.setattr(T, "OSH_HOME", str(tmp_path))
    # Rebind _handle to the freshly reloaded wrapped fn (so it sees
    # the new OSH_HOME).
    globals()["_handle"] = P.handle_projects_stats.__wrapped__
    globals()["_req"] = lambda method="GET", path="stats", body=None, query=None: \
        _handle(method, path, body or {}, query or {}, handler=None,
                current_user={"user_id": 42, "org_id": 1,
                              "email": "t@example.com", "role": "admin"})
    return tmp_path


def _write(tmp_path, relpath, content):
    p = tmp_path / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content if isinstance(content, str) else json.dumps(content),
                     encoding="utf-8")
    return p


def _project(tmp_path, name, spec_md=None, sessions=None,
             project_files=None):
    """Create project layout so requirements + tests + projects_stats
    scanners all see it under OSH_HOME.

    Layout convention:
      * spec          <OSH_HOME>/projects/<name>/spec.md
      * project_files list of (rel_under_project, content) for files that
        live inside ``projects/<name>/`` — those are the ones
        ``requirements._iter_project_files`` actually scans (the walker
        SKIPS dot-prefixed dirs like ``.osh``).
      * session       <OSH_HOME>/.osh/sessions/<run_id>/...  (NOT under
        projects/<name>/; tests._iter_sessions scans here, top-level)

    sessions: list of dicts {run_id, files: [(rel_under_session, content)]}
    """
    proj = tmp_path / "projects" / name
    proj.mkdir(parents=True, exist_ok=True)
    if spec_md is not None:
        _write(tmp_path, f"projects/{name}/spec.md", spec_md)
    for rel, content in (project_files or []):
        _write(tmp_path, f"projects/{name}/{rel}", content)
    for sess in (sessions or []):
        run_id = sess["run_id"]
        _write(tmp_path, f".osh/sessions/{run_id}/session.json",
               {"project": name, "run_id": run_id, "status": "completed"})
        for rel, content in sess.get("files", []):
            _write(tmp_path, f".osh/sessions/{run_id}/{rel}", content)
    return proj


# ── routing + auth ─────────────────────────────────────────────────────

class TestRouting:
    def test_requires_auth(self):
        """GIVEN no auth context WHEN handle THEN 401 fail closed."""
        payload, status = P.handle_projects_stats("GET", "stats",
                                                 {}, {"project": "x"},
                                                 handler=None)
        assert status == 401 and payload["ok"] is False

    def test_decorated(self):
        """GIVEN handle_projects_stats THEN it is wrapped by require_auth."""
        assert hasattr(P.handle_projects_stats, "__wrapped__")

    def test_stats_route(self, _isolate):
        """GIVEN GET stats WHEN handle THEN 200 with project payload."""
        _project(_isolate, "demo", spec_md="# spec")
        payload, status = _req("GET", "stats", query={"project": "demo"})
        assert status == 200 and payload["ok"] is True
        body = payload["data"]
        assert body["project"] == "demo"
        # All three numeric keys are present (even if 0)
        for key in ("missing_requirements", "pending_tests", "evidence_count"):
            assert isinstance(body[key], int)

    def test_unknown_subpath(self, _isolate):
        """GIVEN unknown sub-path WHEN handle THEN 404."""
        payload, status = _req("GET", "nope", query={"project": "demo"})
        assert status == 404 and payload["ok"] is False

    def test_post_not_allowed(self, _isolate):
        """GIVEN POST on stats WHEN handle THEN 404 (read-only)."""
        payload, status = _req("POST", "stats", query={"project": "demo"})
        assert status == 404


# ── input validation ───────────────────────────────────────────────────

class TestValidation:
    def test_missing_project(self, _isolate):
        """GIVEN no project WHEN handle THEN 400."""
        payload, status = _req("GET", "stats", query={})
        assert status == 400 and payload["ok"] is False

    def test_traversal_rejected(self, _isolate):
        """GIVEN project with slash WHEN handle THEN 403."""
        payload, status = _req("GET", "stats", query={"project": "../etc"})
        assert status == 403 and payload["ok"] is False

    def test_dot_prefix_rejected(self, _isolate):
        """GIVEN project starting with dot WHEN handle THEN 403."""
        payload, status = _req("GET", "stats", query={"project": ".hidden"})
        assert status == 403


# ── aggregate math ─────────────────────────────────────────────────────

class TestAggregate:
    def test_missing_spec_zero(self, _isolate):
        """GIVEN project dir but no spec WHEN handle THEN zero counters + note."""
        _project(_isolate, "empty")
        payload, status = _req("GET", "stats", query={"project": "empty"})
        assert status == 200
        body = payload["data"]
        assert body["missing_requirements"] == 0
        assert body["pending_tests"] == 0
        assert body["evidence_count"] == 0
        assert body["note"]

    def test_gaps_counted(self, _isolate):
        """GIVEN spec with 3 reqs + 1 evidence ref WHEN handle THEN
        missing_requirements == 3 (all 3 lack test artifacts; the gaps
        list counts each req with at least one missing artifact)."""
        # 3 reqs; evidence/swe.md covers Req-A-001 only → Req-A still
        # missing 'test' → 3 total gaps (one per req).
        # evidence/swe.md lives INSIDE projects/p/ (NOT under .osh) because
        # _iter_project_files skips dot-prefixed dirs.
        spec = (
            "## Req-A-001: A\n**SHALL** do A.\n\n"
            "## Req-B-002: B\n**SHALL** do B.\n\n"
            "## Req-C-003: C\n**SHALL** do C.\n\n"
        )
        _project(_isolate, "p", spec_md=spec,
                 project_files=[("evidence/swe.md", "covers Req-A-001")])
        payload, status = _req("GET", "stats", query={"project": "p"})
        assert status == 200
        body = payload["data"]
        # All 3 reqs lack 'test' coverage, so 3 gaps total.
        assert body["missing_requirements"] == 3

    def test_evidence_count(self, _isolate):
        """GIVEN 2 sessions with ASPICE docs WHEN handle THEN evidence_count sum.

        File basenames must be in ``_ASPICE_EVIDENCE_BASENAMES`` (mirrors
        artifacts.py — keeps the "evidence" notion consistent across the
        dashboard).
        """
        spec = "## Req-A-001: A\n**SHALL** do A.\n"
        _project(_isolate, "p", spec_md=spec, sessions=[
            {"run_id": "r1", "files": [
                ("prd.md", "# prd"),
                ("architecture.md", "# arch"),
            ]},
            {"run_id": "r2", "files": [
                ("final-report.md", "# final"),
            ]},
        ])
        payload, status = _req("GET", "stats", query={"project": "p"})
        assert status == 200
        # 3 ASPICE doc files total
        assert payload["data"]["evidence_count"] == 3

    def test_pending_tests_from_summary(self, _isolate):
        """GIVEN test artifact having 1 failed + 2 skipped WHEN handle THEN
        pending_tests == 3."""
        spec = "## Req-A-001: A\n**SHALL** do A.\n"
        _project(_isolate, "p", spec_md=spec, sessions=[
            {"run_id": "r1", "files": [
                ("c-unit-test.json", json.dumps({
                    "passed": 5, "failed": 1, "skipped": 2, "total": 8,
                    "status": "fail",
                    "cases": [
                        {"name": "t1"}, {"name": "t2"}, {"name": "t3"},
                    ],
                })),
            ]},
        ])
        payload, status = _req("GET", "stats", query={"project": "p"})
        assert status == 200
        # failed (1) + skipped (2) = pending 3
        assert payload["data"]["pending_tests"] == 3