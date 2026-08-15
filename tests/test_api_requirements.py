"""Unit tests for yuleosh.api.requirements — requirements management (module ②).

Covers, offline against tmp_path project dirs:
  - requirement list parsing (Req-XXX-001 headers, SHALL/SHOULD/MAY kinds,
    Status state, GIVEN/WHEN/THEN scenarios)
  - traceability (project scan classifies design/code/test/evidence refs)
  - gap analysis (test/evidence coverage stats + gap list)
  - path traversal protection (403), missing project (400), no-spec → empty
    list + note (real data only, no fabrication)
  - auth-required → 401
"""

import pytest

from yuleosh.api import requirements as R

_handle = R.handle_requirements.__wrapped__

SPEC_TEXT = """# Demo Spec

> Version: 1.0.0

## 1. Requirements

### Req-DEMO-001: 刹车灯控制

- The system SHALL turn on the brake light when brake is pressed.
- The system SHOULD debounce the signal.

**GIVEN** the brake pedal is pressed
**WHEN** the control unit receives the signal
**THEN** the brake light SHALL be activated within 50ms

Status: APPROVED

### Req-DEMO-002: 故障诊断

- The system SHALL detect a broken bulb.

**GIVEN** the bulb is broken
**WHEN** the system runs self-diagnosis
**THEN** the system SHALL set a fault code

Status: IMPLEMENTED

### Req-DEMO-003: 附加功能

- The system MAY provide a dim mode.

Status: PROPOSED
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Point OSH_HOME at tmp_path and lay out a project with spec + refs."""
    monkeypatch.setattr(R, "OSH_HOME", str(tmp_path))
    proj = tmp_path / "projects" / "demo"
    (proj / "docs").mkdir(parents=True)
    (proj / "src").mkdir()
    (proj / "tests").mkdir()
    (proj / "evidence").mkdir()
    (proj / "spec.md").write_text(SPEC_TEXT, encoding="utf-8")
    (proj / "src" / "brake.c").write_text(
        "// implements REQ-DEMO-001 brake light\n", encoding="utf-8")
    (proj / "tests" / "test_brake.c").write_text(
        "// covers REQ-DEMO-001 and REQ-DEMO-002\n", encoding="utf-8")
    (proj / "evidence" / "report.md").write_text(
        "Evidence report for REQ-DEMO-002\n", encoding="utf-8")
    return tmp_path


def _req(method, path, query=None):
    return _handle(method, path, {}, query or {}, handler=None,
                   current_user={"user_id": 1, "org_id": 1,
                                 "email": "t@example.com", "role": "admin"})


def _by_id(payload):
    return {r["req_id"]: r for r in payload["data"]["requirements"]}


# ── GET /api/v1/requirements — list ─────────────────────────────────────

class TestList:
    def test_parses_requirements(self, env):
        """GIVEN spec.md WHEN GET requirements THEN 3 parsed requirements."""
        payload, status = _req("GET", "", {"project": "demo"})
        assert status == 200 and payload["ok"] is True
        assert payload["data"]["count"] == 3
        assert payload["data"]["note"] is None
        reqs = _by_id(payload)
        assert set(reqs) == {"REQ-DEMO-001", "REQ-DEMO-002", "REQ-DEMO-003"}

    def test_requirement_fields(self, env):
        """GIVEN Req-DEMO-001 WHEN parsed THEN id/title/kind/text/state."""
        req = _by_id(_req("GET", "", {"project": "demo"})[0])["REQ-DEMO-001"]
        assert req["title"] == "刹车灯控制"
        assert req["kind"] == "SHALL"      # SHALL outranks SHOULD
        assert req["state"] == "APPROVED"
        assert "turn on the brake light" in req["text"]
        assert "debounce" in req["text"]   # SHOULD statement included

    def test_scenarios_parsed(self, env):
        """GIVEN GIVEN/WHEN/THEN lines THEN one scenario per requirement."""
        req = _by_id(_req("GET", "", {"project": "demo"})[0])["REQ-DEMO-001"]
        assert len(req["scenarios"]) == 1
        sc = req["scenarios"][0]
        assert sc["given"] == ["the brake pedal is pressed"]
        assert sc["when"] == ["the control unit receives the signal"]
        assert sc["then"] == ["the brake light SHALL be activated within 50ms"]

    def test_kind_may_and_default_state(self, env):
        """GIVEN MAY-only requirement WHEN parsed THEN kind MAY, state default."""
        req = _by_id(_req("GET", "", {"project": "demo"})[0])["REQ-DEMO-003"]
        assert req["kind"] == "MAY"
        assert req["state"] == "PROPOSED"
        assert req["scenarios"] == []

    def test_state_implemented(self, env):
        req = _by_id(_req("GET", "", {"project": "demo"})[0])["REQ-DEMO-002"]
        assert req["state"] == "IMPLEMENTED"
        assert req["kind"] == "SHALL"

    def test_spec_cache_fallback(self, env, monkeypatch):
        """GIVEN no project spec but .osh/specs cache THEN parsed from cache."""
        cache = env / ".osh" / "specs" / "v1.0.0"
        cache.mkdir(parents=True)
        (cache / "spec.md").write_text(
            "### Req-CACHE-001: 缓存需求\n- The system SHALL read cache.\n",
            encoding="utf-8")
        payload, _ = _req("GET", "", {"project": "ghost"})
        assert payload["data"]["count"] == 1
        assert "REQ-CACHE-001" in _by_id(payload)

    def test_no_spec_returns_empty_with_note(self, env):
        """GIVEN project without spec files THEN [] + note, never fabricated."""
        (env / "projects" / "empty").mkdir(parents=True)
        payload, status = _req("GET", "", {"project": "empty"})
        assert status == 200
        assert payload["data"]["requirements"] == []
        assert payload["data"]["count"] == 0
        assert payload["data"]["note"]

    def test_missing_project_param_400(self, env):
        payload, status = _req("GET", "")
        assert status == 400
        assert "project" in payload["error"]

    def test_path_traversal_rejected(self, env):
        """GIVEN ../ or absolute project names THEN 403."""
        for evil in ("../etc", "..", ".hidden", "/etc/passwd", "a/b"):
            payload, status = _req("GET", "", {"project": evil})
            assert status == 403, f"project={evil!r} should be rejected"
            assert payload["ok"] is False


# ── GET /api/v1/requirements/{req_id}/trace ─────────────────────────────

class TestTrace:
    def test_trace_artifacts_classified(self, env):
        """GIVEN REQ-DEMO-001 WHEN trace THEN code + test artifacts."""
        payload, status = _req("GET", "Req-DEMO-001/trace", {"project": "demo"})
        assert status == 200
        data = payload["data"]
        assert data["req_id"] == "REQ-DEMO-001"
        types = {a["type"] for a in data["artifacts"]}
        assert types == {"code", "test"}
        refs = {a["ref"] for a in data["artifacts"]}
        assert refs == {"src/brake.c", "tests/test_brake.c"}

    def test_trace_spec_file_excluded(self, env):
        """GIVEN the defining spec.md WHEN trace THEN not listed as artifact."""
        payload, _ = _req("GET", "REQ-DEMO-001/trace", {"project": "demo"})
        assert "spec.md" not in {a["ref"] for a in payload["data"]["artifacts"]}

    def test_trace_unknown_req_id_empty(self, env):
        """GIVEN req id with no references WHEN trace THEN empty artifacts."""
        payload, status = _req("GET", "REQ-NOPE-999/trace", {"project": "demo"})
        assert status == 200
        assert payload["data"]["artifacts"] == []

    def test_trace_missing_project_400(self, env):
        payload, status = _req("GET", "REQ-DEMO-001/trace")
        assert status == 400

    def test_trace_traversal_rejected(self, env):
        payload, status = _req("GET", "REQ-DEMO-001/trace",
                               {"project": "../evil"})
        assert status == 403


# ── GET /api/v1/requirements/gaps ───────────────────────────────────────

class TestGaps:
    def test_gap_analysis(self, env):
        """GIVEN spec + refs WHEN gaps THEN stats and gap list."""
        payload, status = _req("GET", "gaps", {"project": "demo"})
        assert status == 200
        data = payload["data"]
        assert data["total"] == 3
        assert data["with_test"] == 2      # REQ-DEMO-001, REQ-DEMO-002
        assert data["with_evidence"] == 1  # REQ-DEMO-002
        gaps = {g["req_id"]: g["missing"] for g in data["gaps"]}
        assert gaps == {
            "REQ-DEMO-001": ["evidence"],
            "REQ-DEMO-003": ["test", "evidence"],
        }

    def test_gaps_no_spec_empty(self, env):
        """GIVEN no spec WHEN gaps THEN zero stats + note."""
        (env / "projects" / "bare").mkdir(parents=True)
        payload, status = _req("GET", "gaps", {"project": "bare"})
        assert status == 200
        assert payload["data"]["total"] == 0
        assert payload["data"]["gaps"] == []
        assert payload["data"]["note"]

    def test_gaps_missing_project_400(self, env):
        payload, status = _req("GET", "gaps")
        assert status == 400


# ── Routing / auth ──────────────────────────────────────────────────────

class TestRouting:
    def test_unknown_route_404(self, env):
        payload, status = _req("GET", "wat", {"project": "demo"})
        assert status == 404 and payload["ok"] is False

    def test_method_not_allowed(self, env):
        payload, status = _req("POST", "", {"project": "demo"})
        assert status == 404

    def test_auth_required(self):
        """GIVEN no current_user and no handler WHEN called THEN 401.

        Uses the DECORATED handler (__wrapped__ bypasses require_auth).
        """
        payload, status = R.handle_requirements("GET", "", {}, {}, handler=None)
        assert status == 401
        assert "Authorization" in payload["error"]
