#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Ultra-Plan Agent — context analyzer.

Gathers project context for plan generation:
  - Project directory structure (modules, tests, key files)
  - Knowledge Graph summary (nodes, edges, per-layer coverage)
  - Existing requirements (from KG or spec files)
  - Pipeline capabilities (CheckpointEngine available step IDs)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("yuleosh.plan.context")


class PlanContext:
    """Project / KG / pipeline context used by PlanGenerator.

    Safe to construct even when the KG is not available — all
    get_* methods return sensible defaults on failure.
    """

    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir).resolve()
        self._kg_store = None  # lazily acquired

    # ── Project structure ───────────────────────────────────────────

    def get_project_summary(self) -> dict:
        """Return a dict describing the project directory structure.

        Returns:
            dict with keys::
                project_dir         — absolute project path
                module_dirs         — list of top-level module subdir names
                test_dir            — test directory path (or None)
                test_files          — count of test files found
                source_files        — count of Python source files in src/
                main_entry          — entry point path or None
        """
        summary: dict = {
            "project_dir": str(self.project_dir),
            "module_dirs": [],
            "test_dir": None,
            "test_files": 0,
            "source_files": 0,
            "main_entry": None,
        }

        # Discover src/ tree
        src_dir = self.project_dir / "src"
        if src_dir.is_dir():
            try:
                for entry in sorted(src_dir.iterdir()):
                    if entry.is_dir() and not entry.name.startswith("_"):
                        summary["module_dirs"].append(entry.name)
                summary["source_files"] = sum(
                    1 for f in src_dir.rglob("*.py") if f.is_file()
                )
            except OSError:
                log.warning("Could not list src/ directory", exc_info=True)

        # Discover tests/
        test_dir = self.project_dir / "tests"
        if test_dir.is_dir():
            summary["test_dir"] = str(test_dir)
            try:
                summary["test_files"] = sum(
                    1 for f in test_dir.rglob("test_*.py") if f.is_file()
                )
            except OSError:
                log.warning("Could not list tests/ directory", exc_info=True)

        # Main entry
        for candidate in ("yuleosh_cli.py", "setup.py", "pyproject.toml"):
            p = self.project_dir / candidate
            if p.is_file():
                summary["main_entry"] = str(p)
                break

        return summary

    # ── Knowledge Graph ──────────────────────────────────────────────

    def _lazy_kg(self):
        """Lazily initialise the KG store (accept failure gracefully)."""
        if self._kg_store is not None:
            return
        try:
            from yuleosh.knowledge_graph import get_store
            store = get_store()
            # Quick health-check
            store.setup()
            self._kg_store = store
        except Exception:
            log.debug("KG store not available", exc_info=True)
            self._kg_store = False  # sentinel

    def get_kg_summary(self) -> dict:
        """Return a summary of the current knowledge graph.

        Returns:
            dict with keys::
                available       — bool (KG loaded OK)
                node_count      — total nodes
                edge_count      — total edges
                entity_types    — per-type node counts
                edge_types      — per-type edge counts
                per_layer       — per ASPICE-layer edge counts
                uncovered_reqs  — count of requirements without coverage
                orphan_files    — count of code files without traces
        """
        result: dict = {
            "available": False,
            "node_count": 0,
            "edge_count": 0,
            "entity_types": {},
            "edge_types": {},
            "per_layer": {},
            "uncovered_reqs": 0,
            "orphan_files": 0,
        }
        self._lazy_kg()
        if not self._kg_store:
            return result

        try:
            from yuleosh.knowledge_graph import get_graph_stats
            stats = get_graph_stats(self._kg_store)
            result["available"] = True
            result["node_count"] = stats.get("node_count", 0)
            result["edge_count"] = stats.get("edge_count", 0)
            result["entity_types"] = stats.get("entities_by_type", {})
            result["edge_types"] = stats.get("edges_by_type", {})
            result["per_layer"] = stats.get("per_layer", {})

            from yuleosh.knowledge_graph import (
                list_uncovered_requirements,
                list_orphan_code_files,
            )
            uncovered = list_uncovered_requirements(self._kg_store)
            result["uncovered_reqs"] = len(uncovered)
            orphans = list_orphan_code_files(self._kg_store)
            result["orphan_files"] = len(orphans)

        except Exception:
            log.warning("Failed to query KG stats", exc_info=True)

        return result

    def get_aspice_coverage(self) -> dict:
        """Return per-ASPICE-layer coverage from the KG.

        Returns dict mapping layer name to dict with total/match/miss.
        Falls back to empty dict when KG is unavailable.
        """
        self._lazy_kg()
        if not self._kg_store:
            return {}

        try:
            from yuleosh.knowledge_graph import get_aspice_coverage
            return get_aspice_coverage(self._kg_store)
        except Exception:
            log.warning("get_aspice_coverage failed", exc_info=True)
            return {}

    # ── Requirements ─────────────────────────────────────────────────

    def get_existing_requirements(self) -> list[dict]:
        """Return existing requirements from KG or spec files.

        Returns list of dicts with at minimum "id", "title" keys,
        plus optional KG metadata.  Empty list on failure / no data.
        """
        reqs: list[dict] = []

        # Try KG first
        self._lazy_kg()
        if self._kg_store:
            try:
                from yuleosh.knowledge_graph.queries import (
                    list_uncovered_requirements,
                )
                # This returns requirement nodes from the KG
                from yuleosh.knowledge_graph.queries import (
                    get_graph_stats,
                )
                # Try reading nodes directly from store
                nodes = self._kg_store.list_nodes(
                    entity_type="requirement", limit=100
                )
                for n in nodes:
                    reqs.append({
                        "id": n.entity_id,
                        "title": n.label,
                        "properties": n.properties,
                    })
            except Exception:
                log.debug("Could not read requirements from KG", exc_info=True)

        # Fallback: scan spec files from project
        if not reqs:
            specs_dir = self.project_dir / "specs"
            if not specs_dir.is_dir():
                specs_dir = self.project_dir
            for spec_file in sorted(specs_dir.glob("*.md")):
                reqs.append({
                    "id": spec_file.stem,
                    "title": spec_file.name,
                    "source": str(spec_file),
                })

        return reqs

    # ── Pipeline capabilities ────────────────────────────────────────

    def get_pipeline_capabilities(self) -> list[dict]:
        """Return the list of available CheckpointEngine pipeline steps.

        Returns list of dicts with keys::
            step_id  — pipeline step identifier
            agent    — responsible agent
            name     — human-readable step name

        Empty list when the pipeline module is unavailable.
        """
        try:
            from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
            return [
                {"step_id": step[0], "agent": step[1], "name": step[2]}
                for step in PIPELINE_STEPS
            ]
        except (ImportError, AttributeError):
            log.debug("Pipeline module not available", exc_info=True)
            return []


# ── Convenience constructor ─────────────────────────────────────────────

def default_context(project_dir: str | None = None) -> PlanContext:
    """Build a PlanContext using the current project directory.

    Uses OSH_HOME env var or CWD when project_dir is None.
    """
    if project_dir is not None:
        return PlanContext(project_dir)
    base = os.environ.get("OSH_HOME", os.getcwd())
    return PlanContext(base)
