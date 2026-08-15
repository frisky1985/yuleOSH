"""Unit tests for yuleosh.api.artifacts (design doc 模块 ④).

Covers offline (no HTTP server):
  - handle_artifacts routing (list / preview / evidence-pack + 404s)
  - require_auth enforcement (401 without an authenticated context)
  - list: real session scanning, session.json name/status, file metadata,
    session.json excluded, project filter, empty -> note
  - preview: markdown/json content, 100KB truncation, path traversal
    (../) rejected 403, missing run/file params, unknown run/file,
    unsupported file type
  - evidence-pack: final-report.md + related JSONs only

Test data is created in tmp_path which is pointed to via OSH_HOME
(monkeypatched) — the same isolation pattern as test_api_dashboard_unit.
"""

import json
import os

import pytest

from yuleosh.api import artifacts as A

# Bypass the auth wrapper like test_api_dashboard_unit does.
_handle = A.handle_artifacts.__wrapped__


def _req(method="GET", path="list", body=None, query=None):
    """Call the wrapped handler with an authenticated current_user."""
    return _handle(method, path, body or {}, query or {}, handler=None,
                   current_user={"user_id": 42, "org_id": 1,
                                 "email": "t@example.com", "role": "admin"})


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Point OSH_HOME at tmp_path so sessions are scanned there."""
    monkeypatch.setattr(A, "OSH_HOME", str(tmp_path))
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


def _session(tmp_path, run_id, name="PRD 生成", status="completed", **extra):
    """Create a session dir with session.json; returns the session dir."""
    meta = {"name": name, "run_id": run_id, "status": status}
    meta.update(extra)
    _write(tmp_path, f".osh/sessions/{run_id}/session.json", meta)
    return tmp_path / ".osh" / "sessions" / run_id


# ── routing + auth ─────────────────────────────────────────────────────

class TestRouting:
    def test_requires_auth(self):
        """GIVEN no auth context WHEN handle THEN 401 fail closed."""
        payload, status = A.handle_artifacts("GET", "list", {}, {}, handler=None)
        assert status == 401 and payload["ok"] is False

    def test_decorated(self):
        """GIVEN handle_artifacts THEN it is wrapped by require_auth."""
        assert hasattr(A.handle_artifacts, "__wrapped__")

    def test_list_route(self, _isolate):
        """GIVEN GET list WHEN handle THEN 200 with real runs."""
        payload, status = _req("GET", "list")
        assert status == 200 and payload["ok"] is True

    def test_preview_route(self, _isolate):
        """GIVEN GET preview WHEN handle THEN 200 (or 400 without params)."""
        payload, status = _req("GET", "preview")
        assert status == 400  # missing run/file params

    def test_evidence_pack_route(self, _isolate):
        """GIVEN GET evidence-pack WHEN handle THEN 200 (or 400 without run)."""
        payload, status = _req("GET", "evidence-pack")
        assert status == 400

    def test_unknown_subpath(self):
        """GIVEN unknown sub-path WHEN handle THEN 404."""
        payload, status = _req("GET", "nope")
        assert status == 404 and payload["ok"] is False

    def test_method_not_allowed(self):
        """GIVEN POST on list WHEN handle THEN 404."""
        payload, status = _req("POST", "list")
        assert status == 404


# ── list ───────────────────────────────────────────────────────────────

class TestList:
    def test_empty_returns_note(self, _isolate):
        """GIVEN no sessions WHEN list THEN empty runs + note (no fake data)."""
        payload, status = _req("GET", "list")
        assert status == 200
        data = payload["data"]
        assert data["runs"] == [] and data["count"] == 0
        assert data["note"] and "无" in data["note"]

    def test_session_with_artifacts(self, _isolate):
        """GIVEN session with prd.md + prd-review.json WHEN list THEN tree."""
        sdir = _session(_isolate, "run1")
        _write(_isolate, f".osh/sessions/run1/prd.md", "# PRD\n")
        _write(_isolate, f".osh/sessions/run1/prd-review.json", {"ok": True})
        _write(_isolate, f".osh/sessions/run1/spec.md", "# Spec\n")
        payload, _ = _req("GET", "list")
        data = payload["data"]
        assert data["count"] == 1
        run = data["runs"][0]
        assert run["run_id"] == "run1"
        assert run["name"] == "PRD 生成"
        assert run["status"] == "completed"
        paths = {f["path"] for f in run["files"]}
        assert paths == {"prd.md", "prd-review.json", "spec.md"}
        # session.json is metadata — never listed as an artifact
        assert "session.json" not in paths
        md = next(f for f in run["files"] if f["path"] == "prd.md")
        assert md["name"] == "prd.md"
        assert md["ext"] == "md"
        assert md["size"] == len("# PRD\n")
        j = next(f for f in run["files"] if f["path"] == "prd-review.json")
        assert j["ext"] == "json"
        assert data["note"] is None

    def test_session_without_session_json_fallback(self, _isolate):
        """GIVEN dir without session.json WHEN list THEN run listed with fallback."""
        _write(_isolate, ".osh/sessions/legacy-run/artifact.md", "x")
        payload, _ = _req("GET", "list")
        data = payload["data"]
        assert data["count"] == 1
        run = data["runs"][0]
        assert run["run_id"] == "legacy-run"
        assert run["name"] == "legacy-run"  # fallback to run_id
        assert run["status"] == "unknown"
        assert [f["path"] for f in run["files"]] == ["artifact.md"]

    def test_corrupt_session_json_fallback(self, _isolate):
        """GIVEN corrupt session.json WHEN list THEN fallback, no crash."""
        _write(_isolate, ".osh/sessions/bad/session.json", "not json{{")
        _write(_isolate, ".osh/sessions/bad/spec.md", "s")
        payload, _ = _req("GET", "list")
        data = payload["data"]
        assert data["count"] == 1
        assert data["runs"][0]["name"] == "bad"
        assert data["runs"][0]["status"] == "unknown"

    def test_project_filter(self, _isolate):
        """GIVEN sessions for two projects WHEN ?project= THEN only one."""
        _session(_isolate, "rA", project="alpha")
        _session(_isolate, "rB", project="beta")
        _write(_isolate, ".osh/sessions/rA/spec.md", "a")
        _write(_isolate, ".osh/sessions/rB/spec.md", "b")
        payload, _ = _req("GET", "list", query={"project": "alpha"})
        data = payload["data"]
        assert [r["run_id"] for r in data["runs"]] == ["rA"]

    def test_project_filter_no_match(self, _isolate):
        """GIVEN project with no sessions WHEN list THEN empty + note."""
        _session(_isolate, "rA", project="alpha")
        payload, _ = _req("GET", "list", query={"project": "nope"})
        data = payload["data"]
        assert data["runs"] == [] and data["note"] and "nope" in data["note"]

    def test_project_filter_list_value(self, _isolate):
        """GIVEN parse_qs-style query (?project=alpha) THEN filter works."""
        _session(_isolate, "rA", project="alpha")
        _session(_isolate, "rB", project="beta")
        payload, _ = _req("GET", "list", query={"project": ["beta"]})
        assert [r["run_id"] for r in payload["data"]["runs"]] == ["rB"]


# ── preview ────────────────────────────────────────────────────────────

class TestPreview:
    def test_missing_params(self):
        """GIVEN no run/file WHEN preview THEN 400."""
        payload, status = _req("GET", "preview")
        assert status == 400
        payload, status = _req("GET", "preview", query={"run": "r1"})
        assert status == 400

    def test_unknown_run(self, _isolate):
        """GIVEN unknown run WHEN preview THEN 404."""
        payload, status = _req("GET", "preview", query={"run": "nope", "file": "a.md"})
        assert status == 404

    def test_markdown_content(self, _isolate):
        """GIVEN prd.md WHEN preview THEN content returned."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/prd.md", "# 需求\n- 功能A\n")
        payload, status = _req("GET", "preview", query={"run": "run1", "file": "prd.md"})
        assert status == 200
        data = payload["data"]
        assert data["content"] == "# 需求\n- 功能A\n"
        assert data["truncated"] is False
        assert data["ext"] == "md"
        assert data["size"] == len("# 需求\n- 功能A\n".encode("utf-8"))

    def test_json_content(self, _isolate):
        """GIVEN review json WHEN preview THEN raw JSON string returned."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/prd-review.json",
               {"verdict": "pass", "issues": 2})
        payload, _ = _req("GET", "preview", query={"run": "run1", "file": "prd-review.json"})
        data = payload["data"]
        assert json.loads(data["content"]) == {"verdict": "pass", "issues": 2}

    def test_unknown_file(self, _isolate):
        """GIVEN missing file WHEN preview THEN 404."""
        _session(_isolate, "run1")
        payload, status = _req("GET", "preview", query={"run": "run1", "file": "nope.md"})
        assert status == 404

    def test_traversal_rejected(self, _isolate):
        """SECURITY: ../ traversal in file param is rejected with 403."""
        _session(_isolate, "run1")
        secret = _write(_isolate, "secret.txt", "top secret")
        payload, status = _req("GET", "preview",
                               query={"run": "run1", "file": "../secret.txt"})
        assert status == 403
        assert "inside" in payload["error"]

    def test_nested_traversal_rejected(self, _isolate):
        """SECURITY: nested ../ traversal is rejected with 403."""
        _session(_isolate, "run1")
        payload, status = _req("GET", "preview",
                               query={"run": "run1", "file": "sub/../../secret.txt"})
        assert status == 403

    def test_run_id_traversal_rejected(self, _isolate):
        """SECURITY: run id escaping sessions dir is treated as not found."""
        _session(_isolate, "run1")
        payload, status = _req("GET", "preview",
                               query={"run": "../run1", "file": "prd.md"})
        assert status == 404

    def test_large_file_truncated(self, _isolate):
        """GIVEN file > 100KB WHEN preview THEN truncated flag + cap."""
        _session(_isolate, "run1")
        big = "x" * (A.MAX_PREVIEW_BYTES + 5000)
        _write(_isolate, ".osh/sessions/run1/big.txt", big)
        payload, _ = _req("GET", "preview", query={"run": "run1", "file": "big.txt"})
        data = payload["data"]
        assert data["truncated"] is True
        assert len(data["content"]) == A.MAX_PREVIEW_BYTES
        assert data["size"] == len(big)
        assert data["note"] and "截断" in data["note"]

    def test_unsupported_type(self, _isolate):
        """GIVEN binary ext WHEN preview THEN 415."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/firmware.bin", b"\x00\x01")
        payload, status = _req("GET", "preview", query={"run": "run1", "file": "firmware.bin"})
        assert status == 415


# ── evidence-pack ──────────────────────────────────────────────────────

class TestEvidencePack:
    def test_missing_run(self):
        """GIVEN no run WHEN evidence-pack THEN 400."""
        payload, status = _req("GET", "evidence-pack")
        assert status == 400

    def test_unknown_run(self, _isolate):
        """GIVEN unknown run WHEN evidence-pack THEN 404."""
        payload, status = _req("GET", "evidence-pack", query={"run": "nope"})
        assert status == 404

    def test_pack_files(self, _isolate):
        """GIVEN final-report + json evidence WHEN pack THEN both listed."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/final-report.md", "# 最终报告\n")
        _write(_isolate, ".osh/sessions/run1/test-qualification.json", {"ok": True})
        _write(_isolate, ".osh/sessions/run1/misra-review.json", {"ok": True})
        _write(_isolate, ".osh/sessions/run1/prd.md", "# PRD\n")  # not evidence
        payload, status = _req("GET", "evidence-pack", query={"run": "run1"})
        assert status == 200
        data = payload["data"]
        assert data["run_id"] == "run1"
        assert data["name"] == "PRD 生成"
        paths = {f["path"] for f in data["files"]}
        assert paths == {"final-report.md", "test-qualification.json", "misra-review.json"}
        assert "prd.md" not in paths and "session.json" not in paths
        assert data["count"] == 3
        assert data["note"] is None

    def test_no_evidence_files(self, _isolate):
        """GIVEN run without evidence files WHEN pack THEN empty + note."""
        _session(_isolate, "run1")
        _write(_isolate, ".osh/sessions/run1/prd.md", "# PRD\n")
        payload, _ = _req("GET", "evidence-pack", query={"run": "run1"})
        data = payload["data"]
        assert data["files"] == [] and data["count"] == 0
        assert data["note"] and "无证据包" in data["note"]
