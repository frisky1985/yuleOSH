"""Unit tests for yuleosh.api.tests (design doc 模块 ⑤).

Covers offline (no HTTP server):
  - handle_tests routing (cases / runs / coverage + 404s + 401 auth)
  - cases: per-layer parsing (c-unit-test.json / integration-test.json /
    test-qualification.json + qualification-test.json alias), pass/fail/
    skip counts, case-name extraction, layer filter, invalid layer 400,
    corrupt artifact skipped, empty -> note
  - runs: execution history across sessions, sorted newest first,
    field shape, empty -> note
  - coverage: c-coverage.json per session, root .coverage-report.json
    (coverage.py format), latest wins, empty -> coverage null + note

Test data is created in tmp_path which is pointed to via OSH_HOME
(monkeypatched) — the same isolation pattern as test_api_dashboard_unit.
"""

import json

import pytest

from yuleosh.api import tests as T

# Bypass the auth wrapper like test_api_dashboard_unit does.
_handle = T.handle_tests.__wrapped__


def _req(method="GET", path="", body=None, query=None):
    """Call the wrapped handler with an authenticated current_user."""
    return _handle(method, path, body or {}, query or {}, handler=None,
                   current_user={"user_id": 42, "org_id": 1,
                                 "email": "t@example.com", "role": "admin"})


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Point OSH_HOME at tmp_path so sessions are scanned there."""
    monkeypatch.setattr(T, "OSH_HOME", str(tmp_path))
    return tmp_path


def _write(tmp_path, relpath, content):
    p = tmp_path / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if isinstance(content, str) else json.dumps(content),
                 encoding="utf-8")
    return p


def _session(tmp_path, run_id, name="测试会话", status="completed", **extra):
    """Create a session dir with session.json; returns the session dir."""
    meta = {"name": name, "run_id": run_id, "status": status}
    meta.update(extra)
    _write(tmp_path, f".osh/sessions/{run_id}/session.json", meta)
    return tmp_path / ".osh" / "sessions" / run_id


def _unit_artifact(passed=5, failed=1, skipped=2, cases=None, **extra):
    """A realistic c-unit-test.json payload."""
    data = {
        "step": "c-unit-test",
        "status": "passed" if failed == 0 else "failed",
        "timestamp": "2026-08-15T10:00:00",
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration": 12.5,
        "cases": cases if cases is not None
        else [f"test_can_init_{i}" for i in range(passed + failed + skipped)],
    }
    data.update(extra)
    return data


# ── routing + auth ─────────────────────────────────────────────────────

class TestRouting:
    def test_requires_auth(self):
        """GIVEN no auth context WHEN handle THEN 401 fail closed."""
        payload, status = T.handle_tests("GET", "", {}, {}, handler=None)
        assert status == 401 and payload["ok"] is False

    def test_decorated(self):
        """GIVEN handle_tests THEN it is wrapped by require_auth."""
        assert hasattr(T.handle_tests, "__wrapped__")

    def test_cases_route(self, _isolate):
        """GIVEN GET /tests WHEN handle THEN 200."""
        payload, status = _req("GET", "")
        assert status == 200 and payload["ok"] is True

    def test_runs_route(self, _isolate):
        """GIVEN GET /tests/runs WHEN handle THEN 200."""
        payload, status = _req("GET", "runs")
        assert status == 200 and payload["ok"] is True

    def test_coverage_route(self, _isolate):
        """GIVEN GET /tests/coverage WHEN handle THEN 200."""
        payload, status = _req("GET", "coverage")
        assert status == 200 and payload["ok"] is True

    def test_unknown_subpath(self):
        """GIVEN unknown sub-path WHEN handle THEN 404."""
        payload, status = _req("GET", "nope")
        assert status == 404 and payload["ok"] is False

    def test_method_not_allowed(self):
        """GIVEN POST on /tests WHEN handle THEN 404."""
        payload, status = _req("POST", "")
        assert status == 404


# ── cases listing ──────────────────────────────────────────────────────

class TestCases:
    def test_empty_returns_note(self, _isolate):
        """GIVEN no artifacts WHEN /tests THEN empty runs + note."""
        payload, status = _req("GET", "")
        assert status == 200
        data = payload["data"]
        assert data["runs"] == []
        assert data["summary"] == {"passed": 0, "failed": 0,
                                   "skipped": 0, "total_cases": 0}
        assert data["note"] and "无" in data["note"]

    def test_unit_layer(self, _isolate):
        """GIVEN c-unit-test.json WHEN layer=unit THEN counts + cases."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/c-unit-test.json",
               _unit_artifact(passed=5, failed=1, skipped=2))
        payload, _ = _req("GET", "", query={"layer": "unit"})
        data = payload["data"]
        assert data["layer"] == "unit"
        assert len(data["runs"]) == 1
        run = data["runs"][0]
        assert run["run_id"] == "run1"
        assert run["layer"] == "unit"
        assert run["passed"] == 5 and run["failed"] == 1 and run["skipped"] == 2
        assert run["total"] == 8
        assert run["duration"] == 12.5
        assert run["status"] == "failed"
        assert len(run["cases"]) == 8
        assert run["cases"][0] == "test_can_init_0"
        assert data["summary"]["passed"] == 5
        assert data["summary"]["total_cases"] == 8
        assert data["note"] is None

    def test_integration_layer(self, _isolate):
        """GIVEN integration-test.json WHEN layer=integration THEN parsed."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/integration-test.json", {
            "step": "integration-test",
            "status": "passed",
            "timestamp": "2026-08-15T11:00:00",
            "tests_passed": 3,
            "tests_failed": 0,
            "tests_skipped": 1,
            "elapsed": 4.2,
            "test_cases": ["tc_can_bus", "tc_scheduler", "tc_memory"],
        })
        payload, _ = _req("GET", "", query={"layer": "integration"})
        run = payload["data"]["runs"][0]
        assert run["passed"] == 3 and run["failed"] == 0 and run["skipped"] == 1
        assert run["duration"] == 4.2
        assert set(run["cases"]) == {"tc_can_bus", "tc_scheduler", "tc_memory"}

    def test_qualification_primary_name(self, _isolate):
        """GIVEN test-qualification.json WHEN layer=qualification THEN parsed."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/test-qualification.json", {
            "step": "test-qualification",
            "verdict": "passed",
            "scenario_count": 2,
            "cases": ["SCN_brake_fail", "SCN_can_offline"],
        })
        payload, _ = _req("GET", "", query={"layer": "qualification"})
        run = payload["data"]["runs"][0]
        assert run["status"] == "passed"
        assert run["cases"] == ["SCN_brake_fail", "SCN_can_offline"]

    def test_qualification_alias_name(self, _isolate):
        """GIVEN qualification-test.json WHEN layer=qualification THEN parsed."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/qualification-test.json", {
            "step": "qualification",
            "status": "skipped",
            "reason": "mock mode",
            "cases": [],
        })
        payload, _ = _req("GET", "", query={"layer": "qualification"})
        run = payload["data"]["runs"][0]
        assert run["status"] == "skipped"
        assert run["passed"] == 0 and run["skipped"] == 0

    def test_layer_filter_isolates_layers(self, _isolate):
        """GIVEN unit + integration artifacts WHEN layer=unit THEN only unit."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/c-unit-test.json", _unit_artifact())
        _write(_isolate, ".osh/sessions/run1/integration-test.json", {
            "status": "passed", "passed": 9, "failed": 0, "skipped": 0,
        })
        payload, _ = _req("GET", "", query={"layer": "unit"})
        runs = payload["data"]["runs"]
        assert len(runs) == 1 and runs[0]["layer"] == "unit"

    def test_all_layers_without_filter(self, _isolate):
        """GIVEN artifacts for 2 layers WHEN no layer THEN both aggregated."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/c-unit-test.json", _unit_artifact(passed=1))
        _write(_isolate, ".osh/sessions/run1/integration-test.json", {
            "status": "passed", "passed": 2, "failed": 0, "skipped": 0,
        })
        payload, _ = _req("GET", "")
        assert payload["data"]["layer"] == "all"
        assert {r["layer"] for r in payload["data"]["runs"]} == {"unit", "integration"}
        assert payload["data"]["summary"]["passed"] == 3

    def test_invalid_layer(self, _isolate):
        """GIVEN layer=bogus WHEN /tests THEN 400."""
        payload, status = _req("GET", "", query={"layer": "bogus"})
        assert status == 400
        assert "layer" in payload["error"]

    def test_corrupt_artifact_skipped(self, _isolate):
        """GIVEN corrupt c-unit-test.json WHEN /tests THEN skipped, no crash."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/c-unit-test.json", "not json{{")
        payload, status = _req("GET", "", query={"layer": "unit"})
        assert status == 200
        assert payload["data"]["runs"] == []
        assert payload["data"]["note"]

    def test_layer_with_no_data_note(self, _isolate):
        """GIVEN only unit artifacts WHEN layer=integration THEN empty + note."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/c-unit-test.json", _unit_artifact())
        payload, _ = _req("GET", "", query={"layer": "integration"})
        assert payload["data"]["runs"] == []
        assert "integration" in payload["data"]["note"]

    def test_project_filter(self, _isolate):
        """GIVEN sessions for two projects WHEN ?project= THEN only one."""
        _session(_isolate, "rA", project="alpha")
        _session(_isolate, "rB", project="beta")
        _write(_isolate, ".osh/sessions/rA/c-unit-test.json", _unit_artifact(passed=1))
        _write(_isolate, ".osh/sessions/rB/c-unit-test.json", _unit_artifact(passed=2))
        payload, _ = _req("GET", "", query={"project": "beta"})
        runs = payload["data"]["runs"]
        assert [r["run_id"] for r in runs] == ["rB"]
        assert runs[0]["passed"] == 2


# ── runs history ───────────────────────────────────────────────────────

class TestRuns:
    def test_empty_returns_note(self, _isolate):
        """GIVEN no artifacts WHEN runs THEN empty + note."""
        payload, status = _req("GET", "runs")
        assert status == 200
        assert payload["data"]["runs"] == []
        assert payload["data"]["count"] == 0
        assert payload["data"]["note"]

    def test_history_sorted_newest_first(self, _isolate):
        """GIVEN artifacts with different timestamps WHEN runs THEN desc."""
        _session(_isolate, "rOld")
        _write(_isolate, ".osh/sessions/rOld/c-unit-test.json",
               _unit_artifact(passed=1, timestamp="2026-08-10T09:00:00"))
        _session(_isolate, "rNew")
        _write(_isolate, ".osh/sessions/rNew/c-unit-test.json",
               _unit_artifact(passed=2, timestamp="2026-08-15T09:00:00"))
        _write(_isolate, ".osh/sessions/rNew/integration-test.json", {
            "status": "passed", "passed": 3, "failed": 0, "skipped": 0,
            "timestamp": "2026-08-16T09:00:00",
        })
        payload, _ = _req("GET", "runs")
        runs = payload["data"]["runs"]
        assert payload["data"]["count"] == 3
        assert [r["updated_at"] for r in runs] == sorted(
            (r["updated_at"] for r in runs), reverse=True)
        assert runs[0]["run_id"] == "rNew" and runs[0]["layer"] == "integration"
        assert runs[1]["run_id"] == "rNew" and runs[1]["layer"] == "unit"

    def test_entry_shape(self, _isolate):
        """GIVEN one artifact WHEN runs THEN entry has all contract fields."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/c-unit-test.json",
               _unit_artifact(passed=4, failed=0, skipped=1))
        runs = _req("GET", "runs")[0]["data"]["runs"]
        entry = runs[0]
        assert set(entry) == {"run_id", "layer", "passed", "failed", "skipped",
                              "duration", "status", "updated_at"}
        assert entry["run_id"] == "run1" and entry["layer"] == "unit"
        assert entry["passed"] == 4 and entry["skipped"] == 1
        assert entry["status"] == "passed"

    def test_project_filter(self, _isolate):
        """GIVEN two projects WHEN runs?project= THEN only that project."""
        _session(_isolate, "rA", project="alpha")
        _session(_isolate, "rB", project="beta")
        _write(_isolate, ".osh/sessions/rA/c-unit-test.json", _unit_artifact())
        _write(_isolate, ".osh/sessions/rB/c-unit-test.json", _unit_artifact())
        payload, _ = _req("GET", "runs", query={"project": "alpha"})
        assert [r["run_id"] for r in payload["data"]["runs"]] == ["rA"]


# ── coverage ───────────────────────────────────────────────────────────

class TestCoverage:
    def test_empty_returns_null_and_note(self, _isolate):
        """GIVEN no coverage sources WHEN coverage THEN null + note."""
        payload, status = _req("GET", "coverage")
        assert status == 200
        assert payload["data"]["coverage"] is None
        assert payload["data"]["note"] and "覆盖率" in payload["data"]["note"]

    def test_c_coverage_json(self, _isolate):
        """GIVEN session c-coverage.json WHEN coverage THEN rates parsed."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/c-coverage.json", {
            "step": "c-coverage-gate",
            "line_rate": 80.5,
            "branch_rate": 60.0,
            "timestamp": "2026-08-15T09:00:00",
        })
        payload, _ = _req("GET", "coverage")
        cov = payload["data"]["coverage"]
        assert cov["source"] == "c-coverage.json"
        assert cov["run_id"] == "run1"
        assert cov["line_rate"] == 80.5
        assert cov["branch_rate"] == 60.0
        assert payload["data"]["note"] is None

    def test_root_coveragepy_report(self, _isolate):
        """GIVEN root .coverage-report.json WHEN coverage THEN totals used."""
        _write(_isolate, ".coverage-report.json", {
            "meta": {"timestamp": "2026-08-15T21:51:05", "format": 3},
            "totals": {"percent_covered": 90.67,
                       "percent_branches_covered": 85.11},
            "files": {},
        })
        payload, _ = _req("GET", "coverage")
        cov = payload["data"]["coverage"]
        assert cov["source"] == ".coverage-report.json"
        assert cov["run_id"] is None
        assert round(cov["line_rate"], 2) == 90.67
        assert round(cov["branch_rate"], 2) == 85.11

    def test_latest_wins(self, _isolate):
        """GIVEN two c-coverage.json WHEN coverage THEN newest returned."""
        _session(_isolate, "rOld")
        _write(_isolate, ".osh/sessions/rOld/c-coverage.json", {
            "line_rate": 50.0, "branch_rate": 40.0,
            "timestamp": "2026-08-01T09:00:00",
        })
        _session(_isolate, "rNew")
        _write(_isolate, ".osh/sessions/rNew/c-coverage.json", {
            "line_rate": 88.0, "branch_rate": 70.0,
            "timestamp": "2026-08-15T09:00:00",
        })
        payload, _ = _req("GET", "coverage")
        cov = payload["data"]["coverage"]
        assert cov["run_id"] == "rNew"
        assert cov["line_rate"] == 88.0

    def test_root_report_latest_over_session(self, _isolate):
        """GIVEN session report older than root report THEN root wins."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/c-coverage.json", {
            "line_rate": 60.0, "branch_rate": 50.0,
            "timestamp": "2026-08-01T09:00:00",
        })
        _write(_isolate, ".coverage-report.json", {
            "meta": {"timestamp": "2026-08-15T21:51:05"},
            "totals": {"percent_covered": 91.0,
                       "percent_branches_covered": 80.0},
            "files": {},
        })
        payload, _ = _req("GET", "coverage")
        cov = payload["data"]["coverage"]
        assert cov["source"] == ".coverage-report.json"

    def test_corrupt_source_skipped(self, _isolate):
        """GIVEN corrupt c-coverage.json WHEN coverage THEN skipped."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/c-coverage.json", "not json{{")
        payload, _ = _req("GET", "coverage")
        assert payload["data"]["coverage"] is None
