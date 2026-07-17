#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Bootstrap — full initialization from traceability data.

Sources:
  1. docs/requirement-traceability-matrix.md — fine-grained SHALL → test_function mapping
  2. reports/req-test-mapping.json — coarse req_id → test_file mapping
  3. Code/tests directory scan — creates CodeFile, CodeFunction, TestFile nodes

Import is idempotent: repeated runs produce identical graphs when source data
is unchanged.
"""

import gc
import json
import logging
import re
from pathlib import Path

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.models import Node, Edge
from yuleosh.knowledge_graph.code_scanner import scan_directory
from yuleosh.knowledge_graph.coverage_importer import import_coverage_from_default
from yuleosh.knowledge_graph.edge_builder import (
    _merge_test_functions,
    _annotate_covers_layer,
    _build_implements_edges,
    _build_validates_edges,
    _fallback_code_file_matching,
    _fix_orphan_test_files,
)

log = logging.getLogger("yuleosh.knowledge_graph.bootstrap")

# SHALL ID patterns
_SHALL_ID_RE = re.compile(r"([A-Z]+-\d+(?:\.\d+)*(?:-\d+)?)")


# ═══════════════════════════════════════════════════════════════════════
# RTM parsing
# ═══════════════════════════════════════════════════════════════════════


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
        if not stripped:
            continue
        if not stripped.startswith("|"):
            if in_table:
                in_table = False
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]

        while cells and not cells[-1]:
            cells.pop()

        if all(c in ("", "-", "---", ":---", ":---:") for c in cells):
            continue

        header_match = (
            cells[0].upper().startswith("SHALL ID")
            or cells[0].upper().startswith("ID")
        )
        if header_match and len(cells) >= 4:
            headers = cells
            in_table = True
            continue

        if not in_table:
            if len(cells) >= 2 and any(c for c in cells if _SHALL_ID_RE.match(c)):
                log.debug("P0-4d: Potential row outside table block at line %d: %s", i, stripped[:80])
            continue

        if all(not c or c in ("", "-", "---", ":---", ":---:") or "---" in c for c in cells):
            continue

        if len(cells) < 4:
            log.warning("P0-4d: Skipping row at line %d (only %d cols): %s", i, len(cells), stripped[:80])
            continue

        shall_id = cells[0].strip()
        if not shall_id or shall_id.startswith("---"):
            log.warning("P0-4d: Skipping row at line %d (bad SHALL ID): %s", i, shall_id[:30])
            continue

        if not _SHALL_ID_RE.match(shall_id):
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


# ═══════════════════════════════════════════════════════════════════════
# Importers
# ═══════════════════════════════════════════════════════════════════════


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
    mappings = data.get("mappings", data)

    req_count = 0
    tf_count = 0
    edge_count = 0

    for req_id, test_files in mappings.items():
        if not isinstance(test_files, list):
            continue

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
            tf_path_clean = tf_path.replace("\\", "/").lstrip("/")

            tf_node = Node(
                entity_type="test_file",
                entity_id=tf_path_clean,
                label=tf_path_clean,
                properties={"source": "req-test-mapping.json"},
            )
            tf_nid = store.upsert_node(tf_node)
            tf_count += 1

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

        has_test_file = bool(test_file and test_file.strip())
        is_testable = has_test_file and test_file.strip() not in ("TBD", "-")

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

        if not is_testable:
            continue

        tf_path_clean = test_file.replace("\\", "/")
        tf_node = Node(
            entity_type="test_file",
            entity_id=tf_path_clean,
            label=tf_path_clean,
            properties={"source": "requirement-traceability-matrix.md"},
        )
        tf_nid = store.upsert_node(tf_node)
        tf_ids.add(tf_path_clean)

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

            store.upsert_edge(Edge(
                source_id=tf_nid,
                target_id=tfn_nid,
                edge_type="contains",
                properties={},
            ))
            edge_count += 1

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

    scan_dirs = []
    for candidate in [project_base / "src", project_base]:
        if candidate.exists():
            scan_dirs.append(candidate)

    tests_dir = project_base / "tests"
    if tests_dir.exists():
        scan_dirs.append(tests_dir)

    if not scan_dirs:
        log.warning("No source/test directories found under: %s", project_base)
        return {"code_files": 0, "test_files": 0, "edges": 0}

    for scan_root in scan_dirs:
        for py_file in sorted(scan_root.rglob("*.py")):
            try:
                rel_path = str(py_file.relative_to(project_base))
            except ValueError:
                rel_path = str(py_file)
            rel_path = rel_path.replace("\\", "/")

            if "test_" in py_file.name or py_file.name.startswith("test"):
                entity_type = "test_file"
                test_count += 1
            else:
                entity_type = "code_file"
                code_count += 1

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


# ═══════════════════════════════════════════════════════════════════════
# Bootstrap
# ═══════════════════════════════════════════════════════════════════════


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
    merge_result = _merge_test_functions(store)
    result["merge"] = merge_result

    # Step 6: Annotate covers edges with test layer (ASPICE P0)
    layer_result = _annotate_covers_layer(store)
    result["layer_annotation"] = layer_result
    del layer_result
    gc.collect()

    # Step 7: implements edges (P0-1)
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
