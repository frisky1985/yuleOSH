"""Unit tests for yuleosh.api.dashboard (v3.4.2b Wave 2a).

Covers the dashboard API routes offline:
  - handle_dashboard routing (all 7 routes + unknown -> 404)
  - projects (real store path / mock fallback / project_id filter)
  - swe-status (manifest path / mock fallback / corrupt manifest)
  - gap-analysis (real manifest items / pagination / severity filter)
  - evidence generate (subprocess success/failure/timeout/FileNotFound)
  - evidence status (missing/not-found/found)
  - coverage (real c-coverage.json + trend / corrupt / mock fallback)
  - misra-trend (real jsonl / KB articles / mock fallback)
  - helpers (_get_query_param / _find_latest_manifest / _build_swe_from_manifest
    / _estimate_swe_completed / _simulate_evidence_completion / _mock_note)
"""

import json
import os
import sys
import subprocess

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.api import dashboard as D

# The auth wrapper injects current_user as a kwarg, but handle_dashboard
# has no **kwargs; unit tests call the wrapped original directly.
_handle = D.handle_dashboard.__wrapped__


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
        """GIVEN GET projects WHEN handle THEN ok payload."""
        payload, status = _handle("GET", "projects", {}, {}, handler=None)
        assert status == 200 and payload["ok"] is True
        assert payload["data"]["count"] == 3

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
        """GIVEN POST evidence/generate WHEN handle THEN task response."""
        payload, _ = _handle("POST", "evidence/generate",
                                        {"project_id": "p1"}, {}, handler=None)
        assert payload["ok"] is True
        assert payload["data"]["status"] == "failed"  # CLI not real here

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


# ── projects ───────────────────────────────────────────────────────────

class TestProjects:
    def test_mock_fallback(self):
        """GIVEN no real store WHEN projects THEN mock + demo note."""
        payload, status = _handle("GET", "projects", {}, {}, handler=None)
        assert status == 200
        assert payload["data"]["note"] == "⚠️ 演示数据 — 需连接实际项目"
        assert payload["data"]["count"] == 3

    def test_project_id_filter(self):
        """GIVEN project_id WHEN projects THEN single project."""
        payload, _ = _handle(
            "GET", "projects", {}, {"project_id": "proj-bootloader"}, None)
        assert payload["data"]["count"] == 1
        assert payload["data"]["projects"][0]["id"] == "proj-bootloader"

    def test_project_id_not_found(self):
        """GIVEN unknown project_id WHEN projects THEN 404."""
        payload, status = _handle(
            "GET", "projects", {}, {"project_id": "nope"}, None)
        assert status == 404

    def test_real_projects_from_store(self, monkeypatch):
        """GIVEN real store rows WHEN projects THEN real data used."""
        class FakeCur:
            def fetchall(self):
                return [{"id": "1", "name": "RealProj", "slug": "real-proj",
                         "description": "d", "updated_at": "2026-01-01",
                         "created_at": "2026-01-01"}]

        class FakeConn:
            def execute(self, sql):
                return FakeCur()

        class FakeStore:
            def __init__(self):
                self.conn = FakeConn()

        monkeypatch.setattr("yuleosh.store.Store", FakeStore)
        payload, _ = _handle("GET", "projects", {}, {}, handler=None)
        assert payload["data"]["count"] == 1
        assert payload["data"]["projects"][0]["name"] == "RealProj"
        assert payload["data"]["note"] is None
        assert payload["data"]["projects"][0]["swe_total"] == 6

    def test_real_projects_store_error_falls_back(self, monkeypatch):
        """GIVEN store raising WHEN projects THEN mock fallback."""
        def boom():
            raise RuntimeError("db down")

        monkeypatch.setattr("yuleosh.store.Store", boom)
        payload, _ = _handle("GET", "projects", {}, {}, handler=None)
        assert payload["data"]["count"] == 3


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
        task = D._ev_tasks[task_id]
        assert task["status"] == "completed"
        assert task["valid"] is True
        assert task["total_artifacts"] == 7

    def test_success_without_manifest(self, monkeypatch, _isolate):
        """GIVEN CLI success but no manifest WHEN generate THEN failed."""
        monkeypatch.setattr(D.subprocess, "run",
                            lambda *a, **kw: _FakeCompleted(0))
        payload, _ = _handle(
            "POST", "evidence/generate", {"project_id": "p1"}, {}, handler=None)
        task = D._ev_tasks[payload["data"]["task_id"]]
        assert task["status"] == "failed"
        assert "no manifest" in task["error"]

    def test_cli_failure(self, monkeypatch, _isolate):
        """GIVEN CLI returncode != 0 WHEN generate THEN failed with stderr."""
        monkeypatch.setattr(D.subprocess, "run",
                            lambda *a, **kw: _FakeCompleted(1, stderr="boom"))
        payload, _ = _handle(
            "POST", "evidence/generate", {"project_id": "p1"}, {}, handler=None)
        task = D._ev_tasks[payload["data"]["task_id"]]
        assert task["status"] == "failed"
        assert "boom" in task["error"]

    def test_timeout(self, monkeypatch, _isolate):
        """GIVEN TimeoutExpired WHEN generate THEN failed timeout msg."""

        def timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="x", timeout=300)

        monkeypatch.setattr(D.subprocess, "run", timeout)
        payload, _ = _handle(
            "POST", "evidence/generate", {"project_id": "p1"}, {}, handler=None)
        task = D._ev_tasks[payload["data"]["task_id"]]
        assert task["status"] == "failed"
        assert "timed out" in task["error"]

    def test_file_not_found_simulates(self, monkeypatch, _isolate):
        """GIVEN FileNotFoundError WHEN generate THEN simulated completion."""

        def nf(*a, **kw):
            raise FileNotFoundError("no cli")

        monkeypatch.setattr(D.subprocess, "run", nf)
        payload, _ = _handle(
            "POST", "evidence/generate", {"project_id": "p1"}, {}, handler=None)
        task = D._ev_tasks[payload["data"]["task_id"]]
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
        task = D._ev_tasks[payload["data"]["task_id"]]
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
