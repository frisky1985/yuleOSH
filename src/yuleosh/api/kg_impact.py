#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph API — /api/v1/kg/query/impact endpoint (P1).

Handles POST /api/v1/kg/query/impact:
  - Takes changed_files, change_type, include_* params
  - Returns affected requirements, tests, and code functions
  - Uses either SQLite or PostgreSQL backend based on YULEOSH_DB_URL

Request format:
    POST /api/v1/kg/query/impact
    {
        "changed_files": ["src/yuleosh/foo.py", "src/yuleosh/bar.py"],
        "change_type": "modify",   # optional, default "modify"
        "layer": null,             # optional test layer filter
        "include_affected_tests": true,
        "include_affected_reqs": true
    }

Response:
    {
        "affected_reqs": [...],
        "affected_tests": [...],
        "affected_functions": [...],
        "impact_summary": "...",
        "low_confidence_warning": false,
        "status": "ok"
    }
"""

import json
import logging
import os

from yuleosh.knowledge_graph import get_store
from yuleosh.knowledge_graph.queries import impact_analysis

log = logging.getLogger("yuleosh.knowledge_graph.api.kg_impact")


def handle_kg_impact(handler, params: dict):
    """Handler for POST /api/v1/kg/query/impact.

    Args:
        handler: BaseHTTPRequestHandler (for response writing)
        params: Parsed request body dict

    Returns:
        None (writes response to handler)
    """
    try:
        # Validate input
        if not isinstance(params, dict):
            _write_error(handler, 400, "Body must be a JSON object")
            return

        changed_files = params.get("changed_files")
        if not changed_files or not isinstance(changed_files, list):
            _write_error(handler, 400, "missing or invalid 'changed_files': must be a list of file paths")
            return

        if not changed_files:
            _write_error(handler, 400, "'changed_files' must not be empty")
            return

        for f in changed_files:
            if not isinstance(f, str) or not f.strip():
                _write_error(handler, 400, f"invalid file path: {f!r}")
                return

        changed_files = [f.strip() for f in changed_files]

        change_type = params.get("change_type", "modify")
        layer = params.get("layer")
        include_tests = params.get("include_affected_tests", True)
        include_reqs = params.get("include_affected_reqs", True)

        # Get store
        try:
            store = get_store()
        except Exception as e:
            log.error("Failed to initialize KG store: %s", e)
            _write_error(handler, 500, f"Knowledge Graph store initialization failed: {e}")
            return

        # Run impact analysis
        try:
            result = impact_analysis(store, changed_files, layer=layer)
        except Exception as e:
            log.error("Impact analysis failed: %s", e)
            _write_error(handler, 500, f"Impact analysis failed: {e}")
            return

        # Post-process result
        response = {
            "status": "ok",
            "changed_files": changed_files,
            "change_type": change_type,
        }

        if include_reqs:
            response["affected_reqs"] = result.get("affected_reqs", [])
        if include_tests:
            response["affected_tests"] = result.get("affected_tests", [])
        response["affected_functions"] = result.get("affected_functions", [])
        response["impact_summary"] = result.get("impact_summary", "No impact found")
        if result.get("low_confidence_warning"):
            response["low_confidence_warning"] = True

        _write_ok(handler, response)

    except Exception as e:
        log.error("Unhandled error in kg/query/impact: %s", e, exc_info=True)
        _write_error(handler, 500, f"Internal server error: {e}")


def _write_ok(handler, data: dict):
    """Write a 200 JSON response."""
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_error(handler, status: int, message: str):
    """Write an error JSON response."""
    body = json.dumps({
        "status": "error",
        "error": message,
    }, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
