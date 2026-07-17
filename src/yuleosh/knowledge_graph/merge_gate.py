#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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

    def __init__(self, store, config: MergeGateConfig):
        self.store = store
        self.config = config

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
            nodes = self.store.get_all_nodes()
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
            edges = self.store.get_all_edges()
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
            nodes = self.store.get_all_nodes()
            edges = self.store.get_all_edges()

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
            nodes = self.store.get_all_nodes()
            node_ids = {n.get("entity_id") for n in nodes}
            edges = self.store.get_all_edges()

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
            edges = self.store.get_all_edges()
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
            nodes = self.store.get_all_nodes()
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

    def __init__(self, store, config: MergeGateConfig):
        self.store = store
        self.config = config

    def check_all(self) -> dict:
        """Run confidence checks and return results."""
        errors: list[dict] = []
        warnings: list[dict] = []

        try:
            edges = self.store.get_all_edges()
            nodes = self.store.get_all_nodes()

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

            if coverage < self.config.min_coverage:
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
                warnings.append({
                    "check": "coverage",
                    "severity": "warning",
                    "message": "No requirement nodes found in graph — cannot assess coverage",
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
        checker = GraphConsistencyChecker(self.store, self.config)
        consistency = checker.check_all()
        checks["consistency"] = consistency

        # Step 4: Confidence check
        conf_checker = ConfidenceChecker(self.store, self.config)
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
    result = gate.run()

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

    return output_path


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
