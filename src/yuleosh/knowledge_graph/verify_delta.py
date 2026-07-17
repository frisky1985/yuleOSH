#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Verify Delta — test result mapping for incremental builds (P1).

Maps test execution results (pass/fail/skip) onto the knowledge graph's
'verifies' and 'covers' edges during incremental builds.

Supports multiple test result formats:
  - pytest JSON report (--json-report)
  - Standard JUnit XML
  - yuleOSH CI test result format (layer-X-*.json)
  - Simple dict-based format for programmatic use

Usage:
    from yuleosh.knowledge_graph.verify_delta import apply_test_results
    result = apply_test_results(store, test_results)
    # → {"verifies_updated": 5, "covers_updated": 3}
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.models import Node, Edge

log = logging.getLogger("yuleosh.knowledge_graph.verify_delta")


def normalize_test_result(result: dict) -> dict:
    """Normalize a single test result to a canonical format.

    Canonical format:
      {
        "test_id": "tests/test_foo.py::test_bar",
        "file": "tests/test_foo.py",
        "function": "test_bar",
        "status": "pass",   # pass | fail | skip | error
        "duration_ms": 123,
        "message": ""       # error/failure message (optional)
      }

    Args:
        result: Raw test result dict from any supported source

    Returns:
        Normalized dict or None if unparseable
    """
    if not result:
        return None

    # Extract primary identifiers
    test_id = result.get("test_id") or result.get("nodeid") or result.get("name") or ""
    file_path = result.get("file") or result.get("path") or ""
    function = result.get("function") or result.get("func") or result.get("name") or ""

    # Auto-parse test_id if it contains ::
    if not function and "::" in test_id:
        parts = test_id.split("::")
        if len(parts) >= 2:
            file_path = file_path or parts[0]
            function = parts[-1]

    # Normalize status
    raw_status = (result.get("status") or result.get("outcome") or "").lower()
    if raw_status in ("passed", "pass", "ok", "success", "true"):
        status = "pass"
    elif raw_status in ("failed", "fail", "error", "false"):
        status = "fail"
    elif raw_status in ("skipped", "skip", "xfail"):
        status = "skip"
    elif raw_status in ("blocked",):
        status = "blocked"
    else:
        status = raw_status or "unknown"

    return {
        "test_id": test_id,
        "file": file_path,
        "function": function,
        "status": status,
        "duration_ms": result.get("duration_ms") or result.get("duration") or 0,
        "message": result.get("message") or result.get("call") or "",
    }


def parse_pytest_json_report(json_path: str) -> list[dict]:
    """Parse a pytest JSON report file.

    Supports the format from pytest-json-report plugin:
      {
        "created": ...,
        "duration": ...,
        "tests": [
          {
            "nodeid": "tests/test_foo.py::test_bar",
            "outcome": "passed",
            "duration": 0.123,
            "call": "..."
          },
          ...
        ]
      }
    """
    path = Path(json_path)
    if not path.exists():
        log.warning("pytest JSON report not found: %s", json_path)
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log.warning("Failed to parse pytest JSON report: %s", e)
        return []

    raw_tests = data.get("tests", [])
    results = []
    for raw in raw_tests:
        normalized = normalize_test_result(raw)
        if normalized:
            results.append(normalized)
        else:
            log.debug("Skipping unparseable test result: %s", raw)

    log.debug("Parsed %d test results from pytest JSON report", len(results))
    return results


def parse_yuleosh_ci_results(project_dir: str) -> list[dict]:
    """Parse yuleOSH CI test result files.

    Reads from .yuleosh/ci/ directory: layer-X-*.json files.

    Returns combined list of normalized test results.
    """
    ci_dir = Path(project_dir) / ".yuleosh" / "ci"
    if not ci_dir.exists():
        ci_dir = Path(project_dir) / ".osh" / "ci"
    if not ci_dir.exists():
        log.debug("No CI results directory found under %s", project_dir)
        return []

    results = []
    for f in sorted(ci_dir.glob("layer*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            tests = data if isinstance(data, list) else data.get("tests", [])
            for raw in tests:
                normalized = normalize_test_result(raw)
                if normalized:
                    results.append(normalized)
        except (json.JSONDecodeError, IOError) as e:
            log.warning("Failed to parse CI result %s: %s", f.name, e)

    log.debug("Parsed %d test results from CI directory", len(results))
    return results


def parse_junit_xml(xml_path: str) -> list[dict]:
    """Parse JUnit XML format (without external dependency).

    Simple XML parser for standard JUnit format:
      <testsuite tests="..." failures="..." errors="...">
        <testcase classname="..." name="..." time="...">
          <failure message="..."/>
        </testcase>
      </testsuite>
    """
    path = Path(xml_path)
    if not path.exists():
        log.warning("JUnit XML not found: %s", xml_path)
        return []

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except IOError as e:
        log.warning("Failed to read JUnit XML: %s", e)
        return []

    results = []
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        log.warning("Failed to parse JUnit XML: %s", e)
        return []

    # Handle both <testsuite> and <testsuites> wrappers
    for suite in root.iter("testsuite"):
        for tc in suite.iter("testcase"):
            classname = tc.get("classname", "")
            name = tc.get("name", "")
            time_sec = float(tc.get("time", 0) or 0)

            # Determine test file path and function name
            if classname:
                file_path = classname.replace(".", "/") + ".py"
            else:
                file_path = ""
            function = name

            # Determine status
            failure = tc.find("failure")
            error = tc.find("error")
            skipped = tc.find("skipped")
            if skipped is not None:
                status = "skip"
            elif failure is not None:
                status = "fail"
            elif error is not None:
                status = "error"
            else:
                status = "pass"

            test_id = f"{file_path}::{function}" if file_path else function
            message = ""
            if failure is not None:
                message = failure.get("message", "") or (failure.text or "")[:500]
            elif error is not None:
                msg_elem = error.find("message")
                message = msg_elem.text if msg_elem is not None else (error.text or "")[:500]

            results.append({
                "test_id": test_id,
                "file": file_path,
                "function": function,
                "status": status,
                "duration_ms": int(time_sec * 1000),
                "message": message,
            })

    log.debug("Parsed %d test results from JUnit XML", len(results))
    return results


def get_code_function_from_test_func(store, tfn_node):
    """Resolve the code_function(s) verified by a test_function.

    Uses the 'verifies' edge: test_function → verifies → code_function

    Returns list of code_function nodes.
    """
    code_fns = []
    for edge, target in store.get_outgoing_edges(tfn_node.id):
        if edge.edge_type == "verifies" and target.entity_type == "code_function":
            code_fns.append(target)
    return code_fns


def get_requirements_from_test_func(store, tfn_node):
    """Resolve requirement(s) covered by a test_function.

    Uses the 'covers' edge: requirement → covers → test_function
    (or via test_file → contains → test_function)

    Returns list of requirement nodes.
    """
    reqs = set()

    # Direct: requirement → covers → test_function
    for edge, source in store.get_incoming_edges(tfn_node.id):
        if edge.edge_type == "covers" and source.entity_type == "requirement":
            reqs.add(source.id)

    # Via test_file: requirement → covers → test_file → contains → test_function
    for edge, source in store.get_incoming_edges(tfn_node.id):
        if edge.edge_type == "contains" and source.entity_type == "test_file":
            for e2, req_source in store.get_incoming_edges(source.id):
                if e2.edge_type == "covers" and req_source.entity_type == "requirement":
                    reqs.add(req_source.id)

    return [store.get_node_by_id(rid) for rid in reqs if store.get_node_by_id(rid)]


def apply_single_test_result(store, test_result: dict) -> dict:
    """Apply a single test result to the knowledge graph.

    Updates:
      1. verifies edge: test_function → code_function (adds status/duration)
      2. covers edge: requirement → test_function/test_file (updates status)

    Args:
        store: KGStore instance
        test_result: Normalized test result dict

    Returns:
        dict with "verifies_updated" and "covers_updated" counts
    """
    result_counts = {"verifies_updated": 0, "covers_updated": 0}

    # Find the test_function node
    file_path = test_result.get("file", "")
    function = test_result.get("function", "")

    if not function:
        # Try using test_id
        test_id = test_result.get("test_id", "")
        if "::" in test_id:
            parts = test_id.split("::")
            function = parts[-1]

    if not function:
        log.debug("Skipping test result without function name")
        return result_counts

    status = test_result.get("status", "unknown")
    duration_ms = test_result.get("duration_ms", 0)

    # Try different ways to find the node
    tfn_node = None
    fqn = f"{file_path}::{function}" if file_path else function

    # 1. Exact FQN match
    tfn_node = store.get_node("test_function", fqn)
    if tfn_node is None:
        # 2. Label match with file filter
        for node in store.list_nodes("test_function"):
            if node.label == function and (not file_path or node.properties.get("file_path", "").endswith(file_path)):
                tfn_node = node
                break

    if tfn_node is None:
        log.debug("Test function node not found: %s", fqn)
        return result_counts

    # Update verifies edges: test_function → code_function
    code_fns = get_code_function_from_test_func(store, tfn_node)
    for cf_node in code_fns:
        # Update the verifies edge properties
        existing_edge = store.get_edge(tfn_node.id, cf_node.id, "verifies")
        if existing_edge:
            props = dict(existing_edge.properties)
            props["last_status"] = status
            props["last_duration_ms"] = duration_ms
            props["last_run_time"] = test_result.get("__timestamp", "")
            if status == "fail" and test_result.get("message"):
                props["last_error"] = test_result["message"][:500]

            store.upsert_edge(Edge(
                source_id=existing_edge.source_id,
                target_id=existing_edge.target_id,
                edge_type=existing_edge.edge_type,
                properties=props,
                verified_at=existing_edge.verified_at,
                build_id=existing_edge.build_id,
            ))
            result_counts["verifies_updated"] += 1

    # Update covers edges: requirement → test_function/test_file
    reqs = get_requirements_from_test_func(store, tfn_node)
    for req_node in reqs:
        existing_edge = store.get_edge(req_node.id, tfn_node.id, "covers")
        if existing_edge:
            props = dict(existing_edge.properties)
            props["test_status"] = status
            props["last_test_duration_ms"] = duration_ms
            if status == "fail" and test_result.get("message"):
                props["last_error"] = test_result["message"][:500]

            store.upsert_edge(Edge(
                source_id=existing_edge.source_id,
                target_id=existing_edge.target_id,
                edge_type=existing_edge.edge_type,
                properties=props,
                verified_at=existing_edge.verified_at,
                build_id=existing_edge.build_id,
            ))
            result_counts["covers_updated"] += 1

    return result_counts


def apply_test_results(store, test_results: list[dict], timestamp: Optional[str] = None) -> dict:
    """Apply a batch of test results to the knowledge graph.

    Each test result is mapped to verifies and covers edges.

    Args:
        store: KGStore instance
        test_results: List of normalized test result dicts
        timestamp: Optional ISO timestamp for the run

    Returns:
        Summary dict:
          {
            "verifies_updated": N,
            "covers_updated": N,
            "passed": N,
            "failed": N,
            "skipped": N,
            "not_found": N,
            "total": N
          }
    """
    if not test_results:
        log.info("No test results to apply")
        return {"verifies_updated": 0, "covers_updated": 0, "total": 0}

    import datetime
    ts = timestamp or datetime.datetime.now().isoformat()

    total_vu = 0
    total_cu = 0
    passed = 0
    failed = 0
    skipped = 0
    not_found = 0

    for result in test_results:
        result["__timestamp"] = ts
        r = apply_single_test_result(store, result)
        total_vu += r["verifies_updated"]
        total_cu += r["covers_updated"]

        status = result.get("status", "")
        if status == "pass":
            passed += 1
        elif status == "fail":
            failed += 1
        elif status == "skip":
            skipped += 1
        else:
            not_found += 1

    log.info(
        "Applied %d test results: %d passed, %d failed, %d skipped, "
        "%d verifies edges, %d covers edges updated",
        len(test_results), passed, failed, skipped, total_vu, total_cu,
    )
    return {
        "verifies_updated": total_vu,
        "covers_updated": total_cu,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "not_found": not_found,
        "total": len(test_results),
    }


def load_test_results(project_dir: str, json_path: Optional[str] = None,
                      junit_path: Optional[str] = None) -> list[dict]:
    """Load test results from available sources.

    Priority:
      1. Explicit json_path (pytest JSON report)
      2. Explicit junit_path (JUnit XML)
      3. Auto-detect from .yuleosh/ci/ directory

    Args:
        project_dir: Project root directory
        json_path: Optional path to pytest JSON report
        junit_path: Optional path to JUnit XML

    Returns:
        Combined list of normalized test results
    """
    all_results = []

    if json_path and os.path.exists(json_path):
        all_results.extend(parse_pytest_json_report(json_path))

    if junit_path and os.path.exists(junit_path):
        all_results.extend(parse_junit_xml(junit_path))

    if not json_path and not junit_path:
        all_results.extend(parse_yuleosh_ci_results(project_dir))

    return all_results
