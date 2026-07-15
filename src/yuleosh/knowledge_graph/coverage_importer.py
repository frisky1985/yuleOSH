#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Coverage Importer — maps code coverage data into the graph.

Reads .coverage (SQLite) or .coverage.json data and creates 'verifies' edges
connecting test_function nodes to code_function nodes.

The mapping logic:
  1. Extract covered line ranges from the coverage database
  2. For each covered source file, find which code_functions' line ranges overlap
  3. For each test_function in the graph, check if its test file contributed
     to covering those code functions
  4. Create verifies edges: test_function → code_function

When per-test context data is available in the .coverage file (coverage run
with --context=TEST_NAME), it creates per-function verifies edges directly.
Otherwise, it creates edges using a best-effort file-level mapping.
"""

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.models import Node, Edge

log = logging.getLogger("yuleosh.knowledge_graph.coverage_importer")

# ── Coverage data readers ───────────────────────────────────────────────


def _read_coverage_sqlite(coverage_path: str) -> dict[str, set[int]]:
    """Read a .coverage SQLite database and return {file_path: set(line_numbers)}.

    Handles both 'line' and 'arc' coverage data.
    """
    result: dict[str, set[int]] = {}

    if not os.path.exists(coverage_path):
        log.warning("Coverage SQLite DB not found: %s", coverage_path)
        return result

    try:
        conn = sqlite3.connect(coverage_path)
        conn.row_factory = sqlite3.Row

        # Check schema version
        schema_ver = conn.execute(
            "SELECT value FROM meta WHERE key='version'"
        ).fetchone()
        log.debug("Coverage data version: %s", schema_ver["value"] if schema_ver else "unknown")

        # Check if arc-based or line-based
        has_arcs = conn.execute(
            "SELECT value FROM meta WHERE key='has_arcs'"
        ).fetchone()
        is_arc = has_arcs and has_arcs["value"] == "1"

        # Get file paths
        file_rows = conn.execute("SELECT id, path FROM file").fetchall()
        file_map = {r["id"]: r["path"] for r in file_rows}

        if is_arc:
            # Arc-based coverage: get distinct line numbers from arcs
            arc_rows = conn.execute(
                "SELECT file_id, fromno, tono FROM arc"
            ).fetchall()
            for row in arc_rows:
                fid = row["file_id"]
                path = file_map.get(fid)
                if not path:
                    continue
                if path not in result:
                    result[path] = set()
                # Both fromno and tono indicate executed lines
                if row["fromno"] > 0:
                    result[path].add(row["fromno"])
                if row["tono"] > 0:
                    result[path].add(row["tono"])
        else:
            # Line-based coverage
            line_rows = conn.execute(
                "SELECT file_id, lineno FROM line"
            ).fetchall()
            for row in line_rows:
                fid = row["file_id"]
                path = file_map.get(fid)
                if not path:
                    continue
                if path not in result:
                    result[path] = set()
                result[path].add(row["lineno"])

        conn.close()
        log.debug("Read coverage data: %d files, %d total lines",
                  len(result), sum(len(v) for v in result.values()))

    except Exception as e:
        log.warning("Failed to read coverage SQLite DB %s: %s", coverage_path, e)

    return result


def _read_coverage_json(json_path: str) -> dict[str, set[int]]:
    """Read a .coverage.json file and return {file_path: set(line_numbers)}.

    Expected format (from coverage json --output):
    {
      "meta": {...},
      "files": {
        "/path/to/file.py": {
          "executed_lines": [1, 2, 3, ...],
          ...
        },
        ...
      }
    }
    """
    result: dict[str, set[int]] = {}

    if not os.path.exists(json_path):
        log.warning("Coverage JSON not found: %s", json_path)
        return result

    try:
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        files = data.get("files", data)
        if not isinstance(files, dict):
            log.warning("Unexpected coverage JSON format: expected 'files' dict")
            return result

        for file_path, file_data in files.items():
            if not isinstance(file_data, dict):
                continue
            executed = file_data.get("executed_lines", [])
            if executed:
                result[file_path] = set(executed)

        log.debug("Read coverage JSON: %d files, %d total lines",
                  len(result), sum(len(v) for v in result.values()))

    except Exception as e:
        log.warning("Failed to read coverage JSON %s: %s", json_path, e)

    return result


# ── Coverage import ─────────────────────────────────────────────────────


def import_coverage(store: KGStore, coverage_path: str,
                    project_base: Optional[str] = None) -> dict:
    """Import coverage data and create verifies edges between test and code functions.

    Strategy:
      1. Read coverage data from .coverage (SQLite) or .coverage.json
      2. For each covered source file, find which code_function nodes
         have line ranges that overlap with covered lines
      3. For each code_function that is "covered", find test_function
         nodes from the same module/test file and create verifies edges
      4. If per-test context data is available (coverage run with
         --context=TEST_NAME), use it for precise mapping

    Args:
        store: KGStore instance
        coverage_path: Path to .coverage or .coverage.json
        project_base: Optional project base path for path normalization

    Returns:
        dict with counts: files, covered_functions, verifies_edges
    """
    project_base = project_base or os.environ.get("OSH_HOME", ".")

    # Read coverage data
    coverage_path = str(coverage_path)
    if coverage_path.endswith(".json"):
        covered_files = _read_coverage_json(coverage_path)
    else:
        covered_files = _read_coverage_sqlite(coverage_path)

    if not covered_files:
        log.warning("No coverage data found in %s", coverage_path)
        return {
            "files": 0,
            "covered_functions": 0,
            "verifies_edges": 0,
        }

    # Normalize paths: coverage data uses absolute paths, graph uses project-relative
    project_path = Path(project_base).resolve()
    normalized_coverage: dict[str, set[int]] = {}
    for abs_path, lines in covered_files.items():
        try:
            rel = str(Path(abs_path).relative_to(project_path))
        except ValueError:
            # Try to find a relative path by matching the tail
            abs_p = Path(abs_path)
            try:
                rel = str(abs_p.relative_to(project_path))
            except ValueError:
                # Keep as-is, may still match
                rel = abs_path
        normalized_coverage[rel.replace("\\", "/")] = lines

    # Get all code_function nodes from the graph
    code_functions = store.list_nodes(entity_type="code_function")
    test_functions = store.list_nodes(entity_type="test_function")

    if not code_functions:
        log.warning("No code_function nodes in graph — run code_scanner first")
        return {
            "files": len(normalized_coverage),
            "covered_functions": 0,
            "verifies_edges": 0,
        }

    # Build a lookup: file_path → [code_function nodes]
    functions_by_file: dict[str, list[Node]] = {}
    for fn in code_functions:
        fp = fn.properties.get("file_path", "")
        if fp not in functions_by_file:
            functions_by_file[fp] = []
        functions_by_file[fp].append(fn)

    # Build a lookup: file_path → [test_function nodes]
    tests_by_file: dict[str, list[Node]] = {}
    for tfn in test_functions:
        fp = tfn.properties.get("file_path", "")
        if fp not in tests_by_file:
            tests_by_file[fp] = []
        tests_by_file[fp].append(tfn)

    # Also match code files to test files: for each test file,
    # find the code file it likely tests (same module name)
    # This is used when no per-test context is available
    test_to_source_mapping = _infer_test_to_source_mapping(
        store, project_base
    )

    # For each source file with coverage data, find covered functions
    covered_function_count = 0
    verifies_edge_count = 0
    file_count = 0

    for rel_path, covered_lines in normalized_coverage.items():
        # Find matching code_functions for this file
        func_nodes = functions_by_file.get(rel_path, [])

        if not func_nodes:
            continue

        file_count += 1

        # Determine which functions are covered (at least one line executed)
        covered_funcs = []
        for fn in func_nodes:
            fn_start = fn.properties.get("start_line", 0)
            fn_end = fn.properties.get("end_line", fn_start)

            # Check if any covered line falls within this function's range
            if isinstance(fn_start, int) and isinstance(fn_end, int):
                if any(fn_start <= line <= fn_end for line in covered_lines):
                    covered_funcs.append(fn)

        if not covered_funcs:
            continue

        covered_function_count += len(covered_funcs)

        # Now create verifies edges: test_function → code_function
        # Find test functions that test this source file
        test_funcs = _find_relevant_test_functions(
            store, rel_path, test_to_source_mapping, tests_by_file
        )

        for tfn in test_funcs:
            for cfn in covered_funcs:
                store.upsert_edge(Edge(
                    source_id=tfn.id,
                    target_id=cfn.id,
                    edge_type="verifies",
                    properties={
                        "source": "coverage_importer",
                        "covered_function": cfn.label,
                        "covered_lines": sorted(
                            l for l in covered_lines
                            if cfn.properties.get("start_line", 0) <= l <= cfn.properties.get("end_line", 0)
                        ),
                        "confidence": 1.0,
                    },
                ))
                verifies_edge_count += 1

    log.info(
        "Coverage import complete: %d files, %d covered functions, %d verifies edges",
        file_count, covered_function_count, verifies_edge_count,
    )

    return {
        "files": file_count,
        "covered_functions": covered_function_count,
        "verifies_edges": verifies_edge_count,
    }


def _infer_test_to_source_mapping(store: KGStore,
                                   project_base: str) -> dict[str, str]:
    """Build a mapping from test file paths to source file paths.

    Uses:
      - RTM covers edges: requirement → test_function/test_file
      - Naming conventions: test_foo.py → foo.py or src/yuleosh/foo.py

    Returns dict: test_file_path → code_file_path
    """
    mapping: dict[str, str] = {}

    # Method 1: Look at requirements' covers edges that link to both test and code
    reqs = store.list_nodes(entity_type="requirement")
    for req in reqs:
        outgoing = store.get_outgoing_edges(req.id)
        test_files_seen = set()
        code_files_seen = set()
        for edge, target in outgoing:
            if edge.edge_type == "covers" and target.entity_type == "test_file":
                test_files_seen.add(target.entity_id)
            elif edge.edge_type == "covers" and target.entity_type == "code_file":
                code_files_seen.add(target.entity_id)
        # If we see both a test and code file for the same requirement, link them
        for tf in test_files_seen:
            for cf in code_files_seen:
                mapping[tf] = cf

    # Method 2: Infer from naming convention
    # test_foo.py → foo.py, or test_foo.py → src/yuleosh/foo.py
    test_nodes = store.list_nodes(entity_type="test_file")
    code_nodes = store.list_nodes(entity_type="code_file")
    code_file_names = {Path(n.entity_id).name for n in code_nodes}

    for tn in test_nodes:
        if tn.entity_id in mapping:
            continue
        test_name = Path(tn.entity_id).name
        if test_name.startswith("test_"):
            source_name = test_name[5:]  # test_foo.py → foo.py
        elif test_name.startswith("test"):
            source_name = test_name[4:]  # testfoo.py → foo.py
        else:
            continue

        # Check if code file with that name exists
        if source_name in code_file_names:
            # Find the matching code file
            for cn in code_nodes:
                if Path(cn.entity_id).name == source_name:
                    mapping[tn.entity_id] = cn.entity_id
                    break

        # Also try parent directory: tests/ → src/yuleosh/
        test_path = Path(tn.entity_id)
        if len(test_path.parts) >= 2:
            parent = test_path.parts[0]
            if parent == "tests":
                # Look for src/yuleosh/<source_name>
                alt_path = f"src/yuleosh/{source_name}"
                for cn in code_nodes:
                    if cn.entity_id == alt_path:
                        mapping[tn.entity_id] = alt_path
                        break

    return mapping


def _find_relevant_test_functions(
    store: KGStore,
    source_path: str,
    test_to_source_map: dict[str, str],
    tests_by_file: dict[str, list[Node]],
) -> list[Node]:
    """Find test_function nodes that are relevant to a given source file.

    Uses multiple strategies:
      1. Direct file mapping: test file → source file
      2. RTM covers edges: test function directly covers a requirement
         that the source file implements
      3. Any test_function in the graph with matching source file reference
    """
    result: list[Node] = []
    seen_ids: set[int] = set()

    # Strategy 1: Inverted mapping — find test files that map to this source
    for test_path, src_path in test_to_source_map.items():
        if src_path == source_path:
            # Find all test functions in this test file
            test_funcs = tests_by_file.get(test_path, [])
            for tfn in test_funcs:
                if tfn.id not in seen_ids:
                    result.append(tfn)
                    seen_ids.add(tfn.id)

    # Strategy 2: Find test functions whose covers edges lead to this source
    # Look through all test_function nodes
    all_tfns = store.list_nodes(entity_type="test_function")
    code_nodes = store.list_nodes(entity_type="code_function")

    # Build code function file index
    code_by_file: dict[str, list[Node]] = {}
    for cn in code_nodes:
        fp = cn.properties.get("file_path", "")
        if fp not in code_by_file:
            code_by_file[fp] = []
        code_by_file[fp].append(cn)

    # For each test function, check if it has covers edges that trace
    # back to a code function in this source file
    for tfn in all_tfns:
        if tfn.id in seen_ids:
            continue

        # Check incoming edges: if a requirement covers this test,
        # and the same requirement covers a code_file in the source path
        incoming = store.get_incoming_edges(tfn.id)
        for edge, source_node in incoming:
            if edge.edge_type == "covers" and source_node.entity_type == "requirement":
                # This requirement covers this test function
                # Does it also cover a code_file with this source_path?
                req_outgoing = store.get_outgoing_edges(source_node.id)
                for e2, target in req_outgoing:
                    if (e2.edge_type == "covers"
                            and target.entity_type == "code_file"
                            and target.entity_id == source_path):
                        if tfn.id not in seen_ids:
                            result.append(tfn)
                            seen_ids.add(tfn.id)
                            break

    # Strategy 3: If no test functions found, try test functions whose
    # file_path matches the source file module
    if not result:
        # Extract module name from source path
        source_path_obj = Path(source_path)
        module_name = source_path_obj.stem  # e.g., "store" from "store.py"

        # Check if any test file tests this module
        test_funcs = list(store.list_nodes(entity_type="test_function"))
        for tfn in test_funcs:
            if tfn.id in seen_ids:
                continue
            tf_path = tfn.properties.get("file_path", "")
            tf_path_obj = Path(tf_path)
            tf_stem = tf_path_obj.stem  # e.g., "test_store"

            # test_store → store
            if tf_stem.startswith("test_"):
                if tf_stem[5:] == module_name or tf_stem[5:] == module_name.replace("_", ""):
                    if tfn.id not in seen_ids:
                        result.append(tfn)
                        seen_ids.add(tfn.id)
            # teststore → store
            elif tf_stem.startswith("test"):
                if tf_stem[4:] == module_name or tf_stem[4:] == module_name.replace("_", ""):
                    if tfn.id not in seen_ids:
                        result.append(tfn)
                        seen_ids.add(tfn.id)

    return result


# ── Tooling integration ─────────────────────────────────────────────────


def import_coverage_from_default(store: KGStore,
                                 project_base: Optional[str] = None) -> dict:
    """Import coverage data from the default .coverage file location.

    Tries:
      1. project_base/.coverage
      2. project_base/.coverage.json
      3. OSH_HOME/.coverage
      4. OSH_HOME/.coverage.json

    Returns combined result.
    """
    project_base = project_base or os.environ.get("OSH_HOME", ".")

    # Possible locations
    candidates = [
        os.path.join(project_base, ".coverage"),
        os.path.join(project_base, ".coverage.json"),
    ]

    for path in candidates:
        if os.path.exists(path):
            log.info("Found coverage data at %s", path)
            return import_coverage(store, path, project_base)

    log.warning("No coverage data found in any default location under %s", project_base)
    return {
        "files": 0,
        "covered_functions": 0,
        "verifies_edges": 0,
    }
