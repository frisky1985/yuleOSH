#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
"""
Knowledge Graph Store — SQLite-backed persistent store for nodes and edges.

Maintains its own SQLite database at .yuleosh/knowledge_graph.db.
Schema adapted from the PostgreSQL design in kg-architecture.md (v0.1.0).

Tables:
  kg_nodes     — polymorphic node table
  kg_edges     — directed edge table
  kg_snapshots — CI build snapshots

Note: BFS traversal is implemented in Python (not recursive CTE) since
SQLite's recursive CTE support is limited for JSON deserialization.
"""
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.knowledge_graph.models import Node, Edge, Snapshot

log = logging.getLogger("yuleosh.knowledge_graph.store")

# Schema version — bump to trigger re-migration
_SCHEMA_VERSION = 1


class KGStore:
    """SQLite-backed knowledge graph store. Thread-safe singleton per db_path."""

    _instances = {}
    _lock = threading.Lock()

    def __new__(cls, db_path: Optional[str] = None):
        key = db_path or "default"
        with cls._lock:
            if key not in cls._instances:
                instance = super().__new__(cls)
                resolved = db_path or os.environ.get(
                    "YULEOSH_KG_DB",
                    str(Path(os.environ.get("OSH_HOME", ".")) / ".yuleosh" / "knowledge_graph.db"),
                )
                Path(resolved).parent.mkdir(parents=True, exist_ok=True)
                instance.db_path = resolved
                instance.conn = sqlite3.connect(resolved, check_same_thread=False)
                instance.conn.row_factory = sqlite3.Row
                instance._migrate()
                cls._instances[key] = instance
            return cls._instances[key]

    @classmethod
    def reset(cls):
        """Clear all instances (for testing). Recreates new instances on next access."""
        for inst in cls._instances.values():
            try:
                inst.conn.close()
            except Exception:
                pass
        cls._instances = {}

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _migrate(self):
        """Create tables and apply any pending schema changes."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS kg_nodes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id   TEXT NOT NULL,
                label       TEXT NOT NULL,
                properties  TEXT NOT NULL DEFAULT '{}',
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                UNIQUE (entity_type, entity_id)
            );
            CREATE INDEX IF NOT EXISTS idx_kg_nodes_type ON kg_nodes(entity_type);
            CREATE INDEX IF NOT EXISTS idx_kg_nodes_entity_id ON kg_nodes(entity_id);

            CREATE TABLE IF NOT EXISTS kg_edges (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   INTEGER NOT NULL REFERENCES kg_nodes(id),
                target_id   INTEGER NOT NULL REFERENCES kg_nodes(id),
                edge_type   TEXT NOT NULL,
                properties  TEXT NOT NULL DEFAULT '{}',
                verified_at TEXT,
                build_id    TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                UNIQUE (source_id, target_id, edge_type)
            );
            CREATE INDEX IF NOT EXISTS idx_kg_edges_source ON kg_edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_kg_edges_target ON kg_edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_kg_edges_type ON kg_edges(edge_type);

            CREATE TABLE IF NOT EXISTS kg_snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                build_id    TEXT UNIQUE NOT NULL,
                built_at    TEXT NOT NULL,
                node_count  INTEGER NOT NULL,
                edge_count  INTEGER NOT NULL,
                meta        TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS kg_meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        self.conn.execute(
            "INSERT OR REPLACE INTO kg_meta (key, value) VALUES ('schema_version', ?)",
            (str(_SCHEMA_VERSION),)
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Node CRUD
    # ------------------------------------------------------------------

    def upsert_node(self, node: Node) -> int:
        """Insert or update a node. Returns the rowid."""
        now = datetime.now().isoformat()
        self.conn.execute("""
            INSERT INTO kg_nodes (entity_type, entity_id, label, properties, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (entity_type, entity_id) DO UPDATE SET
                label       = excluded.label,
                properties  = excluded.properties,
                is_active   = excluded.is_active,
                updated_at  = excluded.updated_at
        """, (
            node.entity_type,
            node.entity_id,
            node.label,
            json.dumps(node.properties),
            1 if node.is_active else 0,
            now,
            now,
        ))
        self.conn.commit()
        # Always query to get the definitive rowid (safe across INSERT vs UPDATE)
        cur = self.conn.execute(
            "SELECT id FROM kg_nodes WHERE entity_type=? AND entity_id=?",
            (node.entity_type, node.entity_id)
        )
        row = cur.fetchone()
        return row["id"]

    def get_node(self, entity_type: str, entity_id: str) -> Optional[Node]:
        """Get a node by its type+id."""
        cur = self.conn.execute(
            "SELECT * FROM kg_nodes WHERE entity_type=? AND entity_id=?",
            (entity_type, entity_id)
        )
        row = cur.fetchone()
        return self._row_to_node(row) if row else None

    def get_node_by_id(self, node_id: int) -> Optional[Node]:
        """Get a node by its internal ID."""
        cur = self.conn.execute("SELECT * FROM kg_nodes WHERE id=?", (node_id,))
        row = cur.fetchone()
        return self._row_to_node(row) if row else None

    def list_nodes(self, entity_type: Optional[str] = None, active_only: bool = True) -> list[Node]:
        """List nodes, optionally filtered by type."""
        if entity_type:
            if active_only:
                cur = self.conn.execute(
                    "SELECT * FROM kg_nodes WHERE entity_type=? AND is_active=1 ORDER BY entity_id",
                    (entity_type,)
                )
            else:
                cur = self.conn.execute(
                    "SELECT * FROM kg_nodes WHERE entity_type=? ORDER BY entity_id",
                    (entity_type,)
                )
        else:
            if active_only:
                cur = self.conn.execute("SELECT * FROM kg_nodes WHERE is_active=1 ORDER BY entity_type, entity_id")
            else:
                cur = self.conn.execute("SELECT * FROM kg_nodes ORDER BY entity_type, entity_id")
        return [self._row_to_node(r) for r in cur.fetchall()]

    def delete_node(self, entity_type: str, entity_id: str) -> bool:
        """Soft-delete a node. Returns True if affected."""
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            "UPDATE kg_nodes SET is_active=0, updated_at=? WHERE entity_type=? AND entity_id=?",
            (now, entity_type, entity_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Edge CRUD
    # ------------------------------------------------------------------

    def upsert_edge(self, edge: Edge) -> int:
        """Insert or update an edge. Returns the rowid."""
        now = datetime.now().isoformat()
        # Sync layer field into properties for DB storage
        props = dict(edge.properties) if edge.properties else {}
        if edge.layer is not None:
            props["layer"] = edge.layer
        elif "layer" in props:
            # Back-fill the dataclass field from properties if present
            object.__setattr__(edge, "layer", props["layer"])
        self.conn.execute("""
            INSERT INTO kg_edges (source_id, target_id, edge_type, properties, verified_at, build_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source_id, target_id, edge_type) DO UPDATE SET
                properties  = excluded.properties,
                verified_at = excluded.verified_at,
                build_id    = excluded.build_id,
                updated_at  = excluded.updated_at
        """, (
            edge.source_id,
            edge.target_id,
            edge.edge_type,
            json.dumps(props),
            edge.verified_at,
            edge.build_id,
            now,
            now,
        ))
        self.conn.commit()
        # Always query to get definitive rowid (safe across INSERT vs UPDATE)
        cur = self.conn.execute(
            "SELECT id FROM kg_edges WHERE source_id=? AND target_id=? AND edge_type=?",
            (edge.source_id, edge.target_id, edge.edge_type)
        )
        row = cur.fetchone()
        return row["id"]

    def get_edge(self, source_id: int, target_id: int, edge_type: str) -> Optional[Edge]:
        """Get an edge by its source, target, and type."""
        cur = self.conn.execute(
            "SELECT * FROM kg_edges WHERE source_id=? AND target_id=? AND edge_type=?",
            (source_id, target_id, edge_type)
        )
        row = cur.fetchone()
        return self._row_to_edge(row) if row else None

    def list_edges(self, edge_type: Optional[str] = None) -> list[Edge]:
        """List all edges, optionally filtered by type."""
        if edge_type:
            cur = self.conn.execute(
                "SELECT * FROM kg_edges WHERE edge_type=? ORDER BY id", (edge_type,)
            )
        else:
            cur = self.conn.execute("SELECT * FROM kg_edges ORDER BY id")
        return [self._row_to_edge(r) for r in cur.fetchall()]

    def get_outgoing_edges(self, node_id: int) -> list[tuple[Edge, Node]]:
        """Get all outgoing edges from a node, with target nodes."""
        cur = self.conn.execute("""
            SELECT e.*, n.id AS n_id, n.entity_type AS n_type, n.entity_id AS n_eid,
                   n.label AS n_label, n.properties AS n_props, n.is_active AS n_active,
                   n.created_at AS n_created, n.updated_at AS n_updated
            FROM kg_edges e
            JOIN kg_nodes n ON n.id = e.target_id
            WHERE e.source_id=?
            ORDER BY e.edge_type
        """, (node_id,))
        results = []
        for row in cur.fetchall():
            edge = self._row_to_edge(row)
            target = Node(
                id=row["n_id"],
                entity_type=row["n_type"],
                entity_id=row["n_eid"],
                label=row["n_label"],
                properties=json.loads(row["n_props"]),
                is_active=bool(row["n_active"]),
                created_at=row["n_created"],
                updated_at=row["n_updated"],
            )
            results.append((edge, target))
        return results

    def get_incoming_edges(self, node_id: int) -> list[tuple[Edge, Node]]:
        """Get all incoming edges to a node, with source nodes."""
        cur = self.conn.execute("""
            SELECT e.*, n.id AS n_id, n.entity_type AS n_type, n.entity_id AS n_eid,
                   n.label AS n_label, n.properties AS n_props, n.is_active AS n_active,
                   n.created_at AS n_created, n.updated_at AS n_updated
            FROM kg_edges e
            JOIN kg_nodes n ON n.id = e.source_id
            WHERE e.target_id=?
            ORDER BY e.edge_type
        """, (node_id,))
        results = []
        for row in cur.fetchall():
            edge = self._row_to_edge(row)
            source = Node(
                id=row["n_id"],
                entity_type=row["n_type"],
                entity_id=row["n_eid"],
                label=row["n_label"],
                properties=json.loads(row["n_props"]),
                is_active=bool(row["n_active"]),
                created_at=row["n_created"],
                updated_at=row["n_updated"],
            )
            results.append((edge, source))
        return results

    def delete_edge(self, source_id: int, target_id: int, edge_type: str) -> bool:
        """Hard-delete an edge. Returns True if affected."""
        cur = self.conn.execute(
            "DELETE FROM kg_edges WHERE source_id=? AND target_id=? AND edge_type=?",
            (source_id, target_id, edge_type)
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Snapshot CRUD
    # ------------------------------------------------------------------

    def create_snapshot(self, build_id: str, meta: Optional[dict] = None) -> Snapshot:
        """Create a snapshot of the current graph state (idempotent on build_id)."""
        now = datetime.now().isoformat()
        node_count = self.conn.execute("SELECT COUNT(*) FROM kg_nodes WHERE is_active=1").fetchone()[0]
        edge_count = self.conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0]
        meta_json = json.dumps(meta or {})
        self.conn.execute("""
            INSERT OR REPLACE INTO kg_snapshots (build_id, built_at, node_count, edge_count, meta)
            VALUES (?, ?, ?, ?, ?)
        """, (build_id, now, node_count, edge_count, meta_json))
        self.conn.commit()
        cur = self.conn.execute(
            "SELECT id FROM kg_snapshots WHERE build_id=?", (build_id,)
        )
        snap_row = cur.fetchone()
        return Snapshot(
            id=snap_row["id"],
            build_id=build_id,
            built_at=now,
            node_count=node_count,
            edge_count=edge_count,
            meta=meta or {},
        )

    def get_snapshot(self, build_id: str) -> Optional[Snapshot]:
        """Get a snapshot by build_id."""
        cur = self.conn.execute(
            "SELECT * FROM kg_snapshots WHERE build_id=?", (build_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return Snapshot(
            id=row["id"],
            build_id=row["build_id"],
            built_at=row["built_at"],
            node_count=row["node_count"],
            edge_count=row["edge_count"],
            meta=json.loads(row["meta"]),
        )

    def list_snapshots(self, limit: int = 20) -> list[Snapshot]:
        """List recent snapshots."""
        cur = self.conn.execute(
            "SELECT * FROM kg_snapshots ORDER BY built_at DESC LIMIT ?", (limit,)
        )
        return [
            Snapshot(
                id=r["id"],
                build_id=r["build_id"],
                built_at=r["built_at"],
                node_count=r["node_count"],
                edge_count=r["edge_count"],
                meta=json.loads(r["meta"]),
            )
            for r in cur.fetchall()
        ]

    # ------------------------------------------------------------------
    # Graph statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return overall graph statistics."""
        node_counts = {}
        for row in self.conn.execute(
            "SELECT entity_type, COUNT(*) as c FROM kg_nodes WHERE is_active=1 GROUP BY entity_type"
        ).fetchall():
            node_counts[row["entity_type"]] = row["c"]

        edge_counts = {}
        for row in self.conn.execute(
            "SELECT edge_type, COUNT(*) as c FROM kg_edges GROUP BY edge_type"
        ).fetchall():
            edge_counts[row["edge_type"]] = row["c"]

        return {
            "total_nodes": sum(node_counts.values()),
            "total_edges": sum(edge_counts.values()),
            "nodes_by_type": node_counts,
            "edges_by_type": edge_counts,
        }

    def get_uncovered_requirements(self) -> list[Node]:
        """Find requirement nodes with no outgoing 'covers' edges.

        P0-4c: Excludes requirements marked as testable=False (管理需求).
        """
        cur = self.conn.execute("""
            SELECT n.* FROM kg_nodes n
            WHERE n.entity_type='requirement'
              AND n.is_active=1
              AND n.id NOT IN (
                  SELECT DISTINCT e.source_id FROM kg_edges e
                  WHERE e.edge_type='covers'
              )
              -- P0-4c: exclude management/non-testable requirements
              AND coalesce(json_extract(n.properties, '$.testable'), 1) = 1
            ORDER BY n.entity_id
        """)
        return [self._row_to_node(r) for r in cur.fetchall()]

    def get_orphan_code_files(self) -> list[Node]:
        """Find code files with no incoming or outgoing edges."""
        cur = self.conn.execute("""
            SELECT n.* FROM kg_nodes n
            WHERE n.entity_type='code_file'
              AND n.is_active=1
              AND n.id NOT IN (
                  SELECT DISTINCT e.source_id FROM kg_edges e
                  UNION
                  SELECT DISTINCT e.target_id FROM kg_edges e
              )
            ORDER BY n.entity_id
        """)
        return [self._row_to_node(r) for r in cur.fetchall()]

    def get_top_fan_out(self, limit: int = 10) -> list[tuple[Node, int]]:
        """Return nodes with the most outgoing edges."""
        cur = self.conn.execute("""
            SELECT n.*, COUNT(e.id) AS edge_count
            FROM kg_nodes n
            JOIN kg_edges e ON e.source_id = n.id
            WHERE n.is_active=1
            GROUP BY n.id
            ORDER BY edge_count DESC
            LIMIT ?
        """, (limit,))
        return [(self._row_to_node(r), r["edge_count"]) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Recursive trace (breadth-first, SQLite-compatible)
    # ------------------------------------------------------------------

    def trace_downstream(self, start_node_id: int, max_depth: int = 5,
                         edge_types: Optional[set[str]] = None) -> tuple[list[Node], list[Edge]]:
        """BFS downstream trace from a node, returning all reachable nodes and edges."""
        visited_nodes: set[int] = {start_node_id}
        all_nodes: dict[int, Node] = {}
        all_edges: list[Edge] = []
        current_level = {start_node_id}
        depth = 0

        start_node = self.get_node_by_id(start_node_id)
        if start_node:
            all_nodes[start_node_id] = start_node

        while current_level and depth < max_depth:
            next_level: set[int] = set()
            for nid in current_level:
                for edge, target in self.get_outgoing_edges(nid):
                    if edge_types and edge.edge_type not in edge_types:
                        continue
                    all_edges.append(edge)
                    if target.id not in visited_nodes:
                        visited_nodes.add(target.id)
                        all_nodes[target.id] = target
                        next_level.add(target.id)
            current_level = next_level
            depth += 1

        return list(all_nodes.values()), all_edges

    def trace_upstream(self, start_node_id: int, max_depth: int = 5,
                       edge_types: Optional[set[str]] = None) -> tuple[list[Node], list[Edge]]:
        """BFS upstream trace from a node."""
        visited_nodes: set[int] = {start_node_id}
        all_nodes: dict[int, Node] = {}
        all_edges: list[Edge] = []
        current_level = {start_node_id}
        depth = 0

        start_node = self.get_node_by_id(start_node_id)
        if start_node:
            all_nodes[start_node_id] = start_node

        while current_level and depth < max_depth:
            next_level: set[int] = set()
            for nid in current_level:
                for edge, source in self.get_incoming_edges(nid):
                    if edge_types and edge.edge_type not in edge_types:
                        continue
                    all_edges.append(edge)
                    if source.id not in visited_nodes:
                        visited_nodes.add(source.id)
                        all_nodes[source.id] = source
                        next_level.add(source.id)
            current_level = next_level
            depth += 1

        return list(all_nodes.values()), all_edges

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _row_to_node(self, row: sqlite3.Row) -> Node:
        return Node(
            id=row["id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            label=row["label"],
            properties=json.loads(row["properties"]) if row["properties"] else {},
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_edge(self, row: sqlite3.Row) -> Edge:
        props = json.loads(row["properties"]) if row["properties"] else {}
        return Edge(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            edge_type=row["edge_type"],
            properties=props,
            layer=props.get("layer"),
            verified_at=row["verified_at"],
            build_id=row["build_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def close(self):
        """Close the database connection."""
        self.conn.close()
