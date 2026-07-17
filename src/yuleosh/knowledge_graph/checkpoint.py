#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Checkpoint — save/restore state for incremental builds.

Manages checkpoints of nodes and edges related to changed files,
enabling safe rollback on incremental build failure.
"""

import logging

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.models import Node, Edge

log = logging.getLogger("yuleosh.knowledge_graph.checkpoint")


def _save_checkpoint(store: KGStore, changed_files: list[str]) -> dict:
    """Save a checkpoint of all nodes and edges related to *changed_files*.

    Captures:
      - code_file / test_file nodes matching any changed file path
      - code_function / test_function nodes contained in those files
      - All edges involving any of the above nodes

    Returns a serialisable dict that can be restored via _restore_checkpoint().
    """
    checkpoint = {
        "nodes": [],
        "edges": [],
        "affected_node_ids": set(),
    }

    for cf in changed_files:
        norm = cf.replace("\\", "/")
        for etype in ("code_file", "test_file"):
            node = store.get_node(etype, norm)
            if node is not None and node.is_active:
                checkpoint["nodes"].append(node.to_dict())
                checkpoint["affected_node_ids"].add(node.id)
                outgoing = store.get_outgoing_edges(node.id)
                for _, target in outgoing:
                    tnode = store.get_node_by_id(target.id)
                    if tnode and tnode.is_active:
                        checkpoint["nodes"].append(tnode.to_dict())
                        checkpoint["affected_node_ids"].add(tnode.id)

    seen_edge_pairs = set()
    for nid in checkpoint["affected_node_ids"]:
        for edge, _ in store.get_outgoing_edges(nid):
            key = (edge.source_id, edge.target_id, edge.edge_type)
            if key not in seen_edge_pairs:
                checkpoint["edges"].append(edge.to_dict())
                seen_edge_pairs.add(key)
        for edge, _ in store.get_incoming_edges(nid):
            key = (edge.source_id, edge.target_id, edge.edge_type)
            if key not in seen_edge_pairs:
                checkpoint["edges"].append(edge.to_dict())
                seen_edge_pairs.add(key)

    checkpoint["affected_node_ids"] = list(checkpoint["affected_node_ids"])
    return checkpoint


def _restore_checkpoint(store: KGStore, checkpoint: dict):
    """Restore a checkpoint saved by _save_checkpoint().

    Re-inserts all saved nodes first, then all saved edges.
    Intentional side effect: previously deleted nodes will be recreated
    with new rowids, so edges are re-created with the correct IDs.
    """
    log.info("Restoring checkpoint: %d nodes, %d edges",
             len(checkpoint["nodes"]), len(checkpoint["edges"]))

    id_map = {}
    for nd in checkpoint["nodes"]:
        n = Node(
            entity_type=nd["entity_type"],
            entity_id=nd["entity_id"],
            label=nd["label"],
            properties=nd["properties"],
            is_active=nd["is_active"],
        )
        new_id = store.upsert_node(n)
        if nd.get("id") is not None:
            id_map[nd["id"]] = new_id

    for ed in checkpoint["edges"]:
        src = id_map.get(ed["source_id"], ed["source_id"])
        tgt = id_map.get(ed["target_id"], ed["target_id"])
        store.upsert_edge(Edge(
            source_id=src,
            target_id=tgt,
            edge_type=ed["edge_type"],
            properties=ed.get("properties", {}),
            verified_at=ed.get("verified_at"),
            build_id=ed.get("build_id"),
            layer=ed.get("layer"),
        ))

    log.info("Checkpoint restored: %d nodes, %d edges",
             len(checkpoint["nodes"]), len(checkpoint["edges"]))


def _delete_changed_file_nodes(store: KGStore, changed_files: list[str]) -> dict:
    """Soft-delete all nodes and hard-delete all edges related to changed files.

    1. For each changed file path, find code_file / test_file node
    2. Find all contained code_function / test_function nodes
    3. Delete edges to/from all these nodes
    4. Soft-delete all affected nodes

    Returns summary dict with counts.
    """
    deleted_nodes = 0
    deleted_edges = 0
    affected_ids: set[int] = set()

    for cf in changed_files:
        norm = cf.replace("\\", "/")
        for etype in ("code_file", "test_file"):
            node = store.get_node(etype, norm)
            if node is None or not node.is_active:
                continue
            affected_ids.add(node.id)

            outgoing = store.get_outgoing_edges(node.id)
            for _, target in outgoing:
                affected_ids.add(target.id)

    for nid in affected_ids:
        for edge, _ in store.get_outgoing_edges(nid):
            if store.delete_edge(edge.source_id, edge.target_id, edge.edge_type):
                deleted_edges += 1
        for edge, _ in store.get_incoming_edges(nid):
            if store.delete_edge(edge.source_id, edge.target_id, edge.edge_type):
                deleted_edges += 1

    for nid in affected_ids:
        node = store.get_node_by_id(nid)
        if node and node.is_active:
            store.delete_node(node.entity_type, node.entity_id)
            deleted_nodes += 1

    log.debug("Deleted %d nodes and %d edges for changed files",
              deleted_nodes, deleted_edges)
    return {"deleted_nodes": deleted_nodes, "deleted_edges": deleted_edges}
