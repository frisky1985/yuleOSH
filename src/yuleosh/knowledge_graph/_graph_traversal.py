# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Shared recursive-CTE builders for KG traversal (P2-6).

SQLite 与 PostgreSQL 两个 store 后端共用同一套遍历语义，仅在方言细节上
分叉（占位符 ``?`` / ``%s``、PG 显式类型 NULL 列）。业务规则（如
low_confidence_warning）仍留在 Python 查询层。
"""

from __future__ import annotations

from typing import Optional


def build_edge_type_filter(edge_types: Optional[set[str]],
                           placeholder: str) -> tuple[str, list[str]]:
    """Return ``(sql_clause, params)`` for an edge_type filter."""
    if not edge_types:
        return "", []
    ordered = sorted(edge_types)
    placeholders = ",".join(placeholder for _ in ordered)
    return f"AND e.edge_type IN ({placeholders})", ordered


def build_trace_sql(dialect: str, direction: str,
                    edge_types: Optional[set[str]] = None,
                    ) -> tuple[str, list[str]]:
    """Build traversal SQL for the given dialect/direction.

    Returns ``(sql, type_params)``. Caller passes ``[start_id, max_depth]``
    first, followed by *type_params*.

    SQLite: 紧凑 ids-only CTE，节点/边在 Python 侧批量取回。
    PostgreSQL: 原 typed CTE（列类型显式 NULL），行为保持不变。
    """
    if dialect not in ("sqlite", "pg"):
        raise ValueError(f"unknown dialect: {dialect}")
    if direction not in ("downstream", "upstream"):
        raise ValueError(f"unknown direction: {direction}")

    placeholder = "?" if dialect == "sqlite" else "%s"
    type_filter, type_params = build_edge_type_filter(edge_types, placeholder)

    if dialect == "pg":
        if direction == "downstream":
            join = ("JOIN kg_edges e ON e.source_id = t.id\n"
                    "                    JOIN kg_nodes n ON n.id = e.target_id")
        else:
            join = ("JOIN kg_edges e ON e.target_id = t.id\n"
                    "                    JOIN kg_nodes n ON n.id = e.source_id")
        sql = f"""
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
                    {join}
                    WHERE t.depth < %s
                    {type_filter}
                )
                SELECT * FROM trace
                ORDER BY depth, entity_type
            """
        return sql, type_params

    # SQLite: ids-only recursive CTE
    if direction == "downstream":
        join = ("JOIN kg_edges e ON e.source_id = t.node_id\n"
                "            JOIN kg_nodes n ON n.id = e.target_id")
    else:
        join = ("JOIN kg_edges e ON e.target_id = t.node_id\n"
                "            JOIN kg_nodes n ON n.id = e.source_id")
    sql = f"""
        WITH RECURSIVE trace(node_id, edge_id, depth) AS (
            SELECT {placeholder}, NULL, 0

            UNION

            SELECT n.id, e.id, t.depth + 1
            FROM trace t
            {join}
            WHERE t.depth < {placeholder}
            {type_filter}
        )
        SELECT node_id, edge_id, MIN(depth) AS depth
        FROM trace
        GROUP BY node_id, edge_id
        ORDER BY depth, node_id
    """
    return sql, type_params
