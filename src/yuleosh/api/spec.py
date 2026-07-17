# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""OpenSpec validate and diff endpoints."""

import json
import os
import sys
from pathlib import Path

from . import json_ok, json_error
from .middleware import require_auth


@require_auth
def handle_spec(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to spec sub-resources."""
    if path_tail == "validate":
        return _validate(method, body)
    elif path_tail == "diff":
        return _diff(method, body)
    return json_error(f"Unknown spec resource: {path_tail}", 404)


def _validate(method: str, body: dict) -> tuple[dict, int]:
    """POST /api/v1/spec/validate — validate an OpenSpec file."""
    if method != "POST":
        return json_error("Use POST to validate", 405)

    spec_path = body.get("path", "")
    if not spec_path:
        return json_error("'path' is required")

    from . import OSH_HOME
    project_root = Path(OSH_HOME).resolve()
    resolved = (project_root / spec_path.lstrip("/")).resolve()

    # SECURITY: path traversal guard
    try:
        resolved.relative_to(project_root)
    except ValueError:
        return json_error("Spec path must be within project directory", 403)

    if not resolved.exists():
        return json_error(f"Spec file not found: {resolved}")

    # Import and run validation
    from yuleosh.spec.validate import parse_spec, validate_spec, _compute_coverage

    doc = parse_spec(str(resolved))
    issues = validate_spec(doc)
    coverage = _compute_coverage(doc)

    result = {
        "file": str(resolved),
        "requirements": len(doc.requirements),
        "scenarios": len(doc.scenarios),
        "total_shall": sum(len(r.shall) for r in doc.requirements),
        "issues": issues,
        "issue_count": len(issues),
        "error_count": sum(1 for i in issues if i["severity"] == "ERROR"),
        "coverage": coverage,
    }
    return json_ok(result)


def _diff(method: str, body: dict) -> tuple[dict, int]:
    """POST /api/v1/spec/diff — diff two OpenSpec files."""
    if method != "POST":
        return json_error("Use POST to diff", 405)

    old_path = body.get("old", "")
    new_path = body.get("new", "")

    if not old_path or not new_path:
        return json_error("'old' and 'new' paths are required")

    from yuleosh.spec.validate import diff_specs

    resolved_old = Path(old_path)
    resolved_new = Path(new_path)
    if not resolved_old.is_absolute():
        from . import OSH_HOME
        resolved_old = Path(OSH_HOME) / resolved_old
    if not resolved_new.is_absolute():
        from . import OSH_HOME
        resolved_new = Path(OSH_HOME) / resolved_new

    if not resolved_old.exists():
        return json_error(f"Old spec not found: {resolved_old}")
    if not resolved_new.exists():
        return json_error(f"New spec not found: {resolved_new}")

    delta = diff_specs(str(resolved_old), str(resolved_new))
    return json_ok(delta)
