# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Hybrid search — FTS5 关键词 + 向量近邻 双路召回 RRF 融合（EI-M3E）。

现代 RAG 标准检索: 关键词路（精确/中文 trigram）+ 语义路（embedding 近邻）
→ Reciprocal Rank Fusion（RRF）融合排序 → 返回带来源与两路分数的结果。

设计:
- 关键词路: KbStore.list_articles（FTS5，<3 字符自动 LIKE）
- 语义路: VectorStore.search（sqlite-vec KNN，可 content_hash 过滤=租户隔离预留）
- RRF 融合: score = Σ 1/(k + rank)，k=60（RRF 标准参数）
- 优雅降级: 无向量/无 embedding → 纯关键词路（结果仍有效，两路分数标注）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("kb.hybrid_search")

RRF_K = 60  # RRF 标准常数


@dataclass
class SearchHit:
    """融合检索结果。"""

    article_id: int
    title: str
    content: str
    source: str
    source_ref: str
    score: float
    keyword_rank: Optional[int] = None
    vector_rank: Optional[int] = None
    keyword_hit: bool = False
    vector_hit: bool = False
    # M4-B: 三源联合召回字段
    hit_type: str = "article"  # article | lesson | fmea | kg
    extra: dict | None = None


@dataclass
class HybridResult:
    """融合检索返回。"""

    query: str
    hits: list[SearchHit] = field(default_factory=list)
    keyword_count: int = 0
    vector_count: int = 0
    vector_available: bool = False


class HybridSearch:
    """双路混合检索（EI-M3E.1）。"""

    def __init__(self, store, vector_store=None, embedding_provider=None,
                 top_k: int = 10):
        self.store = store
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider
        self.top_k = top_k

    def _vector_ready(self) -> bool:
        return (
            self.vector_store is not None
            and self.embedding_provider is not None
            and self.vector_store.available
        )

    def _tenant_content_hashes(self, tenant_org: str) -> list[str]:
        """该租户全部文章的 content_hash（向量候选集过滤，EI-M4A.1）。"""
        conn = self.store._get_conn()
        cur = conn.execute(
            "SELECT content_hash FROM kb_articles WHERE tenant_org = ? AND content_hash != ''",
            (tenant_org,),
        )
        return [r[0] for r in cur.fetchall()]

    def search(self, query: str, top_k: int | None = None,
               content_hashes: list[str] | None = None,
               tenant_org: str | None = None) -> HybridResult:
        """混合检索（RRF 融合）。

        content_hashes: 限定候选内容集（向量路过滤）。
        tenant_org: 租户标识（EI-M4A.1: 关键词路 SQL 层强制过滤，非 None 时）。
        """
        k = top_k or self.top_k
        result = HybridResult(query=query)
        keyword_hits: list[dict] = []

        # ── 路 1: 关键词（FTS5/LIKE + 租户过滤）──
        for article in self.store.list_articles(
            search=query, limit=k, tenant_org=tenant_org,
        ):
            keyword_hits.append({
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "source": article.source,
                "source_ref": article.source_ref,
            })
        result.keyword_count = len(keyword_hits)

        # ── 路 2: 向量近邻（可用时）──
        vector_hits: list[dict] = []
        if self._vector_ready():
            result.vector_available = True
            try:
                assert self.embedding_provider is not None
                assert self.vector_store is not None
                # EI-M4A.1: 租户过滤向量候选集（该租户文章的 content_hash）
                tenant_hashes = None
                if tenant_org is not None:
                    tenant_hashes = self._tenant_content_hashes(tenant_org)
                vecs = self.embedding_provider.embed([query])
                if vecs:
                    matches = self.vector_store.search(
                        vecs[0], k=k,
                        content_hashes=tenant_hashes or content_hashes,
                    )
                    for m in matches:
                        article = self.store.get_article(m["rowid"])
                        if article is None:
                            continue
                        vector_hits.append({
                            "id": article.id,
                            "title": article.title,
                            "content": article.content,
                            "source": article.source,
                            "source_ref": article.source_ref,
                            "distance": m["distance"],
                        })
            except Exception as e:  # noqa: BLE001 — 向量路失败降级关键词
                log.warning("vector search failed, fallback to keyword: %s", e)
                result.vector_available = False
        result.vector_count = len(vector_hits)

        # ── RRF 融合 ──
        scores: dict[int, float] = {}
        meta: dict[int, dict] = {}
        for rank, hit in enumerate(keyword_hits):
            scores[hit["id"]] = scores.get(hit["id"], 0.0) + 1.0 / (RRF_K + rank + 1)
            meta.setdefault(hit["id"], {}).update({
                "title": hit["title"], "content": hit["content"],
                "source": hit["source"], "source_ref": hit["source_ref"],
                "keyword_rank": rank,
            })
        for rank, hit in enumerate(vector_hits):
            scores[hit["id"]] = scores.get(hit["id"], 0.0) + 1.0 / (RRF_K + rank + 1)
            m = meta.setdefault(hit["id"], {})
            m.update({
                "title": hit["title"], "content": hit["content"],
                "source": hit["source"], "source_ref": hit["source_ref"],
                "vector_rank": rank,
            })

        # 排序并组装
        for article_id, score in sorted(scores.items(), key=lambda x: -x[1]):
            m = meta[article_id]
            result.hits.append(SearchHit(
                article_id=article_id,
                title=m.get("title", ""),
                content=m.get("content", ""),
                source=m.get("source", ""),
                source_ref=m.get("source_ref", ""),
                score=score,
                keyword_rank=m.get("keyword_rank"),
                vector_rank=m.get("vector_rank"),
                keyword_hit=m.get("keyword_rank") is not None,
                vector_hit=m.get("vector_rank") is not None,
            ))
        return result

    # ── EI-M4B: 三源联合召回（articles + lessons + fmea + KG 节点）──

    def unified_search(self, query: str, top_k: int | None = None,
                       tenant_org: str | None = None) -> list[SearchHit]:
        """一次查询联合召回多源知识（EI-M4B.1/.2）。

        来源: articles（混合检索）+ lessons + fmea + knowledge-graph 节点，
        按相关性融合排序，带 hit_type 来源标注。

        简化策略（可演进）: 主源 = HybridSearch（文章语义+关键词）；
        辅助源 = lessons/fmea/KG 按关键词 LIKE 匹配 title/问题字段。
        """
        k = top_k or self.top_k
        hits: list[SearchHit] = []

        # 主源: 文章混合检索
        hybrid = self.search(query, top_k=k, tenant_org=tenant_org)
        for h in hybrid.hits:
            h.hit_type = "article"
            hits.append(h)

        # 辅助源: lessons / fmea / KG（关键词匹配 title 字段）
        pattern = query.lower()
        try:
            for lesson in self.store.list_lessons():
                hay = f"{lesson.title} {lesson.problem} {lesson.solution}".lower()
                if pattern in hay:
                    hits.append(SearchHit(
                        article_id=lesson.id or 0,
                        title=f"[lesson] {lesson.title}",
                        content=lesson.solution or lesson.problem,
                        source="lesson",
                        source_ref=lesson.ticket_id or "",
                        score=0.9,  # 固定分（辅助源）
                        keyword_hit=True, vector_hit=False,
                        hit_type="lesson",
                        extra={"root_cause": lesson.root_cause,
                               "project_id": lesson.project_id},
                    ))
        except Exception as e:  # noqa: BLE001 — 辅助源失败不影响主源
            log.warning("lesson recall failed: %s", e)

        try:
            for fmea in self.store.list_fmea():
                hay = f"{fmea.item} {fmea.failure_mode} {fmea.cause}".lower()
                if pattern in hay:
                    hits.append(SearchHit(
                        article_id=fmea.id or 0,
                        title=f"[fmea] {fmea.item} — {fmea.failure_mode}",
                        content=f"{fmea.cause} → {fmea.effect}",
                        source="fmea",
                        source_ref="",
                        score=0.9,
                        keyword_hit=True, vector_hit=False,
                        hit_type="fmea",
                        extra={"rpn": fmea.rpn, "recommendation": fmea.recommendation},
                    ))
        except Exception as e:  # noqa: BLE001
            log.warning("fmea recall failed: %s", e)

        try:
            from yuleosh.knowledge_graph.store import KGStore
            kg = KGStore()
            for node in kg.list_nodes():
                if pattern in (node.label or "").lower():
                    hits.append(SearchHit(
                        article_id=node.id or 0,
                        title=f"[kg] {node.label}",
                        content=node.properties.get("summary", "") or node.label,
                        source="knowledge_graph",
                        source_ref=node.entity_type or "",
                        score=0.9,
                        keyword_hit=True, vector_hit=False,
                        hit_type="kg",
                        extra={"entity_type": node.entity_type,
                               "entity_id": node.entity_id},
                    ))
        except Exception as e:  # noqa: BLE001
            log.warning("kg recall failed: %s", e)

        # 融合排序: 主源按 RRF 分，辅助源固定 0.9 但排在主源后（type 优先级）
        hits.sort(key=lambda h: (h.hit_type != "article", -h.score))
        return hits[:k]
