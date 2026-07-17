#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph API dispatcher — routes /api/v1/kg/*.

Sub-routes:
  POST /api/v1/kg/query/impact     — Impact analysis from changed files
"""

import json
import logging

from yuleosh.api import json_error
from .middleware import require_auth

log = logging.getLogger("yuleosh.knowledge_graph.api.kg")


@require_auth
def handle_kg(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Main dispatcher for /api/v1/kg/* routes. Requires authentication.

    Routes by path structure:
      - /query/impact → impact analysis
    """
    if not path_tail:
        return json_error("KG API resource required (query/impact)", 400)

    parts = path_tail.split("/", 2)
    if len(parts) < 2 or parts[0] != "query":
        return json_error(f"Unknown KG resource: {path_tail}", 404)

    resource = parts[1]

    if resource == "impact":
        if method != "POST":
            return json_error("POST required for /kg/query/impact", 405)
        return _handle_impact(kwargs.get("handler"), body)

    return json_error(f"Unknown KG resource: /{path_tail}", 404)


def _handle_impact(handler, body: dict):
    """Handle POST /api/v1/kg/query/impact.

    Delegates to kg_impact handler which writes its own response.
    """
    from yuleosh.api.kg_impact import handle_kg_impact
    handle_kg_impact(handler, body)
    return None  # Already wrote response
