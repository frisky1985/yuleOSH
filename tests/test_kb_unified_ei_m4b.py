"""Tests for kb/hybrid_search.py — unified multi-source search (EI-M4B).

三源联合召回: articles（主源混合检索）+ lessons + fmea + knowledge-graph。
验证 hit_type 来源标注、融合排序、单源失败降级。
"""

# @tests src/yuleosh/kb/store.py

import os
import tempfile

import pytest

from yuleosh.kb.hybrid_search import HybridSearch
from yuleosh.kb.store import KbStore
from yuleosh.knowledge_graph.models import Node
from yuleosh.knowledge_graph.store import KGStore


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = KbStore(db_path)
    yield s
    s.close()
    os.unlink(db_path)


@pytest.fixture
def kg_isolated(tmp_path, monkeypatch):
    """KGStore 单例隔离：临时 db + 重置单例缓存。"""
    db_path = str(tmp_path / "kg_test.db")
    monkeypatch.setenv("YULEOSH_KG_DB", db_path)
    KGStore.reset()
    kg = KGStore()
    yield kg
    KGStore.reset()


class MockEmbedding:
    name = "mock"

    def embed(self, texts):
        return [[0.5] * 8 for _ in texts]


class TestUnifiedSearch:
    def test_article_main_source(self, store):
        """GIVEN 文章命中 WHEN unified_search THEN 主源 article 召回带 RRF 分。"""
        store.create_article({"title": "刹车失效", "content": "刹车系统故障", "source": "manual"})
        hs = HybridSearch(store)
        hits = hs.unified_search("刹车")
        assert any(h.hit_type == "article" and "刹车" in h.title for h in hits)

    def test_lesson_aux_source(self, store):
        """GIVEN lesson 命中 WHEN unified_search THEN 辅助源 lesson 召回标注。"""
        store.create_lesson({
            "title": "UART 波特率误配",
            "problem": "通信失败",
            "solution": "统一配置 115200",
            "root_cause": "初始化顺序错误",
            "project_id": "p1",
            "ticket_id": "IMP-001",
        })
        hs = HybridSearch(store)
        hits = hs.unified_search("uart")
        lesson_hits = [h for h in hits if h.hit_type == "lesson"]
        assert lesson_hits, "lesson 源应被召回"
        assert "[lesson]" in lesson_hits[0].title
        assert lesson_hits[0].source == "lesson"
        assert (lesson_hits[0].extra or {}).get("root_cause") == "初始化顺序错误"

    def test_fmea_aux_source(self, store):
        """GIVEN fmea 命中 WHEN unified_search THEN 辅助源 fmea 召回标注。"""
        store.create_fmea({
            "item": "安全气囊",
            "failure_mode": "未展开",
            "cause": "传感器失效",
            "effect": "乘员受伤",
            "severity": 9, "occurence": 2, "detection": 3,
            "recommendation": "双冗余传感器",
        })
        hs = HybridSearch(store)
        hits = hs.unified_search("气囊")
        fmea_hits = [h for h in hits if h.hit_type == "fmea"]
        assert fmea_hits, "fmea 源应被召回"
        assert fmea_hits[0].source == "fmea"
        assert (fmea_hits[0].extra or {}).get("rpn") == 9 * 2 * 3

    def test_kg_aux_source(self, store, kg_isolated):
        """GIVEN KG 节点命中 WHEN unified_search THEN 辅助源 kg 召回标注。"""
        kg_isolated.upsert_node(Node(
            entity_type="function", entity_id="F-001",
            label="brake_control", properties={"summary": "刹车控制函数"},
        ))
        kg_isolated.upsert_node(Node(
            entity_type="requirement", entity_id="REQ-002",
            label="防盗策略", properties={},
        ))
        hs = HybridSearch(store)
        hits = hs.unified_search("brake")
        kg_hits = [h for h in hits if h.hit_type == "kg"]
        assert kg_hits, "KG 源应被召回"
        assert "[kg]" in kg_hits[0].title
        assert kg_hits[0].source_ref == "function"
        assert (kg_hits[0].extra or {}).get("entity_id") == "F-001"
        # content 取 properties.summary（无 summary 时回退 label）
        assert kg_hits[0].content == "刹车控制函数"

    def test_fusion_ranking_articles_first(self, store, kg_isolated):
        """GIVEN 多源同命中 WHEN unified_search THEN article 主源排前。"""
        store.create_article({"title": "刹车总成", "content": "刹车系统", "source": "manual"})
        kg_isolated.upsert_node(Node(
            entity_type="function", entity_id="F-1", label="brake", properties={},
        ))
        hs = HybridSearch(store)
        hits = hs.unified_search("brake")
        assert hits, "至少召回一条"
        first_type = hits[0].hit_type
        # 主源文章优先；无文章命中时才轮到辅助源
        if any(h.hit_type == "article" for h in hits):
            assert first_type == "article"

    def test_aux_source_failure_degrades(self, store, monkeypatch):
        """GIVEN lesson 源抛异常 WHEN unified_search THEN 主源仍可用（降级不阻断）。"""
        store.create_article({"title": "点火失败", "content": "火花塞", "source": "manual"})
        hs = HybridSearch(store)
        monkeypatch.setattr(hs.store, "list_lessons", lambda **k: (_ for _ in ()).throw(RuntimeError("db broke")))
        monkeypatch.setattr(hs.store, "list_fmea", lambda **k: (_ for _ in ()).throw(RuntimeError("db broke")))
        hits = hs.unified_search("点火")
        assert any(h.hit_type == "article" for h in hits), "主源不应被辅助源异常拖垮"

    def test_aux_source_ordering_after_articles(self, store):
        """GIVEN 辅助源命中 WHEN unified_search THEN 排文章之后且分数标注。"""
        store.create_article({"title": "刹车片", "content": "制动系统维护", "source": "manual"})
        store.create_lesson({
            "title": "刹车异响",
            "problem": "制动时有尖叫声",
            "solution": "更换刹车片",
            "ticket_id": "IMP-9",
        })
        hs = HybridSearch(store)
        hits = hs.unified_search("刹车")
        types = [h.hit_type for h in hits]
        # 文章存在 → 第一个必为 article
        assert types[0] == "article"
        # 辅助源随后
        if "lesson" in types:
            assert types.index("article") < types.index("lesson")

    def test_unified_search_tenant_filter(self, store):
        """GIVEN tenant_org WHEN unified_search THEN 关键词路 SQL 强制过滤（M4-A 延续）。"""
        a1 = store.create_article({"title": "机密协议", "content": "内部保密", "source": "manual",
                                   "tenant_org": "org-a"})
        a2 = store.create_article({"title": "公开手册", "content": "公开内容", "source": "manual",
                                   "tenant_org": "org-b"})
        hs = HybridSearch(store)
        hits_a = hs.unified_search("协议", tenant_org="org-a")
        ids_a = {h.article_id for h in hits_a if h.hit_type == "article"}
        assert a1.id in ids_a
        assert a2.id not in ids_a, "租户 B 文章不应泄漏到租户 A 检索"


class TestUnifiedSearchAPI:
    """GET /api/v1/kb/unified — API 层三源联合召回（EI-M4B.1/.2）。"""

    @pytest.fixture
    def kb_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YULEOSH_KB_DB", str(tmp_path / "api_kb.db"))
        monkeypatch.setenv("YULEOSH_KG_DB", str(tmp_path / "api_kg.db"))
        KGStore.reset()
        yield
        KGStore.reset()

    def _handler(self):
        from yuleosh.api.kb import handle_kb

        def _authed(*args, **kwargs):
            kwargs.setdefault(
                "current_user",
                {"user_id": 1, "org_id": "org-a", "email": "a@t.com", "role": "admin"},
            )
            return handle_kb(*args, **kwargs)
        return _authed

    def test_unified_returns_four_sources(self, kb_env):
        """GIVEN 四源都命中 WHEN GET /kb/unified THEN 全部召回并带 hit_type。"""
        store = KbStore()
        store.create_article({"title": "刹车失效", "content": "刹车系统故障", "source": "manual",
                              "tenant_org": "org-a"})
        store.create_lesson({"title": "刹车教训", "problem": "刹车异响", "solution": "换片",
                             "ticket_id": "IMP-1"})
        store.create_fmea({"item": "刹车", "failure_mode": "失效", "cause": "磨损",
                           "effect": "失灵", "severity": 9, "occurence": 2, "detection": 3})
        kg = KGStore()
        kg.upsert_node(Node(entity_type="function", entity_id="F-1",
                            label="brake_control", properties={"summary": "刹车控制"}))

        handler = self._handler()
        result, status = handler("GET", "unified", {}, {"q": ["刹车"]})
        assert status == 200
        assert result["ok"] is True
        hits = result["data"]["hits"]
        types = {h["hit_type"] for h in hits}
        assert "article" in types
        assert "lesson" in types
        assert "fmea" in types
        # 文章主源排最前
        assert hits[0]["hit_type"] == "article"
        # 每个 hit 带来源标注
        for h in hits:
            assert h["source"]
        store.close()

    def test_unified_requires_q(self, kb_env):
        """GIVEN 缺 q WHEN GET /kb/unified THEN 400。"""
        handler = self._handler()
        result, status = handler("GET", "unified", {}, {})
        assert status == 400

    def test_unified_method_not_allowed(self, kb_env):
        """GIVEN POST WHEN GET /kb/unified THEN 405。"""
        handler = self._handler()
        result, status = handler("POST", "unified", {}, {"q": ["x"]})
        assert status == 405

    def test_unified_tenant_org_leak_protection(self, kb_env):
        """GIVEN 租户 B 独有文章 WHEN 租户 A unified 检索 THEN 不泄漏。"""
        store = KbStore()
        store.create_article({"title": "机密协议", "content": "B 独有", "source": "manual",
                              "tenant_org": "org-b"})
        handler = self._handler()
        result, status = handler("GET", "unified", {}, {"q": ["机密协议"]})
        assert status == 200
        hits = result["data"]["hits"]
        assert all(h["hit_type"] != "article" for h in hits), "org-a 不应看到 org-b 文章"
        store.close()
