# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Unit tests for yuleOSH Memory — fact store + session search."""

import os
import tempfile

import pytest

from yuleosh.memory.store import MemoryStore


@pytest.fixture()
def store(tmp_path):
    """MemoryStore isolated in a temp dir (no repo pollution)."""
    db = tmp_path / "memory.db"
    s = MemoryStore(db_path=str(db))
    yield s
    s.close()


# ── remember / get / list ────────────────────────────────────────────────

def test_remember_creates_fact(store):
    fact = store.remember("hub gRPC port is 8080", entity="hub",
                          category="architecture")
    assert fact["id"] > 0
    assert fact["content"] == "hub gRPC port is 8080"
    assert fact["entity"] == "hub"
    assert fact["category"] == "architecture"
    assert fact["trust"] == pytest.approx(0.5)
    assert fact["recall_count"] == 0
    assert fact["created_at"]


def test_remember_custom_trust_clamped(store):
    f1 = store.remember("high trust", trust=1.5)
    f2 = store.remember("low trust", trust=-0.2)
    f3 = store.remember("mid trust", trust=0.7)
    assert f1["trust"] == pytest.approx(1.0)
    assert f2["trust"] == pytest.approx(0.0)
    assert f3["trust"] == pytest.approx(0.7)


def test_list_facts_filters(store):
    store.remember("fact a", entity="e1", category="cat1")
    store.remember("fact b", entity="e2", category="cat2")
    store.remember("fact c", entity="e1", category="cat2")

    by_cat = store.list_facts(category="cat2")
    assert len(by_cat) == 2

    by_ent = store.list_facts(entity="e1")
    assert len(by_ent) == 2

    both = store.list_facts(category="cat2", entity="e1")
    assert len(both) == 1
    assert both[0]["content"] == "fact c"


# ── recall + trust reinforcement ─────────────────────────────────────────

def test_recall_matches_content(store):
    store.remember("SCP03 secure channel established", entity="se050",
                   category="security")
    store.remember("unrelated note", entity="other", category="general")

    hits = store.recall("SCP03")
    assert len(hits) == 1
    assert hits[0]["entity"] == "se050"


def test_recall_bumps_trust_and_count(store):
    fact = store.remember("replay protection uses seq+ts", entity="carsim",
                          category="security")

    store.recall("replay protection")
    store.recall("replay protection")

    updated = store.get_fact(fact["id"])
    assert updated["recall_count"] == 2
    assert updated["trust"] == pytest.approx(0.5 + 2 * 0.1)
    # Five total recalls → 0.5 + 5*0.1 = 1.0, trust caps at 1.0
    store.recall("replay protection")
    store.recall("replay protection")
    store.recall("replay protection")
    updated = store.get_fact(fact["id"])
    assert updated["trust"] == pytest.approx(1.0)


def test_recall_filters(store):
    store.remember("alpha config", entity="ecu_a", category="config")
    store.remember("alpha config", entity="ecu_b", category="config")

    hits = store.recall("alpha", entity="ecu_a")
    assert len(hits) == 1
    assert hits[0]["entity"] == "ecu_a"


def test_forget_removes_fact(store):
    fact = store.remember("temporary note")
    assert store.forget(fact["id"]) is True
    assert store.get_fact(fact["id"]) is None
    assert store.forget(fact["id"]) is False  # already gone


def test_update_trust_explicit(store):
    fact = store.remember("manual override")
    updated = store.update_trust(fact["id"], 0.9)
    assert updated["trust"] == pytest.approx(0.9)


def test_stats(store):
    store.remember("one", category="a")
    store.remember("two", category="b")
    store.remember("three", category="b")
    st = store.stats()
    assert st["facts"] == 3
    assert st["by_category"]["b"] == 2


# ── Session log + FTS search ─────────────────────────────────────────────

def test_log_session_and_search(store):
    store.log_session("Decided to use kustomize for deployment",
                      session_key="s1", kind="decision")
    store.log_session("Reviewed MISRA baseline", session_key="s2", kind="review")

    hits = store.search_sessions("kustomize")
    assert len(hits) == 1
    assert hits[0]["kind"] == "decision"
    assert "kustomize" in hits[0]["snippet"] or "kustomize" in hits[0]["content"]

    hits = store.search_sessions("MISRA")
    assert len(hits) == 1
    assert hits[0]["session_key"] == "s2"


def test_session_search_malformed_query_falls_back(store):
    store.log_session("plain text note")
    # A stray quote breaks FTS5 MATCH — must fall back to LIKE, not crash.
    hits = store.search_sessions('stray " quote')
    assert isinstance(hits, list)


def test_idempotent_setup(store, tmp_path):
    """Repeated MemoryStore init on same db must not error."""
    db = tmp_path / "memory2.db"
    MemoryStore(db_path=str(db)).close()
    MemoryStore(db_path=str(db)).close()
    MemoryStore(db_path=str(db)).close()  # no error


def test_env_db_override(tmp_path, monkeypatch):
    db = tmp_path / "env.db"
    monkeypatch.setenv("YULEOSH_MEMORY_DB", str(db))
    s = MemoryStore()
    s.remember("env-driven db")
    assert db.exists()
    assert s.stats()["facts"] == 1
    s.close()
