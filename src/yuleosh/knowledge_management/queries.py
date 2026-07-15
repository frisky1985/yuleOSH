#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Management — Query API.

Higher-level query functions that wrap KBStore for Pipeline and CI caller use.
Follows KG queries.py pattern.
"""

import logging
from typing import Optional

from yuleosh.knowledge_management.store import KBStore
from yuleosh.knowledge_management.models import (
    KnowledgeArticle,
    ARTICLE_STATUSES,
)

log = logging.getLogger("yuleosh.knowledge_management.queries")


def search(store: KBStore, query: str,
           status: Optional[str] = None,
           include_deleted: bool = False,
           offset: int = 0,
           limit: int = 50) -> dict:
    """Search articles by text query on title and content.

    Args:
        store: KBStore instance.
        query: Free-text search string.
        status: Optional status filter.
        include_deleted: Include soft-deleted articles.
        offset: Pagination offset.
        limit: Page size.

    Returns:
        Dict with "items", "total", "offset", "limit", "query".
    """
    articles, total = store.search(
        query=query,
        status=status,
        include_deleted=include_deleted,
        offset=offset,
        limit=limit,
    )
    return {
        "items": [a.to_dict() for a in articles],
        "total": total,
        "offset": offset,
        "limit": limit,
        "query": query,
    }


def list_articles(store: KBStore,
                  status: Optional[str] = None,
                  include_deleted: bool = False,
                  offset: int = 0,
                  limit: int = 50) -> dict:
    """List articles, optionally filtered by status.

    Returns dict with "items", "total", "offset", "limit".
    """
    articles, total = store.list(
        status=status,
        include_deleted=include_deleted,
        offset=offset,
        limit=limit,
    )
    return {
        "items": [a.to_dict() for a in articles],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def get_by_id(store: KBStore, article_id: str,
              include_deleted: bool = False) -> Optional[dict]:
    """Get a single article by UUID.

    Returns article dict, or None if not found.
    """
    article = store.get(article_id, include_deleted=include_deleted)
    return article.to_dict() if article else None


def get_by_status(store: KBStore, status: str,
                  offset: int = 0,
                  limit: int = 50) -> dict:
    """List articles by a specific status.

    Args:
        store: KBStore instance.
        status: One of ARTICLE_STATUSES.
        offset: Pagination offset.
        limit: Page size.

    Returns:
        Dict with "items", "total", "offset", "limit".
    """
    if status not in ARTICLE_STATUSES:
        return {"items": [], "total": 0, "offset": offset, "limit": limit,
                "error": f"Invalid status: {status}. Valid: {sorted(ARTICLE_STATUSES)}"}

    articles, total = store.list(status=status, offset=offset, limit=limit)
    return {
        "items": [a.to_dict() for a in articles],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def search_by_tags(store: KBStore, tags: list[str],
                   match_all: bool = False,
                   offset: int = 0,
                   limit: int = 50) -> dict:
    """Search articles by tags.

    Returns dict with "items", "total", "offset", "limit", "tags", "match_all".
    """
    articles, total = store.search_by_tags(
        tags=tags,
        match_all=match_all,
        offset=offset,
        limit=limit,
    )
    return {
        "items": [a.to_dict() for a in articles],
        "total": total,
        "offset": offset,
        "limit": limit,
        "tags": tags,
        "match_all": match_all,
    }


def list_deleted(store: KBStore, offset: int = 0,
                 limit: int = 50) -> dict:
    """List soft-deleted articles (admin only).

    Returns dict with "items", "total".
    """
    # Override the store's default exclude_deleted by passing include_deleted=True
    # and then manual-fetching only deleted ones via raw store access.
    articles, total = store.list(include_deleted=True, offset=offset, limit=limit)
    deleted = [a for a in articles if a.is_deleted]
    return {
        "items": [a.to_dict() for a in deleted],
        "total": len(deleted),
        "offset": offset,
        "limit": limit,
    }


def get_stats(store: KBStore) -> dict:
    """Return KB statistics.

    Wraps store.get_stats() for use by dashboard / CI.
    """
    return store.get_stats()


def list_versions(store: KBStore, article_id: str,
                  limit: int = 50) -> dict:
    """List version history for an article.

    Returns dict with "versions", "total".
    """
    versions, total = store.list_versions(article_id, limit=limit)
    return {
        "versions": versions,
        "total": total,
    }
