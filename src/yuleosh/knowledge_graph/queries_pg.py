#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Queries — PostgreSQL RECURSIVE CTE variants.

All query functions take a KGStorePG instance. Trace queries use
the store's built-in RECURSIVE CTE methods (not Python BFS).

P0 query scope:
  - trace_by_req_id       — find tests covering a requirement
  - trace_by_file_path    — find requirements linked to a file
  - trace_by_test_function — find requirements tested by a test function
  - impact_analysis        — find affected reqs/tests from file changes
  - list_uncovered_requirements — reqs with no test coverage
  - list_orphan_code_files      — code files with no links
"""

import logging
from typing import Optional

from yuleosh.knowledge_graph.store_pg import KGStorePG
from yuleosh.knowledge_graph.models_pg import NodePG, TraceResultPG

log = logging.getLogger("yuleosh.knowledge_graph.queries_pg")


def trace_by_req_id(store: KGStorePG, req_id: str, include_tests: bool = True,
                    include_functions: bool = True,
                    layer: Optional[str] = None) -> Optional[dict]:
    """Trace downstream from a requirement via RECURSIVE CTE.

    Finds covering test files and functions.
    Accepts both detailed IDs (RS-001-01) and parent IDs (RS-001).

    If *layer* is specified, only edges whose ``properties["layer"]``
    matches are returned.
    """
    req_node = store.get_node("requirement", req_id)

    # Fuzzy fallback: try listing and matching if exact not found
    if req_node is None:
        for node in store.list_nodes("requirement"):
            if node.entity_id == req_id:
                req_node = node
                break
            # Parent ID match: RS-001 matches RS-001-01, RS-001-02
            if req_id.startswith("-"):
                if node.entity_id.startswith(req_id.rstrip("-")):
                    pass  # continue scanning
            if req_id == node.entity_id:
                req_node = node
                break

    if req_node is None:
        # Try all nodes — last resort
        all_reqs = store.list_nodes("requirement")
        for n in all_reqs:
            if n.entity_id == req_id or n.entity_id.startswith(req_id):
                req_node = n
                break

    if req_node is None:
        return None

    # Use RECURSIVE CTE downstream trace
    trace_types = {"covers", "contains"} if include_functions else {"covers"}
    nodes, edges = store.trace_downstream(req_node.id, max_depth=3, edge_types=trace_types)

    # Apply layer filter if requested
    if layer is not None:
        edges = [e for e in edges
                 if e.properties.get("layer") == layer
                 or e.properties.get("layer") is None]
        reachable_ids = {req_node.id}
        for e in edges:
            reachable_ids.add(e.target_id)
            reachable_ids.add(e.source_id)
        nodes = [n for n in nodes if n.id in reachable_ids]

    result = TraceResultPG(source_node=req_node, nodes=nodes, edges=edges)
    return result.to_dict()


def trace_by_file_path(store: KGStorePG, file_path: str) -> Optional[dict]:
    """Trace upstream from a file: find linked requirements."""
    file_node = store.get_node("code_file", file_path)
    if file_node is None:
        file_node = store.get_node("test_file", file_path)

    if file_node is None:
        return None

    # RECURSIVE CTE upstream trace
    nodes, edges = store.trace_upstream(file_node.id, max_depth=3)

    result = TraceResultPG(source_node=file_node, nodes=nodes, edges=edges)
    return result.to_dict()


def trace_by_test_function(store: KGStorePG, test_fqn: str) -> Optional[dict]:
    """Trace from a test function: find file and covered requirements."""
    func_node = store.get_node("test_function", test_fqn)

    if func_node is None:
        for node in store.list_nodes("test_function"):
            if node.entity_id.endswith(f"::{test_fqn}") or node.entity_id == test_fqn:
                func_node = node
                break

    if func_node is None:
        return None

    # Trace both directions
    down_nodes, down_edges = store.trace_downstream(func_node.id, max_depth=2)
    up_nodes, up_edges = store.trace_upstream(func_node.id, max_depth=2)

    all_nodes = {n.id: n for n in down_nodes + up_nodes}
    all_edges = down_edges + up_edges

    result = TraceResultPG(source_node=func_node, nodes=list(all_nodes.values()), edges=all_edges)
    return result.to_dict()


def impact_analysis(store: KGStorePG, changed_files: list[str],
                     layer: Optional[str] = None) -> dict:
    """Analyze impact of changed files.

    Delegates to store.impact_analysis(), then optionally filters
    results by test layer.

    If *layer* is specified, only covers edges matching that layer
    are considered.
    """
    result = store.impact_analysis(changed_files)

    if layer is not None and result.get("affected_reqs"):
        # Re-check: this is a best-effort filter since the PG store
        # doesn't natively support layer filtering yet.
        # We mark which reqs actually have the right layer.
        filtered_reqs = []
        for req in result.get("affected_reqs", []):
            req_id = req.get("req_id")
            req_node = store.get_node("requirement", req_id)
            if req_node is None:
                continue
            _, edges = store.trace_downstream(req_node.id, max_depth=1,
                                              edge_types={"covers"})
            has_layer = any(
                e.properties.get("layer") == layer
                for e in edges
            )
            if has_layer:
                filtered_reqs.append(req)
        result["affected_reqs"] = filtered_reqs

    return result


def list_uncovered_requirements(store: KGStorePG) -> list[dict]:
    """Find requirement nodes with no outgoing 'covers' edges."""
    nodes = store.get_uncovered_requirements()
    return [n.to_dict() for n in nodes]


def list_orphan_code_files(store: KGStorePG) -> list[dict]:
    """Find active code files with no edges at all."""
    nodes = store.get_orphan_code_files()
    return [n.to_dict() for n in nodes]


def list_snapshots(store: KGStorePG, limit: int = 20) -> list[dict]:
    """List recent snapshots."""
    return [s.to_dict() for s in store.list_snapshots(limit=limit)]


def get_graph_stats(store: KGStorePG) -> dict:
    """Return overall graph statistics."""
    return store.get_stats()


# ═══════════════════════════════════════════════════════════════════════
# ASPICE Coverage Report
# ═══════════════════════════════════════════════════════════════════════

def get_aspice_coverage(store: KGStorePG) -> dict:
    """Return an ASPICE coverage summary broken down by test layer.

    Iterates all 'covers' edges and groups them by the ``layer``
    property ("unit" / "integration" / "sil" / "hil" / "system").
    For each layer, reports the count of edges and the distinct
    set of test files involved.
    """
    layer_names = ["unit", "integration", "sil", "hil", "system"]
    report: dict[str, dict] = {
        ln: {"total_covers": 0, "files": []} for ln in layer_names
    }
    report["_unknown"] = {"total_covers": 0, "files": []}

    seen_files_by_layer: dict[str, set[str]] = {
        ln: set() for ln in layer_names
    }
    seen_files_by_layer["_unknown"] = set()

    covers_edges = store.list_edges(edge_type="covers")
    for edge in covers_edges:
        layer = edge.properties.get("layer") or "_unknown"

        if layer not in report:
            report[layer] = {"total_covers": 0, "files": []}
            seen_files_by_layer[layer] = set()

        report[layer]["total_covers"] += 1

        # Resolve target to get file path
        target_node = store.get_node_by_id(edge.target_id)
        if target_node:
            if target_node.entity_type == "test_file":
                fpath = target_node.entity_id
            elif target_node.entity_type == "test_function":
                fpath = target_node.properties.get("file_path", "") \
                        or target_node.entity_id.split("::")[0]
            else:
                fpath = str(target_node.entity_id)
            if fpath:
                seen_files_by_layer[layer].add(fpath)

    for ln in layer_names:
        report[ln]["files"] = sorted(seen_files_by_layer[ln])

    if report["_unknown"]["total_covers"] == 0:
        del report["_unknown"]

    return report


def get_confirmation_trace(store):
    """返回所有 validates 边的完整确认追溯链路（P0-5 SWE.5 确认）。

    PostgreSQL 后端版本。
    """
    validates_edges = store.list_edges(edge_type="validates")
    result = []
    for edge in validates_edges:
        source_node = store.get_node_by_id(edge.source_id)
        target_node = store.get_node_by_id(edge.target_id)
        if source_node is None or target_node is None:
            continue
        result.append({
            "edge_type": edge.edge_type,
            "source": source_node.to_dict(),
            "target": target_node.to_dict(),
            "layer": edge.layer or edge.properties.get("layer"),
            "properties": edge.properties,
        })
    return result
