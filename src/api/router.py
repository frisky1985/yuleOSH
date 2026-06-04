"""yuleOSH REST API v1 router — dispatches requests to handler modules.

Mounted at /api/v1/ in the main server.
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler

from . import json_ok, json_error, read_body
from .health import handle_health
from .spec import handle_spec
from .pipeline import handle_pipeline
from .ci import handle_ci
from .review import handle_review
from .evidence import handle_evidence
from .project import handle_project
from .stats import handle_stats
from .notify import handle_notify
from .apikeys import handle_apikeys
from .wizard import handle_wizard
from .webhooks import handle_webhooks


# Resource routing map: resource_name -> handler function
ROUTES = {
    "health": handle_health,
    "wizard": handle_wizard,
    "spec": handle_spec,
    "pipeline": handle_pipeline,
    "ci": handle_ci,
    "review": handle_review,
    "evidence": handle_evidence,
    "project": handle_project,
    "stats": handle_stats,
    "notify": handle_notify,
    "apikeys": handle_apikeys,
    "webhooks": handle_webhooks,
}


def dispatch(handler: BaseHTTPRequestHandler, path: str):
    """Dispatch an API request to the appropriate handler.

    path is the full URL path (e.g. /api/v1/pipeline/status)
    """
    parsed = urlparse(path)
    clean_path = parsed.path.rstrip("/")

    # Strip /api/v1 prefix
    prefix = "/api/v1"
    if not clean_path.startswith(prefix):
        return _respond(handler, *json_error("Not an API route", 404))

    remainder = clean_path[len(prefix):].strip("/")
    query = parse_qs(parsed.query)

    # Parse resource from the remainder
    parts = remainder.split("/", 1)
    resource = parts[0] if parts else ""
    path_tail = parts[1] if len(parts) > 1 else ""

    body = read_body(handler)
    method = handler.command

    # Find the handler
    handler_fn = ROUTES.get(resource)
    if handler_fn is None:
        return _respond(handler, *json_error(f"Unknown resource: {resource}", 404))

    try:
        result = handler_fn(method=method, path_tail=path_tail, body=body,
                            query=query, handler=handler)
        # If handler returned None, it already sent the response (e.g. binary download)
        if result is None:
            return
        _respond(handler, *result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        _respond(handler, *json_error(f"Internal error: {e}", 500))


def _respond(handler: BaseHTTPRequestHandler, data: dict, status: int = 200):
    """Send a JSON response."""
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
