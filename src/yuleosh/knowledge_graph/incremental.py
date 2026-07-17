#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Incremental Build — for CI pipelines.

Supports three modes:
  - changed_files=None   → full bootstrap() (backward-compatible)
  - changed_files=[]     → snapshot only; no re-import
  - changed_files=[...]  → incremental: remove old, re-scan, rebuild
"""

import gc
import logging
from pathlib import Path
from typing import Optional

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.bootstrap import bootstrap
from yuleosh.knowledge_graph.coverage_importer import import_coverage_from_default
from yuleosh.knowledge_graph.edge_builder import (
    _merge_test_functions,
    _annotate_covers_layer,
    _build_implements_edges,
    _build_validates_edges,
    _fallback_code_file_matching,
    _fix_orphan_test_files,
)
from yuleosh.knowledge_graph.checkpoint import (
    _save_checkpoint,
    _restore_checkpoint,
    _delete_changed_file_nodes,
)

log = logging.getLogger("yuleosh.knowledge_graph.incremental")


def incremental_bootstrap(
    store: KGStore,
    project_dir: str,
    changed_files: Optional[list[str]] = None,
    create_snapshot: bool = True,
    build_id: Optional[str] = None,
    snapshot_meta: Optional[dict] = None,
) -> dict:
    """Incremental knowledge graph build from changed files.

    Behaviour by *changed_files*:
      - ``None`` → full ``bootstrap()`` (backward-compatible)
      - ``[]``   → update snapshot only; no re-import
      - list of paths → incremental: remove old nodes, re-scan, rebuild

    Steps for incremental:
      1. Save checkpoint (backup affected nodes + edges)
      2. Delete old nodes + edges for changed files
      3. Re-scan each changed file (AST-based)
      4. Re-run coverage import
      5. Re-implement merge, layer annotation
      6. Rebuild implements / validates / fallback / orphan edges (idempotent)
      7. Create new snapshot

    Args:
        store: KGStore instance
        project_dir: Project root directory
        changed_files: List of relative file paths, ``None`` for full, ``[]`` for snapshot-only
        create_snapshot: Whether to create a snapshot at the end
        build_id: Optional build identifier for the snapshot
        snapshot_meta: Optional extra metadata for the snapshot

    Returns:
        Rich summary dict with per-step counts

    Raises:
        RuntimeError: On incremental failure, after restoring the checkpoint
    """
    project_path = Path(project_dir)

    # changed_files=None → full bootstrap
    if changed_files is None:
        log.info("incremental_bootstrap: changed_files=None → full bootstrap")
        return bootstrap(store, project_dir, create_snapshot=create_snapshot)

    # changed_files=[] → snapshot only
    if not changed_files:
        log.info("incremental_bootstrap: changed_files=[] → snapshot only")
        stats = store.get_stats()
        if create_snapshot:
            bid = build_id or "incremental-snapshot-only"
            snap_meta = {"source": "incremental_snapshot_only", "project_dir": project_dir}
            if snapshot_meta:
                snap_meta.update(snapshot_meta)
            store.create_snapshot(build_id=bid, meta=snap_meta)
        return {
            "mode": "snapshot_only",
            "stats": stats,
            "incremental": {"code_files": 0, "test_files": 0, "edges_added": 0},
        }

    # Incremental build
    log.info("Incremental bootstrap starting for %d files: %s",
             len(changed_files), changed_files)

    # Step 0: Save checkpoint for rollback safety
    checkpoint = _save_checkpoint(store, changed_files)

    try:
        # Step 1: Delete old nodes and edges for changed files
        delete_result = _delete_changed_file_nodes(store, changed_files)

        # Step 2: Re-scan each changed file
        scanned_code = 0
        scanned_test = 0
        total_funcs = 0
        total_classes = 0
        total_methods = 0
        total_edges_added = 0

        # Use importer module reference for monkey-patch compatibility in tests
        import yuleosh.knowledge_graph.importer as _imp
        _scan_single_file = _imp.scan_single_file

        for cf in changed_files:
            norm = cf.replace("\\", "/")
            if norm.startswith("src/") and norm.endswith(".py"):
                result = _scan_single_file(store, project_dir, norm)
                scanned_code += 1
                total_funcs += result.get("functions", 0)
                total_classes += result.get("classes", 0)
                total_methods += result.get("methods", 0)
                total_edges_added += result.get("edges", 0)
            elif norm.startswith("tests/") and norm.endswith(".py"):
                result = _scan_single_file(store, project_dir, norm)
                scanned_test += 1
                total_funcs += result.get("functions", 0)
                total_classes += result.get("classes", 0)
                total_methods += result.get("methods", 0)
                total_edges_added += result.get("edges", 0)
            else:
                log.debug("Skipping non-scannable file: %s", norm)

        incremental_result = {
            "code_files": scanned_code,
            "test_files": scanned_test,
            "functions": total_funcs,
            "classes": total_classes,
            "methods": total_methods,
            "edges_added": total_edges_added,
            "changed_files": len(changed_files),
        }

        result = {
            "mode": "incremental",
            "incremental": incremental_result,
            "deleted": delete_result,
        }

        # Step 3: Re-run coverage import (idempotent)
        coverage_result = import_coverage_from_default(store, project_dir)
        result["coverage"] = coverage_result

        # Step 4: Merge duplicate test_function nodes
        merge_result = _merge_test_functions(store)
        result["merge"] = merge_result

        # Step 5: Annotate covers edges with test layer
        layer_result = _annotate_covers_layer(store)
        result["layer_annotation"] = layer_result

        # Step 6: Rebuild implements edges
        impl_result = _build_implements_edges(store)
        result["implements"] = impl_result

        # Step 7: Rebuild validates edges
        valid_result = _build_validates_edges(store)
        result["validates"] = valid_result

        # Step 8: Fallback code file matching
        fallback_result = _fallback_code_file_matching(store, project_path)
        result["fallback_matching"] = fallback_result

        # Step 9: Orphan test file auto-covers
        orphan_tf_result = _fix_orphan_test_files(store)
        result["orphan_test_files"] = orphan_tf_result

        # Step 10: Snapshot
        if create_snapshot:
            bid = build_id or "incremental"
            snap_meta = {"source": "incremental_bootstrap", "changed_files": changed_files}
            if snapshot_meta:
                snap_meta.update(snapshot_meta)
            snapshot = store.create_snapshot(build_id=bid, meta=snap_meta)
            result["snapshot"] = {
                "build_id": snapshot.build_id,
                "node_count": snapshot.node_count,
                "edge_count": snapshot.edge_count,
            }

        stats = store.get_stats()
        result["stats"] = stats
        result["summary"] = {
            "total_nodes": stats["total_nodes"],
            "total_edges": stats["total_edges"],
        }

        log.info(
            "Incremental bootstrap complete: %d changed files, "
            "scan: %d src/%d tests, deleted: %d nodes/%d edges",
            len(changed_files),
            scanned_code, scanned_test,
            delete_result.get("deleted_nodes", 0),
            delete_result.get("deleted_edges", 0),
        )
        return result

    except Exception as exc:
        log.error(
            "Incremental bootstrap FAILED: %s. Restoring checkpoint.",
            exc,
            exc_info=True,
        )
        try:
            _restore_checkpoint(store, checkpoint)
        except Exception as restore_exc:
            log.error(
                "Checkpoint restore also FAILED: %s. Graph may be inconsistent.",
                restore_exc,
                exc_info=True,
            )
            raise RuntimeError(
                f"Incremental bootstrap failed and checkpoint restore also failed: "
                f"{exc} / {restore_exc}"
            ) from exc
        raise RuntimeError(
            f"Incremental bootstrap failed; checkpoint restored: {exc}"
        ) from exc
