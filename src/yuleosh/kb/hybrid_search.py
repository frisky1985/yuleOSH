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

    def search(self, query: str, top_k: int | None = None,
               content_hashes: Optional[list[str]] = None) -> HybridResult:
        """混合检索（RRF 融合）。

        content_hashes: 限定候选内容集（M4-A 租户隔离预留）。
        """
        k = top_k or self.top_k
        result = HybridResult(query=query)
        keyword_hits: list[dict] = []

        # ── 路 1: 关键词（FTS5/LIKE）──
        for article in self.store.list_articles(search=query, limit=k):
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
                vecs = self.embedding_provider.embed([query])
                if vecs:
                    matches = self.vector_store.search(
                        vecs[0], k=k, content_hashes=content_hashes,
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
