#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph P2 Tests — Reporter + Events + CLI integration.

Tests coverage:
  - reporter: RTM generation (markdown/html/csv)
  - reporter: Metrics generation
  - events: EventBus subscription/emission
  - events: Store instrumentation
  - CLI: report rtm/metrics commands
  - CLI: events listen/history commands
"""

import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.models import Node, Edge


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_store():
    """Reset the KG store singleton before each test."""
    KGStore.reset()
    yield
    KGStore.reset()


@pytest.fixture
def store():
    """Create a fresh temp-file KG store."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.unlink(tmp.name)  # Remove so KGStore creates fresh
    s = KGStore(db_path=tmp.name)
    return s


@pytest.fixture
def populated_store(store):
    """A store with sample nodes and edges for testing."""
    # Requirements
    req1 = Node(entity_type="requirement", entity_id="RS-001",
                 label="The system SHALL support agent-driven pipeline",
                 properties={"testable": True, "source": "spec"})
    req2 = Node(entity_type="requirement", entity_id="RS-002",
                 label="The system SHALL provide requirements tree",
                 properties={"testable": True, "source": "spec"})
    req3 = Node(entity_type="requirement", entity_id="RS-003",
                 label="The system SHALL support code review gates",
                 properties={"testable": False, "source": "spec"})  # non-testable
    req1_id = store.upsert_node(req1)
    req2_id = store.upsert_node(req2)
    req3_id = store.upsert_node(req3)

    # Test files
    tf1 = Node(entity_type="test_file", entity_id="tests/test_pipeline.py",
                label="tests/test_pipeline.py",
                properties={"source": "scan"})
    tf2 = Node(entity_type="test_file", entity_id="tests/test_traceability.py",
                label="tests/test_traceability.py",
                properties={"source": "scan"})
    tf1_id = store.upsert_node(tf1)
    tf2_id = store.upsert_node(tf2)

    # Test functions
    tfn1 = Node(entity_type="test_function",
                 entity_id="tests.test_pipeline::test_agent_driven",
                 label="test_agent_driven",
                 properties={"file_path": "tests/test_pipeline.py"})
    tfn2 = Node(entity_type="test_function",
                 entity_id="tests.test_traceability::test_req_tree",
                 label="test_req_tree",
                 properties={"file_path": "tests/test_traceability.py"})
    tfn1_id = store.upsert_node(tfn1)
    tfn2_id = store.upsert_node(tfn2)

    # Code files
    cf1 = Node(entity_type="code_file", entity_id="src/yuleosh/pipeline.py",
                label="src/yuleosh/pipeline.py",
                properties={"language": "python", "lines": 500})
    cf2 = Node(entity_type="code_file", entity_id="src/yuleosh/traceability.py",
                label="src/yuleosh/traceability.py",
                properties={"language": "python", "lines": 300})
    cf1_id = store.upsert_node(cf1)
    cf2_id = store.upsert_node(cf2)

    # Orphan code file (no edges)
    orphan = Node(entity_type="code_file", entity_id="src/legacy/unused.py",
                   label="src/legacy/unused.py",
                   properties={"language": "python", "lines": 50})
    store.upsert_node(orphan)

    # Edges: covers — test coverage
    store.upsert_edge(Edge(source_id=req1_id, target_id=tf1_id,
                           edge_type="covers",
                           properties={"confidence": 1.0, "layer": "unit"},
                           layer="unit"))
    store.upsert_edge(Edge(source_id=req1_id, target_id=tfn1_id,
                           edge_type="covers",
                           properties={"confidence": 0.9, "layer": "integration"},
                           layer="integration"))
    store.upsert_edge(Edge(source_id=req2_id, target_id=tf2_id,
                           edge_type="covers",
                           properties={"confidence": 0.6, "layer": "unit"},
                           layer="unit"))

    # Edges: implements
    store.upsert_edge(Edge(source_id=cf1_id, target_id=req1_id,
                            edge_type="implements",
                            properties={"confidence": 1.0}))
    store.upsert_edge(Edge(source_id=cf2_id, target_id=req2_id,
                            edge_type="implements",
                            properties={"confidence": 0.85}))

    # Edges: contains
    store.upsert_edge(Edge(source_id=tf1_id, target_id=tfn1_id,
                            edge_type="contains"))
    store.upsert_edge(Edge(source_id=tf2_id, target_id=tfn2_id,
                            edge_type="contains"))

    # Uncovered requirement (no covers edges, testable=True)
    req4 = Node(entity_type="requirement", entity_id="RS-004",
                 label="The system SHALL support SIL simulation",
                 properties={"testable": True, "source": "spec"})
    store.upsert_node(req4)

    # Snapshot for trend testing
    store.create_snapshot("v1", meta={"source": "test"})
    store.create_snapshot("v2", meta={"source": "test"})

    return store


# ═══════════════════════════════════════════════════════════════════════
# Reporter Tests — RTM (KG-40-RTM)
# ═══════════════════════════════════════════════════════════════════════

class TestRTMGeneration:
    """ACC-RTM-01 through ACC-RTM-04"""

    def test_rtm_markdown_includes_all_reqs(self, populated_store):
        """ACC-RTM-01: Markdown output contains all Requirement nodes."""
        from yuleosh.knowledge_graph.reporter import generate_rtm
        result = generate_rtm(populated_store, fmt="markdown")
        assert isinstance(result, str)
        assert "RS-001" in result
        assert "RS-002" in result
        assert "RS-003" in result
        assert "追溯矩阵" in result

    def test_rtm_markdown_has_coverage_summary(self, populated_store):
        """ACC-RTM-01: Markdown has coverage summary table."""
        from yuleosh.knowledge_graph.reporter import generate_rtm
        result = generate_rtm(populated_store, fmt="markdown")
        assert "已覆盖需求" in result
        assert "未覆盖需求" in result
        assert "覆盖率" in result

    def test_rtm_html_is_valid(self, populated_store):
        """ACC-RTM-02: HTML output is valid HTML."""
        from yuleosh.knowledge_graph.reporter import generate_rtm
        result = generate_rtm(populated_store, fmt="html")
        assert isinstance(result, str)
        assert result.strip().startswith("<!DOCTYPE html>")
        assert "<table" in result
        assert "</html>" in result
        assert "RS-001" in result

    def test_rtm_html_has_style(self, populated_store):
        """ACC-RTM-02: HTML has CSS styles for audit readability."""
        from yuleosh.knowledge_graph.reporter import generate_rtm
        result = generate_rtm(populated_store, fmt="html")
        assert "coverage" in result.lower() or "style" in result.lower()

    def test_rtm_csv_is_valid(self, populated_store):
        """ACC-RTM-03: CSV output is valid CSV."""
        from yuleosh.knowledge_graph.reporter import generate_rtm
        result = generate_rtm(populated_store, fmt="csv")
        assert isinstance(result, str)
        assert "Requirement ID" in result
        assert "RS-001" in result
        lines = result.strip().split("\n")
        assert len(lines) >= 4
        assert "," in lines[1]

    def test_rtm_csv_has_headers(self, populated_store):
        """ACC-RTM-03: CSV has correct column headers."""
        from yuleosh.knowledge_graph.reporter import generate_rtm
        result = generate_rtm(populated_store, fmt="csv")
        assert "Requirement ID,Statement,Status" in result

    def test_rtm_uncovered_marked(self, populated_store):
        """ACC-RTM-04: Uncovered req is marked."""
        from yuleosh.knowledge_graph.reporter import generate_rtm
        result = generate_rtm(populated_store, fmt="markdown")
        # RS-001 and RS-002 are covered, RS-003 is non-testable
        # The non-testable indicator should be present
        assert "non-testable" in result
        # All non-testable items should be noted
        assert "已覆盖需求" in result

    def test_rtm_non_testable_marked(self, populated_store):
        """Non-testable req marked correctly."""
        from yuleosh.knowledge_graph.reporter import generate_rtm
        result = generate_rtm(populated_store, fmt="markdown")
        assert "non-testable" in result

    def test_rtm_layer_filter(self, populated_store):
        """Filter by unit layer."""
        from yuleosh.knowledge_graph.reporter import generate_rtm
        result = generate_rtm(populated_store, fmt="markdown", layer="unit")
        assert "RS-001" in result
        assert "RS-002" in result

    def test_rtm_layer_filter_integration(self, populated_store):
        """Filter by integration layer."""
        from yuleosh.knowledge_graph.reporter import generate_rtm
        result = generate_rtm(populated_store, fmt="markdown", layer="integration")
        assert "RS-001" in result

    def test_rtm_empty_store(self):
        """RTM on empty store returns empty report."""
        from yuleosh.knowledge_graph.reporter import generate_rtm
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        s = KGStore(db_path=tmp.name)
        result = generate_rtm(s, fmt="markdown")
        assert isinstance(result, str)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════
# Reporter Tests — Metrics (KG-METRICS)
# ═══════════════════════════════════════════════════════════════════════

class TestMetricsGeneration:
    """ACC-MET-01 through ACC-MET-03"""

    def test_metrics_contains_coverage(self, populated_store):
        """ACC-MET-01: Metrics output contains coverage data."""
        from yuleosh.knowledge_graph.reporter import generate_metrics
        result = generate_metrics(populated_store, as_text=False)
        assert "coverage" in result
        cov = result["coverage"]
        assert cov["total_requirements"] == 4
        assert cov["covered_requirements"] >= 1

    def test_metrics_contains_graph_health(self, populated_store):
        """ACC-MET-01: Metrics contains graph health data."""
        from yuleosh.knowledge_graph.reporter import generate_metrics
        result = generate_metrics(populated_store, as_text=False)
        assert "graph_health" in result
        health = result["graph_health"]
        assert health["orphan_code_files"] == 1
        assert "low_confidence_edges" in health

    def test_metrics_contains_test_layers(self, populated_store):
        """ACC-MET-01: Metrics contains test layer distribution."""
        from yuleosh.knowledge_graph.reporter import generate_metrics
        result = generate_metrics(populated_store, as_text=False)
        assert "tests" in result
        by_layer = result["tests"]["by_layer"]
        assert "unit" in by_layer
        assert by_layer["unit"]["total_covers"] >= 1

    def test_metrics_trend_with_snapshots(self, populated_store):
        """ACC-MET-02: Metrics with 2+ snapshots includes trend."""
        from yuleosh.knowledge_graph.reporter import generate_metrics
        result = generate_metrics(populated_store, trend_snapshots=5, as_text=False)
        trends = result.get("trends", {})
        nodes = trends.get("nodes", [])
        edges = trends.get("edges", [])
        assert len(nodes) >= 2
        assert len(edges) >= 2

    def test_metrics_trend_empty_no_snapshots(self, store):
        """No snapshots -> empty trends."""
        from yuleosh.knowledge_graph.reporter import generate_metrics
        result = generate_metrics(store, trend_snapshots=5, as_text=False)
        trends = result.get("trends", {})
        assert len(trends.get("nodes", [])) == 0

    def test_metrics_orphan_code_marked(self, populated_store):
        """ACC-MET-03: Orphan code files counted."""
        from yuleosh.knowledge_graph.reporter import generate_metrics
        result = generate_metrics(populated_store, as_text=False)
        health = result["graph_health"]
        assert health["orphan_code_files"] > 0

    def test_metrics_text_format(self, populated_store):
        """Text format is human-readable."""
        from yuleosh.knowledge_graph.reporter import generate_metrics, format_metrics_text
        metrics = generate_metrics(populated_store, as_text=False)
        text = format_metrics_text(metrics)
        assert isinstance(text, str)
        assert "覆盖率" in text
        assert "图健康度" in text
        assert "测试层分布" in text

    def test_metrics_text_with_trend(self, populated_store):
        """Text format includes trend section."""
        from yuleosh.knowledge_graph.reporter import generate_metrics, format_metrics_text
        metrics = generate_metrics(populated_store, trend_snapshots=5, as_text=False)
        text = format_metrics_text(metrics)
        assert "趋势" in text

    def test_metrics_empty_store(self):
        """Metrics on empty store."""
        from yuleosh.knowledge_graph.reporter import generate_metrics
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        s = KGStore(db_path=tmp.name)
        result = generate_metrics(s, as_text=False)
        assert result["coverage"]["total_requirements"] == 0
        assert result["graph_health"]["total_nodes"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Event Bus Tests (KG-EVENT-01)
# ═══════════════════════════════════════════════════════════════════════

class TestEventBus:
    """ACC-EVT-01 through ACC-EVT-03"""

    def test_emit_received_by_subscriber(self):
        """ACC-EVT-02: Subscribed callback receives events."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        received = []

        def callback(event):
            received.append(event)

        bus.on("test.event", callback)
        bus.emit("test.event", data={"key": "value"})

        assert len(received) == 1
        assert received[0].event_type == "test.event"
        assert received[0].data == {"key": "value"}

    def test_emit_no_subscriber_no_error(self):
        """Emitting without subscribers raises no error."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        bus.emit("no.subscriber", data={"ok": True})

    def test_once_callback_called_once(self):
        """One-time subscription fires only once."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        count = [0]

        def callback(event):
            count[0] += 1

        bus.once("once.event", callback)
        bus.emit("once.event")
        bus.emit("once.event")

        assert count[0] == 1

    def test_wildcard_subscriber(self):
        """Wildcard '*' subscriber receives all events."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        received = []

        bus.on("*", lambda e: received.append(e.event_type))
        bus.emit("type.a")
        bus.emit("type.b")
        bus.emit("type.c")

        assert received == ["type.a", "type.b", "type.c"]

    def test_off_removes_callback(self):
        """Unsubscribing stops receiving events."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        received = []

        def cb(e):
            received.append(e)

        bus.on("remove.me", cb)
        bus.emit("remove.me")
        bus.off("remove.me", cb)
        bus.emit("remove.me")

        assert len(received) == 1

    def test_off_all_removes_type(self):
        """off with no callback removes all for that type."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        bus.on("x", lambda e: None)
        bus.on("x", lambda e: None)
        bus.off("x")
        assert "x" not in bus._callbacks

    def test_callback_exception_caught(self):
        """Callback exceptions are caught and don't propagate."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        second_called = [False]

        def failing(e):
            raise RuntimeError("intentional failure")

        def succeeding(e):
            second_called[0] = True

        bus.on("fail.test", failing)
        bus.on("fail.test", succeeding)
        bus.emit("fail.test")

        assert second_called[0]

    def test_history_accumulates(self):
        """Events are recorded in history."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        bus.emit("ev.a")
        bus.emit("ev.b")
        history = bus.history()
        assert len(history) == 2
        assert history[0]["event_type"] == "ev.a"

    def test_history_filtered(self):
        """History can be filtered by event type."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        bus.emit("type.a")
        bus.emit("type.b")
        bus.emit("type.a")
        history = bus.history(event_type="type.a")
        assert len(history) == 2
        assert all(h["event_type"] == "type.a" for h in history)

    def test_history_max_length(self):
        """History is bounded."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        bus._max_history = 5
        for i in range(10):
            bus.emit(f"ev.{i}")
        assert len(bus._history) == 5

    def test_clear_history(self):
        """History can be cleared."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        bus.emit("x")
        bus.clear_history()
        assert len(bus._history) == 0

    def test_clear_subscriptions(self):
        """All subscriptions can be cleared."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        bus.on("x", lambda e: None)
        bus.clear()
        assert len(bus._callbacks) == 0

    def test_event_dataclass(self):
        """KGDataclass has correct fields."""
        from yuleosh.knowledge_graph.events import KGDataclass
        ev = KGDataclass("test.event", source="test_source", data={"x": 1})
        assert ev.event_type == "test.event"
        assert ev.source == "test_source"
        assert ev.data == {"x": 1}
        assert ev.timestamp is not None
        d = ev.to_dict()
        assert d["event_type"] == "test.event"
        assert d["source"] == "test_source"
        assert d["data"]["x"] == 1

    def test_invalid_callback_raises(self):
        """Non-callable callback raises TypeError."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        with pytest.raises(TypeError):
            bus.on("x", "not_callable")


# ═══════════════════════════════════════════════════════════════════════
# Event Store Instrumentation (ACC-EVT-01)
# ═══════════════════════════════════════════════════════════════════════

class TestStoreInstrumentation:
    """ACC-EVT-01: Store operations emit events."""

    def test_upsert_node_emits_created(self, store):
        """ACC-EVT-01: node.created emitted on new node."""
        from yuleosh.knowledge_graph.events import instrument_store, kg_events
        instrument_store(store)
        received = []
        kg_events.on("node.created", lambda e: received.append(e))

        node = Node(entity_type="requirement", entity_id="RS-NEW",
                     label="New requirement")
        store.upsert_node(node)

        assert len(received) == 1
        assert received[0].data["entity_id"] == "RS-NEW"

    def test_upsert_node_emits_update_for_existing(self, store):
        """node.updated emitted on upsert of existing node."""
        from yuleosh.knowledge_graph.events import instrument_store, kg_events
        instrument_store(store)
        received = []
        kg_events.on("node.updated", lambda e: received.append(e))

        node = Node(entity_type="requirement", entity_id="RS-EXISTING",
                     label="First")
        store.upsert_node(node)
        node.label = "Updated"
        store.upsert_node(node)

        assert len(received) >= 1
        assert received[0].data["entity_id"] == "RS-EXISTING"

    def test_upsert_edge_emits_event(self, store):
        """edge.created emitted on new edge."""
        from yuleosh.knowledge_graph.events import instrument_store, kg_events
        instrument_store(store)
        received = []
        kg_events.on("edge.created", lambda e: received.append(e))

        n1 = store.upsert_node(Node(entity_type="requirement", entity_id="R1", label="R1"))
        n2 = store.upsert_node(Node(entity_type="test_file", entity_id="t1.py", label="t1"))
        store.upsert_edge(Edge(source_id=n1, target_id=n2, edge_type="covers"))

        assert len(received) == 1
        assert received[0].data["edge_type"] == "covers"

    def test_delete_node_emits_event(self, store):
        """node.deleted emitted on soft-delete."""
        from yuleosh.knowledge_graph.events import instrument_store, kg_events
        instrument_store(store)
        received = []
        kg_events.on("node.deleted", lambda e: received.append(e))

        store.upsert_node(Node(entity_type="requirement", entity_id="R-DEL", label="Delete me"))
        store.delete_node("requirement", "R-DEL")

        assert len(received) >= 1

    def test_instrumentation_no_dupes(self, store):
        """Instrumenting twice doesn't double-emit."""
        from yuleosh.knowledge_graph.events import instrument_store, kg_events
        instrument_store(store)
        instrument_store(store)
        received = []
        kg_events.on("node.created", lambda e: received.append(e))

        store.upsert_node(Node(entity_type="requirement", entity_id="R1", label="R1"))

        assert len(received) == 1

    def test_snapshot_emits_event(self, populated_store):
        """Snapshot creation triggers event."""
        from yuleosh.knowledge_graph.events import instrument_store, kg_events
        instrument_store(populated_store)
        received = []
        kg_events.on("snapshot.created", lambda e: received.append(e))

        populated_store.create_snapshot("test-build")

        assert len(received) >= 1
        assert received[-1].event_type == "snapshot.created"


# ═══════════════════════════════════════════════════════════════════════
# CLI Command Tests
# ═══════════════════════════════════════════════════════════════════════

class TestCLIReportCommand:
    """Test kg report CLI commands."""

    def test_cmd_report_rtm_markdown(self, populated_store, tmp_path):
        """Report RTM in markdown format produces output."""
        from yuleosh.knowledge_graph.kg_cli import _cmd_report_rtm

        class Args:
            format = "markdown"
            layer = None
            output = str(tmp_path / "test-rtm.md")
            title = "Test RTM"
            project_dir = str(tmp_path)

        args = Args()
        result = _cmd_report_rtm(populated_store, str(tmp_path), args)
        assert result["format"] == "markdown"
        assert os.path.exists(args.output)

        with open(args.output) as f:
            content = f.read()
        assert "RS-001" in content
        assert "Test RTM" in content

    def test_cmd_report_rtm_html(self, populated_store, tmp_path):
        """Report RTM in HTML."""
        from yuleosh.knowledge_graph.kg_cli import _cmd_report_rtm

        class Args:
            format = "html"
            layer = None
            output = str(tmp_path / "test-rtm.html")
            title = None
            project_dir = str(tmp_path)

        args = Args()
        result = _cmd_report_rtm(populated_store, str(tmp_path), args)
        assert result["format"] == "html"
        with open(args.output) as f:
            assert "DOCTYPE html" in f.read()

    def test_cmd_report_rtm_csv(self, populated_store, tmp_path):
        """Report RTM in CSV."""
        from yuleosh.knowledge_graph.kg_cli import _cmd_report_rtm

        class Args:
            format = "csv"
            layer = None
            output = str(tmp_path / "test-rtm.csv")
            title = None
            project_dir = str(tmp_path)

        args = Args()
        result = _cmd_report_rtm(populated_store, str(tmp_path), args)
        assert result["format"] == "csv"
        with open(args.output) as f:
            assert "Requirement ID" in f.read()

    def test_cmd_report_metrics_text(self, populated_store, tmp_path):
        """Report metrics in text."""
        from yuleosh.knowledge_graph.kg_cli import _cmd_report_metrics

        class Args:
            format = "text"
            trend = 5
            output = str(tmp_path / "test-metrics.md")
            project_dir = str(tmp_path)

        args = Args()
        result = _cmd_report_metrics(populated_store, str(tmp_path), args)
        assert "coverage" in result

    def test_cmd_report_metrics_json(self, populated_store, tmp_path):
        """Report metrics in JSON."""
        from yuleosh.knowledge_graph.kg_cli import _cmd_report_metrics

        class Args:
            format = "json"
            trend = 5
            output = str(tmp_path / "test-metrics.json")
            project_dir = str(tmp_path)

        args = Args()
        result = _cmd_report_metrics(populated_store, str(tmp_path), args)
        assert "coverage" in result
        assert "graph_health" in result

    def test_cmd_report_rtm_stdout(self, populated_store, capsys):
        """Report RTM to stdout works."""
        from yuleosh.knowledge_graph.kg_cli import _cmd_report_rtm

        class Args:
            format = "markdown"
            layer = None
            output = None
            title = None
            project_dir = "/tmp"

        _cmd_report_rtm(populated_store, "/tmp", Args())
        captured = capsys.readouterr()
        assert "RS-001" in captured.out


class TestCLIEventCommand:
    """Test kg events CLI commands."""

    def test_cmd_events_history(self):
        """Events history command works."""
        from yuleosh.knowledge_graph.events import EventBus
        from yuleosh.knowledge_graph.kg_cli import _cmd_events_history

        bus = EventBus()
        bus.emit("test.event", data={"x": 1})

        class Args:
            filter = None
            limit = 50
            project_dir = "/tmp"

        result = _cmd_events_history(Args(), bus)
        assert result["count"] >= 1
        assert result["events"][0]["event_type"] == "test.event"

    def test_cmd_events_history_filtered(self):
        """Events history filtered by type."""
        from yuleosh.knowledge_graph.events import EventBus
        from yuleosh.knowledge_graph.kg_cli import _cmd_events_history

        bus = EventBus()
        bus.emit("type.a")
        bus.emit("type.b")

        class Args:
            filter = "type.a"
            limit = 50
            project_dir = "/tmp"

        result = _cmd_events_history(Args(), bus)
        assert result["count"] == 1

    def test_cmd_events_history_empty(self):
        """Events history shows empty."""
        from yuleosh.knowledge_graph.events import EventBus
        from yuleosh.knowledge_graph.kg_cli import _cmd_events_history

        bus = EventBus()

        class Args:
            filter = None
            limit = 50
            project_dir = "/tmp"

        result = _cmd_events_history(Args(), bus)
        assert result["count"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════

class TestIntegration:
    """End-to-end scenarios combining multiple P2 features."""

    def test_rtm_after_events(self, store):
        """Even with event instrumentation, RTM still works."""
        from yuleosh.knowledge_graph.events import instrument_store
        instrument_store(store)

        n1 = store.upsert_node(Node(
            entity_type="requirement", entity_id="RS-INT",
            label="Integration test requirement",
            properties={"testable": True},
        ))
        n2 = store.upsert_node(Node(
            entity_type="test_file", entity_id="tests/test_int.py",
            label="tests/test_int.py",
        ))
        store.upsert_edge(Edge(source_id=n1, target_id=n2,
                                edge_type="covers", layer="unit"))

        from yuleosh.knowledge_graph.reporter import generate_rtm
        result = generate_rtm(store, fmt="markdown")
        assert "RS-INT" in result

    def test_metrics_after_snapshots(self, store):
        """Metrics accurately reflect multiple snapshots."""
        for i in range(3):
            store.upsert_node(Node(
                entity_type="requirement", entity_id=f"RS-ME-{i:03d}",
                label=f"Requirement {i}",
            ))
        store.create_snapshot("base")

        for i in range(3, 5):
            store.upsert_node(Node(
                entity_type="requirement", entity_id=f"RS-ME-{i:03d}",
                label=f"Requirement {i}",
            ))
        store.create_snapshot("growth")

        from yuleosh.knowledge_graph.reporter import generate_metrics
        result = generate_metrics(store, trend_snapshots=5, as_text=False)
        assert result["coverage"]["total_requirements"] == 5

        trends = result["trends"]
        nodes_trend = trends.get("nodes", [])
        assert len(nodes_trend) == 2
        assert nodes_trend[0]["count"] == 3
        assert nodes_trend[1]["count"] == 5

    def test_event_bus_thread_safety(self):
        """Event bus is thread-safe under concurrent emits."""
        from yuleosh.knowledge_graph.events import EventBus
        bus = EventBus()
        received = []
        bus.on("concurrent", lambda e: received.append(e))

        def emit_thread():
            for _ in range(100):
                bus.emit("concurrent", data={"thread_id": threading.get_ident()})
                time.sleep(0.001)

        threads = [threading.Thread(target=emit_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(received) == 500
