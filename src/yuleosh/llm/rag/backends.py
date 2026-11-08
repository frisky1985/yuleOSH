# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Pluggable vector backends for the RAG engine (P2-8).

统一接口（``available`` / ``upsert`` / ``search`` / ``clear`` / ``count``），
可选依赖（chromadb、faiss）采用惰性导入，缺失时返回不可用原因，由
RAGEngine 回退到 in-memory，绝不静默假绿。
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Protocol

log = logging.getLogger("yuleosh.llm.rag.backends")


class VectorBackend(Protocol):
    available: bool
    unavailable_reason: Optional[str]

    def upsert(self, content_hash: str, vector: list[float]) -> bool: ...
    def search(self, query_vector: list[float], k: int = 10) -> list[dict]: ...
    def clear(self) -> None: ...
    def count(self) -> int: ...


class SqliteVecBackend:
    """sqlite-vec 后端（复用 kb.VectorStore）。"""

    def __init__(self, db_path: Optional[str] = None, dim: Optional[int] = None):
        try:
            import sqlite3

            from yuleosh.kb.vector_store import VectorStore

            path = db_path or os.environ.get("YULEOSH_RAG_DB") or ":memory:"
            self._store = VectorStore(sqlite3.connect(path), dim or 768)
            self.available = self._store.available
            self.unavailable_reason = self._store.unavailable_reason
        except Exception as e:  # noqa: BLE001 — 依赖/扩展缺失
            self._store = None
            self.available = False
            self.unavailable_reason = f"sqlite-vec 后端初始化失败: {e}"

    def upsert(self, content_hash: str, vector: list[float]) -> bool:
        return bool(self._store and self._store.upsert(content_hash, vector))

    def search(self, query_vector: list[float], k: int = 10) -> list[dict]:
        return self._store.search(query_vector, k=k) if self._store else []

    def clear(self) -> None:
        if self._store:
            self._store.clear()

    def count(self) -> int:
        return self._store.count() if self._store else 0


class ChromaBackend:
    """ChromaDB 后端（需要 ``pip install chromadb``）。"""

    def __init__(self, persist_dir: Optional[str] = None):
        self._collection = None
        self._ids: set[str] = set()
        try:
            import chromadb

            path = persist_dir or os.environ.get(
                "YULEOSH_RAG_CHROMA_DIR") or ".yuleosh/rag_chroma"
            client = chromadb.PersistentClient(path=path)
            self._collection = client.get_or_create_collection("rag_chunks")
            self.available = True
            self.unavailable_reason = None
        except Exception as e:  # noqa: BLE001 — chromadb 未安装/初始化失败
            self.available = False
            self.unavailable_reason = f"chromadb 不可用: {e}"

    def upsert(self, content_hash: str, vector: list[float]) -> bool:
        if not self._collection:
            return False
        try:
            self._collection.upsert(ids=[content_hash], embeddings=[vector])
            self._ids.add(content_hash)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("chroma upsert failed: %s", e)
            return False

    def search(self, query_vector: list[float], k: int = 10) -> list[dict]:
        if not self._collection:
            return []
        try:
            res = self._collection.query(
                query_embeddings=[query_vector], n_results=max(1, k))
            ids = (res.get("ids") or [[]])[0]
            distances = (res.get("distances") or [[]])[0]
            return [
                {"content_hash": i, "distance": float(d)}
                for i, d in zip(ids, distances)
            ]
        except Exception as e:  # noqa: BLE001
            log.warning("chroma query failed: %s", e)
            return []

    def clear(self) -> None:
        if not self._collection or not self._ids:
            return
        try:
            self._collection.delete(ids=list(self._ids))
        except Exception as e:  # noqa: BLE001
            log.warning("chroma clear failed: %s", e)
        self._ids.clear()

    def count(self) -> int:
        return len(self._ids)


class FaissBackend:
    """FAISS 后端（需要 ``pip install faiss-cpu``）；索引驻留内存。"""

    def __init__(self, dim: Optional[int] = None):
        self._faiss = None
        self._np = None
        self._index = None
        self._ids: list[str] = []
        self._dim = dim
        try:
            import faiss
            import numpy as np

            self._faiss = faiss
            self._np = np
            self.available = True
            self.unavailable_reason = None
        except Exception as e:  # noqa: BLE001 — faiss 未安装
            self.available = False
            self.unavailable_reason = f"faiss 不可用: {e}"

    def _ensure_index(self, dim: int) -> None:
        if self._index is None or self._dim != dim:
            self._index = self._faiss.IndexFlatL2(dim)
            self._ids = []
            self._dim = dim

    def upsert(self, content_hash: str, vector: list[float]) -> bool:
        if not self.available:
            return False
        if content_hash in self._ids:
            return True  # 同内容哈希幂等
        self._ensure_index(len(vector))
        self._index.add(self._np.asarray([vector], dtype="float32"))
        self._ids.append(content_hash)
        return True

    def search(self, query_vector: list[float], k: int = 10) -> list[dict]:
        if not self.available or self._index is None or not self._ids:
            return []
        k = min(max(1, k), len(self._ids))
        distances, indices = self._index.search(
            self._np.asarray([query_vector], dtype="float32"), k)
        return [
            {"content_hash": self._ids[int(idx)], "distance": float(dist)}
            for dist, idx in zip(distances[0], indices[0]) if idx >= 0
        ]

    def clear(self) -> None:
        self._index = None
        self._ids = []

    def count(self) -> int:
        return len(self._ids)


_BACKENDS = {
    "sqlite-vec": SqliteVecBackend,
    "chroma": ChromaBackend,
    "faiss": FaissBackend,
}


def create_backend(name: str, db_path: Optional[str] = None,
                   dim: Optional[int] = None,
                   ) -> tuple[Optional[VectorBackend], Optional[str]]:
    """Build a backend by name.

    Returns ``(backend, None)`` when constructed (may still be ``available=False``),
    or ``(None, reason)`` for unknown/unconstructible backends.
    """
    cls = _BACKENDS.get(name)
    if cls is None:
        return None, f"未知 RAG 后端: {name}（支持: {'/'.join(_BACKENDS)}/inmemory）"
    try:
        if name == "sqlite-vec":
            return cls(db_path=db_path, dim=dim), None
        if name == "chroma":
            return cls(persist_dir=db_path), None
        return cls(dim=dim), None
    except Exception as e:  # noqa: BLE001
        return None, f"{name} 后端构建失败: {e}"
