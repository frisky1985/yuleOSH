#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Edge Builder — construct and annotate edges.

Functions:
  - _merge_test_functions()     — deduplicate test_function nodes
  - _annotate_covers_layer()    — infer ASPICE test layer from filenames
  - _infer_layer_from_filename()
  - _build_implements_edges()   — derive implements from covers + verifies
  - _build_validates_edges()    — create validates for integration/sil/hil
  - _fallback_code_file_matching() — heuristic code→req matching (P0-4b)
  - _match_code_files_to_requirements() — alias
  - _fix_orphan_test_files()    — auto-covers for orphan test files (P0-4e)
"""

import gc
import json
import logging
import re
from pathlib import Path

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.models import Node, Edge

log = logging.getLogger("yuleosh.knowledge_graph.edge_builder")


# ═══════════════════════════════════════════════════════════════════════
# Layer inference
# ═══════════════════════════════════════════════════════════════════════

_LAYER_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"test_sil_"), "sil"),
    (re.compile(r"test_hil_"), "hil"),
    (re.compile(r"test_.*_integration\.py$"), "integration"),
    (re.compile(r"test_e2e_"), "integration"),
]
"""Patterns to infer test layer from filename, ordered by specificity."""


def _infer_layer_from_filename(file_path: str) -> str:
    """Infer ASPICE test layer from a test file path.

    Rules:
      - test_*_integration.py or test_e2e_* → integration
      - test_sil_* → sil
      - test_hil_* → hil
      - everything else → unit (ASPICE default)
    """
    fname = Path(file_path).name.lower()
    for pattern, layer in _LAYER_PATTERNS:
        if pattern.search(fname):
            return layer
    return "unit"


def _annotate_covers_layer(store: KGStore) -> dict:
    """Annotate all 'covers' edges with layer information inferred from
    the target test file name.

    Uses a SQL JOIN cursor-based approach (no full-load of edges into
    Python memory) to iterate all 'covers' edges. Resolves target node
    file path from the joined row and writes ``layer`` into properties.

    Returns summary dict with counts.
    """
    annotated = 0
    skipped = 0

    cur = store.conn.execute("""
        SELECT
            e.id,
            e.source_id,
            e.target_id,
            e.edge_type,
            e.properties        AS edge_props,
            e.verified_at,
            e.build_id,
            t.entity_type       AS target_type,
            t.entity_id         AS target_eid,
            t.properties        AS target_props
        FROM kg_edges e
        JOIN kg_nodes t ON t.id = e.target_id
        WHERE e.edge_type = 'covers'
        ORDER BY e.id
    """)

    while True:
        row = cur.fetchone()
        if row is None:
            break

        edge_props = json.loads(row["edge_props"]) if isinstance(row["edge_props"], str) else (row["edge_props"] or {})

        if edge_props.get("layer"):
            skipped += 1
            continue

        target_type = row["target_type"]
        target_eid = row["target_eid"]
        target_props = json.loads(row["target_props"]) if isinstance(row["target_props"], str) else (row["target_props"] or {})

        if target_type == "test_file":
            file_path = target_eid
        elif target_type == "test_function":
            file_path = target_props.get("file_path", "") or target_eid.split("::")[0]
        else:
            file_path = target_eid

        if not file_path:
            skipped += 1
            continue

        layer = _infer_layer_from_filename(file_path)

        props = dict(edge_props)
        props["layer"] = layer

        store.upsert_edge(Edge(
            source_id=row["source_id"],
            target_id=row["target_id"],
            edge_type=row["edge_type"],
            properties=props,
            verified_at=row["verified_at"],
            build_id=row["build_id"],
            layer=layer,
        ))
        annotated += 1

        if annotated % 5000 == 0:
            gc.collect()

    log.info("Layer annotation: %d covers edges annotated, %d already had layer",
             annotated, skipped)
    return {"annotated": annotated, "skipped": skipped}


# ═══════════════════════════════════════════════════════════════════════
# Merge duplicate test functions
# ═══════════════════════════════════════════════════════════════════════


def _merge_test_functions(store: KGStore) -> dict:
    """Merge duplicate test_function nodes after bootstrap.

    The RTM importer creates test_function nodes with entity_id = FQN
    (e.g., "tests/test_engine.py::test_pipeline_run") while the coverage
    importer creates test_function nodes that may use different entity_id
    formats. The code scanner also creates test_function nodes with the
    same FQN format. This function merges duplicates by:

    1. Grouping test_function nodes by their label
    2. For each group with multiple nodes, picking the canonical node
       (prefer RTM-sourced) and redirecting all edges to it
    3. Marking duplicates as is_active = False

    Returns summary dict with counts.
    """
    all_tfns = store.list_nodes(entity_type="test_function", active_only=False)
    active_tfns = [n for n in all_tfns if n.is_active]

    if len(active_tfns) <= 1:
        return {"merged_nodes": 0, "edges_redirected": 0, "groups_merged": 0}

    by_label: dict[str, list[Node]] = {}
    for n in active_tfns:
        label = n.label
        if label not in by_label:
            by_label[label] = []
        by_label[label].append(n)

    merged_count = 0
    redirected_edges = 0
    groups_merged = 0

    for label, nodes in by_label.items():
        if len(nodes) <= 1:
            continue

        rtm_nodes = [n for n in nodes
                     if n.properties.get("source") == "requirement-traceability-matrix.md"]
        if rtm_nodes:
            canonical = rtm_nodes[0]
            duplicates = [n for n in nodes if n.id != canonical.id]
        else:
            sorted_nodes = sorted(nodes, key=lambda n: len(n.entity_id))
            canonical = sorted_nodes[0]
            duplicates = sorted_nodes[1:]

        if not duplicates:
            continue

        groups_merged += 1
        log.debug("Merging %d duplicates of test_function[%s] (canonical id=%d, eid=%s)",
                  len(duplicates), label, canonical.id, canonical.entity_id)

        for dup in duplicates:
            for edge, source_node in store.get_incoming_edges(dup.id):
                existing = store.get_edge(source_node.id, canonical.id, edge.edge_type)
                if existing is None:
                    new_edge = Edge(
                        source_id=source_node.id,
                        target_id=canonical.id,
                        edge_type=edge.edge_type,
                        properties=dict(edge.properties) if edge.properties else {},
                        verified_at=edge.verified_at,
                        build_id=edge.build_id,
                    )
                    new_edge.properties["_merged_from"] = dup.entity_id
                    store.upsert_edge(new_edge)
                    redirected_edges += 1
                else:
                    existing_props = dict(existing.properties) if existing.properties else {}
                    if edge.properties:
                        existing_props.update(edge.properties)
                    existing_props["_merged_from"] = dup.entity_id
                    store.upsert_edge(Edge(
                        source_id=existing.source_id,
                        target_id=existing.target_id,
                        edge_type=existing.edge_type,
                        properties=existing_props,
                        verified_at=existing.verified_at or edge.verified_at,
                        build_id=existing.build_id or edge.build_id,
                    ))
                store.delete_edge(source_node.id, dup.id, edge.edge_type)

            for edge, target_node in store.get_outgoing_edges(dup.id):
                existing = store.get_edge(canonical.id, target_node.id, edge.edge_type)
                if existing is None:
                    new_edge = Edge(
                        source_id=canonical.id,
                        target_id=target_node.id,
                        edge_type=edge.edge_type,
                        properties=dict(edge.properties) if edge.properties else {},
                        verified_at=edge.verified_at,
                        build_id=edge.build_id,
                    )
                    new_edge.properties["_merged_from"] = dup.entity_id
                    store.upsert_edge(new_edge)
                    redirected_edges += 1
                else:
                    existing_props = dict(existing.properties) if existing.properties else {}
                    if edge.properties:
                        existing_props.update(edge.properties)
                    existing_props["_merged_from"] = dup.entity_id
                    store.upsert_edge(Edge(
                        source_id=existing.source_id,
                        target_id=existing.target_id,
                        edge_type=existing.edge_type,
                        properties=existing_props,
                        verified_at=existing.verified_at or edge.verified_at,
                        build_id=existing.build_id or edge.build_id,
                    ))
                store.delete_edge(dup.id, target_node.id, edge.edge_type)

            store.delete_node(dup.entity_type, dup.entity_id)
            merged_count += 1
            log.debug("  Merged test_function[%s] id=%d (eid=%s) into canonical id=%d",
                      label, dup.id, dup.entity_id, canonical.id)

    log.info("Merge complete: %d duplicates merged into %d groups, %d edges redirected",
             merged_count, groups_merged, redirected_edges)
    return {
        "merged_nodes": merged_count,
        "edges_redirected": redirected_edges,
        "groups_merged": groups_merged,
    }


# ═══════════════════════════════════════════════════════════════════════
# Implements edges (P0-1)
# ═══════════════════════════════════════════════════════════════════════


def _build_implements_edges(store: KGStore) -> dict:
    """从 covers + verifies 推导 implements 边。

    Chain:
      requirement ──covers──→ test_file ──contains──→ test_function ──verifies──→ code_function
      ⇒ code_function ──implements──→ requirement

    Also handles shorter chains:
      requirement ──covers──→ test_function ──verifies──→ code_function

    Idempotent: skips edges that already exist.

    Returns summary dict with counts.
    """
    edge_count = 0
    reqs_covered = set()
    code_fns_covered = set()

    covers_edges = store.list_edges(edge_type="covers")
    log.info("Building implements edges from %d covers edges", len(covers_edges))

    for edge in covers_edges:
        src_node = store.get_node_by_id(edge.source_id)
        tgt_node = store.get_node_by_id(edge.target_id)

        if src_node is None or tgt_node is None:
            continue
        if src_node.entity_type != "requirement":
            continue

        req_nid = src_node.id

        # Path A: requirement ──covers──→ test_file ──contains──→ test_function ──verifies──→ code_function
        if tgt_node.entity_type == "test_file":
            tf_nid = tgt_node.id
            tf_out_edges = store.get_outgoing_edges(tf_nid)
            for contains_edge, tfn_node in tf_out_edges:
                if contains_edge.edge_type != "contains":
                    continue
                if tfn_node.entity_type != "test_function":
                    continue

                tfn_out_edges = store.get_outgoing_edges(tfn_node.id)
                for verifies_edge, code_fn_node in tfn_out_edges:
                    if verifies_edge.edge_type != "verifies":
                        continue
                    if code_fn_node.entity_type != "code_function":
                        continue

                    existing = store.get_edge(code_fn_node.id, req_nid, "implements")
                    if existing is None:
                        store.upsert_edge(Edge(
                            source_id=code_fn_node.id,
                            target_id=req_nid,
                            edge_type="implements",
                            properties={
                                "source": "derived_from_covers_verifies",
                                "via_test_function": tfn_node.entity_id,
                                "confidence": 0.9,
                            },
                        ))
                        edge_count += 1
                        reqs_covered.add(req_nid)
                        code_fns_covered.add(code_fn_node.id)

        # Path B: requirement ──covers──→ test_function ──verifies──→ code_function
        elif tgt_node.entity_type == "test_function":
            tfn_nid = tgt_node.id
            tfn_out_edges = store.get_outgoing_edges(tfn_nid)
            for verifies_edge, code_fn_node in tfn_out_edges:
                if verifies_edge.edge_type != "verifies":
                    continue
                if code_fn_node.entity_type != "code_function":
                    continue

                existing = store.get_edge(code_fn_node.id, req_nid, "implements")
                if existing is None:
                    store.upsert_edge(Edge(
                        source_id=code_fn_node.id,
                        target_id=req_nid,
                        edge_type="implements",
                        properties={
                            "source": "derived_from_covers_verifies",
                            "via_test_function": tgt_node.entity_id,
                            "confidence": 0.8,
                        },
                    ))
                    edge_count += 1
                    reqs_covered.add(req_nid)
                    code_fns_covered.add(code_fn_node.id)

        # Path C: requirement ──covers──→ code_file ──contains──→ code_function
        elif tgt_node.entity_type == "code_file":
            cf_nid = tgt_node.id
            cf_out_edges = store.get_outgoing_edges(cf_nid)
            for contains_edge, code_fn_node in cf_out_edges:
                if contains_edge.edge_type != "contains":
                    continue
                if code_fn_node.entity_type != "code_function":
                    continue

                existing = store.get_edge(code_fn_node.id, req_nid, "implements")
                if existing is None:
                    store.upsert_edge(Edge(
                        source_id=code_fn_node.id,
                        target_id=req_nid,
                        edge_type="implements",
                        properties={
                            "source": "derived_from_covers_contains",
                            "via_code_file": tgt_node.entity_id,
                            "confidence": 0.7,
                        },
                    ))
                    edge_count += 1
                    reqs_covered.add(req_nid)
                    code_fns_covered.add(code_fn_node.id)

    log.info(
        "implements edges built: %d edges, %d code_functions, %d requirements",
        edge_count, len(code_fns_covered), len(reqs_covered),
    )
    return {
        "edges": edge_count,
        "code_functions": len(code_fns_covered),
        "requirements": len(reqs_covered),
    }


# ═══════════════════════════════════════════════════════════════════════
# Validates edges (P0-5)
# ═══════════════════════════════════════════════════════════════════════


def _build_validates_edges(store: KGStore) -> dict:
    """从 integration/sil/hil 层级的 covers 边创建 validates 边（P0-5）。

    ASPICE SWE.5 要求区分验证（verification, SWE.4）和确认（confirmation, SWE.5）。
    规则：
      - covers.layer='unit' → 仅保留 covers（SWE.4 单元测试验证）
      - covers.layer='integration' / 'sil' / 'hil' / 'system'
        → 额外创建同方向的 validates 边（既是验证也是确认）

    幂等：已存在的 validates 边不会重复创建。

    Returns summary dict with counts.
    """
    edge_count = 0

    VALIDATES_LAYERS = {"integration", "hil", "sil", "system"}

    covers_edges = store.list_edges(edge_type="covers")
    log.info("Building validates edges from %d covers edges", len(covers_edges))

    for edge in covers_edges:
        layer = edge.properties.get("layer") or edge.layer
        if layer is None or layer not in VALIDATES_LAYERS:
            continue

        existing = store.get_edge(edge.source_id, edge.target_id, "validates")
        if existing is not None:
            continue

        props = dict(edge.properties) if edge.properties else {}
        props["confidence"] = 1.0
        store.upsert_edge(Edge(
            source_id=edge.source_id,
            target_id=edge.target_id,
            edge_type="validates",
            properties=props,
            verified_at=edge.verified_at,
            build_id=edge.build_id,
            layer=layer,
        ))
        edge_count += 1

    log.info("validates edges built: %d edges", edge_count)
    return {
        "edges": edge_count,
        "layers": list(VALIDATES_LAYERS),
    }


# ═══════════════════════════════════════════════════════════════════════
# Fallback code file matching (P0-4b)
# ═══════════════════════════════════════════════════════════════════════


def _fallback_code_file_matching(store: KGStore, project_base: Path) -> dict:
    """对孤立 code_file 节点进行启发式需求匹配（P0-4b）。

    对于没有任何边的 code_file 节点，尝试通过文件路径关键词
    启发式匹配需求。

    匹配规则：
      1. 从文件路径中提取模块名
      2. 如果模块名匹配需求前缀，创建 covers 边
      3. 只匹配已知需求的 entity_id

    Returns summary dict with counts.
    """
    edge_count = 0
    matched_files = 0

    orphan_nodes = store.get_orphan_code_files()
    if not orphan_nodes:
        log.info("No orphan code files to match (P0-4b)")
        return {"edges": 0, "matched_files": 0}

    all_reqs = store.list_nodes(entity_type="requirement")
    if not all_reqs:
        log.info("No requirements available for fallback matching (P0-4b)")
        return {"edges": 0, "matched_files": 0}

    req_keywords: dict[str, list] = {}
    for req in all_reqs:
        eid = req.entity_id
        prefix = eid.rsplit("-", 1)[0] if eid.count("-") >= 2 and eid.rsplit("-", 1)[1].isdigit() else eid
        for key in (prefix, eid, eid.replace("-", "_")):
            if key not in req_keywords:
                req_keywords[key] = []
            req_keywords[key].append(req)

    known_modules = set()
    for req in all_reqs:
        label = req.label or ""
        for part in label.replace("-", "_").replace("/", "_").lower().split("_"):
            if len(part) >= 3:
                known_modules.add(part)

    for node in orphan_nodes:
        if node.entity_type != "code_file":
            continue

        file_path = node.entity_id
        matched = False

        path_parts = set(file_path.lower().replace("\\", "/").split("/"))
        path_parts.update(file_path.lower().replace("\\", "/").replace("-", "_").replace(".", "_").split("_"))

        from pathlib import Path as _Path
        p = _Path(file_path)
        path_parts.add(p.stem.lower())
        path_parts.add(p.parent.name.lower())

        matched_ids = set()
        for keyword, reqs in req_keywords.items():
            kw_lower = keyword.lower()
            if kw_lower in path_parts or kw_lower in file_path.lower():
                for req in reqs:
                    if req.id is not None:
                        matched_ids.add(req.id)

        for req_nid_iter in matched_ids:
            existing = store.get_edge(req_nid_iter, node.id, "covers")
            if existing is None:
                store.upsert_edge(Edge(
                    source_id=req_nid_iter,
                    target_id=node.id,
                    edge_type="covers",
                    properties={
                        "source": "fallback_matching_p0_4b",
                        "confidence": 0.6,
                    },
                ))
                edge_count += 1
                matched = True

        if matched:
            matched_files += 1

    log.info(
        "Fallback matching (P0-4b): %d matched files, %d edges created",
        matched_files, edge_count,
    )
    return {
        "edges": edge_count,
        "matched_files": matched_files,
    }


def _match_code_files_to_requirements(store: KGStore, project_base: Path) -> dict:
    """Alias for _fallback_code_file_matching (P0-4b)."""
    return _fallback_code_file_matching(store, project_base)


# ═══════════════════════════════════════════════════════════════════════
# Orphan test file auto-covers (P0-4e)
# ═══════════════════════════════════════════════════════════════════════


def _fix_orphan_test_files(store: KGStore) -> dict:
    """对孤立测试文件自动创建 covers 边（P0-4e）。

    对于没有 incoming covers 边的 test_file 节点，
    尝试通过以下路径建立追溯：
      1. 找到 test_file 中包含的 test_function
      2. 找到 test_function 的 verifies 边指向的 code_function
      3. 找到 code_function 的 implements 边指向的 requirement
      4. 如果在第 3 步找到 requirement，创建 requirements → test_file 的 covers 边

    Returns summary dict with counts.
    """
    edge_count = 0
    fixed_files = 0

    all_test_files = store.list_nodes(entity_type="test_file")

    for tf_node in all_test_files:
        incoming = store.get_incoming_edges(tf_node.id)
        has_covers = any(e.edge_type == "covers" for e, _ in incoming)
        if has_covers:
            continue

        outgoing = store.get_outgoing_edges(tf_node.id)
        tfn_ids = [t.id for e, t in outgoing if e.edge_type == "contains" and t.entity_type == "test_function"]

        reqs_found = set()
        for tfn_id in tfn_ids:
            tfn_outgoing = store.get_outgoing_edges(tfn_id)
            for ve, cf_node in tfn_outgoing:
                if ve.edge_type == "verifies" and cf_node.entity_type == "code_function":
                    cf_outgoing = store.get_outgoing_edges(cf_node.id)
                    for ie, req_node in cf_outgoing:
                        if ie.edge_type == "implements" and req_node.entity_type == "requirement":
                            reqs_found.add(req_node.id)

        for req_nid in reqs_found:
            existing = store.get_edge(req_nid, tf_node.id, "covers")
            if existing is None:
                store.upsert_edge(Edge(
                    source_id=req_nid,
                    target_id=tf_node.id,
                    edge_type="covers",
                    properties={
                        "source": "orphan_test_file_fix_p0_4e",
                        "method": "derived_from_implements_chain",
                        "confidence": 0.7,
                    },
                ))
                edge_count += 1

        if reqs_found:
            fixed_files += 1

    log.info(
        "Orphan test file fix (P0-4e): %d fixed test files, %d edges created",
        fixed_files, edge_count,
    )
    return {
        "edges": edge_count,
        "fixed_files": fixed_files,
    }
