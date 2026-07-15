#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
llm/rag/engine.py — RAG retrieval and context assembly engine.

Supports multiple knowledge sources (MISRA rules, embedded best practices,
project review history) with in-memory vector search and keyword re-ranking.

v1 uses in-memory dicts + simple cosine similarity.
v2 will use ChromaDB / FAISS for production-scale retrieval.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("llm.rag")


# ═══════════════════════════════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class RAGChunk:
    """A single retrievable knowledge chunk."""

    id: str
    source: str  # "misra_c", "best_practices", "project_history"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None  # populated at index time


@dataclass
class RAGResult:
    """A single retrieval result."""

    chunk: RAGChunk
    score: float
    rank: int


# ═══════════════════════════════════════════════════════════════════════
# Simple in-memory embedding (character n-gram based)
# ═══════════════════════════════════════════════════════════════════════


def _char_ngrams(text: str, n: int = 3) -> Dict[str, float]:
    """Compute character n-gram frequencies (simple bag-of-ngrams)."""
    text = text.lower()
    ngrams: Dict[str, float] = {}
    for i in range(len(text) - n + 1):
        gram = text[i : i + n]
        ngrams[gram] = ngrams.get(gram, 0) + 1
    # Normalize
    total = sum(ngrams.values())
    if total > 0:
        for k in ngrams:
            ngrams[k] /= total
    return ngrams


def _cosine_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Cosine similarity between two n-gram dicts."""
    intersection = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in intersection)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_overlap(query: str, content: str) -> float:
    """Simple keyword overlap score (0-1)."""
    query_words = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", query.lower()))
    content_words = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", content.lower()))
    if not query_words:
        return 0.0
    overlap = query_words & content_words
    return len(overlap) / len(query_words)


# ═══════════════════════════════════════════════════════════════════════
# MISRA C Rule Source (prototype — ~30 sample rules)
# ═══════════════════════════════════════════════════════════════════════


MISRA_C_RULES_SAMPLE: List[Dict[str, Any]] = [
    {
        "rule_id": "Rule 10.1",
        "category": "Required",
        "title": "Integer type implicit conversion",
        "summary": "The value of an expression of integer type shall not be implicitly converted to a different underlying type.",
        "violation_examples": [
            "uint16_t x = 10; uint32_t y = x + 5;  // implicit promotion",
            "int32_t a = -1; uint32_t b = a;  // signed to unsigned",
        ],
        "fix_examples": [
            "uint16_t x = 10; uint32_t y = (uint32_t)x + 5;",
            "int32_t a = -1; uint32_t b = (uint32_t)a;",
        ],
        "related_rules": ["10.3", "10.4"],
        "severity": "high",
    },
    {
        "rule_id": "Rule 10.3",
        "category": "Required",
        "title": "Complex integer expression assignment",
        "summary": "The value of a complex expression of integer type shall only be cast to a type that is not wider than the essential type of the expression.",
        "violation_examples": [
            "uint64_t x = (uint32_t)a + (uint32_t)b;  // result may overflow",
        ],
        "fix_examples": [
            "uint64_t x = (uint64_t)a + (uint64_t)b;",
        ],
        "related_rules": ["10.1", "10.4"],
        "severity": "high",
    },
    {
        "rule_id": "Rule 11.1",
        "category": "Required",
        "title": "Pointer to object conversion",
        "summary": "Conversions shall not be performed between a pointer to function and any other type.",
        "violation_examples": [
            "void (*fp)(void); uint32_t addr = (uint32_t)fp;  // non-compliant",
        ],
        "fix_examples": [
            "// Store function pointer as-is, do not convert to integer",
        ],
        "related_rules": ["11.2", "11.3"],
        "severity": "high",
    },
    {
        "rule_id": "Rule 18.4",
        "category": "Required",
        "title": "Pointer arithmetic",
        "summary": "The subtract or addition operator shall not be applied to an expression of pointer type except when the resulting pointer points to the same array object.",
        "violation_examples": [
            "int *p = &arr[10]; int *q = p + 5;  // OK\nint *r = p - &x;  // non-compliant",
        ],
        "fix_examples": [
            "// Only use pointer arithmetic within the bounds of the same array",
        ],
        "related_rules": [],
        "severity": "high",
    },
    {
        "rule_id": "Rule 20.9",
        "category": "Required",
        "title": "Undefined macro identifiers",
        "summary": "A macro shall not be defined with the same name as a keyword.",
        "violation_examples": [
            "#define int 42  // non-compliant",
        ],
        "fix_examples": [
            "#define MY_INT 42  // compliant",
        ],
        "related_rules": [],
        "severity": "medium",
    },
    # ... more rules can be added in production
]


# ═══════════════════════════════════════════════════════════════════════
# RAG Engine
# ═══════════════════════════════════════════════════════════════════════


class RAGEngine:
    """In-memory RAG retrieval engine (v1 prototype).

    Indexes knowledge sources on construction and provides
    ``retrieve()`` for context assembly.

    Usage::

        engine = RAGEngine()
        engine.index_misra_rules()     # load MISRA rules
        engine.index_best_practices()  # load best practices

        context = await engine.retrieve(
            "How to fix implicit integer conversion?",
            sources=["misra"],
        )
    """

    def __init__(self):
        self._chunks: List[RAGChunk] = []
        self._embeddings: Dict[str, Dict[str, float]] = {}  # chunk_id → ngram vector
        self._ready = False

    # ── Indexing ────────────────────────────────────────────────────

    def index_misra_rules(self, rules: Optional[List[Dict]] = None) -> int:
        """Index MISRA C rules as retrievable chunks.

        Args:
            rules: List of rule dicts (default: built-in sample).

        Returns:
            Number of chunks indexed.
        """
        rules = rules or MISRA_C_RULES_SAMPLE
        count = 0
        for rule in rules:
            # Compose rule text
            content = (
                f"Rule {rule['rule_id']} ({rule['category']}): {rule['title']}\n\n"
                f"{rule['summary']}\n\n"
                f"Violation examples:\n"
                + "\n".join(f"  • {ex}" for ex in rule.get("violation_examples", []))
                + "\n\n"
                f"Fix examples:\n"
                + "\n".join(f"  • {ex}" for ex in rule.get("fix_examples", []))
            )
            chunk = RAGChunk(
                id=f"misra_{rule['rule_id']}",
                source="misra_c",
                content=content,
                metadata=rule,
            )
            self._add_chunk(chunk)
            count += 1

        log.info("Indexed %d MISRA rule chunks", count)
        return count

    def index_best_practices(self, practices: List[Dict[str, str]]) -> int:
        """Index embedded best practice documents.

        Args:
            practices: List of {"id": ..., "title": ..., "content": ...} dicts.

        Returns:
            Number of chunks indexed.
        """
        count = 0
        for practice in practices:
            content = (
                f"{practice.get('title', '')}\n\n"
                f"{practice.get('content', '')}"
            )
            chunk = RAGChunk(
                id=practice.get("id", f"bp_{count}"),
                source="best_practices",
                content=content,
                metadata=practice,
            )
            self._add_chunk(chunk)
            count += 1

        log.info("Indexed %d best practice chunks", count)
        return count

    def _add_chunk(self, chunk: RAGChunk):
        """Add a single chunk and compute its embedding."""
        self._chunks.append(chunk)
        self._embeddings[chunk.id] = _char_ngrams(chunk.content)

    # ── Retrieval ───────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        top_k: int = 5,
        min_score: float = 0.1,
    ) -> List[RAGResult]:
        """Retrieve top-K relevant chunks for a query.

        Args:
            query: User's query / prompt text.
            sources: Filter to specific sources (e.g. ["misra_c"]).
                    None = all sources.
            top_k: Max results to return.
            min_score: Minimum similarity score threshold.

        Returns:
            Ranked list of RAGResult objects.
        """
        if not self._chunks:
            return []

        query_vec = _char_ngrams(query)
        scored: List[tuple[float, RAGChunk]] = []

        for chunk in self._chunks:
            # Source filter
            if sources and chunk.source not in sources:
                continue

            embed = self._embeddings.get(chunk.id)
            if embed is None:
                continue

            # Combine n-gram similarity + keyword overlap
            vec_score = _cosine_similarity(query_vec, embed)
            kw_score = _keyword_overlap(query, chunk.content)
            combined = vec_score * 0.6 + kw_score * 0.4

            if combined >= min_score:
                scored.append((combined, chunk))

        # Sort by score descending, take top-K
        scored.sort(key=lambda x: -x[0])
        top = scored[:top_k]

        results = [
            RAGResult(chunk=chunk, score=round(score, 4), rank=i + 1)
            for i, (score, chunk) in enumerate(top)
        ]

        log.debug(
            "Retrieved %d results (query=%s, sources=%s, top_k=%d)",
            len(results),
            query[:40],
            sources,
            top_k,
        )
        return results

    async def retrieve_as_context(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        top_k: int = 8,
    ) -> str:
        """Retrieve and format results as a system prompt context block.

        Args:
            query: User's query text.
            sources: Source filter (e.g. ["misra_c"]).
            top_k: Max results.

        Returns:
            Formatted markdown string for injection into system prompt.
        """
        results = await self.retrieve(query, sources, top_k)

        if not results:
            return ""

        sections: List[str] = [
            "## Knowledge Context (RAG)",
            "",
            f"Retrieved {len(results)} relevant knowledge items for this query.",
            "",
        ]

        current_source = None
        for r in results:
            if r.chunk.source != current_source:
                current_source = r.chunk.source
                source_label = {
                    "misra_c": "MISRA-C Rules",
                    "best_practices": "Embedded Best Practices",
                    "project_history": "Project Review History",
                }.get(current_source, current_source)
                sections.append(f"### {source_label}")
                sections.append("")

            sections.append(f"**{r.chunk.id}** (relevance: {r.score:.2f})")
            sections.append("")
            sections.append(f"> {r.chunk.content}")
            sections.append("")

        return "\n".join(sections)

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def clear(self):
        """Reset all indexed data."""
        self._chunks.clear()
        self._embeddings.clear()


# ═══════════════════════════════════════════════════════════════════════
# Convenience: default engine singleton
# ═══════════════════════════════════════════════════════════════════════

_default_engine: Optional[RAGEngine] = None


def get_default_engine() -> RAGEngine:
    """Get or create the default RAG engine (lazy-initialized)."""
    global _default_engine
    if _default_engine is None:
        _default_engine = RAGEngine()
        _default_engine.index_misra_rules()
    return _default_engine
