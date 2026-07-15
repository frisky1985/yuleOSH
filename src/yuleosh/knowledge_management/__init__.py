#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Knowledge Management (KB) — P0.

Core KB module providing article CRUD, soft delete, status machine,
version management, and search/list query API.

Usage:
    from yuleosh.knowledge_management import get_store
    from yuleosh.knowledge_management.models import KnowledgeArticle

    store = get_store()

    # Create
    article = KnowledgeArticle(title="Brake Calibration Guide",
                                content="# Brake Calibration\\n...",
                                safety_level="ASIL_D",
                                created_by="alice")
    article = store.create(article)

    # Query
    from yuleosh.knowledge_management.queries import search
    result = search(store, "brake calibration")
"""

import logging

log = logging.getLogger("yuleosh.knowledge_management")


def get_store(**kwargs):
    """Return a KBStore instance.

    Uses YULEOSH_KB_DB env var or defaults to .yuleosh/knowledge_management.db
    under OSH_HOME (or CWD if unset).

    Returns:
        KBStore (SQLite)
    """
    from yuleosh.knowledge_management.store import KBStore
    return KBStore(**kwargs)


# Re-export common API
from yuleosh.knowledge_management.queries import (
    search,
    list_articles,
    get_by_id,
    get_by_status,
    search_by_tags,
    list_deleted,
    get_stats,
    list_versions,
)

from yuleosh.knowledge_management.models import (
    KnowledgeArticle,
    ARTICLE_STATUSES,
    SAFETY_LEVELS,
    VALID_TRANSITIONS,
)

__all__ = [
    "get_store",
    "search",
    "list_articles",
    "get_by_id",
    "get_by_status",
    "search_by_tags",
    "list_deleted",
    "get_stats",
    "list_versions",
    "KnowledgeArticle",
    "ARTICLE_STATUSES",
    "SAFETY_LEVELS",
    "VALID_TRANSITIONS",
]
