"""Healthcheck endpoint."""

from . import json_ok, OSH_HOME
from src.store import Store


def handle_health(method: str, **kwargs):
    """GET /api/v1/health — return system health status."""
    store = Store()
    s = store.list_pipelines()
    return json_ok({
        "status": "ok",
        "version": "0.1.0",
        "auth_enabled": _auth_enabled(),
        "store_pipelines": len(s),
        "osh_home": OSH_HOME,
    })


def _auth_enabled() -> bool:
    try:
        from src.ui.auth import AUTH_ENABLED
        return AUTH_ENABLED
    except (ImportError, Exception):
        return False


def _extract_v1(path: str) -> str:
    """Strip /api/v1/ prefix, return the resource path."""
    for prefix in ("/api/v1/", "/api/v1"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path.lstrip("/")
