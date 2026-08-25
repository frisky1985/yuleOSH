"""Tests for kb/hybrid_search.py — RRF hybrid search (EI-M3E)."""

# @tests src/yuleosh/kb/store.py

import os
import tempfile

import pytest

from yuleosh.kb.hybrid_search import HybridSearch, SearchHit
from yuleosh.kb.store import KbStore


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = KbStore(db_path)
    yield s
    s.close()
    os.unlink(db_path)


class MockEmbedding:
    name = "mock"

    def embed(self, texts):
        # 固定向量：同 query 返回同向量（语义上全相关）
        return [[0.5] * 8 for _ in texts]


class MockVectorStore:
    available = True

    def __init__(self, hit_ids):
        self.hit_ids = hit_ids
        self.last_filter = None

    def search(self, q, k=10, content_hashes=None):
        self.last_filter = content_hashes
        return [{"rowid": i, "content_hash": f"h{i}", "distance": 0.1}
                for i in self.hit_ids]


class TestHybridSearch:
    def test_keyword_only_when_no_vectors(self, store):
        """GIVEN 无向量 WHEN search THEN 关键词路有效。"""
        store.create_article({"title": "错误处理", "content": "系统处理错误", "source": "manual"})
        store.create_article({"title": "其他", "content": "无关", "source": "manual"})
        hs = HybridSearch(store)
        result = hs.search("错误处理")
        assert result.keyword_count >= 1
        assert result.vector_available is False
        assert all(h.keyword_hit for h in result.hits)

    def test_rrf_fusion_both_paths(self, store):
        """GIVEN 关键词+向量都命中 WHEN search THEN 双路融合排序。"""
        a1 = store.create_article({"title": "刹车失效", "content": "刹车系统故障", "source": "manual"})
        a2 = store.create_article({"title": "通信模块", "content": "UART 通信", "source": "manual"})
        # 向量路命中 a1 + a2（a1 优先）
        vs = MockVectorStore([a1.id, a2.id])
        hs = HybridSearch(store, vs, MockEmbedding())
        result = hs.search("刹车")
        assert result.vector_available is True
        # a1 同时被两路命中 → RRF 分数更高 → 排第一
        assert result.hits[0].article_id == a1.id
        assert result.hits[0].keyword_hit and result.hits[0].vector_hit

    def test_vector_only_hit(self, store):
        """GIVEN 向量命中但关键词未命中 WHEN search THEN 仍召回（语义能力）。"""
        a1 = store.create_article({"title": "无关标题", "content": "完全不同的文字", "source": "manual"})
        vs = MockVectorStore([a1.id])
        hs = HybridSearch(store, vs, MockEmbedding())
        result = hs.search("语义相关的词")
        assert any(h.article_id == a1.id and h.vector_hit and not h.keyword_hit
                   for h in result.hits)

    def test_content_hash_filter_passthrough(self, store):
        """GIVEN content_hashes WHEN search THEN 传给向量路（M4-A 租户隔离预留）。"""
        a1 = store.create_article({"title": "t", "content": "内容", "source": "manual"})
        vs = MockVectorStore([a1.id])
        hs = HybridSearch(store, vs, MockEmbedding())
        hs.search("q", content_hashes=["tenant-a-only"])
        assert vs.last_filter == ["tenant-a-only"]

    def test_vector_failure_fallback(self, store):
        """GIVEN 向量路异常 WHEN search THEN 关键词路仍返回。"""
        store.create_article({"title": "错误", "content": "错误处理逻辑", "source": "manual"})
        class BrokenVectorStore:
            available = True
            def search(self, *a, **k):
                raise RuntimeError("vector broke")
        hs = HybridSearch(store, BrokenVectorStore(), MockEmbedding())
        result = hs.search("错误")
        assert result.keyword_count >= 1
        assert result.vector_available is False

    def test_score_order(self, store):
        """GIVEN 多结果 WHEN search THEN score 降序。"""
        for i in range(3):
            store.create_article({"title": f"项{i}", "content": f"公共内容{i}", "source": "manual"})
        hs = HybridSearch(store)
        result = hs.search("公共")
        scores = [h.score for h in result.hits]
        assert scores == sorted(scores, reverse=True)

    def test_hit_dataclass_fields(self):
        """GIVEN SearchHit WHEN 构造 THEN 字段完整。"""
        h = SearchHit(article_id=1, title="t", content="c", source="s", source_ref="r",
                      score=0.5, keyword_rank=0, vector_rank=1,
                      keyword_hit=True, vector_hit=True)
        assert h.keyword_hit and h.vector_hit
