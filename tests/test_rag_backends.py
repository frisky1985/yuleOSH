"""Tests for pluggable RAG vector backends (P2-8)."""

import sys
import types

import asyncio
import numpy as np
import pytest

from yuleosh.llm.rag.backends import (
    ChromaBackend,
    FaissBackend,
    create_backend,
)
from yuleosh.llm.rag.engine import RAGEngine


class MockEmbedding:
    name = "mock"

    def embed(self, texts):
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


def _fake_chroma(monkeypatch):
    class FakeCollection:
        def __init__(self):
            self.ids, self.embeddings = [], []

        def upsert(self, ids, embeddings):
            for i, e in zip(ids, embeddings):
                if i in self.ids:
                    self.embeddings[self.ids.index(i)] = e
                else:
                    self.ids.append(i)
                    self.embeddings.append(e)

        def query(self, query_embeddings, n_results):
            n = min(n_results, len(self.ids))
            return {"ids": [self.ids[:n]], "distances": [[0.0] * n]}

        def delete(self, ids):
            for i in ids:
                if i in self.ids:
                    idx = self.ids.index(i)
                    self.ids.pop(idx)
                    self.embeddings.pop(idx)

    class FakeClient:
        def __init__(self):
            self.collection = FakeCollection()

        def get_or_create_collection(self, name):
            return self.collection

    module = types.SimpleNamespace(
        PersistentClient=lambda path: FakeClient())
    monkeypatch.setitem(sys.modules, "chromadb", module)


def _fake_faiss(monkeypatch):
    class FakeIndexFlatL2:
        def __init__(self, dim):
            self.vectors = np.empty((0, dim), dtype="float32")

        def add(self, arr):
            self.vectors = np.concatenate(
                [self.vectors, np.asarray(arr, dtype="float32")], axis=0)

        def search(self, query, k):
            diff = self.vectors - np.asarray(query, dtype="float32")[0]
            dist = np.sum(diff * diff, axis=1)
            idx = np.argsort(dist)[:k]
            return dist[idx].reshape(1, -1), idx.reshape(1, -1)

    monkeypatch.setitem(
        sys.modules, "faiss", types.SimpleNamespace(IndexFlatL2=FakeIndexFlatL2))


class TestFactory:
    def test_unknown_backend(self):
        backend, reason = create_backend("mysql")
        assert backend is None
        assert "未知 RAG 后端" in reason

    def test_chroma_missing_returns_unavailable(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "chromadb", raising=False)
        monkeypatch.setenv("YULEOSH_RAG_CHROMA_DIR", "/tmp/__nope__")
        real_import = __import__

        def _blocked(name, *a, **k):
            if name == "chromadb":
                raise ImportError("chromadb not installed")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _blocked)
        backend, _ = create_backend("chroma")
        assert backend is not None
        assert backend.available is False
        assert "chromadb" in backend.unavailable_reason

    def test_faiss_missing_returns_unavailable(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "faiss", None)
        backend, _ = create_backend("faiss")
        assert backend is not None
        assert backend.available is False
        assert "faiss" in backend.unavailable_reason


class TestChromaBackend:
    def test_upsert_search_clear(self, monkeypatch):
        _fake_chroma(monkeypatch)
        b = ChromaBackend(persist_dir="/tmp/chroma-test")
        assert b.available is True
        assert b.upsert("h1", [1.0, 0.0]) is True
        assert b.count() == 1
        hits = b.search([1.0, 0.0], k=1)
        assert hits[0]["content_hash"] == "h1"
        b.clear()
        assert b.count() == 0

    def test_engine_end_to_end(self, monkeypatch):
        _fake_chroma(monkeypatch)
        engine = RAGEngine(backend="chroma", embedding_provider=MockEmbedding())
        assert engine.backend == "chroma"
        engine.index_best_practices([
            {"id": "bp1", "title": "Brake", "content": "brake system fault diagnosis"},
        ])
        results = asyncio.run(engine.retrieve("brake", top_k=1))
        assert results and results[0].chunk.id == "bp1"


class TestFaissBackend:
    def test_upsert_search_clear(self, monkeypatch):
        _fake_faiss(monkeypatch)
        b = FaissBackend()
        assert b.available is True
        assert b.upsert("h1", [1.0, 0.0]) is True
        assert b.upsert("h1", [1.0, 0.0]) is True  # 幂等
        assert b.count() == 1
        hits = b.search([1.0, 0.0], k=1)
        assert hits[0]["content_hash"] == "h1"
        b.clear()
        assert b.count() == 0

    def test_engine_end_to_end(self, monkeypatch):
        _fake_faiss(monkeypatch)
        engine = RAGEngine(backend="faiss", embedding_provider=MockEmbedding())
        assert engine.backend == "faiss"
        engine.index_best_practices([
            {"id": "bp1", "title": "Brake", "content": "brake system fault diagnosis"},
        ])
        results = asyncio.run(engine.retrieve("brake", top_k=1))
        assert results and results[0].chunk.id == "bp1"


class TestEngineFallback:
    def test_unknown_backend_degrades(self):
        engine = RAGEngine(backend="unknown", embedding_provider=MockEmbedding())
        assert engine.backend == "inmemory"
        assert "未知 RAG 后端" in engine.degraded_reason
