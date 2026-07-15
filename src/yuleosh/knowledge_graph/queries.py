#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Queries — trace, impact, and meta query API.

All functions take a KGStore (SQLite) instance.
PostgreSQL variants in queries_pg.py use the same interface.

P0 query scope:
  - trace_by_req_id       — find tests covering a requirement
  - trace_by_file_path    — find requirements linked to a file
  - trace_by_test_function — find requirements tested by a test function
  - impact_analysis        — find affected reqs/tests from file changes
  - list_uncovered_requirements — reqs with no test coverage
  - list_orphan_code_files      — code files with no links
  - list_snapshots         — CI build snapshots
  - get_graph_stats        — count nodes/edges by type
"""

import logging
from typing import Optional

from yuleosh.knowledge_graph.store import KGStore

log = logging.getLogger("yuleosh.knowledge_graph.queries")


# ═══════════════════════════════════════════════════════════════════════
# Trace Queries
# ═══════════════════════════════════════════════════════════════════════

def trace_by_req_id(store: KGStore, req_id: str, include_tests: bool = True,
                    include_functions: bool = True,
                    layer: Optional[str] = None) -> Optional[dict]:
    """Trace downstream from a requirement.

    Finds covering test files and functions.
    Accepts both detailed IDs (RS-001-01) and parent IDs (RS-001).

    If *layer* is specified (e.g. "unit", "integration"), only edges whose
    ``properties["layer"]`` matches are returned.
    """
    req_node = store.get_node("requirement", req_id)
    if req_node is None:
        for node in store.list_nodes("requirement"):
            if node.entity_id == req_id:
                req_node = node
                break
            if node.entity_id.startswith(req_id):
                req_node = node
                break
    if req_node is None:
        return None

    nodes, edges = store.trace_downstream(req_node.id, max_depth=3)

    # Apply layer filter if requested
    if layer is not None:
        edges = [e for e in edges
                 if e.properties.get("layer") == layer
                 or e.properties.get("layer") is None]
        # Recompute reachable nodes from filtered edges
        reachable_ids = {req_node.id}
        for e in edges:
            reachable_ids.add(e.target_id)
            reachable_ids.add(e.source_id)
        nodes = [n for n in nodes if n.id in reachable_ids]

    # Filter: only include requirement types as source
    result_nodes = [n for n in nodes if n.id != req_node.id]
    result_edges = [e for e in edges]

    # Add confidence field to each edge and check for low-confidence chain
    edge_dicts = []
    has_low_confidence = False
    for e in result_edges:
        ed = e.to_dict()
        confidence = e.properties.get("confidence", 1.0)
        ed["confidence"] = confidence
        if confidence < 0.8:
            has_low_confidence = True
        edge_dicts.append(ed)

    result = {
        "source_node": req_node.to_dict(),
        "nodes": [n.to_dict() for n in result_nodes],
        "edges": edge_dicts,
    }
    if has_low_confidence:
        result["low_confidence_warning"] = True

    return result


def trace_by_file_path(store: KGStore, file_path: str) -> Optional[dict]:
    """Trace upstream from a file to find requirements."""
    file_node = store.get_node("code_file", file_path)
    if file_node is None:
        file_node = store.get_node("test_file", file_path)
    if file_node is None:
        return None

    nodes, edges = store.trace_upstream(file_node.id, max_depth=4)

    # Add confidence field to each edge and check for low-confidence chain
    edge_dicts = []
    has_low_confidence = False
    for e in edges:
        ed = e.to_dict()
        confidence = e.properties.get("confidence", 1.0)
        ed["confidence"] = confidence
        if confidence < 0.8:
            has_low_confidence = True
        edge_dicts.append(ed)

    result = {
        "source_node": file_node.to_dict(),
        "nodes": [n.to_dict() for n in nodes if n.id != file_node.id],
        "edges": edge_dicts,
    }
    if has_low_confidence:
        result["low_confidence_warning"] = True

    return result


def trace_by_test_function(store: KGStore, test_fqn: str) -> Optional[dict]:
    """Trace upstream from a test function to find requirements."""
    tf_node = store.get_node("test_function", test_fqn)
    if tf_node is None:
        for node in store.list_nodes("test_function"):
            if node.label == test_fqn or node.entity_id.endswith(test_fqn):
                tf_node = node
                break
    if tf_node is None:
        return None

    nodes, edges = store.trace_upstream(tf_node.id, max_depth=4)

    # Add confidence field to each edge and check for low-confidence chain
    edge_dicts = []
    has_low_confidence = False
    for e in edges:
        ed = e.to_dict()
        confidence = e.properties.get("confidence", 1.0)
        ed["confidence"] = confidence
        if confidence < 0.8:
            has_low_confidence = True
        edge_dicts.append(ed)

    result = {
        "source_node": tf_node.to_dict(),
        "nodes": [n.to_dict() for n in nodes if n.id != tf_node.id],
        "edges": edge_dicts,
    }
    if has_low_confidence:
        result["low_confidence_warning"] = True

    return result


# ═══════════════════════════════════════════════════════════════════════
# Impact Analysis
# ═══════════════════════════════════════════════════════════════════════

def impact_analysis(store: KGStore, changed_files: list[str],
                     layer: Optional[str] = None) -> dict:
    """Analyze the impact of changes to one or more files.

    If *layer* is specified (e.g. "unit", "integration"), only
    covers edges matching that test layer are considered.

    Multi-path traversal:
      Path A: code_file ──contains──→ code_function
                                  ←── verifies ── test_function
                                  ──contains──→ test_file (via test_function's parent)
                                  ──covers──← requirement
      Path B: test_file ──contains──→ test_function
                                  ──covers──← requirement
      Path C: code_file ──covers──→ requirement (if direct edges exist)
    """
    affected_reqs: dict[str, dict] = {}
    affected_tests: dict[str, list[str]] = {}
    affected_functions: list[str] = []

    for file_path in changed_files:
        file_node = store.get_node("code_file", file_path)
        if file_node is None:
            file_node = store.get_node("test_file", file_path)
        if file_node is None:
            log.debug("File not in graph: %s", file_path)
            continue

        # ── Path A: code_file → code_function → test_function → test_file → requirement
        out_edges = store.get_outgoing_edges(file_node.id)
        func_ids = []
        for edge, target in out_edges:
            if edge.edge_type == "contains" and target.entity_type in ("code_function", "test_function"):
                func_ids.append(target.id)
                affected_functions.append(f"{target.entity_type}[{target.label}]")

        # For each function, find tests that verify it AND requirements it implements
        test_func_ids: set[int] = set()
        for func_id in func_ids:
            in_edges = store.get_incoming_edges(func_id)
            for edge, source in in_edges:
                if edge.edge_type == "verifies" and source.entity_type == "test_function":
                    test_func_ids.add(source.id)
            # Also find requirements via implements edges (code_function → requirement)
            out_edges_fn = store.get_outgoing_edges(func_id)
            for edge, target in out_edges_fn:
                if edge.edge_type == "implements" and target.entity_type == "requirement":
                    affected_reqs[target.entity_id] = {
                        "req_id": target.entity_id,
                        "label": target.label,
                        "confidence": "implements",
                        "confidence_score": edge.properties.get("confidence", 1.0),
                    }

        # For each test function, find its parent test file and requirements
        for tf_id in test_func_ids:
            tf_node = store.get_node_by_id(tf_id)
            if tf_node is None:
                continue
            tf_path = tf_node.properties.get("file_path",
                        tf_node.entity_id.split("::")[0] if "::" in tf_node.entity_id else tf_node.entity_id)
            if tf_path not in affected_tests:
                affected_tests[tf_path] = []
            if tf_node.label not in affected_tests[tf_path]:
                affected_tests[tf_path].append(tf_node.label)

            # Find requirements via contains → test_file → covers → requirement
            in_edges = store.get_incoming_edges(tf_id)
            for edge, source in in_edges:
                if edge.edge_type == "contains" and source.entity_type == "test_file":
                    req_in_edges = store.get_incoming_edges(source.id)
                    for e2, src2 in req_in_edges:
                        if e2.edge_type == "covers" and src2.entity_type == "requirement":
                            if layer is not None and e2.properties.get("layer") != layer:
                                continue
                            affected_reqs[src2.entity_id] = {
                                "req_id": src2.entity_id,
                                "label": src2.label,
                                "confidence": "via_coverage",
                                "confidence_score": e2.properties.get("confidence", 1.0),
                            }

        # ── Path B: Direct test_file coverage (from RTM data)
        if file_node.entity_type == "test_file":
            # Record the test file itself
            if file_node.entity_id not in affected_tests:
                affected_tests[file_node.entity_id] = []
            affected_functions.append(f"test_file[{file_node.entity_id}]")
            # Find requirements covering this test file
            req_in_edges = store.get_incoming_edges(file_node.id)
            for edge, source in req_in_edges:
                if edge.edge_type == "covers" and source.entity_type == "requirement":
                    if layer is not None and edge.properties.get("layer") != layer:
                        continue
                    affected_reqs[source.entity_id] = {
                        "req_id": source.entity_id,
                        "label": source.label,
                        "confidence": "direct",
                        "confidence_score": edge.properties.get("confidence", 1.0),
                    }

        # ── Path C: Direct covers from code_file to requirement
        if file_node.entity_type == "code_file":
            # Record the code file itself
            affected_functions.append(f"code_file[{file_node.entity_id}]")
            for edge, target in out_edges:
                if edge.edge_type == "covers" and target.entity_type == "requirement":
                    if layer is not None and edge.properties.get("layer") != layer:
                        continue
                    affected_reqs[target.entity_id] = {
                        "req_id": target.entity_id,
                        "label": target.label,
                        "confidence": "direct",
                        "confidence_score": edge.properties.get("confidence", 1.0),
                    }

    total_affected_tests = sum(len(funcs) for funcs in affected_tests.values())

    # Check for low confidence in affected reqs
    has_low_confidence = any(
        r.get("confidence_score", 1.0) < 0.8
        for r in affected_reqs.values()
    )

    result = {
        "affected_reqs": list(affected_reqs.values()),
        "affected_tests": [
            {"file": tf, "functions": funcs}
            for tf, funcs in sorted(affected_tests.items())
        ],
        "affected_functions": affected_functions,
        "impact_summary": (
            f"{len(affected_reqs)} requirements, "
            f"{total_affected_tests} test functions, "
            f"{len(affected_functions)} code functions affected"
        ),
    }
    if has_low_confidence:
        result["low_confidence_warning"] = True

    return result


# ═══════════════════════════════════════════════════════════════════════
# Meta Queries
# ═══════════════════════════════════════════════════════════════════════

def list_uncovered_requirements(store: KGStore) -> list[dict]:
    """Find requirement nodes with no outgoing 'covers' edges."""
    nodes = store.get_uncovered_requirements()
    return [n.to_dict() for n in nodes]


def list_orphan_code_files(store: KGStore) -> list[dict]:
    """Find active code files with no edges at all."""
    nodes = store.get_orphan_code_files()
    return [n.to_dict() for n in nodes]


def list_snapshots(store: KGStore, limit: int = 20) -> list[dict]:
    """List recent snapshots."""
    return [s.to_dict() for s in store.list_snapshots(limit=limit)]


def get_graph_stats(store: KGStore) -> dict:
    """Return overall graph statistics."""
    return store.get_stats()


# ═══════════════════════════════════════════════════════════════════════
# ASPICE Coverage Report
# ═══════════════════════════════════════════════════════════════════════

def get_aspice_coverage(store: KGStore) -> dict:
    """Return an ASPICE coverage summary broken down by test layer.

    Uses a single SQL JOIN query (instead of loading all edges into Python
    memory + per-edge node lookups). For each test layer (unit/integration/
    sil/hil/system), reports the count of covers edges and the distinct
    set of test files involved.

    Returns:
        {
            "unit":  {"total_covers": N, "files": ["test_a.py", ...]},
            "integration": {"total_covers": N, "files": [...]},
            "sil":  {"total_covers": N, "files": [...]},
            "hil":  {"total_covers": N, "files": [...]},
            "system": {"total_covers": N, "files": [...]},
        }
    """
    import json

    layer_names = ["unit", "integration", "sil", "hil", "system"]
    report: dict[str, dict] = {
        ln: {"total_covers": 0, "files": []} for ln in layer_names
    }
    seen_files_by_layer: dict[str, set[str]] = {
        ln: set() for ln in layer_names
    }

    # Single SQL query: JOIN covers edges with target nodes
    # Extract file path from target node based on entity_type
    # and extract layer from edge.properties JSON
    cur = store.conn.execute("""
        SELECT
            json_extract(e.properties, '$.layer') AS layer,
            t.entity_type AS target_type,
            t.entity_id   AS target_eid,
            t.properties  AS target_props,
            COUNT(*)      AS cnt
        FROM kg_edges e
        JOIN kg_nodes t ON t.id = e.target_id
        WHERE e.edge_type = 'covers'
        GROUP BY layer, t.entity_type, t.entity_id, t.properties
        ORDER BY layer
    """)

    for row in cur:
        layer = row["layer"] or "_unknown"
        target_type = row["target_type"]
        target_eid = row["target_eid"]
        target_props = json.loads(row["target_props"]) if isinstance(row["target_props"], str) else (row["target_props"] or {})
        cnt = row["cnt"]

        if layer not in report:
            report[layer] = {"total_covers": 0, "files": []}
            seen_files_by_layer[layer] = set()

        report[layer]["total_covers"] += cnt

        # Resolve file path from target node
        if target_type == "test_file":
            fpath = target_eid
        elif target_type == "test_function":
            fpath = target_props.get("file_path", "") or target_eid.split("::")[0]
        else:
            fpath = str(target_eid)
        if fpath:
            seen_files_by_layer[layer].add(fpath)

    for ln in layer_names:
        report[ln]["files"] = sorted(seen_files_by_layer[ln])

    # Clean up _unknown if empty
    if "_unknown" in report and report["_unknown"]["total_covers"] == 0:
        del report["_unknown"]

    return report


def get_confirmation_trace(store: KGStore) -> list[dict]:
    """返回所有 validates 边的完整确认追溯链路（P0-5 SWE.5 确认）。

    Uses a single SQL JOIN query instead of iterating edges + per-edge
    node lookups (optimized for 100K+ node graphs).

    Returns:
        list of dicts, each with:
          - edge_type: "validates"
          - source: source node info (entity_type, entity_id, label)
          - target: target node info (entity_type, entity_id, label)
          - layer: test layer (integration/sil/hil/system)
    """
    cur = store.conn.execute("""
        SELECT
            e.source_id,
            e.target_id,
            e.edge_type,
            e.properties,
            e.build_id,
            json_extract(e.properties, '$.layer') AS layer,
            e.created_at,
            e.updated_at,
            -- Source node
            s.entity_type AS s_type,
            s.entity_id   AS s_eid,
            s.label       AS s_label,
            s.properties  AS s_props,
            s.is_active   AS s_active,
            s.created_at  AS s_created,
            s.updated_at  AS s_updated,
            -- Target node
            t.entity_type AS t_type,
            t.entity_id   AS t_eid,
            t.label       AS t_label,
            t.properties  AS t_props,
            t.is_active   AS t_active,
            t.created_at  AS t_created,
            t.updated_at  AS t_updated
        FROM kg_edges e
        JOIN kg_nodes s ON s.id = e.source_id
        JOIN kg_nodes t ON t.id = e.target_id
        WHERE e.edge_type = 'validates'
        ORDER BY e.id
    """)

    import json
    result = []
    for row in cur:
        source_dict = {
            "id": row["source_id"],
            "entity_type": row["s_type"],
            "entity_id": row["s_eid"],
            "label": row["s_label"],
            "properties": json.loads(row["s_props"]) if isinstance(row["s_props"], str) else (row["s_props"] or {}),
            "is_active": bool(row["s_active"]),
            "created_at": row["s_created"],
            "updated_at": row["s_updated"],
        }
        target_dict = {
            "id": row["target_id"],
            "entity_type": row["t_type"],
            "entity_id": row["t_eid"],
            "label": row["t_label"],
            "properties": json.loads(row["t_props"]) if isinstance(row["t_props"], str) else (row["t_props"] or {}),
            "is_active": bool(row["t_active"]),
            "created_at": row["t_created"],
            "updated_at": row["t_updated"],
        }
        edge_props = json.loads(row["properties"]) if isinstance(row["properties"], str) else (row["properties"] or {})
        result.append({
            "edge_type": row["edge_type"],
            "source": source_dict,
            "target": target_dict,
            "layer": row["layer"],
            "properties": edge_props,
        })

    return result
