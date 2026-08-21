# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Vector store — sqlite-vec 向量存储（EI-M3C.2/.3）。

在 kb.db 内维护向量表（复用同一 SQLite 文件，零新服务），
支持写入与最近邻查询（k=10）。

设计:
- sqlite-vec 为 SQLite 扩展：``loadable_path()`` 加载，注册后可用
  ``vec0`` 虚拟表。
- 表结构: kb_embeddings(vec0) — (embedding float[dim], content_hash, rowid)。
- 写入按 content_hash 幂等（同内容不重复 embedding）。
- 无 sqlite-vec 扩展时 ``vector_available()`` 返回 False，调用方降级
  FTS5 仍可用（EI-M3C.4 优雅降级）。
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Optional

log = logging.getLogger("kb.vector_store")

# 向量维度（与默认嵌入模型一致：nomic-embed-text 768 维）
DEFAULT_DIM = 768
MAX_DIM = 2048  # 防御：超维度拒绝


class VectorStoreUnavailableError(Exception):
    """sqlite-vec 扩展不可用。"""


def load_vector_extension(conn: sqlite3.Connection) -> bool:
    """尝试加载 sqlite-vec 扩展，返回是否可用。"""
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        return True
    except Exception:  # noqa: BLE001 — 扩展缺失时降级
        return False


class VectorStore:
    """sqlite-vec 向量表封装（kb.db 内）。"""

    def __init__(self, conn: sqlite3.Connection, dim: int = DEFAULT_DIM):
        self.conn = conn
        self.dim = dim
        self._available = load_vector_extension(conn)
        if self._available:
            self._ensure_table()

    @property
    def available(self) -> bool:
        return self._available

    def _ensure_table(self) -> None:
        """建 vec0 虚拟表（幂等）。"""
        self.conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS kb_embeddings USING vec0("
            f"embedding float[{self.dim}], content_hash text)"
        )
        self.conn.commit()

    # ---- 写入 ----

    def upsert(self, content_hash: str, embedding: list[float],
               rowid: int | None = None) -> bool:
        """写入向量（按 content_hash 幂等）。

        rowid 可选（与 kb_articles.id 关联，用于 join 回原表）。
        """
        if not self._available:
            return False
        if len(embedding) > MAX_DIM:
            raise ValueError(f"embedding dim {len(embedding)} > MAX_DIM {MAX_DIM}")
        # 先删旧（同 content_hash），再插
        self.conn.execute(
            "DELETE FROM kb_embeddings WHERE content_hash = ?",
            (content_hash,),
        )
        if rowid is not None:
            self.conn.execute(
                "INSERT INTO kb_embeddings(rowid, embedding, content_hash) VALUES (?, ?, ?)",
                (rowid, self._serialize(embedding), content_hash),
            )
        else:
            self.conn.execute(
                "INSERT INTO kb_embeddings(embedding, content_hash) VALUES (?, ?)",
                (self._serialize(embedding), content_hash),
            )
        self.conn.commit()
        return True

    # ---- 查询 ----

    def search(self, query_embedding: list[float], k: int = 10,
               content_hashes: Optional[list[str]] = None) -> list[dict]:
        """最近邻查询（k=10 默认，EI-M3C.3）。

        可选 content_hashes 过滤（多租户隔离预留: 只搜指定内容集）。
        返回 [{content_hash, rowid, distance}]。
        """
        if not self._available:
            return []
        q = self._serialize(query_embedding)
        if content_hashes:
            # vec0 KNN: WHERE embedding MATCH ? [AND 过滤] ORDER BY distance
            placeholders = ",".join("?" for _ in content_hashes)
            cur = self.conn.execute(
                f"""SELECT rowid, content_hash, distance
                    FROM kb_embeddings
                    WHERE embedding MATCH ? AND content_hash IN ({placeholders})
                    ORDER BY distance
                    LIMIT ?""",
                (q, *content_hashes, k),
            )
        else:
            cur = self.conn.execute(
                """SELECT rowid, content_hash, distance
                   FROM kb_embeddings
                   WHERE embedding MATCH ?
                   ORDER BY distance
                   LIMIT ?""",
                (q, k),
            )
        rows = cur.fetchall()
        return [
            {"rowid": r[0], "content_hash": r[1], "distance": float(r[2])}
            for r in rows
        ]

    def count(self) -> int:
        if not self._available:
            return 0
        try:
            cur = self.conn.execute("SELECT COUNT(*) FROM kb_embeddings")
            return cur.fetchone()[0]
        except Exception:  # noqa: BLE001
            return 0

    # ---- helpers ----

    @staticmethod
    def _serialize(vec: list[float]) -> bytes:
        """向量转 sqlite-vec 序列化格式（小端 float32）。"""
        import struct
        return struct.pack(f"<{len(vec)}f", *vec)
