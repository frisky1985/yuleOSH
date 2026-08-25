#!/usr/bin/env python3

# @req RS-015  @req KG-042
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Knowledge Graph Merge Gate (KG-42) — PR 合入前自动 KG 验证

Implements the merge gate process:
  1. Incremental build trigger — detect changed files, rebuild delta KG
  2. Graph consistency verification — validate node/edge integrity
  3. Confidence check — ensure traceability confidence meets threshold
  4. Block low-quality merges — return pass/fail with detailed report

CLI entry: ``yuleosh kg check-merge``
Pipeline step: ``merge-gate`` (registered in PIPELINE_STEPS)

Usage:
    from yuleosh.knowledge_graph.merge_gate import MergeGate, MergeGateConfig

    gate = MergeGate(store, project_dir="/path/to/project")
    result = gate.run()
    print(result["verdict"])  # "pass" | "fail"
"""

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("yuleosh.knowledge_graph.merge_gate")


# ═══════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class MergeGateConfig:
    """Configuration for the KG merge gate.

    Attributes:
        min_confidence: Minimum traceability confidence threshold (0.0–1.0).
            Merges with confidence below this threshold are blocked.
        min_coverage: Minimum requirement coverage threshold (0.0–1.0).
        max_orphan_nodes: Maximum allowed orphan nodes (nodes without edges).
        max_orphan_edges: Maximum allowed orphan edges (edges with missing target/source).
        check_cycles: Whether to check for cycles in the graph.
        check_consistency: Whether to perform full graph consistency check.
        auto_build: Whether to trigger incremental build before check.
        base_ref: Git base ref for detecting changed files.
        fail_on_warning: Whether to fail on warnings (not just errors).
        output_path: Path to write the merge gate report.
        exclude_patterns: File patterns to exclude from change detection.
    """
    min_confidence: float = 0.7
    min_coverage: float = 0.8
    max_orphan_nodes: int = 5
    max_orphan_edges: int = 3
    check_cycles: bool = True
    check_consistency: bool = True
    auto_build: bool = True
    base_ref: str = "HEAD~1"
    fail_on_warning: bool = False
    output_path: Optional[str] = None
    exclude_patterns: list[str] = field(default_factory=lambda: [
        "*.pyc", "__pycache__/*", ".git/*", "node_modules/*",
        ".yuleosh/*", ".osh/*", "*.egg-info/*", ".coverage/*",
    ])

    @classmethod
    def from_dict(cls, d: dict) -> "MergeGateConfig":
        """Create config from dict (e.g. from YAML config)."""
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)


# ═══════════════════════════════════════════════════════════════════════
# Graph Consistency Checks
# ═══════════════════════════════════════════════════════════════════════


def _node_matches_scope(node: dict, scope_files: list[str]) -> bool:
    """True if a node's entity_id ties it to one of the scope files.

    Path-like ids (contain ``/`` or end with a source extension) match by
    substring so a changed file picks up its file node and any requirement
    that names it; bare requirement ids match only via exact equality.
    See ``GraphConsistencyChecker._scoped_nodes`` for the rationale.
    """
    nid = node.get("entity_id", "") or ""
    if not nid:
        return False
    looks_like_path = "/" in nid or nid.lower().endswith(
        (".c", ".h", ".cpp", ".hpp", ".py", ".md", ".json", ".yaml", ".yml")
    )
    for f in scope_files:
        if not f:
            continue
        if nid == f:
            return True
        if looks_like_path and (nid.endswith("/" + f) or f in nid):
            return True
    return False


def _filter_nodes_by_scope(nodes: list[dict], scope_files: list[str] | None) -> list[dict]:
    """Narrow nodes to the session-artifact subgraph.

    ``None``/empty scope = full graph (compat with legacy callers/tests).
    """
    if not scope_files:
        return nodes
    return [n for n in nodes if _node_matches_scope(n, scope_files)]


def _filter_edges_by_scope(edges: list[dict], scoped_ids: set) -> list[dict]:
    """Keep edges touching any of the scoped node ids."""
    if not scoped_ids:
        return []
    return [
        e for e in edges
        if e.get("source_id") in scoped_ids or e.get("target_id") in scoped_ids
    ]


class GraphConsistencyChecker:
    """Performs graph consistency verification on the knowledge graph.

    Checks:
    - Node type validation (each node has a recognized entity_type)
    - Edge type validation (each edge has a recognized relation_type)
    - Orphan nodes (nodes with zero edges)
    - Orphan edges (edges referencing non-existent source/target)
    - Cycle detection (using DFS on directed edges)
    - Duplicate node detection (same entity_id, different attributes)
    """

    VALID_NODE_TYPES = {
        "requirement", "function", "test", "file", "module",
        "scenario", "component", "interface", "safety_goal",
        "hazard", "risk", "feature", "release",
    }

    VALID_EDGE_TYPES = {
        "covers", "verifies", "implements", "depends_on",
        "refines", "traces_to", "satisfies", "allocated_to",
        "derived_from", "conflicts_with", "related_to",
    }

    def __init__(self, store, config: MergeGateConfig,
                 scope_files: list[str] | None = None):
        self.store = store
        self.config = config
        # 2026-08-08 (P1-3): 收窄到 session 产物。传 changed_files 时，
        # 结构检查只看这些文件相关的节点/边子图，避免全图噪声（stash、
        # 历史手工改动）导致 gate 误判。None = 全图（兼容旧调用与测试）。
        self.scope_files: list[str] | None = scope_files

    def _scoped_nodes(self) -> list[dict]:
        """Return nodes, optionally filtered to scope_files.

        Node entity_id for code/test files is the cleaned relative path
        (e.g. ``src/main.c``); requirements use their req id.  Matching is
        substring on the relative path so a changed file picks up its
        file node and any requirement that names it.  To avoid a broad
        path substring matching a requirement id by accident (e.g. changed
        file ``REQ`` vs req ``REQ-001``), only treat entity_ids that look
        like paths (contain ``/`` or end with a source extension) as
        file nodes; requirement ids are matched only via exact equality
        or when the changed file literally appears in the id.
        """
        return _filter_nodes_by_scope(self.store.get_all_nodes(), self.scope_files)

    def _scoped_edges(self) -> list[dict]:
        """Return edges, optionally filtered to scope_files' node ids.

        Edges touching a scoped node are kept so orphan/cycle checks see
        the same subgraph the node checks do.
        """
        edges = self.store.get_all_edges()
        if not self.scope_files:
            return edges
        scoped_ids = {n.get("entity_id") for n in self._scoped_nodes() if n.get("entity_id")}
        return _filter_edges_by_scope(edges, scoped_ids)

    def check_all(self) -> dict:
        """Run all consistency checks and return results."""
        errors: list[dict] = []
        warnings: list[dict] = []

        # 1. Node type validation
        node_type_errors = self._check_node_types()
        errors.extend(node_type_errors)

        # 2. Edge type validation
        edge_type_errors = self._check_edge_types()
        errors.extend(edge_type_errors)

        # 3. Orphan nodes
        orphan_nodes = self._find_orphan_nodes()
        if len(orphan_nodes) > self.config.max_orphan_nodes:
            errors.append({
                "check": "orphan_nodes",
                "severity": "error",
                "message": f"Too many orphan nodes: {len(orphan_nodes)} (max {self.config.max_orphan_nodes})",
                "details": orphan_nodes[:20],
            })
        elif orphan_nodes:
            warnings.append({
                "check": "orphan_nodes",
                "severity": "warning",
                "message": f"{len(orphan_nodes)} orphan node(s) found",
                "details": orphan_nodes[:10],
            })

        # 4. Orphan edges
        if self.config.check_consistency:
            orphan_edges = self._find_orphan_edges()
            if len(orphan_edges) > self.config.max_orphan_edges:
                errors.append({
                    "check": "orphan_edges",
                    "severity": "error",
                    "message": f"Too many orphan edges: {len(orphan_edges)} (max {self.config.max_orphan_edges})",
                    "details": orphan_edges[:20],
                })
            elif orphan_edges:
                warnings.append({
                    "check": "orphan_edges",
                    "severity": "warning",
                    "message": f"{len(orphan_edges)} orphan edge(s) found",
                    "details": orphan_edges[:10],
                })

        # 5. Cycle detection
        if self.config.check_cycles:
            cycles = self._detect_cycles()
            if cycles:
                errors.append({
                    "check": "cycles",
                    "severity": "error",
                    "message": f"Graph contains {len(cycles)} cycle(s)",
                    "details": cycles[:10],
                })

        # 6. Duplicate nodes
        dupes = self._find_duplicate_nodes()
        if dupes:
            warnings.append({
                "check": "duplicate_nodes",
                "severity": "warning",
                "message": f"Found {len(dupes)} potential duplicate node(s)",
                "details": dupes[:10],
            })

        passed = len(errors) == 0
        if self.config.fail_on_warning:
            passed = passed and len(warnings) == 0

        return {
            "passed": passed,
            "errors": errors,
            "warnings": warnings,
            "error_count": len(errors),
            "warning_count": len(warnings),
        }

    def _check_node_types(self) -> list[dict]:
        """Check all nodes have recognized entity types."""
        errors = []
        try:
            nodes = self._scoped_nodes()
            for node in nodes:
                etype = node.get("entity_type", "")
                if etype and etype not in self.VALID_NODE_TYPES:
                    errors.append({
                        "check": "node_type",
                        "severity": "error",
                        "message": f"Unrecognized node type '{etype}' for node {node.get('entity_id', '?')}",
                        "node_id": node.get("entity_id"),
                    })
        except Exception as e:
            errors.append({
                "check": "node_types_read",
                "severity": "error",
                "message": f"Failed to read nodes: {e}",
            })
        return errors

    def _check_edge_types(self) -> list[dict]:
        """Check all edges have recognized relation types."""
        errors = []
        try:
            edges = self._scoped_edges()
            for edge in edges:
                rtype = edge.get("relation_type", "")
                if rtype and rtype not in self.VALID_EDGE_TYPES:
                    errors.append({
                        "check": "edge_type",
                        "severity": "error",
                        "message": f"Unrecognized edge type '{rtype}'",
                        "edge_id": edge.get("id"),
                    })
        except Exception as e:
            errors.append({
                "check": "edge_types_read",
                "severity": "error",
                "message": f"Failed to read edges: {e}",
            })
        return errors

    def _find_orphan_nodes(self) -> list[dict]:
        """Find nodes with no edges (no incoming or outgoing connections)."""
        orphans = []
        try:
            nodes = self._scoped_nodes()
            edges = self._scoped_edges()

            connected_ids = set()
            for edge in edges:
                connected_ids.add(edge.get("source_id"))
                connected_ids.add(edge.get("target_id"))

            for node in nodes:
                nid = node.get("entity_id")
                if nid and nid not in connected_ids:
                    orphans.append({
                        "entity_id": nid,
                        "entity_type": node.get("entity_type", "?"),
                        "name": node.get("name", ""),
                    })
        except Exception as e:
            log.warning("Orphan node check failed: %s", e)
        return orphans

    def _find_orphan_edges(self) -> list[dict]:
        """Find edges whose source or target node doesn't exist."""
        orphan_edges = []
        try:
            nodes = self._scoped_nodes()
            node_ids = {n.get("entity_id") for n in nodes}
            edges = self._scoped_edges()

            for edge in edges:
                src = edge.get("source_id")
                tgt = edge.get("target_id")
                if src and src not in node_ids:
                    orphan_edges.append({
                        "edge_id": edge.get("id"),
                        "source_id": src,
                        "target_id": tgt,
                        "problem": "missing_source",
                    })
                elif tgt and tgt not in node_ids:
                    orphan_edges.append({
                        "edge_id": edge.get("id"),
                        "source_id": src,
                        "target_id": tgt,
                        "problem": "missing_target",
                    })
        except Exception as e:
            log.warning("Orphan edge check failed: %s", e)
        return orphan_edges

    def _detect_cycles(self) -> list[list[str]]:
        """Detect directed cycles in the graph using DFS."""
        cycles = []
        try:
            edges = self._scoped_edges()
            adj: dict[str, list[str]] = {}
            for edge in edges:
                src = edge.get("source_id")
                tgt = edge.get("target_id")
                if src and tgt:
                    adj.setdefault(src, []).append(tgt)

            visited: set[str] = set()
            rec_stack: set[str] = set()

            def dfs(node: str, path: list[str]):
                visited.add(node)
                rec_stack.add(node)
                for neighbor in adj.get(node, []):
                    if neighbor not in visited:
                        if dfs(neighbor, path + [neighbor]):
                            return True
                    elif neighbor in rec_stack:
                        cycle_path = path[path.index(neighbor):] + [neighbor]
                        cycles.append(cycle_path)
                        return True
                rec_stack.discard(node)
                return False

            for node in list(adj.keys()):
                if node not in visited:
                    dfs(node, [node])
        except Exception as e:
            log.warning("Cycle detection failed: %s", e)

        return cycles

    def _find_duplicate_nodes(self) -> list[dict]:
        """Find nodes with the same entity_id but different attributes."""
        dupes = []
        try:
            nodes = self._scoped_nodes()
            seen: dict[str, list[dict]] = {}
            for node in nodes:
                eid = node.get("entity_id")
                if eid:
                    seen.setdefault(eid, []).append(node)

            for eid, entries in seen.items():
                if len(entries) > 1:
                    dupes.append({
                        "entity_id": eid,
                        "occurrences": len(entries),
                        "types": list({e.get("entity_type") for e in entries}),
                    })
        except Exception as e:
            log.warning("Duplicate node check failed: %s", e)
        return dupes


# ═══════════════════════════════════════════════════════════════════════
# Confidence Check
# ═══════════════════════════════════════════════════════════════════════


class ConfidenceChecker:
    """Checks traceability confidence in the knowledge graph.

    Evaluates:
    - Per-requirement traceability confidence (low/medium/high)
    - Overall graph confidence score
    - Requirements with low confidence
    """

    def __init__(self, store, config: MergeGateConfig,
                 scope_files: list[str] | None = None):
        self.store = store
        self.config = config
        # 2026-08-08 (D): 与 GraphConsistencyChecker 同步收窄到 session 产物子图。
        # 传 changed_files 时，置信度/覆盖率只统计这些文件相关的节点/边，
        # 不再扫全图，避免全图历史噪声（stash、手工改动）误伤门禁。
        # None/[] = 全图（兼容旧调用与测试）。
        self.scope_files: list[str] | None = scope_files

    def _scoped_nodes(self) -> list[dict]:
        """Nodes narrowed to scope_files (None/[] = full graph)."""
        return _filter_nodes_by_scope(self.store.get_all_nodes(), self.scope_files)

    def _scoped_edges(self) -> list[dict]:
        """Edges narrowed to scope_files' node ids (None/[] = full graph)."""
        edges = self.store.get_all_edges()
        if not self.scope_files:
            return edges
        scoped_ids = {n.get("entity_id") for n in self._scoped_nodes() if n.get("entity_id")}
        return _filter_edges_by_scope(edges, scoped_ids)

    def check_all(self) -> dict:
        """Run confidence checks and return results."""
        errors: list[dict] = []
        warnings: list[dict] = []

        try:
            edges = self._scoped_edges()
            nodes = self._scoped_nodes()

            # Collect confidence per node
            node_confidences: dict[str, list[float]] = {}
            for edge in edges:
                src = edge.get("source_id")
                conf = edge.get("confidence")
                if src and conf is not None:
                    node_confidences.setdefault(src, []).append(float(conf))

            # Calculate per-requirement stats
            low_conf_reqs = []
            for node in nodes:
                nid = node.get("entity_id")
                if not nid or node.get("entity_type") != "requirement":
                    continue
                confs = node_confidences.get(nid, [])
                if not confs:
                    low_conf_reqs.append({
                        "entity_id": nid,
                        "name": node.get("name", ""),
                        "reason": "No traceability edges",
                        "avg_confidence": 0.0,
                    })
                elif sum(confs) / len(confs) < self.config.min_confidence:
                    low_conf_reqs.append({
                        "entity_id": nid,
                        "name": node.get("name", ""),
                        "reason": f"Low avg confidence: {sum(confs)/len(confs):.2f}",
                        "avg_confidence": round(sum(confs) / len(confs), 2),
                    })

            if low_conf_reqs:
                errors.append({
                    "check": "confidence",
                    "severity": "error",
                    "message": f"{len(low_conf_reqs)} requirement(s) below confidence threshold ({self.config.min_confidence})",
                    "details": low_conf_reqs[:20],
                })

            # Overall graph confidence
            all_confidences = []
            for confs in node_confidences.values():
                all_confidences.extend(confs)

            overall = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

            # Coverage check
            requirement_count = sum(
                1 for n in nodes if n.get("entity_type") == "requirement"
            )
            requirements_with_trace = len(node_confidences)
            coverage = requirements_with_trace / requirement_count if requirement_count > 0 else 0.0

            # 2026-08-08 (D): 收窄到 session 产物后，子图内可能没有 requirement
            # 节点（会话只产出文件/文档节点）——覆盖率无从评估，只警告不阻断，
            # 避免会话产物不含需求时门禁误伤。全图模式（scope_files 为空）保持原行为。
            scope_has_no_reqs = requirement_count == 0 and self.scope_files
            if coverage < self.config.min_coverage and not scope_has_no_reqs:
                errors.append({
                        "check": "coverage",
                        "severity": "error",
                        "message": (
                            f"Requirement traceability coverage below threshold: "
                            f"{coverage:.1%} (min {self.config.min_coverage:.0%})"
                        ),
                        "details": {
                            "total_requirements": requirement_count,
                            "with_traceability": requirements_with_trace,
                            "coverage": coverage,
                        },
                    })

            if requirement_count == 0:
                scope_note = "in scope" if self.scope_files else "in graph"
                warnings.append({
                    "check": "coverage",
                    "severity": "warning",
                    "message": f"No requirement nodes found {scope_note} — cannot assess coverage",
                })

        except Exception as e:
            errors.append({
                "check": "confidence_read",
                "severity": "error",
                "message": f"Confidence check failed: {e}",
            })
            overall = 0.0
            coverage = 0.0
            requirement_count = 0
            requirements_with_trace = 0

        passed = len(errors) == 0
        if self.config.fail_on_warning:
            passed = passed and len(warnings) == 0

        return {
            "passed": passed,
            "overall_confidence": round(overall, 3) if 'overall' in dir() or overall else 0.0,
            "coverage": round(coverage, 3) if 'coverage' in dir() or coverage else 0.0,
            "total_requirements": requirement_count if 'requirement_count' in dir() else 0,
            "with_traceability": requirements_with_trace if 'requirements_with_trace' in dir() else 0,
            "low_confidence_requirements": low_conf_reqs if 'low_conf_reqs' in dir() else [],
            "errors": errors,
            "warnings": warnings,
            "error_count": len(errors),
            "warning_count": len(warnings),
        }


# ═══════════════════════════════════════════════════════════════════════
# Merge Gate Orchestrator
# ═══════════════════════════════════════════════════════════════════════


class MergeGate:
    """Merge Gate orchestrator — coordinates all checks and produces verdict.

    Steps:
    1. Detect changed files (from git or explicit file list)
    2. Optionally trigger incremental KG build
    3. Run graph consistency check
    4. Run confidence check
    5. Apply threshold rules
    6. Produce verdict (pass/fail) with detailed report
    """

    def __init__(
        self,
        store,
        project_dir: str = ".",
        config: Optional[MergeGateConfig] = None,
    ):
        self.store = store
        self.project_dir = Path(project_dir).resolve()
        self.config = config or MergeGateConfig()
        self._changed_files: list[str] = []

    def run(
        self,
        changed_files: Optional[list[str]] = None,
        base_ref: Optional[str] = None,
    ) -> dict:
        """Execute the merge gate checks.

        Args:
            changed_files: Explicit list of changed files. If None, auto-detect.
            base_ref: Git base ref for change detection. Overrides config.

        Returns:
            Dict with verdict, checks, and detailed report.
        """
        if base_ref:
            self.config.base_ref = base_ref

        gate_start = datetime.now()
        checks: dict[str, dict] = {}

        # Step 1: Detect changed files
        if changed_files is not None:
            self._changed_files = changed_files
        else:
            self._changed_files = self._detect_changed_files()

        checks["change_detection"] = {
            "passed": True,
            "changed_files_count": len(self._changed_files),
            "changed_files": self._changed_files[:50],
        }

        # Step 2: Trigger incremental build (configurable)
        if self.config.auto_build and self._changed_files:
            build_result = self._trigger_incremental_build()
            checks["incremental_build"] = build_result

        # Step 3: Graph consistency check
        checker = GraphConsistencyChecker(self.store, self.config, scope_files=self._changed_files)
        consistency = checker.check_all()
        checks["consistency"] = consistency

        # Step 4: Confidence check (2026-08-08 D: 与一致性检查同一 scope，
        # 收窄到 session 产物子图，不扫全图)
        conf_checker = ConfidenceChecker(self.store, self.config, scope_files=self._changed_files)
        confidence = conf_checker.check_all()
        checks["confidence"] = confidence

        # Step 5: Compute verdict
        all_errors = []
        all_warnings = []
        for name, check in checks.items():
            if isinstance(check, dict):
                errors = check.get("errors", [])
                warnings = check.get("warnings", [])
                all_errors.extend(errors)
                all_warnings.extend(warnings)

        total_errors = len(all_errors)
        total_warnings = len(all_warnings)
        passed = total_errors == 0

        # Apply fail_on_warning
        if self.config.fail_on_warning and total_warnings > 0:
            passed = False

        verdict = "pass" if passed else "fail"
        duration = (datetime.now() - gate_start).total_seconds()

        result = {
            "verdict": verdict,
            "passed": passed,
            "timestamp": gate_start.isoformat(),
            "duration_seconds": round(duration, 3),
            "config": asdict(self.config),
            "change_summary": {
                "detected_changes": len(self._changed_files),
                "changed_files": self._changed_files[:50],
            },
            "checks": checks,
            "summary": {
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "error_details": all_errors[:30],
                "warning_details": all_warnings[:20],
            },
            "recommendations": self._generate_recommendations(
                all_errors, all_warnings, checks,
            ),
        }

        # Write report if output_path is configured
        if self.config.output_path:
            out_path = Path(self.config.output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str)
            )
            result["report_path"] = str(out_path)

        return result

    def _detect_changed_files(self) -> list[str]:
        """Detect changed files via git diff."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", self.config.base_ref],
                capture_output=True, text=True, check=False, timeout=30,
                cwd=str(self.project_dir),
            )
            if result.returncode == 0:
                files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
                # Apply exclude patterns
                filtered = []
                for f in files:
                    excluded = False
                    for pattern in self.config.exclude_patterns:
                        if pattern.endswith("*") and f.startswith(pattern.rstrip("*")):
                            excluded = True
                            break
                        if pattern in f:
                            excluded = True
                            break
                    if not excluded:
                        filtered.append(f)
                return filtered
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.warning("Git diff failed: %s", e)
        return []

    def _trigger_incremental_build(self) -> dict:
        """Trigger incremental knowledge graph build."""
        try:
            from yuleosh.knowledge_graph.importer import incremental_bootstrap
            from datetime import datetime as _dt

            build_id = f"merge-gate-build-{_dt.now().strftime('%Y%m%d-%H%M%S')}"
            result = incremental_bootstrap(
                self.store,
                project_dir=str(self.project_dir),
                changed_files=self._changed_files,
                create_snapshot=True,
                build_id=build_id,
                snapshot_meta={
                    "source": "merge_gate",
                    "base_ref": self.config.base_ref,
                },
            )
            return {
                "passed": result.get("status") != "failed",
                "build_id": build_id,
                "mode": result.get("mode", "unknown"),
                "changed_files": sum(
                    result.get("incremental", {}).get(field, 0)
                    for field in ["changed_files", "code_files", "test_files"]
                ),
                "stats": result.get("summary", result.get("stats", {})),
            }
        except Exception as e:
            log.error("Incremental build failed: %s", e)
            return {
                "passed": False,
                "mode": "failed",
                "error": str(e),
            }

    def _generate_recommendations(
        self,
        errors: list[dict],
        warnings: list[dict],
        checks: dict[str, dict],
    ) -> list[str]:
        """Generate human-readable recommendations."""
        recs = []

        if not errors and not warnings:
            recs.append("✅ All checks passed — merge is safe to proceed.")
            return recs

        if errors:
            recs.append(f"🔴 {len(errors)} error(s) found — merge is BLOCKED.")

        # Check specific error types
        error_checks = {e.get("check") for e in errors}

        if "orphan_nodes" in error_checks:
            recs.append("Run 'yuleosh kg bootstrap' to resolve orphan nodes.")
        if "orphan_edges" in error_checks:
            recs.append("Review 'yuleosh kg report rtm' to identify missing references.")
        if "cycles" in error_checks:
            recs.append("Break circular dependencies in the knowledge graph.")
        if "confidence" in error_checks:
            recs.append(
                f"Add traceability edges with confidence ≥ {self.config.min_confidence} "
                "to low-confidence requirements."
            )
        if "coverage" in error_checks:
            recs.append("Ensure all requirements have at least one traceability edge.")
        if "node_type" in error_checks or "edge_type" in error_checks:
            recs.append("Use recognized type names from the KG schema.")

        if not recs:
            recs.append("Review the detailed check results above and fix all issues.")

        return recs


# ═══════════════════════════════════════════════════════════════════════
# CLI Handler
# ═══════════════════════════════════════════════════════════════════════


def cmd_check_merge(args) -> dict:
    """CLI implementation for ``yuleosh kg check-merge``.

    Parses CLI args, runs merge gate, prints results, and exits with
    appropriate code (0 = pass, 1 = fail).
    """
    project_dir = getattr(args, "project_dir", os.environ.get("OSH_HOME", os.getcwd()))
    base_ref = getattr(args, "base_ref", "HEAD~1")
    min_confidence = getattr(args, "min_confidence", None)
    min_coverage = getattr(args, "min_coverage", None)
    auto_build = getattr(args, "auto_build", True)
    output_path = getattr(args, "output", None)
    fail_on_warning = getattr(args, "fail_on_warning", False)
    no_build = getattr(args, "no_build", False)
    json_output = getattr(args, "json", False)

    # Create config
    config = MergeGateConfig(
        base_ref=base_ref,
        auto_build=not no_build,
        fail_on_warning=fail_on_warning,
        output_path=output_path,
    )
    if min_confidence is not None:
        config.min_confidence = float(min_confidence)
    if min_coverage is not None:
        config.min_coverage = float(min_coverage)

    # Get store
    from yuleosh.knowledge_graph import get_store
    store = get_store(
        db_path=str(Path(project_dir) / ".yuleosh" / "knowledge_graph.db")
    )

    # Run merge gate
    gate = MergeGate(store, project_dir=project_dir, config=config)
    result = gate.run()

    # Print summary
    verdict = result["verdict"]
    passed = result["passed"]
    dur = result["duration_seconds"]
    summary = result["summary"]

    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"\n  🔀 KG Merge Gate")
        print(f"  {'=' * 50}")
        print(f"  Verdict: {'✅ PASS' if passed else '❌ FAIL'}")
        print(f"  Duration: {dur:.3f}s")
        print(f"  Changes: {result['change_summary']['detected_changes']} file(s)")
        print(f"  Errors:   {summary['total_errors']}")
        print(f"  Warnings: {summary['total_warnings']}")
        print()

        # Show consistency details
        consistency = result.get("checks", {}).get("consistency", {})
        if consistency:
            print(f"  📊 Graph Consistency:")
            for e in consistency.get("errors", []):
                print(f"    🔴 {e['message']}")
            for w in consistency.get("warnings", []):
                print(f"    🟡 {w['message']}")

        # Show confidence details
        confidence = result.get("checks", {}).get("confidence", {})
        if confidence:
            print(f"\n  📊 Traceability Confidence:")
            print(f"    Overall confidence: {confidence.get('overall_confidence', 'N/A')}")
            print(f"    Coverage:           {confidence.get('coverage', 'N/A')}")
            print(f"    Requirements:       {confidence.get('total_requirements', 0)} total, "
                  f"{confidence.get('with_traceability', 0)} traced")
            for e in confidence.get("errors", []):
                print(f"    🔴 {e['message']}")
            for w in confidence.get("warnings", []):
                print(f"    🟡 {w['message']}")

        # Recommendations
        recs = result.get("recommendations", [])
        if recs:
            print(f"\n  💡 Recommendations:")
            for r in recs:
                print(f"    {r}")

        # Report path
        if result.get("report_path"):
            print(f"\n  📄 Report: {result['report_path']}")

        print()

    return result


# ═══════════════════════════════════════════════════════════════════════
# Pipeline Step Handler
# ═══════════════════════════════════════════════════════════════════════


def step_merge_gate(session) -> str:
    """Pipeline step handler for the KG Merge Gate (KG-42).

    Called by the pipeline orchestrator as entry in PIPELINE_STEPS.
    Runs merge gate checks and raises PipelineStepError if blocked.

    Args:
        session: PipelineSession instance.

    Returns:
        Path to the merge gate report file.

    Raises:
        PipelineStepError: If the merge gate verdict is "fail".
    """
    from yuleosh.pipeline.session import PipelineStepError

    print("  🚦 [小马] KG Merge Gate — checking merge eligibility...")

    # ── Mock mode: skip real KG checks ─────────────────────────────
    # In --mock runs the knowledge graph is empty (no real code scanned);
    # traceability coverage would read 0% and block the demo. Record a
    # PASSED report and continue. Strict `is True` keeps MagicMock honest.
    if getattr(session, "mock_mode", None) is True:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())
        output_path = str(
            Path(session.session_dir) / "merge-gate-report.json"
            if hasattr(session, "session_dir") and session.session_dir
            else Path(project_dir) / ".yuleosh" / "reports" / "merge-gate-report.json"
        )
        report = {
            "gate": "merge_gate",
            "skipped": True,
            "reason": "mock mode — knowledge graph empty, no real code to validate",
            # 假绿修复 (2026-08-07)：mock 报告不再伪装 passed=True。
            # 门禁报告是证据产物，mock 未做真实检查 → passed=False + verdict=skipped，
            # 避免下游把 mock 产物当"门禁通过"证据消费。
            "passed": False,
            "verdict": "skipped",
            "summary": {"total_errors": 0, "total_warnings": 0, "error_details": []},
        }
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(report, indent=2))
        print("  ⏭️  KG Merge Gate skipped — mock mode")
        return output_path

    project_dir = os.environ.get("OSH_HOME", os.getcwd())
    output_path = str(
        Path(session.session_dir) / "merge-gate-report.json"
        if hasattr(session, "session_dir") and session.session_dir
        else Path(project_dir) / ".yuleosh" / "reports" / "merge-gate-report.json"
    )

    config = MergeGateConfig(
        min_confidence=0.7,
        min_coverage=0.8,
        auto_build=True,
        fail_on_warning=False,
        output_path=output_path,
    )

    from yuleosh.knowledge_graph import get_store
    store = get_store(
        db_path=str(Path(project_dir) / ".yuleosh" / "knowledge_graph.db")
    )

    gate = MergeGate(store, project_dir=project_dir, config=config)

    # Scope the gate to THIS session's artifacts instead of the whole
    # working tree.  `git diff HEAD~1` picks up unrelated local changes
    # (stashes, prior manual edits), which makes the gate fail on noise.
    # Artifacts written under the session dir are the pipeline's own output.
    session_scope = []
    try:
        sdir = Path(session.session_dir)
        if sdir.is_dir():
            session_scope = sorted(
                str(p.relative_to(Path(project_dir).resolve()))
                for p in sdir.rglob("*")
                if p.is_file() and p.suffix.lower() in (".md", ".json", ".xlsx", ".c", ".h")
            )
    except Exception as _e:  # pragma: no cover - defensive
        log.debug("Session scoping failed, falling back to git diff: %s", _e)
    if session_scope:
        result = gate.run(changed_files=session_scope)
    else:
        # 2026-08-08 (D): 无 session 产物时退化为全图扫描——显式传 [] 使
        # scope_files=[]（一致性/置信度检查扫全图），不再走 git diff
        # （会拾取工作区 stash/手工改动噪声）。报告 change_summary 记录 0 changes。
        result = gate.run(changed_files=[])

    passed = result.get("passed", False)
    verdict = result.get("verdict", "fail")

    # Log result
    print(f"  {'✅' if passed else '❌'} KG Merge Gate verdict: {verdict.upper()}")
    print(f"    Errors: {result.get('summary', {}).get('total_errors', 0)} | "
          f"Warnings: {result.get('summary', {}).get('total_warnings', 0)}")
    print(f"    Report: {output_path}")

    if not passed:
        errors = result.get("summary", {}).get("error_details", [])
        error_msgs = "\n".join(f"  - {e.get('message', str(e))}" for e in errors[:5])
        raise PipelineStepError(
            f"KG Merge Gate BLOCKED: {result.get('summary', {}).get('total_errors', 0)} error(s)\n"
            f"{error_msgs}\n"
            f"Fix issues and re-run pipeline."
        )

    # ── CM Gate（第九轮决策 2026-08-19, 角色=小仓）─────────────
    # KG 检查通过后执行 4 项确定性 CM 检查（非 LLM）:
    #   1) 工作区清洁 (warning 不阻断)  2) 提交规范 (failed 阻断)
    #   3) 生成产物泄漏 (failed 阻断)   4) 部署护栏状态确认
    cm_result = _run_cm_gate_checks(project_dir, session)

    # 把 CM 检查结果并入 merge-gate 报告（追加 section, 保留 KG 部分）
    try:
        _merge_cm_into_report(output_path, cm_result)
    except Exception as e:  # pragma: no cover - defensive  # noqa: BLE001
        log.warning("CM report merge failed (non-fatal): %s", e)

    if cm_result.get("status") == "failed":
        failed_checks = cm_result.get("failed_checks", [])
        raise PipelineStepError(
            f"CM Gate BLOCKED: {failed_checks} — 仓库管理检查未通过\n"
            f"{cm_result.get('summary', '')}\n"
            f"详见 merge-gate-report.json (cm_checks section)。"
        )

    if cm_result.get("status") == "warning":
        print(f"  🟡 [小仓] CM Gate: {cm_result.get('summary', '')} "
              f"(warning 不阻断)")
    else:
        print(f"  {'✅' if cm_result.get('status') == 'passed' else '⏭️'} "
              f"[小仓] CM Gate: {cm_result.get('summary', '')}")

    return output_path


# ═══════════════════════════════════════════════════════════════════════
# CM Gate helpers（第九轮决策 2026-08-19, 角色=小仓）
# ═══════════════════════════════════════════════════════════════════════


def _run_cm_gate_checks(project_dir: str, session) -> dict:
    """Run the 4 deterministic CM checks (non-LLM).

    Merges results into the session report and returns the aggregated dict.
    """
    from yuleosh.knowledge_graph.cm_checks import run_cm_checks

    session_dir = None
    if hasattr(session, "session_dir") and session.session_dir:
        session_dir = Path(session.session_dir)
    # r21q: 断点续跑 (--from-step > 9) / diff 裁剪未执行 codegen-deploy 时,
    # 全局 codegen-deploy.json 仍是上次 run 的 deployed → deploy_guardrail
    # 必须跳过, 否则恢复 run 的 merge-gate 误报 RED (window-anti-pinch 实测)。
    deploy_step_executed = _deploy_step_executed_in_session(session)
    return run_cm_checks(project_dir, session_dir, deploy_step_executed=deploy_step_executed)


def _deploy_step_executed_in_session(session) -> bool:
    """codegen-deploy (step 9) 是否在本 session 执行过 (completed)。"""
    steps = getattr(session, "steps", None) or []
    for s in steps:
        if isinstance(s, dict) and s.get("name") == "codegen-deploy":
            return s.get("status") == "completed"
    return False


def _merge_cm_into_report(report_path: str, cm_result: dict) -> None:
    """Append the CM check results into the existing merge-gate report JSON.

    Preserves the KG gate section; adds a top-level ``cm_checks`` section.
    """
    import json as _json

    p = Path(report_path)
    if not p.exists():
        return
    data = _json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return
    data["cm_checks"] = cm_result
    p.write_text(_json.dumps(data, indent=2, ensure_ascii=False, default=str),
                 encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════════════════


def _mock_store():
    """Create a minimal mock store for testing purposes."""
    from unittest.mock import MagicMock

    store = MagicMock()
    store.get_all_nodes.return_value = []
    store.get_all_edges.return_value = []
    store.setup = MagicMock()
    return store