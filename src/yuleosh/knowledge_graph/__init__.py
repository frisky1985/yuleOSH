#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Traceability Knowledge Graph (TKG) — P0.

Auto-selects backend based on environment:
  - YULEOSH_DB_URL set → PostgreSQL (RECURSIVE CTE 图遍历) ⭐
  - Otherwise           → SQLite (Python BFS 遍历)

Dual backend design keeps local dev fast (SQLite) while production
gets full PostgreSQL graph traversal capability.

Usage:
    from yuleosh.knowledge_graph import get_store, import_data

    store = get_store()
    store.setup()

    # Import from existing traceability data
    import_data(store)

    # Query
    result = store.trace_by_req_id("RS-001-01")
"""

import logging
import os

log = logging.getLogger("yuleosh.knowledge_graph")

# ── Backend auto-selection ──────────────────────────────────────────────
_USE_POSTGRES = bool(os.environ.get("YULEOSH_DB_URL", "").strip())


def get_store(**kwargs):
    """Return a KGStore / KGStorePG instance based on YULEOSH_DB_URL.

    Args:
        **kwargs: Forwarded to the store constructor.

    Returns:
        KGStore (SQLite) or KGStorePG (PostgreSQL)
    """
    if _USE_POSTGRES:
        log.info("Knowledge Graph: PostgreSQL backend (RECURSIVE CTE)")
        from yuleosh.knowledge_graph.store_pg import KGStorePG
        return KGStorePG(**kwargs)
    else:
        log.info("Knowledge Graph: SQLite backend (Python BFS)")
        from yuleosh.knowledge_graph.store import KGStore
        return KGStore(**kwargs)


def import_data(store, project_dir=None, create_snapshot=True):
    """Bootstrap import from RTM + JSON + code scan.

    Convenience wrapper around importer.bootstrap().
    """
    from yuleosh.knowledge_graph.importer import bootstrap
    return bootstrap(store, project_dir=project_dir,
                     create_snapshot=create_snapshot)


# ── Re-export common API ────────────────────────────────────────────────
# These work identically on both backends.

from yuleosh.knowledge_graph.queries import (
    trace_by_req_id,
    trace_by_file_path,
    trace_by_test_function,
    impact_analysis,
    list_uncovered_requirements,
    list_orphan_code_files,
    list_snapshots,
    get_graph_stats,
    get_confirmation_trace,
)

# Also export case-insensitive alias for the new queries submodule
from yuleosh.knowledge_graph.queries_pg import (
    trace_by_req_id as _trace_by_req_id_pg,
    trace_by_file_path as _trace_by_file_path_pg,
    trace_by_test_function as _trace_by_test_function_pg,
    impact_analysis as _impact_analysis_pg,
    list_uncovered_requirements as _list_uncovered_pg,
    list_orphan_code_files as _list_orphan_pg,
    get_confirmation_trace as _get_confirmation_trace_pg,
)

from yuleosh.knowledge_graph.git_hook_check import (
    check_installed as git_hook_installed,
    is_version_current as git_hook_version_current,
    install_hook as git_hook_install,
    uninstall_hook as git_hook_uninstall,
    get_status as git_hook_status,
)

from yuleosh.knowledge_graph.ci_hook import kg_ci_append

# P1-1: Code scanner & coverage importer
from yuleosh.knowledge_graph.code_scanner import scan_directory, scan_single_file
from yuleosh.knowledge_graph.coverage_importer import (
    import_coverage,
    import_coverage_from_default,
)

# Incremental build
from yuleosh.knowledge_graph.importer import incremental_bootstrap

__all__ = [
    # Factory
    "get_store", "import_data",
    # SQLite + PG queries
    "trace_by_req_id", "trace_by_file_path", "trace_by_test_function",
    "impact_analysis", "list_uncovered_requirements", "list_orphan_code_files",
    "list_snapshots", "get_graph_stats", "get_confirmation_trace",
    # CI hook
    "kg_ci_append",
    # Git hook management
    "git_hook_installed", "git_hook_version_current",
    "git_hook_install", "git_hook_uninstall", "git_hook_status",
    # P1-1: Code scanner & coverage
    "scan_directory",
    "scan_single_file",
    "import_coverage",
    "import_coverage_from_default",
    # Incremental build
    "incremental_bootstrap",
    # Backend status
    "_USE_POSTGRES",
]
