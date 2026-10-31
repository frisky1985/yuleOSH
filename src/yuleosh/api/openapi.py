# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""OpenAPI 3.0 description for the desktop API.

The spec is built from a declarative route table so it stays in sync with
:mod:`yuleosh.api.desktop` without duplicating handler logic.  It is served
at ``GET /api/v1/desktop/openapi.json``.
"""

from __future__ import annotations

from typing import Any

API_VERSION = "1.0.0"

# (method, path, summary, tag, request_fields)
# ``request_fields``: comma-separated body field names for POST endpoints.
_ROUTES: list[tuple[str, str, str, str, str]] = [
    ("GET", "/projects", "List desktop projects", "projects", ""),
    ("POST", "/projects", "Create a desktop project", "projects", "name,description"),
    ("GET", "/projects/{project_id}", "Get project metadata", "projects", ""),
    ("DELETE", "/projects/{project_id}", "Delete a desktop project", "projects", ""),

    ("GET", "/projects/{project_id}/requirements", "Read project requirements", "requirements", ""),
    ("POST", "/projects/{project_id}/requirements", "Import requirements", "requirements", "content,filename"),

    ("GET", "/projects/{project_id}/change-requests", "List change requests", "change-control", ""),
    ("POST", "/projects/{project_id}/change-requests", "Create a change request", "change-control", "title,description"),
    ("POST", "/projects/{project_id}/change-requests/{cr_id}/transition", "Transition a change request", "change-control", "status,comment,author"),

    ("GET", "/projects/{project_id}/baselines", "List baselines", "baselines", ""),
    ("POST", "/projects/{project_id}/baselines", "Create a baseline snapshot", "baselines", "name,note"),

    ("GET", "/projects/{project_id}/traceability", "Traceability matrix", "traceability", ""),
    ("POST", "/projects/{project_id}/traceability/refresh", "Refresh traceability matrix", "traceability", "baseline"),

    ("GET", "/projects/{project_id}/templates", "List document templates", "templates", ""),
    ("POST", "/projects/{project_id}/templates", "Generate a document template", "templates", "name,overwrite"),

    ("GET", "/projects/{project_id}/qa", "List QA audits", "qa", ""),
    ("POST", "/projects/{project_id}/qa", "Create a QA audit", "qa", "title,auditor,auditor_role,scope"),
    ("GET", "/projects/{project_id}/qa/{audit_id}", "Get a QA audit", "qa", ""),
    ("GET", "/projects/{project_id}/qa/export", "Export the QA audit report", "qa", ""),
    ("POST", "/projects/{project_id}/qa/{audit_id}/approve", "Approve and close a QA audit", "qa", "approver,role,note"),
    ("POST", "/projects/{project_id}/qa/{audit_id}/findings", "Add a nonconformity finding", "qa", "description,severity,assigned_to"),
    ("POST", "/projects/{project_id}/qa/{audit_id}/findings/{finding_id}/transition", "Transition a finding", "qa", "status,resolution,verifier"),

    ("GET", "/projects/{project_id}/issues", "List issues", "issues", ""),
    ("POST", "/projects/{project_id}/issues", "Create an issue", "issues", "title,description,severity,owner,reported_by"),
    ("POST", "/projects/{project_id}/issues/{issue_id}/transition", "Transition an issue", "issues", "status,root_cause,resolution,verification,verified_by"),

    ("GET", "/projects/{project_id}/risks", "List risks", "project-mgmt", ""),
    ("POST", "/projects/{project_id}/risks", "Create a risk", "project-mgmt", "description,likelihood,impact,owner,owner_role"),
    ("POST", "/projects/{project_id}/risks/{risk_id}/transition", "Transition a risk", "project-mgmt", "status,mitigation,accepted_by,acceptance_role"),

    ("GET", "/projects/{project_id}/milestones", "List milestones", "project-mgmt", ""),
    ("POST", "/projects/{project_id}/milestones", "Create a milestone", "project-mgmt", "title,date,status"),

    ("POST", "/projects/{project_id}/compliance/run", "Run the compliance audit", "compliance", "version"),
    ("GET", "/projects/{project_id}/compliance", "Read the latest audit summary", "compliance", ""),
    ("GET", "/projects/{project_id}/compliance/dashboard", "Render the audit dashboard HTML", "compliance", ""),
]


def _body_schema(fields: str) -> dict[str, Any]:
    props = {
        name.strip(): {"type": "string"}
        for name in fields.split(",")
        if name.strip()
    }
    return {
        "required": False,
        "content": {
            "application/json": {
                "schema": {"type": "object", "properties": props},
            }
        },
    }


def build_openapi_spec() -> dict[str, Any]:
    """Build the OpenAPI 3.0.3 document for ``/api/v1/desktop``."""
    paths: dict[str, dict[str, Any]] = {}
    for method, path, summary, tag, fields in _ROUTES:
        operation: dict[str, Any] = {
            "summary": summary,
            "tags": [tag],
            "responses": {
                "200": {"description": "Success"},
                "400": {"description": "Invalid request or state transition"},
                "404": {"description": "Project or record not found"},
            },
        }
        if method in ("POST", "PUT") and fields:
            operation["requestBody"] = _body_schema(fields)
        paths.setdefault(path, {})[method.lower()] = operation

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "yuleOSH Desktop API",
            "version": API_VERSION,
            "description": (
                "Local desktop workspace API. E1–E3 in audit responses are "
                "evidence-coverage grades, NOT Automotive SPICE capability levels."
            ),
        },
        "servers": [{"url": "/api/v1/desktop"}],
        "tags": [
            {"name": "projects"},
            {"name": "requirements"},
            {"name": "change-control"},
            {"name": "baselines"},
            {"name": "traceability"},
            {"name": "templates"},
            {"name": "qa"},
            {"name": "issues"},
            {"name": "project-mgmt"},
            {"name": "compliance"},
        ],
        "paths": paths,
    }
