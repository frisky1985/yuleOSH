"""Tests for tenant-scoped KB search (EI-M4A) — SQL-layer org isolation."""

# @tests src/yuleosh/kb/store.py

import os
import tempfile

import pytest

from yuleosh.kb.store import KbStore
from yuleosh.kb.hybrid_search import HybridSearch


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
        return [[0.5] * 8 for _ in texts]


class MockVectorStore:
    available = True

    def __init__(self):
        self.last_filter = None

    def search(self, q, k=10, content_hashes=None):
        self.last_filter = content_hashes
        return []  # 无命中：验证过滤参数传递


class TestTenantScopedSearch:
    def _seed(self, store):
        """租户 A 与 B 各一条独有内容。"""
        a1 = store.create_article({
            "title": "A 独有错误处理", "content": "租户A的刹车失效逻辑",
            "source": "manual", "tenant_org": "org-a",
        })
        b1 = store.create_article({
            "title": "B 独有错误处理", "content": "租户B的机密协议",
            "source": "manual", "tenant_org": "org-b",
        })
        return a1, b1

    def test_list_articles_org_filter(self, store):
        """GIVEN 两租户数据 WHEN list(tenant_org) THEN SQL 层过滤。"""
        self._seed(store)
        a = store.list_articles(tenant_org="org-a")
        assert len(a) == 1
        assert a[0].tenant_org == "org-a"

    def test_count_org_filter(self, store):
        """GIVEN 两租户数据 WHEN count(tenant_org) THEN 各自计数。"""
        self._seed(store)
        assert store.count_articles(tenant_org="org-a") == 1
        assert store.count_articles(tenant_org="org-b") == 1
        # 无过滤时全量
        assert store.count_articles() == 2

    def test_search_org_filter_keyword(self, store):
        """GIVEN 搜索词两租户都有 WHEN search(tenant_org) THEN 只召回本租户。"""
        self._seed(store)
        a = store.list_articles(search="错误处理", tenant_org="org-a")
        assert all(x.tenant_org == "org-a" for x in a)
        assert len(a) == 1

    def test_org_a_cannot_see_org_b(self, store):
        """GIVEN 租户 A 检索任意词 WHEN tenant_org=org-a THEN 不含 B 数据（越权零泄漏）。"""
        self._seed(store)
        # 搜索词精确匹配 B 独有内容
        b_only = store.list_articles(search="机密协议", tenant_org="org-a")
        assert len(b_only) == 0

    def test_hybrid_passes_tenant_filter(self, store):
        """GIVEN HybridSearch WHEN search(tenant_org) THEN 关键词路 SQL 过滤 + 向量候选过滤。"""
        self._seed(store)
        vs = MockVectorStore()
        hs = HybridSearch(store, vs, MockEmbedding())
        result = hs.search("错误处理", tenant_org="org-a")
        # 关键词路：只召回 A
        assert all(h.source == "manual" for h in result.hits)
        assert vs.last_filter is not None  # 向量候选集已限定
        # 候选集全部是 org-a 的 content_hash
        conn = store._get_conn()
        for ch in vs.last_filter:
            row = conn.execute(
                "SELECT tenant_org FROM kb_articles WHERE content_hash = ?",
                (ch,),
            ).fetchone()
            assert row[0] == "org-a"

    def test_hybrid_no_tenant_no_filter(self, store):
        """GIVEN 无 tenant_org WHEN search THEN 向量路不过滤（系统级）。"""
        self._seed(store)
        vs = MockVectorStore()
        hs = HybridSearch(store, vs, MockEmbedding())
        hs.search("错误处理")
        assert vs.last_filter is None

    def test_tenant_org_column_default(self, store):
        """GIVEN 不带 tenant_org 创建 WHEN 读取 THEN 默认 ''（系统级）。"""
        a = store.create_article({"title": "t", "content": "c", "source": "manual"})
        assert a.tenant_org == ""
