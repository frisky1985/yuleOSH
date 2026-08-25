#!/usr/bin/env python3

# @tests src/yuleosh/knowledge_graph/events.py

"""Deep tests for knowledge_graph/events.py — KG-005 event notification."""

import pytest
import threading

from yuleosh.knowledge_graph.events import EventBus, KGDataclass


class TestKGDataclass:
    def test_basic_creation(self):
        event = KGDataclass("node.created", source="test", data={"id": "RS-001"})
        assert event.event_type == "node.created"
        assert event.source == "test"
        assert event.data == {"id": "RS-001"}
        assert event.timestamp

    def test_to_dict(self):
        event = KGDataclass("build.completed", data={"status": "ok"})
        d = event.to_dict()
        assert d["event_type"] == "build.completed"
        assert d["data"]["status"] == "ok"
        assert "id" in d
        assert "timestamp" in d

    def test_default_data_empty_dict(self):
        event = KGDataclass("test.event")
        assert event.data == {}

    def test_repr(self):
        event = KGDataclass("node.created")
        assert "KGEvent" in repr(event)
        assert "node.created" in repr(event)

    def test_unique_ids(self):
        e1 = KGDataclass("test")
        e2 = KGDataclass("test")
        assert e1._id != e2._id


class TestEventBus:
    def test_on_and_emit(self):
        bus = EventBus()
        received = []
        bus.on("test.event", lambda e: received.append(e))
        bus.emit("test.event", data={"key": "value"})
        assert len(received) == 1
        assert received[0].data == {"key": "value"}

    def test_multiple_subscribers(self):
        bus = EventBus()
        results = []
        bus.on("evt", lambda e: results.append("a"))
        bus.on("evt", lambda e: results.append("b"))
        bus.emit("evt")
        assert results == ["a", "b"]

    def test_once_fires_once(self):
        bus = EventBus()
        count = []
        bus.once("evt", lambda e: count.append(1))
        bus.emit("evt")
        bus.emit("evt")
        assert len(count) == 1

    def test_no_subscribers_no_error(self):
        bus = EventBus()
        bus.emit("nonexistent.event")

    def test_callback_exception_does_not_propagate(self):
        bus = EventBus()
        bus.on("evt", lambda e: 1 / 0)
        bus.on("evt", lambda e: None)
        bus.emit("evt")

    def test_history_recorded(self):
        bus = EventBus()
        bus.emit("evt1", {"a": 1})
        bus.emit("evt2", {"b": 2})
        assert len(bus._history) == 2

    def test_history_max_limit(self):
        bus = EventBus()
        bus._max_history = 5
        for i in range(10):
            bus.emit(f"evt-{i}")
        assert len(bus._history) <= 5

    def test_thread_safety(self):
        bus = EventBus()
        counter = {"value": 0}
        lock = threading.Lock()

        def callback(e):
            with lock:
                counter["value"] += 1

        bus.on("inc", callback)
        threads = [threading.Thread(target=bus.emit, args=("inc",)) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert counter["value"] == 50

    def test_different_event_types_isolated(self):
        bus = EventBus()
        a_count = []
        b_count = []
        bus.on("a", lambda e: a_count.append(1))
        bus.on("b", lambda e: b_count.append(1))
        bus.emit("a")
        bus.emit("a")
        bus.emit("b")
        assert len(a_count) == 2
        assert len(b_count) == 1
