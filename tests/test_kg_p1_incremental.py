#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph P1 Tests — incremental build, spec diff, verify delta, CLI, API.

Tests for:
  1. spec_diff module: SHALL extraction, diff analysis, store application
  2. verify_delta module: test result normalization, store application
  3. kg_cli commands: build, bootstrap, snapshot, query impact
  4. API: POST /api/v1/kg/query/impact handler
  5. Incremental build via importer.incremental_bootstrap()

All tests use in-memory SQLite store (no PostgreSQL dependency).
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Ensure src is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.models import Node, Edge


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def store():
    """Fresh KGStore instance for testing.

    Uses __new__ to bypass singleton, creates a raw sqlite in-memory DB.
    """
    import sqlite3
    from yuleosh.knowledge_graph.store import KGStore

    # Reset existing singletons so fresh tests don't share state
    KGStore.reset()

    # Create instance manually (bypass singleton)
    instance = object.__new__(KGStore)
    instance.db_path = ":memory:"
    instance.conn = sqlite3.connect(":memory:", check_same_thread=False)
    instance.conn.row_factory = sqlite3.Row
    instance._migrate()
    yield instance
    try:
        instance.conn.close()
    except Exception:
        pass
    KGStore.reset()


@pytest.fixture
def sample_spec_md():
    """Sample spec markdown with SHALL statements."""
    return """# Software Requirements Specification

## Functional Requirements

* [RS-001-01] The system SHALL process UART data within 10ms.
* [RS-001-02] The system SHALL validate checksum on incoming packets.

## Safety Requirements

* [SWR-001.1-01] The fault handler SHALL log all errors to persistent storage.
* [SWR-001.1-02] The system SHALL transition to safe state on critical fault.
"""


@pytest.fixture
def sample_spec_md_updated():
    """Updated spec with one added, one modified, one deleted."""
    return """# Software Requirements Specification

## Functional Requirements

* [RS-001-01] The system SHALL process UART data within 5ms.  (modified: tighter timing)
* [RS-001-02] The system SHALL validate checksum on incoming packets.

## New Features

* [RS-003-01] The system SHALL support over-the-air firmware updates.  (new)

## Safety Requirements

* [SWR-001.1-02] The system SHALL transition to safe state on critical fault.
"""


@pytest.fixture
def sample_test_results():
    """Sample pytest JSON report data."""
    return {
        "created": 1700000000,
        "duration": 1.5,
        "tests": [
            {"nodeid": "tests/test_uart.py::test_uart_process", "outcome": "passed", "duration": 0.1},
            {"nodeid": "tests/test_uart.py::test_checksum", "outcome": "passed", "duration": 0.05},
            {"nodeid": "tests/test_safety.py::test_fault_logging", "outcome": "failed", "duration": 0.2},
            {"nodeid": "tests/test_safety.py::test_safe_state", "outcome": "passed", "duration": 0.15},
        ]
    }


@pytest.fixture
def sample_junit_xml():
    """Sample JUnit XML data."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="pytest" tests="3" failures="1" errors="0">
    <testcase classname="tests.test_uart" name="test_uart_process" time="0.1">
    </testcase>
    <testcase classname="tests.test_uart" name="test_checksum" time="0.05">
    </testcase>
    <testcase classname="tests.test_safety" name="test_fault_logging" time="0.2">
        <failure message="AssertionError: Expected True, got False">
Traceback (most recent call last):
  File "tests/test_safety.py", line 15, in test_fault_logging
    assert result == True
AssertionError: Expected True, got False
        </failure>
    </testcase>
</testsuite>
"""


# ═══════════════════════════════════════════════════════════════════════
# Test 1: spec_diff — extract_shall_statements
# ═══════════════════════════════════════════════════════════════════════

class TestExtractShallStatements:

    def test_extract_standard_format(self, sample_spec_md):
        """Extract SHALL statements from standard bullet format."""
        from yuleosh.knowledge_graph.spec_diff import extract_shall_statements
        statements = extract_shall_statements(sample_spec_md)
        assert len(statements) == 4
        ids = [s["shall_id"] for s in statements]
        assert "RS-001-01" in ids
        assert "RS-001-02" in ids
        assert "SWR-001.1-01" in ids
        assert "SWR-001.1-02" in ids

    def test_extract_empty_text(self):
        """Empty text returns empty list."""
        from yuleosh.knowledge_graph.spec_diff import extract_shall_statements
        assert extract_shall_statements("") == []
        assert extract_shall_statements(None) == []
        assert extract_shall_statements("   ") == []

    def test_extract_with_section_info(self, sample_spec_md):
        """Each extracted statement has section info."""
        from yuleosh.knowledge_graph.spec_diff import extract_shall_statements
        statements = extract_shall_statements(sample_spec_md)
        for s in statements:
            section = s.get("section", "")
            assert section in ("Functional Requirements", "Safety Requirements")
        # Check RS-001-01 is in Functional Requirements
        rs001 = [s for s in statements if s["shall_id"] == "RS-001-01"][0]
        assert rs001["section"] == "Functional Requirements"

    def test_extract_alternate_formats(self):
        """Handle dash format and other formats."""
        from yuleosh.knowledge_graph.spec_diff import extract_shall_statements
        text = """# Spec
- RS-001-01: The SHALL process data
- RS-001-02: The SHALL validate checksum
"""
        statements = extract_shall_statements(text)
        assert len(statements) >= 2

    def test_extract_ids_from_text(self, sample_spec_md):
        """extract_shall_ids returns just the IDs in order."""
        from yuleosh.knowledge_graph.spec_diff import extract_shall_ids
        ids = extract_shall_ids(sample_spec_md)
        assert ids == ["RS-001-01", "RS-001-02", "SWR-001.1-01", "SWR-001.1-02"]


# ═══════════════════════════════════════════════════════════════════════
# Test 2: spec_diff — analyze_spec_changes
# ═══════════════════════════════════════════════════════════════════════

class TestAnalyzeSpecChanges:

    def test_detect_additions(self, sample_spec_md, sample_spec_md_updated):
        """Detect added SHALL statements."""
        from yuleosh.knowledge_graph.spec_diff import analyze_spec_changes
        changes = analyze_spec_changes(sample_spec_md, sample_spec_md_updated)
        added_ids = [s["shall_id"] for s in changes["added"]]
        assert "RS-003-01" in added_ids

    def test_detect_modifications(self, sample_spec_md, sample_spec_md_updated):
        """Detect modified SHALL statements."""
        from yuleosh.knowledge_graph.spec_diff import analyze_spec_changes
        changes = analyze_spec_changes(sample_spec_md, sample_spec_md_updated)
        modified_ids = [s["shall_id"] for s in changes["modified"]]
        assert "RS-001-01" in modified_ids

    def test_detect_deletions(self, sample_spec_md, sample_spec_md_updated):
        """Detect deleted SHALL statements."""
        from yuleosh.knowledge_graph.spec_diff import analyze_spec_changes
        changes = analyze_spec_changes(sample_spec_md, sample_spec_md_updated)
        deleted_ids = [s["shall_id"] for s in changes["deleted"]]
        assert "SWR-001.1-01" in deleted_ids

    def test_no_changes(self):
        """No changes between identical specs."""
        from yuleosh.knowledge_graph.spec_diff import analyze_spec_changes
        text = "* [RS-001-01] The SHALL process data."
        changes = analyze_spec_changes(text, text)
        assert len(changes["added"]) == 0
        assert len(changes["modified"]) == 0
        assert len(changes["deleted"]) == 0
        assert len(changes["unchanged"]) == 1
        assert "unchanged" in changes["summary"]
        # When there are unchanged items but no added/modified/deleted, it still works

    def test_summary_format(self, sample_spec_md, sample_spec_md_updated):
        """Summary string is human-readable."""
        from yuleosh.knowledge_graph.spec_diff import analyze_spec_changes
        changes = analyze_spec_changes(sample_spec_md, sample_spec_md_updated)
        summary = changes["summary"]
        assert "added" in summary
        assert "modified" in summary
        assert "deleted" in summary

    def test_detect_spec_files_in_changes(self):
        """Filter spec files from changed file list."""
        from yuleosh.knowledge_graph.spec_diff import detect_spec_files_in_changes
        files = [
            "src/main.c",
            "docs/software-requirements.spec.md",
            "tests/test_main.py",
            "docs/safety.spec.md",
        ]
        spec_files = detect_spec_files_in_changes(files)
        assert len(spec_files) == 2
        assert "docs/software-requirements.spec.md" in spec_files
        assert "docs/safety.spec.md" in spec_files
        assert "src/main.c" not in spec_files


# ═══════════════════════════════════════════════════════════════════════
# Test 3: spec_diff — apply_spec_changes_to_store
# ═══════════════════════════════════════════════════════════════════════

class TestApplySpecChangesToStore:

    def test_apply_additions(self, store):
        """Adding new requirements via spec changes."""
        from yuleosh.knowledge_graph.spec_diff import apply_spec_changes_to_store
        changes = {
            "added": [{"shall_id": "RS-003-01", "statement": "The SHALL support OTA updates"}],
            "modified": [],
            "deleted": [],
        }
        result = apply_spec_changes_to_store(store, changes)
        assert result["created"] == 1

        node = store.get_node("requirement", "RS-003-01")
        assert node is not None
        assert node.properties.get("change_type") == "added"

    def test_apply_modifications(self, store):
        """Modified requirements get updated properties."""
        from yuleosh.knowledge_graph.spec_diff import apply_spec_changes_to_store

        # First create original
        store.upsert_node(Node(
            entity_type="requirement", entity_id="RS-001-01",
            label="RS-001-01",
            properties={"statement": "Original statement"},
        ))

        # Then apply modification
        changes = {
            "added": [],
            "modified": [{"shall_id": "RS-001-01",
                          "new_statement": "Updated statement",
                          "old_statement": "Original statement"}],
            "deleted": [],
        }
        result = apply_spec_changes_to_store(store, changes)
        assert result["updated"] == 1

        node = store.get_node("requirement", "RS-001-01")
        assert node.properties.get("statement") == "Updated statement"
        assert node.properties.get("has_pending_changes") is True

    def test_apply_deletions(self, store):
        """Deleted requirements are soft-deleted."""
        from yuleosh.knowledge_graph.spec_diff import apply_spec_changes_to_store

        store.upsert_node(Node(
            entity_type="requirement", entity_id="OBSOLETE-01",
            label="OBSOLETE-01",
            properties={"statement": "Obsolete req"},
        ))

        changes = {
            "added": [],
            "modified": [],
            "deleted": [{"shall_id": "OBSOLETE-01", "statement": "Obsolete req"}],
        }
        result = apply_spec_changes_to_store(store, changes)
        assert result["deleted"] == 1

        node = store.get_node("requirement", "OBSOLETE-01")
        assert node.is_active is False


# ═══════════════════════════════════════════════════════════════════════
# Test 4: verify_delta — normalize_test_result
# ═══════════════════════════════════════════════════════════════════════

class TestNormalizeTestResult:

    def test_normalize_pytest_format(self):
        """Normalize pytest-style test result."""
        from yuleosh.knowledge_graph.verify_delta import normalize_test_result
        result = normalize_test_result({
            "nodeid": "tests/test_foo.py::test_bar",
            "outcome": "passed",
            "duration": 0.123,
        })
        assert result["test_id"] == "tests/test_foo.py::test_bar"
        assert result["status"] == "pass"
        assert result["duration_ms"] == 0.123

    def test_normalize_various_statuses(self):
        """Multiple status values map correctly."""
        from yuleosh.knowledge_graph.verify_delta import normalize_test_result
        assert normalize_test_result({"status": "passed"})["status"] == "pass"
        assert normalize_test_result({"status": "failed"})["status"] == "fail"
        assert normalize_test_result({"status": "skipped"})["status"] == "skip"
        assert normalize_test_result({"outcome": "passed"})["status"] == "pass"
        assert normalize_test_result({"outcome": "error"})["status"] == "fail"

    def test_normalize_empty(self):
        """Empty result returns None."""
        from yuleosh.knowledge_graph.verify_delta import normalize_test_result
        assert normalize_test_result(None) is None
        assert normalize_test_result({}) is None


# ═══════════════════════════════════════════════════════════════════════
# Test 5: verify_delta — parse_pytest_json_report
# ═══════════════════════════════════════════════════════════════════════

class TestParsePytestJsonReport:

    def test_parse_json_report(self, sample_test_results, tmp_path):
        """Parse a pytest JSON report file."""
        from yuleosh.knowledge_graph.verify_delta import parse_pytest_json_report
        report_file = tmp_path / ".pytest_results.json"
        report_file.write_text(json.dumps(sample_test_results))

        results = parse_pytest_json_report(str(report_file))
        assert len(results) == 4
        assert results[0]["status"] == "pass"
        assert results[2]["status"] == "fail"

    def test_parse_missing_file(self):
        """Missing report file returns empty list."""
        from yuleosh.knowledge_graph.verify_delta import parse_pytest_json_report
        assert parse_pytest_json_report("/nonexistent/report.json") == []

    def test_parse_invalid_json(self, tmp_path):
        """Invalid JSON returns empty list."""
        from yuleosh.knowledge_graph.verify_delta import parse_pytest_json_report
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json")
        assert parse_pytest_json_report(str(bad_file)) == []


# ═══════════════════════════════════════════════════════════════════════
# Test 6: verify_delta — parse_junit_xml
# ═══════════════════════════════════════════════════════════════════════

class TestParseJunitXml:

    def test_parse_junit_xml(self, sample_junit_xml, tmp_path):
        """Parse JUnit XML file."""
        from yuleosh.knowledge_graph.verify_delta import parse_junit_xml
        xml_file = tmp_path / "junit.xml"
        xml_file.write_text(sample_junit_xml)

        results = parse_junit_xml(str(xml_file))
        assert len(results) == 3
        assert results[0]["status"] == "pass"
        assert results[2]["status"] == "fail"
        assert results[2]["message"] != ""

    def test_parse_junit_xml_invalid(self, tmp_path):
        """Invalid XML returns empty list."""
        from yuleosh.knowledge_graph.verify_delta import parse_junit_xml
        bad_file = tmp_path / "bad.xml"
        bad_file.write_text("<not-xml")
        assert parse_junit_xml(str(bad_file)) == []

    def test_parse_junit_xml_missing(self):
        """Missing file returns empty list."""
        from yuleosh.knowledge_graph.verify_delta import parse_junit_xml
        assert parse_junit_xml("/nonexistent/results.xml") == []


# ═══════════════════════════════════════════════════════════════════════
# Test 7: verify_delta — apply_test_results
# ═══════════════════════════════════════════════════════════════════════

class TestApplyTestResults:

    def test_apply_test_results_updates_edges(self, store):
        """Apply test results updates verifies and covers edges."""
        from yuleosh.knowledge_graph.verify_delta import apply_test_results

        # Create test nodes and edges
        # upsert_node returns int (node ID)
        req = Node(
            entity_type="requirement", entity_id="RS-001-01", label="RS-001-01",
        )
        req_id = store.upsert_node(req)

        test_file = Node(
            entity_type="test_file", entity_id="tests/test_foo.py", label="test_foo.py",
        )
        tf_id = store.upsert_node(test_file)

        tfn = Node(
            entity_type="test_function",
            entity_id="tests/test_foo.py::test_bar",
            label="test_bar",
            properties={"file_path": "tests/test_foo.py"},
        )
        tfn_id = store.upsert_node(tfn)

        code_fn = Node(
            entity_type="code_function",
            entity_id="src/main.py::do_stuff",
            label="do_stuff",
            properties={"file_path": "src/main.py"},
        )
        code_fn_id = store.upsert_node(code_fn)

        # Create covers edge: req → test_file
        store.upsert_edge(Edge(source_id=req_id, target_id=tf_id, edge_type="covers"))
        # Create contains edge: test_file → test_function
        store.upsert_edge(Edge(source_id=tf_id, target_id=tfn_id, edge_type="contains"))
        # Create verifies edge: test_function → code_function
        store.upsert_edge(Edge(source_id=tfn_id, target_id=code_fn_id, edge_type="verifies"))

        # Apply test results
        results = apply_test_results(store, [
            {
                "test_id": "tests/test_foo.py::test_bar",
                "file": "tests/test_foo.py",
                "function": "test_bar",
                "status": "pass",
                "duration_ms": 100,
            }
        ])
        assert results["verifies_updated"] == 1
        assert results["passed"] == 1

        # Verify edge was updated
        edge = store.get_edge(tfn_id, code_fn_id, "verifies")
        assert edge is not None
        assert edge.properties.get("last_status") == "pass"
        assert edge.properties.get("last_duration_ms") == 100

    def test_apply_empty_results(self, store):
        """Empty results list returns no updates."""
        from yuleosh.knowledge_graph.verify_delta import apply_test_results
        result = apply_test_results(store, [])
        assert result["total"] == 0
        assert result["verifies_updated"] == 0

    def test_apply_unknown_function(self, store):
        """Unknown test function is skipped gracefully."""
        from yuleosh.knowledge_graph.verify_delta import apply_test_results
        result = apply_test_results(store, [
            {"test_id": "unknown.py::no_such_func", "status": "pass"},
        ])
        assert result["total"] == 1
        assert result["verifies_updated"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Test 8: Incremental build via importer.incremental_bootstrap
# ═══════════════════════════════════════════════════════════════════════

class TestIncrementalBootstrap:

    def test_incremental_bootstrap_with_changed_files(self, store, tmp_path):
        """Incremental bootstrap processes changed files."""
        from yuleosh.knowledge_graph.importer import incremental_bootstrap

        # Create a minimal project structure
        src_dir = tmp_path / "src" / "yuleosh"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        (src_dir / "engine.py").write_text("def run():\n    pass\n")
        (src_dir / "utils.py").write_text("def helper():\n    return 42\n")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_engine.py").write_text("def test_run():\n    assert True\n")

        result = incremental_bootstrap(
            store,
            project_dir=str(tmp_path),
            changed_files=["src/yuleosh/engine.py"],
            create_snapshot=True,
            build_id="test-incremental-001",
        )

        assert result["mode"] == "incremental"
        inc_result = result.get("incremental", {})
        assert inc_result.get("changed_files", 0) >= 1
        assert inc_result.get("code_files", 0) >= 1

        # Verify engine.py node was created
        node = store.get_node("code_file", "src/yuleosh/engine.py")
        assert node is not None

    def test_incremental_bootstrap_full(self, store, tmp_path):
        """Incremental bootstrap can fall back to full scan."""
        from yuleosh.knowledge_graph.importer import incremental_bootstrap

        result = incremental_bootstrap(
            store,
            project_dir=str(tmp_path),
            changed_files=None,
            create_snapshot=True,
            build_id="test-full-001",
        )

        assert "summary" in result or "stats" in result

    def test_incremental_bootstrap_with_snapshot(self, store, tmp_path):
        """Incremental bootstrap creates a snapshot."""
        from yuleosh.knowledge_graph.importer import incremental_bootstrap

        # Create minimal project
        src_dir = tmp_path / "src"
        src_dir.mkdir(parents=True)
        (src_dir / "main.py").write_text("x = 1\n")

        result = incremental_bootstrap(
            store,
            project_dir=str(tmp_path),
            changed_files=["src/main.py"],
            create_snapshot=True,
            build_id="test-snap-001",
        )

        snap = result.get("snapshot", {})
        assert snap.get("build_id") == "test-snap-001"


# ═══════════════════════════════════════════════════════════════════════
# Test 9: CLI commands (via kg_cli module)
# ═══════════════════════════════════════════════════════════════════════

class TestKgCliCommands:

    def test_cmd_stats(self, store):
        """kg stats command returns valid statistics."""
        # Add some data
        store.upsert_node(Node(entity_type="requirement", entity_id="R-001", label="R-001"))
        store.upsert_node(Node(entity_type="code_file", entity_id="src/main.py", label="main.py"))

        # Mock args and call cmd_stats
        from yuleosh.knowledge_graph.kg_cli import cmd_stats

        class Args:
            project_dir = "."
            json = False

        result = cmd_stats(Args())
        assert result.get("total_nodes", 0) >= 2

    def test_cmd_snapshot_list(self, store):
        """kg snapshot list returns snapshots."""
        from yuleosh.knowledge_graph.kg_cli import cmd_snapshot_list

        # Create a snapshot first
        store.create_snapshot(build_id="test-snap", meta={})

        class Args:
            project_dir = "."
            limit = 10

        result = cmd_snapshot_list(Args())
        assert len(result.get("snapshots", [])) >= 1

    def test_cmd_snapshot_diff_with_build_ids(self, store):
        """kg snapshot diff with valid build IDs."""
        from yuleosh.knowledge_graph.kg_cli import cmd_snapshot_diff

        # Create two snapshots
        store.create_snapshot(build_id="snap-a", meta={})
        store.create_snapshot(build_id="snap-b", meta={})

        class Args:
            project_dir = "."
            build_a = "snap-a"
            build_b = "snap-b"

        result = cmd_snapshot_diff(Args())
        assert isinstance(result, dict)

    def test_cmd_bootstrap(self, store, tmp_path):
        """kg bootstrap command runs successfully."""
        from yuleosh.knowledge_graph.kg_cli import cmd_bootstrap

        class Args:
            project_dir = str(tmp_path)

        result = cmd_bootstrap(Args())
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════
# Test 10: API handler
# ═══════════════════════════════════════════════════════════════════════

class TestKgImpactApi:

    def test_handle_impact_with_changed_files(self):
        """API handler returns proper impact result."""
        from yuleosh.api.kg_impact import handle_kg_impact

        # Mock HTTP handler
        mock_handler = mock.MagicMock()
        mock_handler.command = "POST"
        mock_handler.headers = {}
        mock_handler.client_address = ("127.0.0.1", 12345)
        mock_handler._request_start_time = 0.0

        params = {"changed_files": ["src/main.py"]}

        # The handler writes response via handler.send_response etc.
        handle_kg_impact(mock_handler, params)

        # Verify response was written
        mock_handler.send_response.assert_called_once()
        mock_handler.send_header.assert_called()
        mock_handler.end_headers.assert_called_once()

        # Get the written body
        written_data = mock_handler.wfile.write.call_args[0][0]
        response = json.loads(written_data.decode("utf-8"))
        assert response["status"] == "ok"

    def test_handle_impact_missing_files(self):
        """Missing changed_files returns 400 error."""
        from yuleosh.api.kg_impact import handle_kg_impact

        mock_handler = mock.MagicMock()

        handle_kg_impact(mock_handler, {})
        mock_handler.send_response.assert_called_with(400)

    def test_handle_impact_empty_files(self):
        """Empty changed_files list returns 400 error."""
        from yuleosh.api.kg_impact import handle_kg_impact

        mock_handler = mock.MagicMock()
        handle_kg_impact(mock_handler, {"changed_files": []})
        mock_handler.send_response.assert_called_with(400)

    def test_handle_impact_invalid_type(self):
        """Non-list changed_files returns 400 error."""
        from yuleosh.api.kg_impact import handle_kg_impact

        mock_handler = mock.MagicMock()
        handle_kg_impact(mock_handler, {"changed_files": "not-a-list"})
        mock_handler.send_response.assert_called_with(400)


# ═══════════════════════════════════════════════════════════════════════
# Test 11: Implements edge derivation (P1 spec requirement)
# ═══════════════════════════════════════════════════════════════════════

class TestImplementsDerivation:

    def _setup_chain(self, store):
        """Setup a coverage chain for implements derivation tests."""
        req = Node(entity_type="requirement", entity_id="RS-001", label="RS-001")
        req_id = store.upsert_node(req)

        tf = Node(entity_type="test_file", entity_id="tests/test_foo.py", label="test_foo.py")
        tf_id = store.upsert_node(tf)

        tfn = Node(
            entity_type="test_function",
            entity_id="tests/test_foo.py::test_bar",
            label="test_bar",
            properties={"file_path": "tests/test_foo.py"},
        )
        tfn_id = store.upsert_node(tfn)

        cf = Node(
            entity_type="code_function",
            entity_id="src/main.py::do_stuff",
            label="do_stuff",
            properties={"file_path": "src/main.py"},
        )
        cf_id = store.upsert_node(cf)

        store.upsert_edge(Edge(source_id=req_id, target_id=tf_id, edge_type="covers",
                                properties={"confidence": 1.0}))
        store.upsert_edge(Edge(source_id=tf_id, target_id=tfn_id, edge_type="contains"))
        store.upsert_edge(Edge(source_id=tfn_id, target_id=cf_id, edge_type="verifies",
                                properties={"last_status": "pass"}))
        return req_id, tf_id, tfn_id, cf_id

    def test_derived_implements_from_coverage_chain(self, store):
        """implements edges derived from covers + verifies chain (P0-1)."""
        req_id, tf_id, tfn_id, cf_id = self._setup_chain(store)

        # Now build implements edges
        from yuleosh.knowledge_graph.importer import _build_implements_edges
        result = _build_implements_edges(store)
        assert result["edges"] >= 1

        # Verify implements edge exists
        impl_edge = store.get_edge(cf_id, req_id, "implements")
        assert impl_edge is not None
        assert impl_edge.properties.get("confidence") is not None

    def test_implements_idempotent(self, store):
        """Building implements edges again should not create duplicates."""
        from yuleosh.knowledge_graph.importer import _build_implements_edges

        req_id, tf_id, tfn_id, cf_id = self._setup_chain(store)

        result1 = _build_implements_edges(store)
        result2 = _build_implements_edges(store)
        assert result2["edges"] == 0  # No new edges on second run

        # Check only one implements edge exists
        impl_edges = store.list_edges(edge_type="implements")
        assert len(impl_edges) == 1


# ═══════════════════════════════════════════════════════════════════════
# Test 12: Snapshot operations
# ═══════════════════════════════════════════════════════════════════════

class TestSnapshotOperations:

    def test_create_and_list_snapshots(self, store):
        """Create snapshot and list it back."""
        store.create_snapshot(build_id="build-001", meta={"test": True})
        store.create_snapshot(build_id="build-002", meta={"test": True})

        snapshots = store.list_snapshots(limit=10)
        assert len(snapshots) >= 2
        build_ids = [s.build_id for s in snapshots]
        assert "build-001" in build_ids
        assert "build-002" in build_ids

    def test_get_snapshot_by_build_id(self, store):
        """Get snapshot by build_id."""
        store.create_snapshot(build_id="build-001", meta={"test": True})

        snap = store.get_snapshot("build-001")
        assert snap is not None
        assert snap.build_id == "build-001"

    def test_snapshot_counts(self, store):
        """Snapshot records correct node/edge counts."""
        store.upsert_node(Node(entity_type="requirement", entity_id="R-1", label="R-1"))
        store.upsert_node(Node(entity_type="code_file", entity_id="src/main.py", label="main.py"))

        snap = store.create_snapshot(build_id="build-001", meta={})
        assert snap.node_count >= 2


# ═══════════════════════════════════════════════════════════════════════
# Test 13: Impact analysis through query API
# ═══════════════════════════════════════════════════════════════════════

class TestImpactAnalysis:

    def test_impact_analysis_basic(self, store):
        """Basic impact analysis returns affected reqs."""
        from yuleosh.knowledge_graph.queries import impact_analysis

        req_node = Node(
            entity_type="requirement", entity_id="RS-001", label="RS-001",
        )
        req_id = store.upsert_node(req_node)

        cf_node = Node(
            entity_type="code_file", entity_id="src/main.py", label="main.py",
        )
        cf_id = store.upsert_node(cf_node)

        store.upsert_edge(Edge(source_id=cf_id, target_id=req_id, edge_type="implements",
                                properties={"confidence": 1.0}))

        result = impact_analysis(store, ["src/main.py"])
        assert len(result["affected_reqs"]) >= 1
        assert result["affected_reqs"][0]["req_id"] == "RS-001"

    def test_impact_analysis_no_impact(self, store):
        """Files not in the graph return no impact."""
        from yuleosh.knowledge_graph.queries import impact_analysis

        result = impact_analysis(store, ["nonexistent.py"])
        assert len(result["affected_reqs"]) == 0


# ═══════════════════════════════════════════════════════════════════════
# Test 14: CI workflow step runs (integration test helpers)
# ═══════════════════════════════════════════════════════════════════════

class TestCiIntegration:

    def test_kg_ci_append_with_changed_files(self, store, tmp_path):
        """CI hook appends with changed files."""
        from yuleosh.knowledge_graph.ci_hook import kg_ci_append

        # Create a minimal file
        src_dir = tmp_path / "src" / "yuleosh"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        (src_dir / "mod.py").write_text("def foo(): pass\n")

        result = kg_ci_append(
            store,
            build_id="ci-test-001",
            changed_files=["src/yuleosh/mod.py"],
            meta={"project_dir": str(tmp_path)},
        )
        assert result["build_id"] == "ci-test-001"
        assert result["node_count"] > 0

    def test_kg_ci_append_without_files(self, store):
        """CI hook appends without files."""
        from yuleosh.knowledge_graph.ci_hook import kg_ci_append

        result = kg_ci_append(store, build_id="ci-test-002")
        assert result["build_id"] == "ci-test-002"


# ═══════════════════════════════════════════════════════════════════════
# Test 15: Load test results from multiple sources
# ═══════════════════════════════════════════════════════════════════════

class TestLoadTestResults:

    def test_load_from_pytest_json(self, tmp_path):
        """Load test results from explicit pytest JSON."""
        from yuleosh.knowledge_graph.verify_delta import load_test_results

        json_data = {
            "tests": [
                {"nodeid": "tests/test_foo.py::test_bar", "outcome": "passed"},
            ]
        }
        json_file = tmp_path / "results.json"
        json_file.write_text(json.dumps(json_data))

        results = load_test_results(str(tmp_path), json_path=str(json_file))
        assert len(results) == 1
        assert results[0]["status"] == "pass"

    def test_load_from_junit(self, sample_junit_xml, tmp_path):
        """Load test results from JUnit XML."""
        from yuleosh.knowledge_graph.verify_delta import load_test_results

        xml_file = tmp_path / "junit.xml"
        xml_file.write_text(sample_junit_xml)

        results = load_test_results(str(tmp_path), junit_path=str(xml_file))
        assert len(results) == 3

    def test_load_from_ci_dir(self, tmp_path):
        """Load test results from CI results directory."""
        from yuleosh.knowledge_graph.verify_delta import load_test_results

        ci_dir = tmp_path / ".yuleosh" / "ci"
        ci_dir.mkdir(parents=True)
        (ci_dir / "layer1-abc.json").write_text(json.dumps([
            {"nodeid": "tests/test_ci.py::test_a", "outcome": "passed"},
        ]))

        results = load_test_results(str(tmp_path))
        assert len(results) == 1

    def test_load_from_osh_ci_dir(self, tmp_path):
        """Load test results from .osh/ci/ directory (legacy)."""
        from yuleosh.knowledge_graph.verify_delta import load_test_results

        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True)
        (ci_dir / "layer1-xyz.json").write_text(json.dumps([
            {"nodeid": "tests/test_legacy.py::test_a", "outcome": "passed"},
        ]))

        results = load_test_results(str(tmp_path))
        assert len(results) == 1


# ═══════════════════════════════════════════════════════════════════════
# Test 16: Verify delta parses CI results
# ═══════════════════════════════════════════════════════════════════════

class TestParseYuleoshCiResults:

    def test_parse_ci_results(self, tmp_path):
        """Parse yuleOSH CI test result files."""
        from yuleosh.knowledge_graph.verify_delta import parse_yuleosh_ci_results

        ci_dir = tmp_path / ".yuleosh" / "ci"
        ci_dir.mkdir(parents=True)
        (ci_dir / "layer1-test.json").write_text(json.dumps([
            {"nodeid": "tests/test_mod.py::test_func", "outcome": "passed"},
        ]))

        results = parse_yuleosh_ci_results(str(tmp_path))
        assert len(results) == 1
        assert results[0]["status"] == "pass"

    def test_no_ci_dir(self, tmp_path):
        """No CI results directory returns empty list."""
        from yuleosh.knowledge_graph.verify_delta import parse_yuleosh_ci_results
        assert parse_yuleosh_ci_results(str(tmp_path)) == []
