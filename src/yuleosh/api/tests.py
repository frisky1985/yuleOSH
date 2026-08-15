#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Tests API — three-layer test case management (design doc 模块 ⑤).

Serves REAL data only, parsed from the test artifacts written by the
pipeline into ``OSH_HOME/.osh/sessions/<run_id>/``:

    layer         artifact file(s)
    -----------   -------------------------------------
    unit          c-unit-test.json
    integration   integration-test.json
    qualification test-qualification.json / qualification-test.json

No mock fallback: when a layer has no artifact on disk the endpoint
returns an empty list plus a ``note`` — fabricated rows are forbidden.

Endpoints (mounted at /api/v1/tests in the main server router):

    GET /api/v1/tests?project=xxx&layer=unit|integration|qualification
        — test case listing with pass/fail/skip counts + case names
    GET /api/v1/tests/runs?project=xxx
        — execution history across runs (newest first)
    GET /api/v1/tests/coverage?project=xxx
        — latest coverage summary (c-coverage.json / .coverage-report.json)
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

from . import json_ok, json_error
from .middleware import require_auth

log = logging.getLogger("api.tests")

# Repository root — OSH_HOME env var wins, falls back to the repo root
# so ``.osh/sessions`` resolves correctly in dev.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
OSH_HOME = os.environ.get("OSH_HOME", str(PROJECT_ROOT))

LAYERS = ("unit", "integration", "qualification")

# Artifact filename(s) per layer (first existing file wins).
LAYER_FILES: dict[str, tuple[str, ...]] = {
    "unit": ("c-unit-test.json",),
    "integration": ("integration-test.json",),
    "qualification": ("test-qualification.json", "qualification-test.json"),
}

_COUNT_KEYS = {
    "passed": ("passed", "tests_passed", "pass_count", "num_passed", "successes"),
    "failed": ("failed", "tests_failed", "fail_count", "num_failed", "failures"),
    "skipped": ("skipped", "tests_skipped", "skip_count", "num_skipped"),
    "total": ("total", "total_tests", "test_count", "num_tests", "count"),
}
_STATUS_KEYS = ("status", "verdict", "result")
_TIME_KEYS = ("timestamp", "updated_at", "created_at", "finished_at", "started_at")
_DURATION_KEYS = ("duration", "duration_s", "elapsed", "total_time", "time")
_CASE_KEYS = ("cases", "test_cases", "tests", "results", "case_names")
_CASE_NAME_KEYS = ("name", "test_name", "tc_name", "case", "title", "id")


def _sessions_root() -> Path:
    """Root directory holding per-run session folders."""
    return Path(OSH_HOME) / ".osh" / "sessions"


def _q(query: dict, key: str, default: str = "") -> str:
    """Get a query parameter value (tolerates parse_qs list values)."""
    val = query.get(key)
    if isinstance(val, list):
        return val[0] if val else default
    return val or default


def _safe_run_id(run_id: str) -> bool:
    """Reject run ids that could address paths outside the sessions dir."""
    return bool(run_id) and run_id not in (".", "..") \
        and "/" not in run_id and "\\" not in run_id


def _session_meta(session_dir: Path) -> dict:
    """Parse session.json for a run; {} when absent/corrupt (no crash)."""
    try:
        meta = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
        return meta if isinstance(meta, dict) else {}
    except Exception:
        log.debug("Unreadable session.json in %s — treated as absent", session_dir)
        return {}


def _iter_sessions() -> Iterator[tuple[str, Path, dict]]:
    """Yield (run_id, session_dir, session_meta) for every session dir.

    name/status come from session.json when present; a dir without one
    yields an empty meta (handlers fall back to run_id / "unknown").
    """
    root = _sessions_root()
    if not root.is_dir():
        return
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        yield d.name, d, _session_meta(d)


def _session_matches_project(meta: dict, project: str) -> bool:
    """Filter sessions by project fields in session.json (exact match)."""
    if not project:
        return True
    for key in ("project", "project_id", "project_name"):
        val = meta.get(key)
        if val is not None and str(val) == project:
            return True
    return False


def _first(data: dict, keys: tuple[str, ...], default: Any = None) -> Any:
    """Return the first present value among candidate keys."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_case_names(data: dict) -> list[str]:
    """Collect test case names from common result-list shapes.

    Accepts both plain string entries and dicts carrying a name-ish key.
    Order is preserved; duplicates are removed.
    """
    names: list[str] = []
    for key in _CASE_KEYS:
        val = data.get(key)
        if not isinstance(val, list):
            continue
        for item in val:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                name = _first(item, _CASE_NAME_KEYS)
                if name is not None:
                    names.append(str(name))
    seen: set[str] = set()
    unique: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    return unique


def _parse_test_artifact(path: Path, layer: str) -> Optional[dict]:
    """Parse one test artifact JSON into a normalized run record.

    Returns None when the file cannot be read/parsed (real-data policy:
    corrupt artifacts are skipped, never replaced with fabricated rows).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.debug("Unreadable test artifact %s — skipped", path)
        return None
    if not isinstance(data, dict):
        return None

    passed = _as_int(_first(data, _COUNT_KEYS["passed"], 0))
    failed = _as_int(_first(data, _COUNT_KEYS["failed"], 0))
    skipped = _as_int(_first(data, _COUNT_KEYS["skipped"], 0))
    total = _as_int(_first(data, _COUNT_KEYS["total"], passed + failed + skipped))

    return {
        "layer": layer,
        "status": str(_first(data, _STATUS_KEYS, "unknown")),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": total,
        "duration": _as_float(_first(data, _DURATION_KEYS, 0.0)),
        "updated_at": str(_first(data, _TIME_KEYS, "") or ""),
        "cases": _extract_case_names(data),
    }


def _find_test_artifacts(session_dir: Path, layer: str) -> list[dict]:
    """Parse every test artifact of a layer present in a session dir."""
    records = []
    for fname in LAYER_FILES[layer]:
        p = session_dir / fname
        if not p.is_file():
            continue
        record = _parse_test_artifact(p, layer)
        if record is not None:
            records.append(record)
    return records


def _layer_note(layer: str) -> str:
    return f"未找到测试用例数据（.osh/sessions 下无 {layer} 层测试产物）"


# ── Handlers ────────────────────────────────────────────────────────────

@require_auth
def handle_tests(method: str, path_tail: str, body: dict, query: dict,
                 handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """Handle /api/v1/tests/... requests.

    ``**kwargs`` absorbs the ``current_user`` injected by require_auth.

    Supported routes:
        GET /api/v1/tests            — test case listing (+layer filter)
        GET /api/v1/tests/runs       — execution history
        GET /api/v1/tests/coverage   — latest coverage summary
    """
    if method != "GET":
        return json_error(f"Unknown tests sub-path or method: {method} {path_tail}", 404)
    if path_tail == "":
        return _tests_cases(query)
    if path_tail == "runs":
        return _tests_runs(query)
    if path_tail == "coverage":
        return _tests_coverage(query)
    return json_error(f"Unknown tests sub-path or method: {method} {path_tail}", 404)


def _tests_cases(query: dict) -> tuple[dict, int]:
    """GET /api/v1/tests — test case listing with pass/fail/skip counts.

    ``layer`` (unit|integration|qualification) is optional; without it all
    three layers are aggregated.  Each run entry carries the parsed counts
    plus the flattened list of case names.
    """
    project = _q(query, "project")
    layer = _q(query, "layer")

    if layer and layer not in LAYERS:
        return json_error(
            f"invalid layer: {layer} (expected one of {', '.join(LAYERS)})", 400)

    layers = [layer] if layer else list(LAYERS)
    runs = []
    for run_id, session_dir, meta in _iter_sessions():
        if not _session_matches_project(meta, project):
            continue
        for lyr in layers:
            for record in _find_test_artifacts(session_dir, lyr):
                runs.append({
                    "run_id": run_id,
                    "name": meta.get("name") or run_id,
                    "updated_at": record["updated_at"],
                    **{k: record[k] for k in
                       ("layer", "status", "passed", "failed", "skipped",
                        "total", "duration", "cases")},
                })

    runs.sort(key=lambda r: (r["updated_at"], r["run_id"]), reverse=True)

    summary = {
        "passed": sum(r["passed"] for r in runs),
        "failed": sum(r["failed"] for r in runs),
        "skipped": sum(r["skipped"] for r in runs),
        "total_cases": sum(len(r["cases"]) for r in runs),
    }

    note = None
    if not runs:
        note = _layer_note(layer) if layer else \
            "未找到测试用例数据（.osh/sessions 下无测试产物）"

    return json_ok({
        "project": project,
        "layer": layer or "all",
        "runs": runs,
        "summary": summary,
        "note": note,
    })


def _tests_runs(query: dict) -> tuple[dict, int]:
    """GET /api/v1/tests/runs — execution history across all sessions.

    One entry per test artifact found, sorted by ``updated_at`` descending
    (newest first).  Entries without a timestamp sort last.
    """
    project = _q(query, "project")

    entries = []
    for run_id, session_dir, meta in _iter_sessions():
        if not _session_matches_project(meta, project):
            continue
        for layer in LAYERS:
            for record in _find_test_artifacts(session_dir, layer):
                entries.append({
                    "run_id": run_id,
                    "layer": record["layer"],
                    "passed": record["passed"],
                    "failed": record["failed"],
                    "skipped": record["skipped"],
                    "duration": record["duration"],
                    "status": record["status"],
                    "updated_at": record["updated_at"],
                })

    entries.sort(key=lambda e: (e["updated_at"], e["run_id"]), reverse=True)

    note = None if entries else \
        "未找到测试执行历史（.osh/sessions 下无测试产物）"
    return json_ok({
        "project": project,
        "runs": entries,
        "count": len(entries),
        "note": note,
    })


def _coverage_from_c_coverage(data: dict) -> Optional[dict]:
    """Extract line/branch rate from a c-coverage.json style report."""
    line_rate = data.get("line_rate")
    branch_rate = data.get("branch_rate")
    if line_rate is None and branch_rate is None:
        return None
    return {
        "line_rate": _as_float(line_rate, 0.0),
        "branch_rate": _as_float(branch_rate, 0.0),
        "files": data.get("files"),
    }


def _coverage_from_coveragepy(data: dict) -> Optional[dict]:
    """Extract line/branch rate from a coverage.py JSON report."""
    totals = data.get("totals") or {}
    if not totals:
        return None
    return {
        "line_rate": _as_float(totals.get("percent_covered"), 0.0),
        "branch_rate": _as_float(totals.get("percent_branches_covered"), 0.0),
        "files": data.get("files"),
    }


def _tests_coverage(query: dict) -> tuple[dict, int]:
    """GET /api/v1/tests/coverage — latest coverage summary.

    Sources scanned (real data only):
      1. ``.osh/sessions/<run_id>/c-coverage.json`` per run
      2. ``OSH_HOME/.coverage-report.json`` (coverage.py format)

    The entry with the newest ``updated_at``/timestamp wins; when no
    source exists the response carries ``coverage: null`` + a note.
    """
    project = _q(query, "project")

    candidates: list[dict] = []
    for run_id, session_dir, meta in _iter_sessions():
        if not _session_matches_project(meta, project):
            continue
        p = session_dir / "c-coverage.json"
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            log.debug("Unreadable c-coverage.json %s — skipped", p)
            continue
        cov = _coverage_from_c_coverage(data)
        if cov is None:
            continue
        updated_at = str(_first(data, _TIME_KEYS, "") or "")
        if not updated_at:
            updated_at = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
        candidates.append({
            "source": "c-coverage.json",
            "run_id": run_id,
            "updated_at": updated_at,
            **cov,
        })

    root_report = Path(OSH_HOME) / ".coverage-report.json"
    if root_report.is_file():
        try:
            data = json.loads(root_report.read_text(encoding="utf-8"))
        except Exception:
            log.debug("Unreadable .coverage-report.json — skipped")
            data = None
        if data:
            cov = _coverage_from_coveragepy(data)
            if cov is not None:
                updated_at = str(data.get("meta", {}).get("timestamp", "") or "")
                if not updated_at:
                    updated_at = datetime.fromtimestamp(
                        root_report.stat().st_mtime).isoformat()
                candidates.append({
                    "source": ".coverage-report.json",
                    "run_id": None,
                    "updated_at": updated_at,
                    **cov,
                })

    if not candidates:
        return json_ok({
            "project": project,
            "coverage": None,
            "note": "未找到覆盖率数据（无 c-coverage.json / .coverage-report.json）",
        })

    latest = max(candidates, key=lambda c: c["updated_at"])
    latest.pop("updated_at", None)
    return json_ok({
        "project": project,
        "coverage": latest,
        "note": None,
    })
