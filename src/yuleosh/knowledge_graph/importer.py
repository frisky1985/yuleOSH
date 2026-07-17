#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Importer — entry point for bootstrap & incremental builds.

Re-exports all public APIs from the split sub-modules:
  - bootstrap.py    — full initialization (RTM, JSON, code scan, snapshot)
  - incremental.py  — incremental update for CI pipelines
  - edge_builder.py — edge construction, merge, layer annotation
  - checkpoint.py   — checkpoint save/restore for incremental builds

Usage:
    from yuleosh.knowledge_graph.importer import bootstrap, incremental_bootstrap
"""

import logging

log = logging.getLogger("yuleosh.knowledge_graph.importer")

# ═══════════════════════════════════════════════════════════════════════
# Re-export from bootstrap.py
# ═══════════════════════════════════════════════════════════════════════

from yuleosh.knowledge_graph.bootstrap import (
    _parse_rtm_table,
    _parse_shall_id,
    import_from_req_test_json,
    import_from_rtm_md,
    scan_code_directory,
    bootstrap,
)

# ═══════════════════════════════════════════════════════════════════════
# Re-export from incremental.py
# ═══════════════════════════════════════════════════════════════════════

from yuleosh.knowledge_graph.incremental import (
    incremental_bootstrap,
)

# ═══════════════════════════════════════════════════════════════════════
# Re-export from edge_builder.py
# ═══════════════════════════════════════════════════════════════════════

from yuleosh.knowledge_graph.edge_builder import (
    _LAYER_PATTERNS,
    _infer_layer_from_filename,
    _annotate_covers_layer,
    _merge_test_functions,
    _build_implements_edges,
    _build_validates_edges,
    _fallback_code_file_matching,
    _match_code_files_to_requirements,
    _fix_orphan_test_files,
)

# ═══════════════════════════════════════════════════════════════════════
# Re-export from checkpoint.py
# ═══════════════════════════════════════════════════════════════════════

from yuleosh.knowledge_graph.checkpoint import (
    _save_checkpoint,
    _restore_checkpoint,
    _delete_changed_file_nodes,
)

# ═══════════════════════════════════════════════════════════════════════
# Re-export from code_scanner (used by tests via imp_mod)
# ═══════════════════════════════════════════════════════════════════════

from yuleosh.knowledge_graph.code_scanner import (
    scan_single_file,
    scan_directory,
)

# ═══════════════════════════════════════════════════════════════════════
# Define __all__ for explicit re-export
# ═══════════════════════════════════════════════════════════════════════

__all__ = [
    # bootstrap.py
    "_parse_rtm_table",
    "_parse_shall_id",
    "import_from_req_test_json",
    "import_from_rtm_md",
    "scan_code_directory",
    "bootstrap",
    # incremental.py
    "incremental_bootstrap",
    # edge_builder.py
    "_LAYER_PATTERNS",
    "_infer_layer_from_filename",
    "_annotate_covers_layer",
    "_merge_test_functions",
    "_build_implements_edges",
    "_build_validates_edges",
    "_fallback_code_file_matching",
    "_match_code_files_to_requirements",
    "_fix_orphan_test_files",
    # checkpoint.py
    "_save_checkpoint",
    "_restore_checkpoint",
    "_delete_changed_file_nodes",
    # code_scanner
    "scan_single_file",
    "scan_directory",
]
