# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Encrypted provider-secret management endpoints (SEC-PK).

POST   /api/v1/secrets          — store a provider secret (encrypts at rest)
GET    /api/v1/secrets          — list secrets (metadata ONLY, never plaintext)
DELETE /api/v1/secrets/{id}     — delete a stored secret

Security:
- The plaintext is accepted in the POST body, encrypted immediately, and NEVER
  returned by any endpoint (not even at set time — the caller already has it).
- GET returns only {id, provider, key_name, created_at, updated_at, last_used_at}.
- All endpoints require authentication (require_auth).
"""
from __future__ import annotations

from . import json_ok, json_error
from ._errors import internal_error
from .middleware import require_auth
from yuleosh.secret_vault import (
    set_provider_secret,
    list_provider_secrets,
    delete_provider_secret,
    ALLOWED_KEY_NAMES,
    vault_available,
)


@require_auth
def handle_secrets(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to secret sub-resources."""
    if method == "POST" and path_tail == "":
        return _set_secret(body)
    elif method == "GET" and path_tail == "":
        return _list_secrets()
    elif method == "DELETE" and path_tail:
        return _delete_secret(path_tail)
    else:
        return json_error(f"Unsupported {method} /api/v1/secrets/{path_tail}", 404)


def _set_secret(body: dict) -> tuple[dict, int]:
    """POST /api/v1/secrets — encrypt and store a provider secret."""
    provider = (body.get("provider") or "").strip()
    key_name = (body.get("key_name") or "").strip()
    value = body.get("value") or ""
    if not provider:
        return json_error("provider is required", 400)
    if not key_name:
        return json_error("key_name is required", 400)
    if key_name not in ALLOWED_KEY_NAMES:
        return json_error(
            f"key_name must be one of: {', '.join(sorted(ALLOWED_KEY_NAMES))}", 400
        )
    if not value:
        return json_error("value is required", 400)

    if not vault_available():
        return json_error(
            "Secret vault unavailable: server missing YULEOSH_JWT_SECRET / "
            "YULEOSH_MASTER_KEY",
            503,
        )

    try:
        record = set_provider_secret(provider, key_name, value)
    except ValueError as e:
        return json_error(str(e), 400)
    except Exception as e:
        # SEC-C2: never echo internal exception details to the client.
        return internal_error("secrets", e)

    return json_ok({
        "id": record["id"],
        "provider": record["provider"],
        "key_name": record["key_name"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }), 201


def _list_secrets() -> tuple[dict, int]:
    """GET /api/v1/secrets — list metadata only (never plaintext)."""
    try:
        secrets = list_provider_secrets()
    except Exception as e:
        return internal_error("secrets", e)
    return json_ok({"secrets": secrets, "count": len(secrets)})


def _delete_secret(path_tail: str) -> tuple[dict, int]:
    """DELETE /api/v1/secrets/{id} — delete a stored secret."""
    try:
        secret_id = int(path_tail)
    except (ValueError, TypeError):
        return json_error("Invalid secret ID", 400)
    try:
        ok = delete_provider_secret(secret_id)
    except Exception as e:
        return internal_error("secrets", e)
    if not ok:
        return json_error("Secret not found", 404)
    return json_ok({"id": secret_id, "deleted": True})
