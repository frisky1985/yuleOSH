# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Knowledge Base API endpoints — kb_articles, lessons, fmea_entries CRUD.

Mounted at /api/v1/kb/ in the main router.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs

from . import json_ok, json_error, get_store
from .middleware import require_auth
from yuleosh.kb.store import KbStore
from yuleosh.kb.models import (
    sanitize_kb_article_fields,
    sanitize_lesson_fields,
    sanitize_fmea_fields,
)


def _get_kb_store():
    """Get or create the KbStore instance."""
    return KbStore()


@require_auth
def handle_kb(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route KB requests to sub-resource handlers."""
    if not path_tail:
        return json_error("KB resource required", 404)

    parts = path_tail.split("/", 1)
    resource = parts[0]
    tail = parts[1] if len(parts) > 1 else ""

    if resource == "articles":
        return _handle_articles(method, tail, body, query)
    elif resource == "lessons":
        return _handle_lessons(method, tail, body, query)
    elif resource == "fmea":
        return _handle_fmea(method, tail, body, query)
    else:
        return json_error(f"Unknown KB resource: {resource}", 404)


# ── Articles ─────────────────────────────────────────────────────────────


def _parse_id(tail: str) -> tuple[int, str]:
    """Parse resource ID from path tail. Returns (id, remaining_path)."""
    if not tail:
        return None, tail
    parts = tail.split("/", 1)
    try:
        return int(parts[0]), parts[1] if len(parts) > 1 else ""
    except ValueError:
        return None, tail


def _handle_articles(method: str, tail: str, body: dict, query: dict):
    store = _get_kb_store()
    article_id, _ = _parse_id(tail)

    if method == "GET":
        if article_id is not None:
            article = store.get_article(article_id)
            if not article:
                return json_error("Article not found", 404)
            return json_ok(article.to_dict())

        # List with optional search
        search = _get_query_param(query, "search")
        limit = int(_get_query_param(query, "limit") or "100")
        offset = int(_get_query_param(query, "offset") or "0")
        articles = store.list_articles(search=search, limit=limit, offset=offset)
        total = store.count_articles(search=search)
        return json_ok({
            "items": [a.to_dict() for a in articles],
            "total": total,
            "limit": limit,
            "offset": offset,
        })

    elif method == "POST":
        fields = sanitize_kb_article_fields(body)
        if not fields.get("title"):
            return json_error("title is required")
        article = store.create_article(fields)
        return json_ok(article.to_dict())

    elif method == "PUT":
        if article_id is None:
            return json_error("Article ID required")
        fields = sanitize_kb_article_fields(body)
        if not fields:
            return json_error("No valid fields to update")
        article = store.update_article(article_id, fields)
        if not article:
            return json_error("Article not found", 404)
        return json_ok(article.to_dict())

    elif method == "DELETE":
        if article_id is None:
            return json_error("Article ID required")
        if store.delete_article(article_id):
            return json_ok({"deleted": True})
        return json_error("Article not found", 404)

    return json_error("Method not allowed", 405)


# ── Lessons ──────────────────────────────────────────────────────────────


def _handle_lessons(method: str, tail: str, body: dict, query: dict):
    store = _get_kb_store()
    lesson_id, _ = _parse_id(tail)

    if method == "GET":
        if lesson_id is not None:
            lesson = store.get_lesson(lesson_id)
            if not lesson:
                return json_error("Lesson not found", 404)
            return json_ok(lesson.to_dict())

        # List with optional filters
        project_id = _get_query_param(query, "project_id")
        severity = _get_query_param(query, "severity")
        limit = int(_get_query_param(query, "limit") or "100")
        offset = int(_get_query_param(query, "offset") or "0")

        if severity and severity not in ("low", "medium", "high", "critical"):
            return json_error(f"Invalid severity: {severity}")

        lessons = store.list_lessons(
            project_id=project_id or None,
            severity=severity or None,
            limit=limit,
            offset=offset,
        )
        total = store.count_lessons(
            project_id=project_id or None,
            severity=severity or None,
        )
        return json_ok({
            "items": [l.to_dict() for l in lessons],
            "total": total,
            "limit": limit,
            "offset": offset,
        })

    elif method == "POST":
        fields = sanitize_lesson_fields(body)
        if not fields.get("title"):
            return json_error("title is required")
        lesson = store.create_lesson(fields)
        return json_ok(lesson.to_dict())

    elif method == "PUT":
        if lesson_id is None:
            return json_error("Lesson ID required")
        fields = sanitize_lesson_fields(body)
        if not fields:
            return json_error("No valid fields to update")
        lesson = store.update_lesson(lesson_id, fields)
        if not lesson:
            return json_error("Lesson not found", 404)
        return json_ok(lesson.to_dict())

    elif method == "DELETE":
        if lesson_id is None:
            return json_error("Lesson ID required")
        if store.delete_lesson(lesson_id):
            return json_ok({"deleted": True})
        return json_error("Lesson not found", 404)

    return json_error("Method not allowed", 405)


# ── FMEA ─────────────────────────────────────────────────────────────────


def _handle_fmea(method: str, tail: str, body: dict, query: dict):
    store = _get_kb_store()
    entry_id, _ = _parse_id(tail)

    if method == "GET":
        if entry_id is not None:
            entry = store.get_fmea(entry_id)
            if not entry:
                return json_error("FMEA entry not found", 404)
            return json_ok(entry.to_dict())

        # List with optional sorting
        sort_by = _get_query_param(query, "sort_by") or "rpn"
        sort_desc = _get_query_param(query, "sort_desc", "true").lower() != "false"
        limit = int(_get_query_param(query, "limit") or "100")
        offset = int(_get_query_param(query, "offset") or "0")

        entries = store.list_fmea(sort_by=sort_by, sort_desc=sort_desc, limit=limit, offset=offset)
        total = store.count_fmea()
        return json_ok({
            "items": [e.to_dict() for e in entries],
            "total": total,
            "limit": limit,
            "offset": offset,
        })

    elif method == "POST":
        fields = sanitize_fmea_fields(body)
        if not fields.get("item"):
            return json_error("item is required")
        if not fields.get("failure_mode"):
            return json_error("failure_mode is required")
        entry = store.create_fmea(fields)
        return json_ok(entry.to_dict())

    elif method == "PUT":
        if entry_id is None:
            return json_error("FMEA entry ID required")
        fields = sanitize_fmea_fields(body)
        if not fields:
            return json_error("No valid fields to update")
        entry = store.update_fmea(entry_id, fields)
        if not entry:
            return json_error("FMEA entry not found", 404)
        return json_ok(entry.to_dict())

    elif method == "DELETE":
        if entry_id is None:
            return json_error("FMEA entry ID required")
        if store.delete_fmea(entry_id):
            return json_ok({"deleted": True})
        return json_error("FMEA entry not found", 404)

    return json_error("Method not allowed", 405)


# ── Helper ────────────────────────────────────────────────────────────────


def _get_query_param(query: dict, key: str, default: str = "") -> str:
    """Get a single query parameter value."""
    vals = query.get(key, [])
    return vals[0] if vals else default
