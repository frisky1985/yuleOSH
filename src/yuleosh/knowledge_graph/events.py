#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Event Bus — lightweight event notification (KG-EVENT-01).

Provides a simple publish/subscribe event bus for KG operations.
Events are emitted by store operations via decorators or explicit calls.

Usage:
    from yuleosh.knowledge_graph.events import kg_events

    # Subscribe
    kg_events.on("node.created", lambda e: print(f"Node created: {e.data}"))

    # Subscribe once
    kg_events.once("build.completed", lambda e: print("Build done!"))

    # Emit
    kg_events.emit("node.created", {"entity_id": "RS-001"})
"""

import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional

log = logging.getLogger("yuleosh.knowledge_graph.events")


class KGDataclass:
    """Minimal event dataclass replacement — avoids dataclass import overhead."""

    __slots__ = ("event_type", "timestamp", "source", "data", "_id")

    def __init__(self, event_type: str, source: str = "kg", data: Optional[dict] = None):
        self.event_type: str = event_type
        self.timestamp: str = datetime.now().isoformat()
        self.source: str = source
        self.data: dict = data or {}
        self._id: str = f"{event_type}-{int(time.time() * 1_000_000)}"

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "source": self.source,
            "data": self.data,
            "id": self._id,
        }

    def __repr__(self):
        return f"<KGEvent {self.event_type} @ {self.timestamp}>"


class EventBus:
    """Thread-safe publish/subscribe event bus for KG operations.

    Thread safety:
      - Subscriptions and emits use a ReentrantLock so that callbacks
        can safely call ``on``/``emit`` from inside other callbacks.
      - A per-event-type list of callbacks is maintained.
      - Exceptions in callbacks are caught and logged (never propagate).
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._callbacks: dict[str, list[dict]] = {}  # event_type → [{fn, once}]
        self._history: list[KGDataclass] = []
        self._max_history = 1000
        self._history_lock = threading.Lock()

    # ── Subscription ──────────────────────────────────────────────────

    def on(self, event_type: str, callback: Callable[[KGDataclass], Any]):
        """Subscribe to an event type.

        Args:
            event_type: Event type string (e.g. "node.created").
            callback: Callable receiving a KGDataclass instance.
        """
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._lock:
            self._callbacks.setdefault(event_type, []).append({
                "fn": callback,
                "once": False,
            })
        log.debug("EventBus: subscribed to '%s'", event_type)

    def once(self, event_type: str, callback: Callable[[KGDataclass], Any]):
        """Subscribe to an event type for one invocation only.

        The callback is removed after the first matching event.
        """
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._lock:
            self._callbacks.setdefault(event_type, []).append({
                "fn": callback,
                "once": True,
            })
        log.debug("EventBus: one-time subscribed to '%s'", event_type)

    def off(self, event_type: str, callback: Optional[Callable] = None):
        """Unsubscribe from an event type.

        Args:
            event_type: Event type string.
            callback: If provided, only that callback is removed.
                      If None, ALL callbacks for that type are removed.
        """
        with self._lock:
            if callback is None:
                self._callbacks.pop(event_type, None)
            else:
                subs = self._callbacks.get(event_type, [])
                self._callbacks[event_type] = [
                    s for s in subs if s["fn"] is not callback
                ]
                if not self._callbacks[event_type]:
                    del self._callbacks[event_type]
        log.debug("EventBus: unsubscribed from '%s'", event_type)

    def clear(self):
        """Remove all subscriptions."""
        with self._lock:
            self._callbacks.clear()

    # ── Emit ──────────────────────────────────────────────────────────

    def emit(self, event_type: str, source: str = "kg", data: Optional[dict] = None):
        """Emit an event.

        Args:
            event_type: Event type string.
            source: Source module name (default: "kg").
            data: Event data dict.

        Returns:
            The KGDataclass that was emitted.
        """
        event = KGDataclass(event_type, source=source, data=data or {})

        # Append to history
        with self._history_lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        # Invoke callbacks
        with self._lock:
            subs = list(self._callbacks.get(event_type, []))
            wildcard_subs = list(self._callbacks.get("*", []))

        all_subs = subs + wildcard_subs
        if not all_subs:
            log.debug("EventBus: '%s' emitted (no subscribers)", event_type)
            return event

        # Execute callbacks while holding the lock only briefly
        for sub in all_subs:
            try:
                sub["fn"](event)
            except Exception:
                log.exception("EventBus: callback error for '%s'", event_type)

        # Clean up one-time subscriptions
        with self._lock:
            for sub in all_subs:
                if sub["once"]:
                    try:
                        self._callbacks[event_type].remove(sub)
                    except (KeyError, ValueError):
                        pass

        log.debug("EventBus: '%s' emitted to %d subscriber(s)",
                  event_type, len(all_subs))
        return event

    # ── History ──────────────────────────────────────────────────────

    def history(self, event_type: Optional[str] = None,
                limit: int = 50) -> list[dict]:
        """Return recent event history, optionally filtered by type.

        Args:
            event_type: Optional filter.
            limit: Max events to return (most recent first).

        Returns:
            List of event dicts.
        """
        with self._history_lock:
            if event_type:
                filtered = [e for e in self._history if e.event_type == event_type]
            else:
                filtered = list(self._history)
        return [e.to_dict() for e in filtered[-limit:]]

    def clear_history(self):
        """Clear the event history."""
        with self._history_lock:
            self._history.clear()


# ── Singleton ──────────────────────────────────────────────────────────

kg_events = EventBus()
"""Global KG event bus instance."""


# ── Store Decorators ───────────────────────────────────────────────────

def emit_on_upsert_node(store: "KGStore", original_upsert):
    """Wrap store.upsert_node to emit events.

    Detects whether the node was created or updated by checking
    if it existed before.

    Usage:
        store.upsert_node = emit_on_upsert_node(store, store.upsert_node)
    """
    import functools

    @functools.wraps(original_upsert)
    def wrapper(node, *args, **kwargs):
        # Check if node exists before upsert
        existing = store.get_node(node.entity_type, node.entity_id)
        was_created = existing is None

        result = original_upsert(node, *args, **kwargs)

        event_type = "node.created" if was_created else "node.updated"
        kg_events.emit(
            event_type,
            source="store.upsert_node",
            data={
                "entity_type": node.entity_type,
                "entity_id": node.entity_id,
                "label": node.label,
                "node_id": result,
            },
        )
        return result

    return wrapper


def emit_on_upsert_edge(store: "KGStore", original_upsert):
    """Wrap store.upsert_edge to emit events."""
    import functools

    @functools.wraps(original_upsert)
    def wrapper(edge, *args, **kwargs):
        existing = store.get_edge(edge.source_id, edge.target_id, edge.edge_type)
        was_created = existing is None

        result = original_upsert(edge, *args, **kwargs)

        event_type = "edge.created" if was_created else "edge.updated"
        kg_events.emit(
            event_type,
            source="store.upsert_edge",
            data={
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "edge_type": edge.edge_type,
                "edge_id": result,
                "layer": edge.layer,
            },
        )
        return result

    return wrapper


def emit_on_delete_node(original_delete):
    """Wrap store.delete_node to emit events."""
    import functools

    @functools.wraps(original_delete)
    def wrapper(entity_type, entity_id, *args, **kwargs):
        result = original_delete(entity_type, entity_id, *args, **kwargs)
        if result:
            kg_events.emit(
                "node.deleted",
                source="store.delete_node",
                data={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                },
            )
        return result

    return wrapper


def emit_on_delete_edge(original_delete):
    """Wrap store.delete_edge to emit events."""
    import functools

    @functools.wraps(original_delete)
    def wrapper(source_id, target_id, edge_type, *args, **kwargs):
        result = original_delete(source_id, target_id, edge_type, *args, **kwargs)
        if result:
            kg_events.emit(
                "edge.deleted",
                source="store.delete_edge",
                data={
                    "source_id": source_id,
                    "target_id": target_id,
                    "edge_type": edge_type,
                },
            )
        return result

    return wrapper


def _emit_on_create_snapshot(original_create):
    """Wrap store.create_snapshot to emit events."""
    import functools

    @functools.wraps(original_create)
    def wrapper(build_id, meta=None, *args, **kwargs):
        result = original_create(build_id, meta=meta, *args, **kwargs)
        kg_events.emit(
            "snapshot.created",
            source="store.create_snapshot",
            data={
                "build_id": build_id,
                "node_count": result.node_count,
                "edge_count": result.edge_count,
            },
        )
        return result

    return wrapper


def instrument_store(store: "KGStore"):
    """Apply event-emitting wrappers to a KGStore instance.

    Idempotent: calling twice has no additional effect.

    Usage:
        store = KGStore()
        instrument_store(store)
    """
    if getattr(store, "_kg_events_instrumented", False):
        return
    store.upsert_node = emit_on_upsert_node(store, store.upsert_node)
    store.upsert_edge = emit_on_upsert_edge(store, store.upsert_edge)
    store.delete_node = emit_on_delete_node(store.delete_node)
    store.delete_edge = emit_on_delete_edge(store.delete_edge)
    store.create_snapshot = _emit_on_create_snapshot(store.create_snapshot)
    store._kg_events_instrumented = True
    log.info("Event instrumentation applied to KGStore")
