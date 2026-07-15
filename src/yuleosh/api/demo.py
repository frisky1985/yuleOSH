#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
SaaS Try-it Demo — mock pipeline API endpoint.

Endpoints:
  GET  /api/v1/demo/pipeline            — Trigger full mock pipeline
  GET  /api/v1/demo/pipeline?step=<N>   — Partial progress (step N running)
  GET  /api/v1/demo/pipeline/<id>       — Query pipeline status by ID
  GET  /api/v1/demo/pipeline/<id>/report — Get final report
  GET  /api/v1/demo/evidence/<id>.zip   — Download evidence pack

Requirements (DEMO-REQ-002 through DEMO-REQ-008):
  - No authentication required
  - No real LLM calls (fully mock)
  - Rate limited: 10 req/min/IP (DEMO-REQ-005)
  - YULEOSH_DEMO_ENABLED gate (DEMO-REQ-003)
"""

import io
import json
import os
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler

from . import json_ok, json_error, read_body
from yuleosh.api.cors import get_cors_origin

# ── Demo state ──────────────────────────────────────────────────────────

DEMO_STEPS = [
    {
        "id": "spec-parse",
        "name": "Spec Parsing",
        "output_summary": "Parsed OpenSpec document: 5 requirements, 3 scenarios detected.",
        "duration_ms": 1200,
        "artifacts": {"requirements_count": 5, "scenarios_count": 3},
    },
    {
        "id": "requirements-analysis",
        "name": "Requirements Analysis",
        "output_summary": "Analysis complete: 5 SHALL statements, 0 conflicts, 2 dependencies.",
        "duration_ms": 2400,
        "artifacts": {"requirements_analyzed": 5, "dependencies": 2},
    },
    {
        "id": "sdd",
        "name": "System Design Document",
        "output_summary": "Generated SDD: 3 modules, 8 interfaces, 12 data flows.",
        "duration_ms": 3800,
        "artifacts": {"modules": 3, "interfaces": 8, "data_flows": 12},
    },
    {
        "id": "code-gen",
        "name": "Code Generation",
        "output_summary": "Generated 4 source files, 2 header files, 1 CMakeLists.txt.",
        "duration_ms": 5100,
        "artifacts": {"source_files": 4, "header_files": 2, "build_files": 1},
    },
    {
        "id": "internal-review",
        "name": "Internal Review",
        "output_summary": "52 issues found: 3 errors, 12 warnings, 37 suggestions.",
        "duration_ms": 2900,
        "artifacts": {"errors": 3, "warnings": 12, "suggestions": 37},
    },
    {
        "id": "test-plan",
        "name": "Test Plan Generation",
        "output_summary": "Generated 18 test cases across 4 test suites.",
        "duration_ms": 1600,
        "artifacts": {"test_cases": 18, "test_suites": 4},
    },
    {
        "id": "code-review",
        "name": "Code Review (4-Agent Matrix)",
        "output_summary": "4 agents reviewed: quality 8.4/10, security 9.1/10, style 7.8/10, safety 8.9/10.",
        "duration_ms": 6200,
        "artifacts": {
            "quality_score": 8.4,
            "security_score": 9.1,
            "style_score": 7.8,
            "safety_score": 8.9,
        },
    },
    {
        "id": "ci-layer1",
        "name": "CI Layer 1 — Unit Test",
        "output_summary": "18/20 tests passed, 83.7% line coverage.",
        "duration_ms": 4100,
        "artifacts": {"tests_passed": 18, "tests_total": 20, "coverage_pct": 83.7},
    },
    {
        "id": "ci-layer2",
        "name": "CI Layer 2 — Cross-Compile + Static Analysis",
        "output_summary": "ARM GCC cross-compile: PASS. MISRA: 3 warnings, 0 errors.",
        "duration_ms": 8800,
        "artifacts": {"cross_compile": "pass", "misra_warnings": 3, "misra_errors": 0},
    },
    {
        "id": "ci-layer3",
        "name": "CI Layer 3 — System Verification + Evidence Pack",
        "output_summary": "All verification gates passed. Evidence pack generated.",
        "duration_ms": 3500,
        "artifacts": {"gates_passed": 5, "evidence_files": 6},
    },
]

FINAL_REPORT = {
    "summary": (
        "## Demo Pipeline Results\\n\\n"
        "The yuleOSH pipeline completed successfully for the embedded C project.\\n\\n"
        "### Key Metrics\\n"
        "- **Spec Coverage**: 100% (5/5 requirements covered by scenarios)\\n"
        "- **Code Quality**: 8.4/10 (4-agent matrix review)\\n"
        "- **Test Coverage**: 83.7% line coverage (18/20 tests passing)\\n"
        "- **MISRA Compliance**: 3 warnings, 0 errors\\n"
        "- **Cross-Compile**: ARM GCC target build passed\\n\\n"
        "### Pipeline Summary\\n"
        "All 10 pipeline steps completed in approximately 39.8 seconds (simulated).\\n"
        "The evidence pack is ready for download.\\n"
    ),
    "coverage_prediction": "72%",
    "review_score": "8.4/10",
    "compliance_gates": {
        "aspice": "passed",
        "misra": "3 warnings",
        "unit_test": "18/20 passed",
    },
}

# In-memory pipeline state store
_pipeline_store: dict[str, dict] = {}


def _is_demo_enabled() -> bool:
    """Check if demo pipeline is enabled (DEMO-REQ-003)."""
    val = os.environ.get("YULEOSH_DEMO_ENABLED", "true").lower()
    return val != "false"


def _generate_pipeline(step_limit: int | None = None) -> dict:
    """Generate a mock pipeline response.

    If step_limit is None, all steps are completed.
    If step_limit is N, steps 0..N-1 are completed, step N is running.
    """
    now = time.time()
    total_steps = len(DEMO_STEPS)

    if step_limit is None:
        current_step = total_steps
        status = "completed"
    else:
        current_step = min(step_limit, total_steps)
        status = "running" if current_step < total_steps else "completed"

    pipeline_id = f"demo-{uuid.uuid4().hex[:12]}"

    steps_out = []
    for i, step in enumerate(DEMO_STEPS):
        if i < current_step:
            s = dict(step, status="completed")
        elif i == current_step:
            s = dict(step, status="running")
        else:
            s = dict(step, status="pending")
        steps_out.append(s)

    response = {
        "status": status,
        "pipeline_id": pipeline_id,
        "total_steps": total_steps,
        "current_step": current_step,
        "steps": steps_out,
        "final_report": FINAL_REPORT if status == "completed" else None,
        "evidence_pack_url": f"/api/v1/demo/evidence/{pipeline_id}.zip",
    }

    # Store for later queries
    _pipeline_store[pipeline_id] = response
    return response


def _generate_evidence_zip(pipeline_id: str) -> bytes:
    """Generate a mock evidence pack ZIP (DEMO-REQ-006)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("traceability-matrix.csv",
                     "Req ID,Test Case,Status,Reviewer\n"
                     "SR-001,TC-001,PASS,Agent-A\n"
                     "SR-002,TC-002,PASS,Agent-B\n"
                     "REQ-001,TC-003,PASS,Agent-A\n"
                     "REQ-002,TC-004,FAIL,Agent-C\n"
                     "REQ-003,TC-005,PASS,Agent-B\n")
        zf.writestr("acceptance-matrix.md",
                     "# Acceptance Matrix\\n\\n"
                     "| ID | Requirement | Status | Evidence |\\n"
                     "|:---|:------------|:-------|:---------|\\n"
                     "| SR-001 | System Initialization | ✅ PASS | traceability-matrix.csv |\\n"
                     "| SR-002 | Task Management | ✅ PASS | traceability-matrix.csv |\\n"
                     "| REQ-001 | GPIO Control | ✅ PASS | traceability-matrix.csv |\\n"
                     "| REQ-002 | Sensor Comms | ❌ FAIL | traceability-matrix.csv |\\n")
        zf.writestr("review-report.md",
                     "# Code Review Report\\n\\n"
                     "## Summary\\n"
                     "- **Review Agent**: 4-Agent Matrix\\n"
                     "- **Files Reviewed**: 12\\n"
                     "- **Total Issues**: 52 (3 errors, 12 warnings, 37 suggestions)\\n\\n"
                     "## Scores\\n"
                     "- Quality: 8.4/10\\n"
                     "- Security: 9.1/10\\n"
                     "- Style: 7.8/10\\n"
                     "- Safety: 8.9/10\\n")
        zf.writestr("coverage-report.xml",
                     '<?xml version="1.0" ?>\n'
                     '<coverage line-rate="0.837" branch-rate="0.72">\n'
                     '  <packages>\n'
                     '    <package name="app" line-rate="0.837">\n'
                     '      <classes>\n'
                     '        <class name="main.c" filename="src/main.c" line-rate="0.85"/>\n'
                     '        <class name="gpio.c" filename="src/hal/gpio.c" line-rate="0.92"/>\n'
                     '        <class name="uart.c" filename="src/hal/uart.c" line-rate="0.78"/>\n'
                     '      </classes>\n'
                     '    </package>\n'
                     '  </packages>\n'
                     '</coverage>\n')
        zf.writestr("compliance-checklist.md",
                     "# Compliance Checklist\\n\\n"
                     "## ASPICE\\n"
                     "- SWE.1: ✅ Software requirements analysis complete\\n"
                     "- SWE.2: ✅ Software architectural design complete\\n"
                     "- SWE.3: ✅ Software detailed design and unit construction complete\\n"
                     "- SWE.4: ✅ Software unit verification complete\\n"
                     "- SWE.5: ✅ Software integration and integration test complete\\n"
                     "- SWE.6: ✅ Software qualification test complete\\n\\n"
                     "## MISRA-C:2012\\n"
                     "- Mandatory rules: 0 violations\\n"
                     "- Required rules: 3 violations (waived)\\n"
                     "- Advisory rules: 0 violations\\n")
    return buf.getvalue()


# ── Rate limiter ────────────────────────────────────────────────────────

_demo_request_log: dict[str, list[float]] = {}
_DEMO_RATE_LIMIT = 10  # requests per minute


def _check_demo_rate_limit(ip: str) -> tuple[bool, int]:
    """Check rate limit per IP. Returns (allowed, retry_after_seconds)."""
    now = time.time()
    window = 60.0  # 1 minute

    if ip not in _demo_request_log:
        _demo_request_log[ip] = []

    # Purge old entries
    _demo_request_log[ip] = [t for t in _demo_request_log[ip] if now - t < window]

    if len(_demo_request_log[ip]) >= _DEMO_RATE_LIMIT:
        oldest = _demo_request_log[ip][0]
        retry_after = int(window - (now - oldest)) + 1
        return False, retry_after

    _demo_request_log[ip].append(now)
    return True, 0


# ── Handler ─────────────────────────────────────────────────────────────

def handle_demo(method: str, path_tail: str, body: dict, query: dict,
                handler: BaseHTTPRequestHandler) -> tuple | None:
    """Route to /api/v1/demo/* endpoints (DEMO-REQ-002 through DEMO-REQ-006)."""
    # Check if demo is enabled
    if not _is_demo_enabled():
        return json_error("demo_pipeline_disabled",
                          "Demo pipeline is disabled by administrator.", 503)

    # Rate limiting (DEMO-REQ-005)
    ip = handler.client_address[0]
    allowed, retry_after = _check_demo_rate_limit(ip)
    if not allowed:
        handler.send_response(429)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Retry-After", str(retry_after))
        handler.send_header("Access-Control-Allow-Origin", get_cors_origin(handler.headers.get("Origin")))
        handler.end_headers()
        handler.wfile.write(json.dumps({
            "ok": False,
            "error": f"Rate limit exceeded. Retry after {retry_after} seconds.",
        }).encode())
        return None

    # Evidence pack download (DEMO-REQ-006)
    if path_tail.startswith("evidence/") and path_tail.endswith(".zip"):
        if method != "GET":
            return json_error("Method not allowed", 405)

        # Extract pipeline_id from path
        zip_path = path_tail[len("evidence/"):]
        pipeline_id = zip_path.replace(".zip", "")

        if not pipeline_id.startswith("demo-"):
            return json_error("Invalid pipeline ID", 400)

        zip_data = _generate_evidence_zip(pipeline_id)
        handler.send_response(200)
        handler.send_header("Content-Type", "application/zip")
        handler.send_header("Content-Disposition",
                            f'attachment; filename="{pipeline_id}.zip"')
        handler.send_header("Content-Length", str(len(zip_data)))
        handler.send_header("Access-Control-Allow-Origin", get_cors_origin(handler.headers.get("Origin")))
        handler.end_headers()
        handler.wfile.write(zip_data)
        return None

    # Pipeline status by ID (DEMO-REQ-002)
    # Pattern: <pipeline_id>  or  <pipeline_id>/report
    if path_tail and path_tail != "pipeline":
        parts = path_tail.split("/")
        pipeline_id = parts[0]
        sub_action = parts[1] if len(parts) > 1 else ""

        if pipeline_id in _pipeline_store:
            entry = _pipeline_store[pipeline_id]
            if sub_action == "report":
                return json_ok(entry.get("final_report"))
            return json_ok(entry)

        return json_error(f"Pipeline '{pipeline_id}' not found", 404)

    # Trigger new pipeline (DEMO-REQ-002)
    if method != "GET":
        return json_error("Method not allowed", 405)

    # Handle ?step=N parameter for partial progress
    step_param = None
    if query and "step" in query:
        try:
            step_param = max(0, min(int(query["step"][0]), len(DEMO_STEPS)))
        except (ValueError, TypeError):
            pass

    result = _generate_pipeline(step_param)
    return json_ok(result)
