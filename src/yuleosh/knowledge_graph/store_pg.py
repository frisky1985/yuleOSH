#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Store — PostgreSQL-backed persistent store with RECURSIVE CTE.

Replaces the SQLite-backed store.py for production use.
Schema matches kg-architecture.md §3.2 exactly:
  - UUID primary keys (vs AUTOINCREMENT)
  - JSONB properties (vs TEXT-encoded JSON)
  - RECURSIVE CTE for graph traversal (vs Python BFS)
  - GIN indexes on JSONB + edge types

Connection via YULEOSH_DB_URL (postgresql://user:pass@host:5432/dbname)
or pass dsn= explicitly.

Usage:
    from yuleosh.knowledge_graph.store_pg import KGStorePG
    store = KGStorePG()  # uses YULEOSH_DB_URL
    store.setup()

    # Bootstrap from RTM
    store.upsert_node(Node(entity_type="requirement", entity_id="RS-001-01", label="..."))
    store.upsert_edge(Edge(source_id=..., target_id=..., edge_type="covers"))

    # Recursive trace (uses WITH RECURSIVE)
    nodes, edges = store.trace_downstream(node_id, max_depth=5)
    nodes, edges = store.trace_upstream(node_id, max_depth=5)

    # Impact analysis with SQL
    result = store.impact_analysis(["src/yuleosh/alm/traceability.py"])
"""

import json
import logging
import os
import threading
from datetime import datetime
from typing import Optional

from yuleosh.knowledge_graph.models_pg import NodePG, EdgePG, SnapshotPG

log = logging.getLogger("yuleosh.knowledge_graph.store_pg")

_SCHEMA_VERSION = 1


class KGStorePG:
    """PostgreSQL-backed knowledge graph store. Thread-safe singleton per DSN."""

    _instances = {}
    _lock = threading.Lock()

    def __new__(cls, dsn: Optional[str] = None):
        key = dsn or "default"
        with cls._lock:
            if key not in cls._instances:
                instance = super().__new__(cls)
                resolved = dsn or os.environ.get("YULEOSH_DB_URL")
                if not resolved:
                    raise ValueError(
                        "PostgreSQL connection string required. Set YULEOSH_DB_URL or pass dsn=.\n"
                        "  export YULEOSH_DB_URL=postgresql://yuleosh:yuleosh@localhost:5432/yuleosh\n"
                        "  # Or start PostgreSQL with:\n"
                        "  docker compose up -d postgres\n"
                        "  # macOS Homebrew:\n"
                        "  brew install postgresql@16 && brew services start postgresql@16"
                    )
                instance.dsn = resolved
                instance._local = threading.local()
                cls._instances[key] = instance
            return cls._instances[key]

    def setup(self):
        """Explicit initialization — run migrations."""
        self._ensure_schema()
        self._migrate()
        return self

    @classmethod
    def reset(cls):
        """Clear all instances (for testing)."""
        for inst in cls._instances.values():
            try:
                inst._close_conn()
            except Exception:
                pass
        cls._instances = {}

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @property
    def conn(self):
        """Get a database connection (per-thread, created on demand)."""
        import psycopg2
        local = self._local
        if not hasattr(local, "conn") or local.conn is None or local.conn.closed:
            local.conn = psycopg2.connect(self.dsn)
            local.conn.autocommit = True
        return local.conn

    def _close_conn(self):
        """Close the current thread's connection."""
        if hasattr(self._local, "conn") and self._local.conn and not self._local.conn.closed:
            self._local.conn.close()
            self._local.conn = None

    def close(self):
        """Close the current thread's connection."""
        self._close_conn()

    # ------------------------------------------------------------------
    # Schema & Migration
    # ------------------------------------------------------------------

    def _ensure_schema(self):
        """Create the _meta tracking table."""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kg_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );
            """)
        self.conn.commit()

    def _migrate(self):
        """Create all knowledge graph tables matching architecture §3.2 schema."""
        with self.conn.cursor() as cur:
            # Enable pgcrypto for gen_random_uuid()
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

            # ── Nodes table ──────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kg_nodes (
                    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    entity_type VARCHAR(20) NOT NULL CHECK (
                        entity_type IN ('requirement','code_module','code_file','code_function',
                                        'test_file','test_function','spec_doc',
                                        'knowledge_article','test_case')
                    ),
                    entity_id   VARCHAR(255) NOT NULL,
                    label       VARCHAR(255) NOT NULL,
                    properties  JSONB NOT NULL DEFAULT '{}',
                    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (entity_type, entity_id)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kg_nodes_type ON kg_nodes(entity_type);")
            cur.execute("CREATE INDEX IF NOT EXISTS kg_nodes_entity_id_idx ON kg_nodes(entity_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kg_nodes_gin ON kg_nodes USING GIN(properties jsonb_path_ops);")

            # ── Edges table ──────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kg_edges (
                    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    source_id   UUID NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
                    target_id   UUID NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
                    edge_type   VARCHAR(20) NOT NULL CHECK (
                        edge_type IN ('defines','implements','covers','verifies',
                                      'depends_on','contains','relates_to','affects')
                    ),
                    properties  JSONB NOT NULL DEFAULT '{}',
                    verified_at TIMESTAMPTZ,
                    build_id    VARCHAR(64),
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (source_id, target_id, edge_type)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_source ON kg_edges(source_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_target ON kg_edges(target_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_type ON kg_edges(edge_type);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_build ON kg_edges(build_id);")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_kg_edges_source_type
                ON kg_edges(source_id, edge_type);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_kg_edges_target_type
                ON kg_edges(target_id, edge_type);
            """)

            # ── Snapshots table ──────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kg_snapshots (
                    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    build_id    VARCHAR(64) NOT NULL UNIQUE,
                    built_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    node_count  INT NOT NULL,
                    edge_count  INT NOT NULL,
                    meta        JSONB NOT NULL DEFAULT '{}'
                );
            """)

            # Track schema version
            cur.execute("""
                INSERT INTO kg_meta (key, value) VALUES ('kg_schema_version', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (str(_SCHEMA_VERSION),))

        self.conn.commit()
        log.info("Knowledge Graph PostgreSQL schema v%s ready", _SCHEMA_VERSION)

    # ------------------------------------------------------------------
    # Node CRUD
    # ------------------------------------------------------------------

    def upsert_node(self, node: NodePG) -> str:
        """Insert or update a node. Returns the UUID string."""
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kg_nodes (entity_type, entity_id, label, properties, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (entity_type, entity_id) DO UPDATE SET
                    label       = EXCLUDED.label,
                    properties  = EXCLUDED.properties,
                    is_active   = EXCLUDED.is_active,
                    updated_at  = EXCLUDED.updated_at
                RETURNING id
            """, (
                node.entity_type,
                node.entity_id,
                node.label,
                json.dumps(node.properties),
                node.is_active,
                now,
                now,
            ))
            row = cur.fetchone()
            return str(row[0])

    def get_node(self, entity_type: str, entity_id: str) -> Optional[NodePG]:
        """Get a node by type+entity_id."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM kg_nodes WHERE entity_type=%s AND entity_id=%s",
                (entity_type, entity_id)
            )
            row = cur.fetchone()
            return self._row_to_node(row) if row else None

    def get_node_by_id(self, node_id: str) -> Optional[NodePG]:
        """Get a node by UUID string."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM kg_nodes WHERE id=%s", (node_id,))
            row = cur.fetchone()
            return self._row_to_node(row) if row else None

    def list_nodes(self, entity_type: Optional[str] = None,
                   active_only: bool = True) -> list[NodePG]:
        """List nodes, optionally filtered by type."""
        parts = ["SELECT * FROM kg_nodes"]
        params = []
        conds = []
        if entity_type:
            conds.append("entity_type=%s")
            params.append(entity_type)
        if active_only:
            conds.append("is_active=TRUE")
        if conds:
            parts.append("WHERE " + " AND ".join(conds))
        parts.append("ORDER BY entity_type, entity_id")
        with self.conn.cursor() as cur:
            cur.execute(" ".join(parts), params)
            return [self._row_to_node(r) for r in cur.fetchall()]

    def soft_delete_node(self, entity_type: str, entity_id: str) -> bool:
        """Soft-delete a node. Returns True if affected."""
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE kg_nodes SET is_active=FALSE, updated_at=NOW() "
                "WHERE entity_type=%s AND entity_id=%s AND is_active=TRUE",
                (entity_type, entity_id)
            )
            affected = cur.rowcount
        self.conn.commit()
        return affected > 0

    # ------------------------------------------------------------------
    # Edge CRUD
    # ------------------------------------------------------------------

    def upsert_edge(self, edge: EdgePG) -> str:
        """Insert or update an edge. Returns the UUID string."""
        now = datetime.now().isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kg_edges (source_id, target_id, edge_type, properties, verified_at, build_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                ON CONFLICT (source_id, target_id, edge_type) DO UPDATE SET
                    properties  = EXCLUDED.properties,
                    verified_at = EXCLUDED.verified_at,
                    build_id    = EXCLUDED.build_id,
                    updated_at  = EXCLUDED.updated_at
                RETURNING id
            """, (
                edge.source_id,
                edge.target_id,
                edge.edge_type,
                json.dumps(edge.properties),
                edge.verified_at,
                edge.build_id,
                now,
                now,
            ))
            return str(cur.fetchone()[0])

    def get_edge(self, source_id: str, target_id: str, edge_type: str) -> Optional[EdgePG]:
        """Get an edge by its source, target, and type."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM kg_edges WHERE source_id=%s AND target_id=%s AND edge_type=%s",
                (source_id, target_id, edge_type)
            )
            row = cur.fetchone()
            return self._row_to_edge(row) if row else None

    def list_edges(self, edge_type: Optional[str] = None) -> list[EdgePG]:
        """List all edges, optionally filtered by type."""
        if edge_type:
            with self.conn.cursor() as cur:
                cur.execute("SELECT * FROM kg_edges WHERE edge_type=%s ORDER BY id", (edge_type,))
                return [self._row_to_edge(r) for r in cur.fetchall()]
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM kg_edges ORDER BY id")
            return [self._row_to_edge(r) for r in cur.fetchall()]

    def delete_edge(self, source_id: str, target_id: str, edge_type: str) -> bool:
        """Hard-delete an edge. Returns True if affected."""
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM kg_edges WHERE source_id=%s AND target_id=%s AND edge_type=%s",
                (source_id, target_id, edge_type)
            )
            affected = cur.rowcount
        self.conn.commit()
        return affected > 0

    # ------------------------------------------------------------------
    # RECURSIVE CTE — Graph Traversal
    # ------------------------------------------------------------------

    def trace_downstream(self, start_node_id: str, max_depth: int = 5,
                         edge_types: Optional[set[str]] = None) -> tuple[list[NodePG], list[EdgePG]]:
        """PostgreSQL RECURSIVE CTE: downstream trace from a node.

        Uses WITH RECURSIVE for server-side graph traversal —
        dramatically more efficient than Python BFS for multi-hop queries.
        """
        type_filter = ""
        params: list = [start_node_id, max_depth]
        if edge_types:
            placeholders = ",".join("%s" for _ in edge_types)
            type_filter = f"AND e.edge_type IN ({placeholders})"
            params.extend(sorted(edge_types))

        with self.conn.cursor() as cur:
            cur.execute(f"""
                WITH RECURSIVE trace AS (
                    -- Base case: start node
                    SELECT
                        n.id, n.entity_type, n.entity_id, n.label,
                        n.properties, n.is_active, n.created_at, n.updated_at,
                        NULL::uuid AS edge_id,
                        NULL::uuid AS edge_source_id,
                        NULL::uuid AS edge_target_id,
                        NULL::varchar AS edge_type,
                        NULL::jsonb AS edge_properties,
                        NULL::timestamptz AS edge_verified_at,
                        NULL::varchar AS edge_build_id,
                        0 AS depth
                    FROM kg_nodes n
                    WHERE n.id = %s

                    UNION ALL

                    -- Recursive: follow outgoing edges
                    SELECT
                        n.id, n.entity_type, n.entity_id, n.label,
                        n.properties, n.is_active, n.created_at, n.updated_at,
                        e.id, e.source_id, e.target_id, e.edge_type,
                        e.properties, e.verified_at, e.build_id,
                        t.depth + 1
                    FROM trace t
                    JOIN kg_edges e ON e.source_id = t.id
                    JOIN kg_nodes n ON n.id = e.target_id
                    WHERE t.depth < %s
                    {type_filter}
                )
                SELECT * FROM trace
                ORDER BY depth, entity_type
            """, params)

            node_map: dict[str, NodePG] = {}
            edges: list[EdgePG] = []

            for row in cur.fetchall():
                if row[8] is None:  # no edge_id means it's a root/base node
                    nid = str(row[0])
                    if nid not in node_map:
                        node_map[nid] = NodePG(
                            id=nid,
                            entity_type=row[1],
                            entity_id=row[2],
                            label=row[3],
                            properties=row[4] if isinstance(row[4], dict) else (row[4] or {}),
                            is_active=row[5],
                            created_at=row[6].isoformat() if row[6] else None,
                            updated_at=row[7].isoformat() if row[7] else None,
                        )
                else:
                    src_id = str(row[9])
                    tgt_id = str(row[10])
                    eid = str(row[8])
                    # Add the target node too
                    nid = str(row[0])
                    if nid not in node_map:
                        node_map[nid] = NodePG(
                            id=nid,
                            entity_type=row[1],
                            entity_id=row[2],
                            label=row[3],
                            properties=row[4] if isinstance(row[4], dict) else (row[4] or {}),
                            is_active=row[5],
                            created_at=row[6].isoformat() if row[6] else None,
                            updated_at=row[7].isoformat() if row[7] else None,
                        )
                    edges.append(EdgePG(
                        id=eid,
                        source_id=src_id,
                        target_id=tgt_id,
                        edge_type=row[11],
                        properties=row[12] if isinstance(row[12], dict) else (row[12] or {}),
                        verified_at=row[13].isoformat() if row[13] else None,
                        build_id=row[14],
                        created_at=row[6].isoformat() if row[6] else None,
                        updated_at=row[7].isoformat() if row[7] else None,
                    ))

            return list(node_map.values()), edges

    def trace_upstream(self, start_node_id: str, max_depth: int = 5,
                       edge_types: Optional[set[str]] = None) -> tuple[list[NodePG], list[EdgePG]]:
        """PostgreSQL RECURSIVE CTE: upstream trace from a node."""
        type_filter = ""
        params: list = [start_node_id, max_depth]
        if edge_types:
            placeholders = ",".join("%s" for _ in edge_types)
            type_filter = f"AND e.edge_type IN ({placeholders})"
            params.extend(sorted(edge_types))

        with self.conn.cursor() as cur:
            cur.execute(f"""
                WITH RECURSIVE trace AS (
                    SELECT
                        n.id, n.entity_type, n.entity_id, n.label,
                        n.properties, n.is_active, n.created_at, n.updated_at,
                        NULL::uuid AS edge_id,
                        NULL::uuid AS edge_source_id,
                        NULL::uuid AS edge_target_id,
                        NULL::varchar AS edge_type,
                        NULL::jsonb AS edge_properties,
                        NULL::timestamptz AS edge_verified_at,
                        NULL::varchar AS edge_build_id,
                        0 AS depth
                    FROM kg_nodes n
                    WHERE n.id = %s

                    UNION ALL

                    SELECT
                        n.id, n.entity_type, n.entity_id, n.label,
                        n.properties, n.is_active, n.created_at, n.updated_at,
                        e.id, e.source_id, e.target_id, e.edge_type,
                        e.properties, e.verified_at, e.build_id,
                        t.depth + 1
                    FROM trace t
                    JOIN kg_edges e ON e.target_id = t.id
                    JOIN kg_nodes n ON n.id = e.source_id
                    WHERE t.depth < %s
                    {type_filter}
                )
                SELECT * FROM trace
                ORDER BY depth, entity_type
            """, params)

            node_map: dict[str, NodePG] = {}
            edges: list[EdgePG] = []

            for row in cur.fetchall():
                nid = str(row[0])
                node_map.setdefault(nid, NodePG(
                    id=nid,
                    entity_type=row[1],
                    entity_id=row[2],
                    label=row[3],
                    properties=row[4] if isinstance(row[4], dict) else (row[4] or {}),
                    is_active=row[5],
                    created_at=row[6].isoformat() if row[6] else None,
                    updated_at=row[7].isoformat() if row[7] else None,
                ))
                if row[8] is not None:  # has edge
                    edges.append(EdgePG(
                        id=str(row[8]),
                        source_id=str(row[9]),
                        target_id=str(row[10]),
                        edge_type=row[11],
                        properties=row[12] if isinstance(row[12], dict) else (row[12] or {}),
                        verified_at=row[13].isoformat() if row[13] else None,
                        build_id=row[14],
                        created_at=row[6].isoformat() if row[6] else None,
                        updated_at=row[7].isoformat() if row[7] else None,
                    ))

            return list(node_map.values()), edges

    # ------------------------------------------------------------------
    # Snapshot CRUD
    # ------------------------------------------------------------------

    def create_snapshot(self, build_id: str, meta: Optional[dict] = None) -> SnapshotPG:
        """Create a snapshot of the current graph state."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM kg_nodes WHERE is_active=TRUE")
            node_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM kg_edges")
            edge_count = cur.fetchone()[0]

        meta_json = json.dumps(meta or {})
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kg_snapshots (build_id, built_at, node_count, edge_count, meta)
                VALUES (%s, NOW(), %s, %s, %s::jsonb)
                RETURNING id, built_at
            """, (build_id, node_count, edge_count, meta_json))
            row = cur.fetchone()
            return SnapshotPG(
                id=str(row[0]),
                build_id=build_id,
                built_at=row[1].isoformat() if row[1] else None,
                node_count=node_count,
                edge_count=edge_count,
                meta=meta or {},
            )

    def get_snapshot(self, build_id: str) -> Optional[SnapshotPG]:
        """Get a snapshot by build_id."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM kg_snapshots WHERE build_id=%s", (build_id,))
            row = cur.fetchone()
            if not row:
                return None
            return SnapshotPG(
                id=str(row[0]),
                build_id=row[1],
                built_at=row[2].isoformat() if row[2] else None,
                node_count=row[3],
                edge_count=row[4],
                meta=row[5] if isinstance(row[5], dict) else {},
            )

    def list_snapshots(self, limit: int = 20) -> list[SnapshotPG]:
        """List recent snapshots."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM kg_snapshots ORDER BY built_at DESC LIMIT %s", (limit,))
            return [
                SnapshotPG(
                    id=str(r[0]),
                    build_id=r[1],
                    built_at=r[2].isoformat() if r[2] else None,
                    node_count=r[3],
                    edge_count=r[4],
                    meta=r[5] if isinstance(r[5], dict) else {},
                )
                for r in cur.fetchall()
            ]

    # ------------------------------------------------------------------
    # Graph Statistics (SQL-powered)
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return overall graph statistics via SQL aggregation."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT entity_type, COUNT(*) AS c
                FROM kg_nodes WHERE is_active=TRUE
                GROUP BY entity_type
                ORDER BY entity_type
            """)
            node_counts = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute("""
                SELECT edge_type, COUNT(*) AS c
                FROM kg_edges GROUP BY edge_type
                ORDER BY edge_type
            """)
            edge_counts = {r[0]: r[1] for r in cur.fetchall()}

            return {
                "total_nodes": sum(node_counts.values()),
                "total_edges": sum(edge_counts.values()),
                "nodes_by_type": node_counts,
                "edges_by_type": edge_counts,
            }

    def get_uncovered_requirements(self) -> list[NodePG]:
        """SQL: requirements with no outgoing 'covers' edges.

        P0-4c: Excludes requirements marked as testable=False (管理需求).
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT n.* FROM kg_nodes n
                WHERE n.entity_type='requirement'
                  AND n.is_active=TRUE
                  AND n.id NOT IN (
                      SELECT DISTINCT e.source_id FROM kg_edges e
                      WHERE e.edge_type='covers'
                  )
                  -- P0-4c: exclude management/non-testable requirements
                  AND (n.properties->>'testable' IS NULL
                       OR n.properties->>'testable' = 'true'
                       OR n.properties->>'testable' = 'True')
                ORDER BY n.entity_id
            """)
            return [self._row_to_node(r) for r in cur.fetchall()]

    def get_orphan_code_files(self) -> list[NodePG]:
        """SQL: code files with no edges at all."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT n.* FROM kg_nodes n
                WHERE n.entity_type='code_file'
                  AND n.is_active=TRUE
                  AND n.id NOT IN (
                      SELECT DISTINCT e.source_id FROM kg_edges e
                      UNION
                      SELECT DISTINCT e.target_id FROM kg_edges e
                  )
                ORDER BY n.entity_id
            """)
            return [self._row_to_node(r) for r in cur.fetchall()]

    def get_top_fan_out(self, limit: int = 10) -> list[tuple[NodePG, int]]:
        """SQL: nodes with the most outgoing edges."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT n.*, COUNT(e.id) AS edge_count
                FROM kg_nodes n
                JOIN kg_edges e ON e.source_id = n.id
                WHERE n.is_active=TRUE
                GROUP BY n.id
                ORDER BY edge_count DESC
                LIMIT %s
            """, (limit,))
            return [(self._row_to_node(r), r["edge_count"]) for r in cur.fetchall()]

    def get_top_fan_in(self, limit: int = 10) -> list[tuple[NodePG, int]]:
        """SQL: nodes with the most incoming edges."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT n.*, COUNT(e.id) AS edge_count
                FROM kg_nodes n
                JOIN kg_edges e ON e.target_id = n.id
                WHERE n.is_active=TRUE
                GROUP BY n.id
                ORDER BY edge_count DESC
                LIMIT %s
            """, (limit,))
            results = []
            for r in cur.fetchall():
                node = self._row_to_node(r)
                edge_count = r["edge_count"] if hasattr(r, "edge_count") else r[-1]
                results.append((node, edge_count))
            return results

    # ------------------------------------------------------------------
    # Snapshot Diff (PostgreSQL-specific)
    # ------------------------------------------------------------------

    def snapshot_diff(self, build_id_a: str, build_id_b: str) -> dict:
        """Compare two graph snapshots — node/edge additions and removals.

        Uses PostgreSQL EXCEPT / INTERSECT set operations.
        """
        with self.conn.cursor() as cur:
            # Nodes
            cur.execute("""
                SELECT entity_type, entity_id, label FROM kg_nodes n
                WHERE EXISTS (SELECT 1 FROM kg_snapshots s WHERE s.build_id=%s AND s.built_at >= n.created_at)
                EXCEPT
                SELECT entity_type, entity_id, label FROM kg_nodes n
                WHERE EXISTS (SELECT 1 FROM kg_snapshots s WHERE s.build_id=%s AND s.built_at >= n.created_at)
            """, (build_id_b, build_id_a))
            added_nodes = [{"entity_type": r[0], "entity_id": r[1], "label": r[2]} for r in cur.fetchall()]

            cur.execute("""
                SELECT entity_type, entity_id, label FROM kg_nodes n
                WHERE EXISTS (SELECT 1 FROM kg_snapshots s WHERE s.build_id=%s AND s.built_at >= n.created_at)
                EXCEPT
                SELECT entity_type, entity_id, label FROM kg_nodes n
                WHERE EXISTS (SELECT 1 FROM kg_snapshots s WHERE s.build_id=%s AND s.built_at >= n.created_at)
            """, (build_id_a, build_id_b))
            removed_nodes = [{"entity_type": r[0], "entity_id": r[1], "label": r[2]} for r in cur.fetchall()]

        # Use snapshots' own counts for summary
        snap_a = self.get_snapshot(build_id_a)
        snap_b = self.get_snapshot(build_id_b)

        return {
            "build_a": build_id_a,
            "build_b": build_id_b,
            "node_count_a": snap_a.node_count if snap_a else None,
            "node_count_b": snap_b.node_count if snap_b else None,
            "added_nodes": added_nodes,
            "removed_nodes": removed_nodes,
            "summary": (
                f"Nodes: {len(added_nodes)} added, {len(removed_nodes)} removed; "
                f"Edges: diff inferred from snapshot counts"
            ),
        }

    # ------------------------------------------------------------------
    # Impact Analysis (SQL-native)
    # ------------------------------------------------------------------

    def impact_analysis(self, changed_files: list[str]) -> dict:
        """Analyze impact of changed files using PostgreSQL CTE.

        Returns affected requirements and test functions.
        This is more efficient than the Python-based version in queries.py.
        """
        if not changed_files:
            return {"affected_reqs": [], "affected_tests": [], "impact_summary": "No files changed"}

        # Build file nodes query
        placeholders = ",".join("%s" for _ in changed_files)
        params = changed_files + changed_files  # for code_file and test_file

        with self.conn.cursor() as cur:
            # Direct requirements: files that implements/covers a requirement
            cur.execute(f"""
                SELECT DISTINCT
                    n.entity_id AS req_id,
                    n.label AS req_label,
                    'direct' AS confidence
                FROM kg_nodes fn
                JOIN kg_edges e ON e.source_id = fn.id
                JOIN kg_nodes n ON n.id = e.target_id
                WHERE fn.entity_type IN ('code_file', 'test_file')
                  AND fn.entity_id IN ({placeholders})
                  AND e.edge_type IN ('implements', 'covers')
                  AND n.entity_type = 'requirement'
                  AND n.is_active = TRUE
                ORDER BY n.entity_id
            """, params[:len(changed_files)])
            direct_reqs = [{"req_id": r[0], "label": r[1], "confidence": r[2]} for r in cur.fetchall()]

            # Indirect requirements: through dependency chain (1-hop)
            cur.execute(f"""
                SELECT DISTINCT
                    n.entity_id AS req_id,
                    n.label AS req_label,
                    'indirect' AS confidence
                FROM kg_nodes fn
                JOIN kg_edges e1 ON e1.source_id = fn.id
                JOIN kg_nodes dep ON dep.id = e1.target_id
                JOIN kg_edges e2 ON e2.source_id = dep.id
                JOIN kg_nodes n ON n.id = e2.target_id
                WHERE fn.entity_type IN ('code_file', 'test_file')
                  AND fn.entity_id IN ({placeholders})
                  AND e1.edge_type = 'depends_on'
                  AND e2.edge_type IN ('implements', 'covers')
                  AND n.entity_type = 'requirement'
                  AND n.is_active = TRUE
                ORDER BY n.entity_id
            """, params[:len(changed_files)])
            indirect_reqs = [{"req_id": r[0], "label": r[1], "confidence": r[2]} for r in cur.fetchall()]

            # Affected tests: find test functions that cover the affected requirements
            req_ids = [r["req_id"] for r in direct_reqs + indirect_reqs]
            affected_tests = []
            if req_ids:
                req_placeholders = ",".join("%s" for _ in req_ids)
                cur.execute(f"""
                    SELECT
                        tf.entity_id AS test_func,
                        tf.label AS func_name,
                        n.entity_id AS req_id,
                        e.edge_type
                    FROM kg_nodes n
                    JOIN kg_edges e ON e.source_id = n.id
                    JOIN kg_nodes tf ON tf.id = e.target_id
                    WHERE n.entity_type = 'requirement'
                      AND n.entity_id IN ({req_placeholders})
                      AND e.edge_type = 'covers'
                      AND tf.entity_type IN ('test_function', 'test_file')
                    ORDER BY tf.entity_id
                """, req_ids)
                test_map: dict[str, list[str]] = {}
                for r in cur.fetchall():
                    func_key = r[0]
                    func_name = r[1]
                    if func_key not in test_map:
                        test_map[func_key] = []
                    test_map[func_key].append(func_name)
                affected_tests = [
                    {"file": k, "functions": v}
                    for k, v in sorted(test_map.items())
                ]

        all_reqs = direct_reqs + [r for r in indirect_reqs if r not in direct_reqs]
        total_tests = sum(len(t["functions"]) for t in affected_tests)

        return {
            "affected_reqs": all_reqs,
            "affected_tests": affected_tests,
            "impact_summary": (
                f"{len(all_reqs)} requirements ({len(direct_reqs)} direct, "
                f"{len(indirect_reqs)} indirect), "
                f"{total_tests} test functions affected"
            ),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _row_to_node(self, row) -> NodePG:
        """Convert a psycopg2 tuple row to NodePG."""
        return NodePG(
            id=str(row[0]),
            entity_type=row[1],
            entity_id=row[2],
            label=row[3],
            properties=row[4] if isinstance(row[4], dict) else (row[4] or {}),
            is_active=row[5],
            created_at=row[6].isoformat() if row[6] else None,
            updated_at=row[7].isoformat() if row[7] else None,
        )

    def _row_to_edge(self, row) -> EdgePG:
        """Convert a psycopg2 tuple row to EdgePG."""
        return EdgePG(
            id=str(row[0]),
            source_id=str(row[1]),
            target_id=str(row[2]),
            edge_type=row[3],
            properties=row[4] if isinstance(row[4], dict) else (row[4] or {}),
            verified_at=row[5].isoformat() if row[5] else None,
            build_id=row[6],
            created_at=row[7].isoformat() if row[7] else None,
            updated_at=row[8].isoformat() if row[8] else None,
        )
