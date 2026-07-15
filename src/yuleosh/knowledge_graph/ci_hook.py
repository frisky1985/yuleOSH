#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph CI Hook — integrates with the yuleOSH CI pipeline.

Called at the end of a CI build (report stage) to:
  1. Record a graph snapshot with the build_id
  2. Append changed file paths to the graph as 'affects' edges
  3. Report basic traceability statistics

Usage (in ci/run.py or pipeline):
    from yuleosh.knowledge_graph.ci_hook import kg_ci_append
    kg_ci_append(build_id="ci-20260714-001", changed_files=[...])
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.queries import get_graph_stats, impact_analysis

log = logging.getLogger("yuleosh.knowledge_graph.ci_hook")


def kg_ci_append(store: KGStore, build_id: str,
                 changed_files: Optional[list[str]] = None,
                 meta: Optional[dict] = None) -> dict:
    """CI append hook: record snapshot + optionally link changed files.

    This is the P0 CI hook. It:
      1. Creates a graph snapshot tagged with build_id
      2. If changed_files provided, records 'affects' edges for each
         file that exists in the graph
      3. If graph is empty, runs a quick bootstrap from default paths
      4. Returns a summary for CI logging

    Args:
        store: KGStore instance
        build_id: Unique build identifier (e.g., "ci-20260714-003")
        changed_files: Optional list of file paths changed in this build
        meta: Optional dict with additional metadata

    Returns:
        dict with summary for CI logging
    """
    meta = meta or {}

    # Determine project directory
    project_dir = (
        meta.get("project_dir")
        or os.environ.get("OSH_HOME")
        or str(Path.cwd())
    )

    from yuleosh.knowledge_graph.importer import incremental_bootstrap

    if not os.path.isdir(project_dir):
        # Fallback: try auto-detecting project root
        project_dir = str(_get_project_root())

    # ── If changed_files with real files on disk, use incremental_bootstrap ──
    if changed_files is not None and changed_files:
        files_on_disk = [
            f for f in changed_files
            if (Path(project_dir) / f).is_file()
        ]
        if files_on_disk:
            log.info(
                "KG CI hook (incremental): %d file(s) on disk, routing to incremental_bootstrap",
                len(files_on_disk),
            )
            incremental_result = incremental_bootstrap(
                store,
                project_dir=project_dir,
                changed_files=files_on_disk,
                create_snapshot=True,
                build_id=build_id,
                snapshot_meta=meta,
            )

            stats = store.get_stats()
            result = {
                "build_id": build_id,
                "mode": "incremental",
                "node_count": stats["total_nodes"],
                "edge_count": stats["total_edges"],
                "nodes_by_type": stats["nodes_by_type"],
                "edges_by_type": stats["edges_by_type"],
                "files_analyzed": len(changed_files),
                "incremental_detail": incremental_result,
            }

            # Backward-compatible snapshot_id if created
            snap = incremental_result.get("snapshot", {})
            if snap.get("build_id"):
                result["snapshot_id"] = store.get_snapshot(build_id).id

            # Also run impact analysis for logging
            impact = impact_analysis(store, changed_files)
            result["impact"] = impact

            log.info(
                "KG CI hook complete (incremental): build=%s nodes=%d edges=%d files=%d",
                build_id, stats["total_nodes"], stats["total_edges"], len(changed_files),
            )
            return result

        log.info(
            "KG CI hook: changed_files given but none found on disk in %s. "
            "Falling through to full path.",
            project_dir,
        )
        # Fall through to full path
        changed_files = None  # Don't re-enter incremental on the fallthrough

    # ── Full bootstrap path (no changed_files) ──
    # Check if graph has data; if not, auto-bootstrap
    stats = get_graph_stats(store)
    if stats["total_nodes"] == 0:
        log.info("KG is empty; running auto-bootstrap before CI append")
        from yuleosh.knowledge_graph.importer import bootstrap

        # Also use resolved project_dir
        bootstrap(store, project_dir, create_snapshot=False)

        stats = get_graph_stats(store)

    # Create snapshot
    snapshot = store.create_snapshot(
        build_id=build_id,
        meta={
            "node_count": stats["total_nodes"],
            "edge_count": stats["total_edges"],
            "source": meta.get("source", "ci_hook_full"),
            **(meta or {}),
        },
    )

    result = {
        "build_id": build_id,
        "snapshot_id": snapshot.id,
        "node_count": stats["total_nodes"],
        "edge_count": stats["total_edges"],
        "nodes_by_type": stats["nodes_by_type"],
        "edges_by_type": stats["edges_by_type"],
        "files_analyzed": 0,
    }

    log.info("KG CI hook complete (full): build=%s nodes=%d edges=%d",
             build_id, stats["total_nodes"], stats["total_edges"])
    return result


def _get_project_root() -> Optional[Path]:
    """Auto-detect project root from git root or OSH_HOME."""
    osh_home = os.environ.get("OSH_HOME")
    if osh_home:
        return Path(osh_home).resolve()
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return Path.cwd().resolve()


def _parse_changed_files(raw: str) -> list[str]:
    """Parse comma-separated changed files into a list, stripping whitespace."""
    if not raw:
        return []
    return [f.strip() for f in raw.split(",") if f.strip()]


def _filter_project_files(files: list[str]) -> list[str]:
    """Keep only files inside src/yuleosh/ or tests/ with .py extension."""
    result = []
    for f in files:
        if f.startswith("src/yuleosh/") and f.endswith(".py"):
            result.append(f)
        elif f.startswith("tests/") and f.endswith(".py"):
            result.append(f)
    return result


def main() -> int:
    """CLI entry point for kg CI hook.

    Usage:
        python -m yuleosh.knowledge_graph.ci_hook --build-id ci-001 --changed-files a.py,b.py
        python -m yuleosh.knowledge_graph.ci_hook --auto  # auto-detect from git HEAD
    """
    parser = argparse.ArgumentParser(
        description="yuleOSH 知识图谱 CI Hook — 记录构建快照并关联变更文件",
    )
    parser.add_argument(
        "--build-id", type=str, default=None,
        help="构建标识符（如 ci-20260714-001）",
    )
    parser.add_argument(
        "--changed-files", type=str, default=None,
        help="逗号分隔的变更文件列表",
    )
    parser.add_argument(
        "--auto", action="store_true",
        help="自动检测：从 git HEAD 获取变更文件，生成 build-id",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="详细日志输出",
    )
    parser.add_argument(
        "--store-dir", type=str, default=None,
        help="知识图谱存储路径（默认自动检测）",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Determine project root
    project_root = _get_project_root()
    log.info("Project root: %s", project_root)

    if not (project_root / ".git").is_dir():
        log.warning("⚠️  项目目录 %s 不是 Git 仓库，部分功能受限", project_root)

    # Determine build_id
    build_id = args.build_id
    if args.auto and not build_id:
        now = datetime.now()
        build_id = f"kg-local-{now.strftime('%Y%m%d-%H%M%S')}"
        log.info("Auto-generated build_id: %s", build_id)
    if not build_id:
        build_id = f"kg-local-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Determine changed files
    changed_files: list[str] = []
    if args.changed_files:
        changed_files = _filter_project_files(_parse_changed_files(args.changed_files))
        log.info("Changed files (filtered): %d files", len(changed_files))

    if args.auto and not changed_files:
        from yuleosh.knowledge_graph.git_hook_check import get_changed_files_from_commit
        raw_files = get_changed_files_from_commit()
        changed_files = _filter_project_files(raw_files)
        log.info("Auto-detected changed files: %d files", len(changed_files))

    if not changed_files:
        log.info("No relevant changed files to process")

    # Initialize store (constructor handles migration)
    try:
        from yuleosh.knowledge_graph import get_store
        kwargs = {}
        if args.store_dir:
            kwargs["db_path"] = args.store_dir
        store = get_store(**kwargs)
    except Exception as exc:
        log.error("Failed to initialize Knowledge Graph store: %s", exc)
        return 1

    # Run CI append
    try:
        result = kg_ci_append(
            store,
            build_id=build_id,
            changed_files=changed_files if changed_files else None,
            meta={
                "project_root": str(project_root),
                "auto_mode": args.auto,
            },
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        log.info("✅ KG CI hook completed successfully")
        return 0
    except Exception as exc:
        log.error("❌ KG CI hook failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
