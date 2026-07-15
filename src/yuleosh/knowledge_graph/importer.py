#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Importer — bootstrap from existing traceability data.

Sources:
  1. docs/requirement-traceability-matrix.md — fine-grained SHALL → test_function mapping
  2. reports/req-test-mapping.json — coarse req_id → test_file mapping
  3. Code/tests directory scan — creates CodeFile, CodeFunction, TestFile nodes

Import is idempotent: repeated runs produce identical graphs when source data
is unchanged.
"""

import copy
import gc
import json
import logging
import os
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.models import Node, Edge
from yuleosh.knowledge_graph.code_scanner import scan_directory, scan_single_file
from yuleosh.knowledge_graph.coverage_importer import import_coverage_from_default

log = logging.getLogger("yuleosh.knowledge_graph.importer")

# SHALL ID patterns
_SHALL_ID_RE = re.compile(r"([A-Z]+-\d+(?:\.\d+)*(?:-\d+)?)")


def import_from_req_test_json(store: KGStore, json_path: str) -> dict:
    """Import traceability data from req-test-mapping.json.

    Creates Requirement nodes (at the req_id granularity) and TestFile nodes,
    linked by 'covers' edges.

    Returns summary dict with counts.
    """
    json_path = Path(json_path)
    if not json_path.exists():
        log.warning("req-test-mapping.json not found at %s", json_path)
        return {"requirements": 0, "test_files": 0, "edges": 0}

    data = json.loads(json_path.read_text(encoding="utf-8"))
    mappings = data.get("mappings", data)  # tolerate both wrapped and flat

    req_count = 0
    tf_count = 0
    edge_count = 0

    for req_id, test_files in mappings.items():
        if not isinstance(test_files, list):
            continue

        # Create/update Requirement node (even when test_files is empty)
        # P0-4c: empty test_files → mark as testable=False (管理需求)
        is_testable = len(test_files) > 0
        req_node = Node(
            entity_type="requirement",
            entity_id=req_id,
            label=req_id,
            properties={
                "source": "req-test-mapping.json",
                "test_count": len(test_files),
                "testable": is_testable,
            },
        )
        req_nid = store.upsert_node(req_node)
        req_count += 1

        for tf_path in test_files:
            if not isinstance(tf_path, str):
                continue
            # Clean test file path
            tf_path_clean = tf_path.replace("\\", "/").lstrip("/")

            # Create/update TestFile node
            tf_node = Node(
                entity_type="test_file",
                entity_id=tf_path_clean,
                label=tf_path_clean,
                properties={"source": "req-test-mapping.json"},
            )
            tf_nid = store.upsert_node(tf_node)
            tf_count += 1

            # Create covers edge
            # Confidence = 1.0 (directly from RTM mapping)
            store.upsert_edge(Edge(
                source_id=req_nid,
                target_id=tf_nid,
                edge_type="covers",
                properties={
                    "source": "req-test-mapping.json",
                    "confidence": 1.0,
                },
            ))
            edge_count += 1

    log.info("Imported %s reqs, %s test files, %s edges from req-test-mapping.json",
             req_count, tf_count, edge_count)
    return {"requirements": req_count, "test_files": tf_count, "edges": edge_count}


def _parse_rtm_table(md_text: str) -> list[dict]:
    """Parse requirement-traceability-matrix.md table rows.

    Expects the format:
      | SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |

    Returns list of dicts with keys: shall_id, spec_source, test_file, test_function, status

    P0-4d: Empty text returns []. Missing fields logged, not crashed.
    """
    rows = []
    if not md_text or not md_text.strip():
        return rows

    lines = md_text.split("\n")
    in_table = False
    headers = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # P0-4d: Skip blank lines and whitespace-only lines without exiting table mode
        if not stripped:
            continue
        if not stripped.startswith("|"):
            if in_table:
                in_table = False
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]

        # Filter out empty cells at the end (formatting artifact)
        while cells and not cells[-1]:
            cells.pop()

        # Detect header row
        if all(c in ("", "-", "---", ":---", ":---:") for c in cells):
            continue

        # Detect table header
        # Fixed P0-4d: use startswith to avoid matching "ID" as substring of data cells like "RS-VALID-01"
        header_match = (
            cells[0].upper().startswith("SHALL ID")
            or cells[0].upper().startswith("ID")
        )
        if header_match and len(cells) >= 4:
            headers = cells
            in_table = True
            continue

        if not in_table:
            # P0-4d: Check if this looks like a table row that was missed
            if len(cells) >= 2 and any(c for c in cells if _SHALL_ID_RE.match(c)):
                log.debug("P0-4d: Potential row outside table block at line %d: %s", i, stripped[:80])
            continue

        # Skip separator rows
        if all(not c or c in ("", "-", "---", ":---", ":---:") or "---" in c for c in cells):
            continue

        if len(cells) < 4:
            log.warning("P0-4d: Skipping row at line %d (only %d cols): %s", i, len(cells), stripped[:80])
            continue

        shall_id = cells[0].strip()
        if not shall_id or shall_id.startswith("---"):
            log.warning("P0-4d: Skipping row at line %d (bad SHALL ID): %s", i, shall_id[:30])
            continue

        # Validate it looks like a SHALL ID
        if not _SHALL_ID_RE.match(shall_id):
            # P0-4d: More permissive: accept IDs starting with letters + containing digits
            if len(shall_id) >= 3 and shall_id[0].isalpha() and any(c.isdigit() for c in shall_id):
                log.debug("P0-4d: Accepted non-standard SHALL ID at line %d: %s", i, shall_id)
            else:
                log.warning("P0-4d: Skipping row at line %d (bad format): %s", i, shall_id[:40])
                continue

        rows.append({
            "shall_id": shall_id,
            "spec_source": cells[1].strip() if len(cells) > 1 else "",
            "test_file": cells[2].strip().strip("`") if len(cells) > 2 else "",
            "test_function": cells[3].strip().strip("`") if len(cells) > 3 else "",
            "status": cells[4].strip() if len(cells) > 4 else "",
        })

    return rows


def _parse_shall_id(raw_id: str) -> tuple[str, str]:
    """Parse a SHALL ID into (parent_id, sub_id).

    E.g., RS-001-01 → (RS-001, 01), RS-001 → (RS-001, "")
    """
    parts = raw_id.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) <= 3:
        return parts[0], parts[1]
    return raw_id, ""


def import_from_rtm_md(store: KGStore, md_path: str) -> dict:
    """Import traceability from requirement-traceability-matrix.md.

    Creates:
      - Requirement nodes for each SHALL ID
      - TestFile nodes for each test file
      - TestFunction nodes for each test function
      - 'covers' edges: Requirement → TestFile and Requirement → TestFunction
      - 'contains' edges: TestFile → TestFunction

    Returns summary dict with counts.
    """
    md_path = Path(md_path)
    if not md_path.exists():
        log.warning("RTM not found at %s", md_path)
        return {"requirements": 0, "test_files": 0, "test_functions": 0, "edges": 0}

    text = md_path.read_text(encoding="utf-8")
    table_rows = _parse_rtm_table(text)

    req_ids = set()
    tf_ids = set()
    tfn_ids = set()
    edge_count = 0

    for row in table_rows:
        shall_id = row["shall_id"]
        test_file = row["test_file"]
        test_function = row["test_function"]

        if not shall_id:
            continue

        # P0-4c: Determine if this requirement is testable.
        # Empty/TBD/- test_file → not testable (管理需求).
        # Still create the requirement node so it's tracked.
        has_test_file = bool(test_file and test_file.strip())
        is_testable = has_test_file and test_file.strip() not in ("TBD", "-")

        # Create Requirement node (always, even with testable=False)
        req_node = Node(
            entity_type="requirement",
            entity_id=shall_id,
            label=shall_id,
            properties={
                "source": "requirement-traceability-matrix.md",
                "spec_source": row["spec_source"],
                "testable": is_testable,
            },
        )
        req_nid = store.upsert_node(req_node)
        req_ids.add(shall_id)

        # P0-4c: Only create test file + edges when testable
        if not is_testable:
            continue

        # Create TestFile node
        tf_path_clean = test_file.replace("\\", "/")
        tf_node = Node(
            entity_type="test_file",
            entity_id=tf_path_clean,
            label=tf_path_clean,
            properties={"source": "requirement-traceability-matrix.md"},
        )
        tf_nid = store.upsert_node(tf_node)
        tf_ids.add(tf_path_clean)

        # Create covers edge: Requirement → TestFile
        # Confidence = 1.0 (directly from RTM mapping)
        store.upsert_edge(Edge(
            source_id=req_nid,
            target_id=tf_nid,
            edge_type="covers",
            properties={
                "source": "requirement-traceability-matrix.md",
                "test_function": test_function,
                "status": row["status"],
                "confidence": 1.0,
            },
        ))
        edge_count += 1

        if test_function:
            # Create TestFunction node
            tfn_fqn = f"{tf_path_clean}::{test_function}"
            tfn_node = Node(
                entity_type="test_function",
                entity_id=tfn_fqn,
                label=test_function,
                properties={
                    "file_path": tf_path_clean,
                    "source": "requirement-traceability-matrix.md",
                },
            )
            tfn_nid = store.upsert_node(tfn_node)
            tfn_ids.add(tfn_fqn)

            # Create contains edge: TestFile → TestFunction
            store.upsert_edge(Edge(
                source_id=tf_nid,
                target_id=tfn_nid,
                edge_type="contains",
                properties={},
            ))
            edge_count += 1

            # Create covers edge: Requirement → TestFunction
            # Confidence = 1.0 (directly from RTM mapping)
            store.upsert_edge(Edge(
                source_id=req_nid,
                target_id=tfn_nid,
                edge_type="covers",
                properties={
                    "source": "requirement-traceability-matrix.md",
                    "test_function": test_function,
                    "status": row["status"],
                    "confidence": 1.0,
                },
            ))
            edge_count += 1

    log.info("Imported %s reqs, %s test files, %s test functions, %s edges from RTM",
             len(req_ids), len(tf_ids), len(tfn_ids), edge_count)
    return {
        "requirements": len(req_ids),
        "test_files": len(tf_ids),
        "test_functions": len(tfn_ids),
        "edges": edge_count,
    }


def scan_code_directory(store: KGStore, project_base: str) -> dict:
    """Scan source and test directories to create CodeFile and CodeFunction nodes.

    Scans both src/ and tests/ (or project_base/src/ and project_base/tests/).

    Creates:
      - CodeFile nodes for every .py file found in src/
      - TestFile nodes for every test_*.py file found
      - 'contains' edges linking files to extracted function names

    Returns summary dict.
    """
    project_base = Path(project_base)

    code_count = 0
    test_count = 0
    edge_count = 0

    # Determine which directories to scan
    scan_dirs = []
    for candidate in [project_base / "src", project_base]:
        if candidate.exists():
            scan_dirs.append(candidate)

    # Also try to find tests dir
    tests_dir = project_base / "tests"
    if tests_dir.exists():
        scan_dirs.append(tests_dir)

    if not scan_dirs:
        log.warning("No source/test directories found under: %s", project_base)
        return {"code_files": 0, "test_files": 0, "edges": 0}

    # Scan all .py files across all directories
    for scan_root in scan_dirs:
        for py_file in sorted(scan_root.rglob("*.py")):
            try:
                rel_path = str(py_file.relative_to(project_base))
            except ValueError:
                rel_path = str(py_file)
            rel_path = rel_path.replace("\\", "/")

            # Detect if test file
            if "test_" in py_file.name or py_file.name.startswith("test"):
                entity_type = "test_file"
                test_count += 1
            else:
                entity_type = "code_file"
                code_count += 1

        # Create node
        file_node = Node(
            entity_type=entity_type,
            entity_id=rel_path,
            label=rel_path,
            properties={
                "language": "python",
                "source": "code_scan",
            },
        )
        file_nid = store.upsert_node(file_node)

        # Extract function definitions (basic regex)
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            content = ""

        func_re = re.compile(r"^def (test_\w+|\w+)\s*\(", re.MULTILINE)
        for m in func_re.finditer(content):
            func_name = m.group(1)
            fqn = f"{rel_path}::{func_name}"
            func_node = Node(
                entity_type="code_function" if entity_type == "code_file" else "test_function",
                entity_id=fqn,
                label=func_name,
                properties={
                    "file_path": rel_path,
                    "source": "code_scan",
                },
            )
            func_nid = store.upsert_node(func_node)

            # Contains edge
            store.upsert_edge(Edge(
                source_id=file_nid,
                target_id=func_nid,
                edge_type="contains",
                properties={"function": func_name},
            ))
            edge_count += 1

    log.info("Scanned %s code files, %s test files, %s edges",
             code_count, test_count, edge_count)
    return {"code_files": code_count, "test_files": test_count, "edges": edge_count}


_LAYER_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Check specific prefixes FIRST so test_hil_e2e_* or test_sil_integration.py
    # get the correct (more specific) layer.
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
    import json
    annotated = 0
    skipped = 0

    # Streaming cursor: JOIN covers edges with target nodes — no full fetch
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

        # Skip if already annotated
        if edge_props.get("layer"):
            skipped += 1
            continue

        # Determine the file path from target node
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

        # Update edge properties with layer
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

        # Periodically yield to avoid building up too many Python objects
        if annotated % 5000 == 0:
            gc.collect()

    log.info("Layer annotation: %d covers edges annotated, %d already had layer",
             annotated, skipped)
    return {"annotated": annotated, "skipped": skipped}


def bootstrap(store: KGStore, project_dir: str, create_snapshot: bool = True) -> dict:
    """Full bootstrap: import all available traceability data.

    Order:
      1. Import from requirement-traceability-matrix.md (rich data)
      2. Import from req-test-mapping.json (additional coverage)
      3. AST-based code scan (replaces regex-based scan_code_directory)
      4. Coverage data import (creates verifies edges)
      5. Merge duplicate test_function nodes
      6. Annotate covers edges with ASPICE test layer (unit/integration/sil/hil)
      7. Build implements edges (P0-1)
      8. Create initial snapshot

    Returns combined summary.
    """
    project_path = Path(project_dir)

    rtm_path = project_path / "docs" / "requirement-traceability-matrix.md"
    json_path = project_path / "reports" / "req-test-mapping.json"

    result = {}

    # Step 1: RTM
    rtm_result = import_from_rtm_md(store, str(rtm_path))
    result["rtm"] = rtm_result
    # Memory release: RTM table rows parsed into memory
    del rtm_result
    gc.collect()

    # Step 2: JSON mapping (additional coverage)
    json_result = import_from_req_test_json(store, str(json_path))
    result["req_test_json"] = json_result
    del json_result
    gc.collect()

    # Step 3: AST-based code scan (P1-1, replaces old scan_code_directory)
    scan_result = scan_directory(store, str(project_path))
    result["code_scan"] = scan_result
    del scan_result
    gc.collect()

    # Step 4: Coverage import (P1-1)
    coverage_result = import_coverage_from_default(store, str(project_path))
    result["coverage"] = coverage_result
    del coverage_result
    gc.collect()

    # Step 5: Post-process — merge duplicate test_function nodes
    # Bridges the gap between RTM-imported test_function nodes (short entity_id like
    # "test_pipeline_run") and code-scanner test_function nodes (FQN entity_id like
    # "tests/test_pipeline_extended.py::test_pipeline_run").
    # After merge, verifies edges from coverage importer and covers edges from RTM
    # point to the same node, making the full chain work end-to-end.
    merge_result = _merge_test_functions(store)
    result["merge"] = merge_result

    # Step 6: Annotate covers edges with test layer (ASPICE P0)
    layer_result = _annotate_covers_layer(store)
    result["layer_annotation"] = layer_result
    del layer_result
    gc.collect()

    # Step 7: implements edges (P0-1)
    # Derive code_function ──implements──→ requirement from:
    #   requirement ──covers──→ test_file ──contains──→ test_function ──verifies──→ code_function
    impl_result = _build_implements_edges(store)
    result["implements"] = impl_result
    del impl_result
    gc.collect()

    # Step 7a: validates edges (P0-5)
    valid_result = _build_validates_edges(store)
    result["validates"] = valid_result
    del valid_result
    gc.collect()

    # Step 7b: Orphan code file fallback matching (P0-4b)
    fallback_result = _fallback_code_file_matching(store, project_path)
    result["fallback_matching"] = fallback_result
    del fallback_result
    gc.collect()

    # Step 7c: Orphan test file auto-covers (P0-4e)
    orphan_tf_result = _fix_orphan_test_files(store)
    result["orphan_test_files"] = orphan_tf_result
    del orphan_tf_result
    gc.collect()

    # Step 8: Snapshot
    if create_snapshot:
        snapshot = store.create_snapshot(
            build_id="bootstrap",
            meta={"source": "bootstrap", "project_dir": project_dir},
        )
        result["snapshot"] = {
            "build_id": snapshot.build_id,
            "node_count": snapshot.node_count,
            "edge_count": snapshot.edge_count,
        }

    # Summary (include all sources) — use result dict, not deleted local refs
    rtm = result.get("rtm", {})
    json_res = result.get("req_test_json", {})
    scan_res = result.get("code_scan", {})
    cov_res = result.get("coverage", {})
    impl_res = result.get("implements", {})
    valid_res_ = result.get("validates", {})
    fallback_res = result.get("fallback_matching", {})
    orphan_res = result.get("orphan_test_files", {})
    merge_res = result.get("merge", {})

    node_components = [
        rtm.get("requirements", 0),
        rtm.get("test_files", 0),
        rtm.get("test_functions", 0),
        scan_res.get("code_files", 0),
        scan_res.get("test_files", 0),
        scan_res.get("functions", 0),
        scan_res.get("classes", 0),
        scan_res.get("methods", 0),
    ]
    edge_components = [
        rtm.get("edges", 0),
        json_res.get("edges", 0),
        scan_res.get("edges", 0),
        cov_res.get("verifies_edges", 0),
        impl_res.get("edges", 0),
        valid_res_.get("edges", 0),
        fallback_res.get("edges", 0),
        orphan_res.get("edges", 0),
    ]
    total_nodes = sum(node_components)
    total_edges = sum(edge_components)

    result["summary"] = {
        "total_nodes": total_nodes,
        "total_edges": total_edges,
    }

    log.info("Bootstrap complete: %s total nodes, %s total edges" +
             " (coverage: %s verifies, merge: %s merged, implements: %s, validates: %s, fallback: %s, orphan_tf: %s)",
             total_nodes, total_edges, cov_res.get("verifies_edges", 0),
             merge_res.get("merged_nodes", 0), impl_res.get("edges", 0),
             valid_res_.get("edges", 0),
             fallback_res.get("edges", 0),
             orphan_res.get("edges", 0))
    return result


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

    This ensures the verifies (coverage) -> code_function -> covers (RTM)
    chain works end-to-end.

    Returns summary dict with counts.
    """
    # Get all active test_function nodes
    all_tfns = store.list_nodes(entity_type="test_function", active_only=False)
    active_tfns = [n for n in all_tfns if n.is_active]

    if len(active_tfns) <= 1:
        return {"merged_nodes": 0, "edges_redirected": 0, "groups_merged": 0}

    # Group by label
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

        # Pick canonical node: prefer RTM-sourced, else one with
        # shortest entity_id (likely short name from RTM)
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
            # === Move INCOMING edges ===
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

            # === Move OUTGOING edges ===
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

            # Mark duplicate as inactive (soft delete)
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


def _build_implements_edges(store: KGStore) -> dict:
    """从 covers + verifies 推导 implements 边。

    Chain:
      requirement ──covers──→ test_file ──contains──→ test_function ──verifies──→ code_function
      ⇒ code_function ──implements──→ requirement

    Also handles shorter chains:
      requirement ──covers──→ test_function ──verifies──→ code_function
      (when RTM has test_function-level covers edges)

    Idempotent: skips edges that already exist.

    Returns summary dict with counts.
    """
    edge_count = 0
    reqs_covered = set()
    code_fns_covered = set()

    # Get all covers edges
    covers_edges = store.list_edges(edge_type="covers")
    log.info("Building implements edges from %d covers edges", len(covers_edges))

    # Build lookup: node_id → Node for finding requirement nodes
    for edge in covers_edges:
        src_node = store.get_node_by_id(edge.source_id)
        tgt_node = store.get_node_by_id(edge.target_id)

        if src_node is None or tgt_node is None:
            continue
        if src_node.entity_type != "requirement":
            continue

        req_nid = src_node.id

        # ── Path A: requirement ──covers──→ test_file ──contains──→ test_function ──verifies──→ code_function
        if tgt_node.entity_type == "test_file":
            tf_nid = tgt_node.id
            # Get test functions contained in this test file
            tf_out_edges = store.get_outgoing_edges(tf_nid)
            for contains_edge, tfn_node in tf_out_edges:
                if contains_edge.edge_type != "contains":
                    continue
                if tfn_node.entity_type != "test_function":
                    continue

                # Get verifies edges from this test function
                tfn_out_edges = store.get_outgoing_edges(tfn_node.id)
                for verifies_edge, code_fn_node in tfn_out_edges:
                    if verifies_edge.edge_type != "verifies":
                        continue
                    if code_fn_node.entity_type != "code_function":
                        continue

                    # Create implements edge: code_function → requirement
                    # Path A confidence = 0.9 (deduced via test_file chain)
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

        # ── Path B: requirement ──covers──→ test_function ──verifies──→ code_function
        # Path B confidence = 0.8 (deduced via test_function direct)
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

        # ── Path C: requirement ──covers──→ code_file ──contains──→ code_function
        # (direct covers of code_file with intent mapping — less common)
        # Path C confidence = 0.7 (deduced via code_file direct)
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

    # 需要创建 validates 边的层级（非 unit）：
    # integration/sil/hil/system 对应 SWE.5 确认
    VALIDATES_LAYERS = {"integration", "hil", "sil", "system"}

    covers_edges = store.list_edges(edge_type="covers")
    log.info("Building validates edges from %d covers edges", len(covers_edges))

    for edge in covers_edges:
        layer = edge.properties.get("layer") or edge.layer
        if layer is None or layer not in VALIDATES_LAYERS:
            continue

        # 检查是否已有 validates 边
        existing = store.get_edge(edge.source_id, edge.target_id, "validates")
        if existing is not None:
            continue

        # 创建 validates 边（同方向）
        # Confidence = 1.0 (directly from known test layer)
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


def _fallback_code_file_matching(store: KGStore, project_base: Path) -> dict:
    """对孤立 code_file 节点进行启发式需求匹配（P0-4b）。

    对于没有任何边的 code_file 节点，尝试通过文件路径关键词
    启发式匹配需求。

    匹配规则：
      1. 从文件路径中提取模块名（如 knowledge_graph 从路径中匹配）
      2. 如果模块名匹配需求前缀（如 RS-xxx），创建 covers 边
      3. 只匹配已知需求的 entity_id

    Returns summary dict with counts.
    """
    edge_count = 0
    matched_files = 0

    # 获取所有孤立 code_file 节点
    orphan_nodes = store.get_orphan_code_files()
    if not orphan_nodes:
        log.info("No orphan code files to match (P0-4b)")
        return {"edges": 0, "matched_files": 0}

    # 获取所有需求
    all_reqs = store.list_nodes(entity_type="requirement")
    if not all_reqs:
        log.info("No requirements available for fallback matching (P0-4b)")
        return {"edges": 0, "matched_files": 0}

    # 构建需求关键词映射：路径关键词 → [requirement_nodes]
    # 从需求 ID 中提取关键词
    req_keywords: dict[str, list] = {}
    for req in all_reqs:
        eid = req.entity_id
        # 提取前缀，如 RS-001 from RS-001-01
        prefix = eid.rsplit("-", 1)[0] if eid.count("-") >= 2 and eid.rsplit("-", 1)[1].isdigit() else eid
        # 也存储整个 ID
        for key in (prefix, eid, eid.replace("-", "_")):
            if key not in req_keywords:
                req_keywords[key] = []
            req_keywords[key].append(req)

    # 构建已知模块名集合
    known_modules = set()
    for req in all_reqs:
        label = req.label or ""
        # 提取小写关键词
        for part in label.replace("-", "_").replace("/", "_").lower().split("_"):
            if len(part) >= 3:
                known_modules.add(part)

    # 对每个孤立 code_file 尝试匹配
    for node in orphan_nodes:
        if node.entity_type != "code_file":
            continue

        file_path = node.entity_id
        matched = False

        # 解析文件路径为关键词集合
        path_parts = set(file_path.lower().replace("\\", "/").split("/"))
        path_parts.update(file_path.lower().replace("\\", "/").replace("-", "_").replace(".", "_").split("_"))

        # 添加文件名和目录名
        from pathlib import Path as _Path
        p = _Path(file_path)
        path_parts.add(p.stem.lower())
        path_parts.add(p.parent.name.lower())

        # 尝试匹配需求
        matched_ids = set()
        for keyword, reqs in req_keywords.items():
            kw_lower = keyword.lower()
            if kw_lower in path_parts or kw_lower in file_path.lower():
                for req in reqs:
                    if req.id is not None:
                        matched_ids.add(req.id)

        # 创建 covers 边
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
    """Alias for _fallback_code_file_matching.

    P0-4b: Match orphan code_file nodes to requirements by filename keywords.
    Iterates all edge-less code_file nodes and matches them to requirements
    via path keywords.
    """
    return _fallback_code_file_matching(store, project_base)


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

    # 找到所有 test_file 节点
    all_test_files = store.list_nodes(entity_type="test_file")

    for tf_node in all_test_files:
        # 检查是否已有 incoming covers 边
        incoming = store.get_incoming_edges(tf_node.id)
        has_covers = any(e.edge_type == "covers" for e, _ in incoming)
        if has_covers:
            continue

        # 找到 test_file 中的 test_function
        outgoing = store.get_outgoing_edges(tf_node.id)
        tfn_ids = [t.id for e, t in outgoing if e.edge_type == "contains" and t.entity_type == "test_function"]

        # 对每个 test_function，找到它 verifies 的 code_function
        reqs_found = set()
        for tfn_id in tfn_ids:
            tfn_outgoing = store.get_outgoing_edges(tfn_id)
            for ve, cf_node in tfn_outgoing:
                if ve.edge_type == "verifies" and cf_node.entity_type == "code_function":
                    # 找到 code_function 的 implements 边
                    cf_outgoing = store.get_outgoing_edges(cf_node.id)
                    for ie, req_node in cf_outgoing:
                        if ie.edge_type == "implements" and req_node.entity_type == "requirement":
                            reqs_found.add(req_node.id)

        # 为每个找到的需求创建 covers 边
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


# ═══════════════════════════════════════════════════════════════════════
# Incremental Build — P0, for CI pipelines
# ═══════════════════════════════════════════════════════════════════════


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
        # Find code_file or test_file node
        for etype in ("code_file", "test_file"):
            node = store.get_node(etype, norm)
            if node is not None and node.is_active:
                checkpoint["nodes"].append(node.to_dict())
                checkpoint["affected_node_ids"].add(node.id)
                # Also capture contained functions
                outgoing = store.get_outgoing_edges(node.id)
                for _, target in outgoing:
                    tnode = store.get_node_by_id(target.id)
                    if tnode and tnode.is_active:
                        checkpoint["nodes"].append(tnode.to_dict())
                        checkpoint["affected_node_ids"].add(tnode.id)

    # Capture all edges to/from affected nodes
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

    # Convert set to list for JSON serialisability
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

    # Build a map: old_node_id → new_node_id
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

    # Restore edges, remapping IDs
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

            # Collect contained function nodes
            outgoing = store.get_outgoing_edges(node.id)
            for _, target in outgoing:
                affected_ids.add(target.id)

    # ── Delete edges (hard delete) ──
    for nid in affected_ids:
        for edge, _ in store.get_outgoing_edges(nid):
            if store.delete_edge(edge.source_id, edge.target_id, edge.edge_type):
                deleted_edges += 1
        for edge, _ in store.get_incoming_edges(nid):
            if store.delete_edge(edge.source_id, edge.target_id, edge.edge_type):
                deleted_edges += 1

    # ── Soft-delete nodes ──
    for nid in affected_ids:
        node = store.get_node_by_id(nid)
        if node and node.is_active:
            store.delete_node(node.entity_type, node.entity_id)
            deleted_nodes += 1

    log.debug("Deleted %d nodes and %d edges for changed files",
              deleted_nodes, deleted_edges)
    return {"deleted_nodes": deleted_nodes, "deleted_edges": deleted_edges}


def incremental_bootstrap(
    store: KGStore,
    project_dir: str,
    changed_files: Optional[list[str]] = None,
    create_snapshot: bool = True,
    build_id: Optional[str] = None,
    snapshot_meta: Optional[dict] = None,
) -> dict:
    """Incremental knowledge graph build from changed files.

    Behaviour by *changed_files*:
      - ``None`` → full ``bootstrap()`` (backward-compatible)
      - ``[]``   → update snapshot only; no re-import
      - list of paths → incremental: remove old nodes, re-scan, rebuild

    Steps for incremental:
      1. Save checkpoint (backup affected nodes + edges)
      2. Delete old nodes + edges for changed files
      3. Re-scan each changed file (AST-based)
      4. Re-run coverage import
      5. Re-implement merge, layer annotation
      6. Rebuild implements / validates / fallback / orphan edges (idempotent)
      7. Create new snapshot

    Args:
        store: KGStore instance
        project_dir: Project root directory
        changed_files: List of relative file paths, ``None`` for full, ``[]`` for snapshot-only
        create_snapshot: Whether to create a snapshot at the end
        build_id: Optional build identifier for the snapshot
        snapshot_meta: Optional extra metadata for the snapshot

    Returns:
        Rich summary dict with per-step counts

    Raises:
        RuntimeError: On incremental failure, after restoring the checkpoint
    """
    project_path = Path(project_dir)
    rtm_path = project_path / "docs" / "requirement-traceability-matrix.md"
    json_path = project_path / "reports" / "req-test-mapping.json"

    # ── changed_files=None → full bootstrap ──
    if changed_files is None:
        log.info("incremental_bootstrap: changed_files=None → full bootstrap")
        return bootstrap(store, project_dir, create_snapshot=create_snapshot)

    # ── changed_files=[] → snapshot only ──
    if not changed_files:
        log.info("incremental_bootstrap: changed_files=[] → snapshot only")
        stats = store.get_stats()
        if create_snapshot:
            bid = build_id or "incremental-snapshot-only"
            snap_meta = {"source": "incremental_snapshot_only", "project_dir": project_dir}
            if snapshot_meta:
                snap_meta.update(snapshot_meta)
            snapshot = store.create_snapshot(build_id=bid, meta=snap_meta)
        return {
            "mode": "snapshot_only",
            "stats": stats,
            "incremental": {"code_files": 0, "test_files": 0, "edges_added": 0},
        }

    # ── Incremental build ──
    log.info("Incremental bootstrap starting for %d files: %s",
             len(changed_files), changed_files)

    # Step 0: Save checkpoint for rollback safety
    checkpoint = _save_checkpoint(store, changed_files)

    try:
        # Step 1: Delete old nodes and edges for changed files
        delete_result = _delete_changed_file_nodes(store, changed_files)

        # Step 2: Re-scan each changed file
        scanned_code = 0
        scanned_test = 0
        total_funcs = 0
        total_classes = 0
        total_methods = 0
        total_edges_added = 0

        for cf in changed_files:
            norm = cf.replace("\\", "/")
            if norm.startswith("src/") and norm.endswith(".py"):
                result = scan_single_file(store, project_dir, norm)
                scanned_code += 1
                total_funcs += result.get("functions", 0)
                total_classes += result.get("classes", 0)
                total_methods += result.get("methods", 0)
                total_edges_added += result.get("edges", 0)
            elif norm.startswith("tests/") and norm.endswith(".py"):
                result = scan_single_file(store, project_dir, norm)
                scanned_test += 1
                total_funcs += result.get("functions", 0)
                total_classes += result.get("classes", 0)
                total_methods += result.get("methods", 0)
                total_edges_added += result.get("edges", 0)
            else:
                log.debug("Skipping non-scannable file: %s", norm)

        incremental_result = {
            "code_files": scanned_code,
            "test_files": scanned_test,
            "functions": total_funcs,
            "classes": total_classes,
            "methods": total_methods,
            "edges_added": total_edges_added,
            "changed_files": len(changed_files),
        }

        result = {
            "mode": "incremental",
            "incremental": incremental_result,
            "deleted": delete_result,
        }

        # Step 3: Re-run coverage import (idempotent)
        coverage_result = import_coverage_from_default(store, project_dir)
        result["coverage"] = coverage_result

        # Step 4: Merge duplicate test_function nodes
        merge_result = _merge_test_functions(store)
        result["merge"] = merge_result

        # Step 5: Annotate covers edges with test layer
        layer_result = _annotate_covers_layer(store)
        result["layer_annotation"] = layer_result

        # Step 6: Rebuild implements edges
        impl_result = _build_implements_edges(store)
        result["implements"] = impl_result

        # Step 7: Rebuild validates edges
        valid_result = _build_validates_edges(store)
        result["validates"] = valid_result

        # Step 8: Fallback code file matching
        fallback_result = _fallback_code_file_matching(store, project_path)
        result["fallback_matching"] = fallback_result

        # Step 9: Orphan test file auto-covers
        orphan_tf_result = _fix_orphan_test_files(store)
        result["orphan_test_files"] = orphan_tf_result

        # Step 10: Snapshot
        if create_snapshot:
            bid = build_id or "incremental"
            snap_meta = {"source": "incremental_bootstrap", "changed_files": changed_files}
            if snapshot_meta:
                snap_meta.update(snapshot_meta)
            snapshot = store.create_snapshot(build_id=bid, meta=snap_meta)
            result["snapshot"] = {
                "build_id": snapshot.build_id,
                "node_count": snapshot.node_count,
                "edge_count": snapshot.edge_count,
            }

        # Summary
        stats = store.get_stats()
        result["stats"] = stats
        result["summary"] = {
            "total_nodes": stats["total_nodes"],
            "total_edges": stats["total_edges"],
        }

        log.info(
            "Incremental bootstrap complete: %d changed files, "
            "scan: %d src/%d tests, deleted: %d nodes/%d edges",
            len(changed_files),
            scanned_code, scanned_test,
            delete_result.get("deleted_nodes", 0),
            delete_result.get("deleted_edges", 0),
        )
        return result

    except Exception as exc:
        log.error(
            "Incremental bootstrap FAILED: %s. Restoring checkpoint.",
            exc,
            exc_info=True,
        )
        # Rollback: restore checkpoint
        try:
            _restore_checkpoint(store, checkpoint)
        except Exception as restore_exc:
            log.error(
                "Checkpoint restore also FAILED: %s. Graph may be inconsistent.",
                restore_exc,
                exc_info=True,
            )
            raise RuntimeError(
                f"Incremental bootstrap failed and checkpoint restore also failed: "
                f"{exc} / {restore_exc}"
            ) from exc
        raise RuntimeError(
            f"Incremental bootstrap failed; checkpoint restored: {exc}"
        ) from exc
