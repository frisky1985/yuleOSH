"""Tests for kb/embedding.py + kb/vector_store.py — Embedding + sqlite-vec (EI-M3C)."""

# @tests src/yuleosh/kb/store.py

import os
import sqlite3
import tempfile

import pytest

from yuleosh.kb.embedding import (
    EmbeddingUnavailableError,
    HttpEmbeddingProvider,
    OllamaEmbeddingProvider,
    get_provider,
)
from yuleosh.kb.vector_store import VectorStore, load_vector_extension


# ── EI-M3C.1: EmbeddingProvider 抽象 ──────────────────────────────────

class TestEmbeddingProviders:
    def test_factory_ollama(self):
        p = get_provider("ollama")
        assert p.name == "ollama"

    def test_factory_http(self):
        p = get_provider("http", api_key="sk-test")
        assert p.name == "http"

    def test_factory_unknown(self):
        with pytest.raises(ValueError):
            get_provider("bogus")

    def test_http_requires_key(self):
        """GIVEN 无 api_key WHEN available THEN False（不可用降级）。"""
        p = HttpEmbeddingProvider(api_key="")
        assert p.available() is False

    def test_http_embed_empty(self):
        """GIVEN 空列表 WHEN embed THEN 返回空（不发请求）。"""
        p = HttpEmbeddingProvider(api_key="sk-test")
        assert p.embed([]) == []

    def test_ollama_embed_empty(self):
        p = OllamaEmbeddingProvider()
        assert p.embed([]) == []

    def test_ollama_unavailable_raises(self):
        """GIVEN Ollama 不可达 WHEN embed THEN EmbeddingUnavailableError。"""
        p = OllamaEmbeddingProvider(base_url="http://127.0.0.1:1", timeout_s=1)
        with pytest.raises(EmbeddingUnavailableError):
            p.embed(["hello"])


# ── EI-M3C.2/.3: sqlite-vec 向量表 ────────────────────────────────────

@pytest.fixture
def conn():
    """临时 SQLite 连接。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()
    os.unlink(db_path)


class TestVectorStore:
    def test_load_extension(self, conn):
        """GIVEN sqlite-vec 已装 WHEN load THEN True。"""
        assert load_vector_extension(conn) is True

    def test_upsert_and_count(self, conn):
        """GIVEN 写入向量 WHEN count THEN 计数正确。"""
        vs = VectorStore(conn)
        assert vs.available
        assert vs.upsert("hash-a", [0.1] * 768, rowid=1)
        assert vs.upsert("hash-b", [0.2] * 768, rowid=2)
        assert vs.count() == 2

    def test_upsert_idempotent(self, conn):
        """GIVEN 同 hash 写两次 WHEN count THEN 只 1 条（幂等）。"""
        vs = VectorStore(conn)
        vs.upsert("hash-a", [0.1] * 768, rowid=1)
        vs.upsert("hash-a", [0.9] * 768, rowid=1)
        assert vs.count() == 1

    def test_search_nearest(self, conn):
        """GIVEN 查询向量 WHEN search THEN 最近邻优先。"""
        vs = VectorStore(conn)
        # 目标: 全 1.0；干扰: 全 -1.0
        vs.upsert("target", [1.0] * 768, rowid=1)
        vs.upsert("noise", [-1.0] * 768, rowid=2)
        results = vs.search([1.0] * 768, k=10)
        assert results[0]["content_hash"] == "target"
        assert results[0]["distance"] < results[1]["distance"]

    def test_search_content_hash_filter(self, conn):
        """GIVEN content_hashes 过滤 WHEN search THEN 只搜指定集（租户隔离预留）。"""
        vs = VectorStore(conn)
        vs.upsert("tenant-a", [1.0] * 768, rowid=1)
        vs.upsert("tenant-b", [1.0] * 768, rowid=2)
        results = vs.search([1.0] * 768, k=10, content_hashes=["tenant-a"])
        assert len(results) == 1
        assert results[0]["content_hash"] == "tenant-a"

    def test_dim_guard(self, conn):
        """GIVEN 超维度向量 WHEN upsert THEN ValueError。"""
        vs = VectorStore(conn)
        with pytest.raises(ValueError):
            vs.upsert("h", [0.1] * 4096)

    def test_graceful_unavailable(self, monkeypatch, conn):
        """GIVEN 扩展不可加载 WHEN VectorStore THEN 降级（available False）。"""
        monkeypatch.setattr(
            "yuleosh.kb.vector_store.load_vector_extension",
            lambda c: False,
        )
        vs = VectorStore(conn)
        assert vs.available is False
        assert vs.upsert("h", [0.1] * 768) is False
        assert vs.search([0.1] * 768) == []
        assert vs.count() == 0
