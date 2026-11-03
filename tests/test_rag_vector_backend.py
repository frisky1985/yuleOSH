"""Tests for RAGEngine v1.5 sqlite-vec backend (P1-3).

验证: 可注入向量后端、索引写入、向量召回、任一环节失败自动回退 in-memory。
"""

import asyncio

from yuleosh.llm.rag.engine import RAGEngine, chunk_content_hash


class MockEmbedding:
    name = "mock"

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class MockVectorStore:
    """有界面的 VectorStore 替身（不依赖 sqlite-vec 扩展）。"""

    def __init__(self, available=True):
        self.available = available
        self.unavailable_reason = None if available else "sqlite-vec 扩展不可用"
        self.vectors = {}
        self.cleared = False

    def upsert(self, content_hash, vector, rowid=None):
        if not self.available:
            return False
        self.vectors[content_hash] = vector
        return True

    def search(self, query_embedding, k=10, content_hashes=None):
        if not self.available:
            return []
        hashes = list(content_hashes) if content_hashes else list(self.vectors)
        return [
            {"rowid": i, "content_hash": h, "distance": 0.0}
            for i, h in enumerate(hashes[:k])
        ]

    def clear(self):
        self.cleared = True
        self.vectors.clear()


class TestRAGVectorBackend:
    def test_default_backend_is_inmemory(self):
        engine = RAGEngine()
        assert engine.backend == "inmemory"
        assert engine.degraded_reason is None
        assert engine.chunk_count == 0

    def test_fallback_when_vector_unavailable(self):
        vs = MockVectorStore(available=False)
        engine = RAGEngine(backend="sqlite-vec", vector_store=vs,
                           embedding_provider=MockEmbedding())
        assert engine.backend == "inmemory"
        assert engine.degraded_reason
        assert "sqlite-vec" in engine.degraded_reason

    def test_vector_index_and_retrieve(self):
        vs = MockVectorStore()
        engine = RAGEngine(backend="sqlite-vec", vector_store=vs,
                           embedding_provider=MockEmbedding())
        assert engine.backend == "sqlite-vec"

        count = engine.index_best_practices([
            {"id": "bp1", "title": "Brake control", "content": "brake system fault diagnosis"},
        ])
        assert count == 1
        assert vs.vectors  # 已写入向量

        results = asyncio.run(engine.retrieve("brake", top_k=1))
        assert results and results[0].chunk.id == "bp1"
        # 向量后端命中的 chunk 不再重复计算 n-gram 索引
        assert engine._embeddings == {}

    def test_index_embedding_failure_degrades_to_inmemory(self):
        class BrokenEmbedding:
            name = "broken"

            def embed(self, texts):
                raise RuntimeError("ollama down")

        vs = MockVectorStore()
        engine = RAGEngine(backend="sqlite-vec", vector_store=vs,
                           embedding_provider=BrokenEmbedding())
        engine.index_best_practices([
            {"id": "bp1", "title": "Brake control", "content": "brake system fault diagnosis"},
        ])
        assert engine.backend == "inmemory"
        assert "索引嵌入失败" in engine.degraded_reason
        # 已索引的 chunk 仍可被 in-memory 路径召回
        results = asyncio.run(engine.retrieve("brake", top_k=1))
        assert results and results[0].chunk.id == "bp1"

    def test_retrieve_embedding_failure_degrades(self):
        class FlakyEmbedding:
            name = "flaky"

            def __init__(self):
                self.calls = 0

            def embed(self, texts):
                self.calls += 1
                if self.calls == 1:  # 索引时成功
                    return [[1.0, 0.0] for _ in texts]
                raise RuntimeError("embedding 服务中途不可用")

        vs = MockVectorStore()
        engine = RAGEngine(backend="sqlite-vec", vector_store=vs,
                           embedding_provider=FlakyEmbedding())
        engine.index_best_practices([
            {"id": "bp1", "title": "Brake control", "content": "brake system fault diagnosis"},
        ])
        results = asyncio.run(engine.retrieve("brake", top_k=1))
        assert engine.backend == "inmemory"
        assert "检索嵌入失败" in engine.degraded_reason
        assert results and results[0].chunk.id == "bp1"

    def test_clear_resets_vector_store(self):
        vs = MockVectorStore()
        engine = RAGEngine(backend="sqlite-vec", vector_store=vs,
                           embedding_provider=MockEmbedding())
        engine.index_best_practices([
            {"id": "bp1", "title": "t", "content": "c"},
        ])
        assert vs.vectors
        engine.clear()
        assert vs.cleared
        assert engine.chunk_count == 0
        assert engine._chunk_by_hash == {}

    def test_chunk_content_hash_is_stable(self):
        from yuleosh.llm.rag.engine import RAGChunk

        c1 = RAGChunk(id="m1", source="misra_c", content="rule text")
        c2 = RAGChunk(id="m1", source="misra_c", content="rule text")
        assert chunk_content_hash(c1) == chunk_content_hash(c2)
