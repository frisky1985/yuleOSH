"""API Key management endpoints.

POST   /api/v1/apikeys          — generate new key (returns full key once)
GET    /api/v1/apikeys          — list keys (prefix + label, never full key)
DELETE /api/v1/apikeys/{id}     — revoke key
"""

import hashlib
import os
import secrets

from . import json_ok, json_error
from src.store import Store


def handle_apikeys(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to api key sub-resources."""
    if method == "POST" and path_tail == "":
        return _generate_key(body)
    elif method == "GET" and path_tail == "":
        return _list_keys()
    elif method == "DELETE" and path_tail:
        return _revoke_key(path_tail)
    else:
        return json_error(f"Unsupported {method} /api/v1/apikeys/{path_tail}", 404)


def _generate_key(body: dict) -> tuple[dict, int]:
    """POST /api/v1/apikeys — generate a new API key.

    Body: {"label": "My Key"}
    Returns: {"key": "yule_xxxx...", "prefix": "yule_abcd1..."}

    The full key is returned ONCE and cannot be retrieved again.
    Only the prefix (first 8 chars) is stored for display.
    """
    label = body.get("label", "").strip()
    if not label:
        return json_error("label is required", 400)
    if len(label) > 100:
        return json_error("label must be 100 characters or fewer", 400)

    # Generate a cryptographically random API key
    raw_key = "yule_" + secrets.token_hex(32)  # e.g. yule_<64 hex chars>
    prefix = raw_key[:16]  # "yule_xxxxx" — 16 chars for display (with yule_ prefix)

    # Hash for storage
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    store = Store()
    try:
        record = store.create_api_key(key_hash, label, prefix)
    except Exception as e:
        # Hash collision or DB error — extremely unlikely
        return json_error(f"Failed to create key: {e}", 500)

    return json_ok({
        "id": record["id"],
        "key": raw_key,  # Full key — only returned once
        "prefix": prefix,
        "label": label,
        "created_at": record["created_at"],
    })


def _list_keys() -> tuple[dict, int]:
    """GET /api/v1/apikeys — list all API keys.

    Returns prefix + label + status only — NEVER the full key.
    """
    store = Store()
    keys = store.list_api_keys()
    return json_ok({
        "keys": keys,
        "count": len(keys),
    })


def _revoke_key(path_tail: str) -> tuple[dict, int]:
    """DELETE /api/v1/apikeys/{id} — revoke an API key by ID."""
    try:
        key_id = int(path_tail)
    except (ValueError, TypeError):
        return json_error("Invalid key ID", 400)

    store = Store()
    success = store.revoke_api_key(key_id)
    if not success:
        return json_error("Key not found or already revoked", 404)

    return json_ok({"id": key_id, "revoked": True})
