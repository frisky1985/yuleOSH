"""Tests for kb/ingest.py — ingestion pipeline (EI-M3D)."""

# @tests src/yuleosh/kb/store.py

import os
import tempfile
from pathlib import Path

import pytest

from yuleosh.kb.ingest import (
    chunk_text,
    collect_source_paths,
    ingest_project,
    remove_stale_articles,
)
from yuleosh.kb.store import KbStore


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = KbStore(db_path)
    yield s
    s.close()
    os.unlink(db_path)


@pytest.fixture
def project(tmp_path):
    """带 docs/spec.md + TASK_STATUS.md 的项目。"""
    p = tmp_path / "proj-a"
    (p / "docs").mkdir(parents=True)
    (p / "docs" / "spec.md").write_text(
        "# 需求规范\n\n## 错误处理\n\n系统必须正确处理错误。\n\n## 通信\n\nUART 驱动实现。",
        encoding="utf-8",
    )
    (p / "TASK_STATUS.md").write_text("# 项目状态\n\n## 里程碑\n\nM1 已完成。", encoding="utf-8")
    return p


class TestChunking:
    def test_split_by_heading(self):
        """GIVEN 多标题文档 WHEN chunk THEN 每标题一块。"""
        chunks = chunk_text("spec.md", "# A\n\n## B\n\n内容B\n\n## C\n\n内容C")
        assert len(chunks) == 3

    def test_no_heading_single_chunk(self):
        """GIVEN 无标题短文 WHEN chunk THEN 单块。"""
        chunks = chunk_text("a.md", "短内容")
        assert len(chunks) == 1

    def test_long_segment_split(self):
        """GIVEN 超长段 WHEN chunk THEN 按窗口切分（重叠）。"""
        long_text = "段落内容。" * 2000
        chunks = chunk_text("a.md", f"## 大段\n\n{long_text}")
        assert len(chunks) >= 2

    def test_chunk_has_hash(self):
        """GIVEN 分块 WHEN chunk THEN content_hash 存在。"""
        chunks = chunk_text("a.md", "# T\n\n内容")
        assert chunks[0].content_hash

    def test_empty_content(self):
        assert chunk_text("a.md", "") == []


class TestCollectSources:
    def test_default_sources(self, project):
        """GIVEN 项目 WHEN collect THEN 默认源收集。"""
        paths = collect_source_paths(project)
        names = [p.name for p in paths]
        assert "spec.md" in names
        assert "TASK_STATUS.md" in names

    def test_extra_source(self, project):
        """GIVEN extra 源 WHEN collect THEN 加入。"""
        (project / "README.md").write_text("# readme", encoding="utf-8")
        paths = collect_source_paths(project, extra=["README.md"])
        assert any(p.name == "README.md" for p in paths)


class TestIngest:
    def test_ingest_writes_articles(self, project, store):
        """GIVEN 项目 WHEN ingest THEN 文章写入。"""
        report = ingest_project(project, store)
        assert report.articles_written >= 2
        assert store.count_articles() == report.articles_written

    def test_ingest_incremental_skips(self, project, store):
        """GIVEN 摄取两次 WHEN ingest THEN 第二次全跳过（增量 EI-M3D.3）。"""
        r1 = ingest_project(project, store)
        r2 = ingest_project(project, store)
        assert r2.skipped_unchanged == r1.articles_written
        assert r2.articles_written == 0
        assert store.count_articles() == r1.articles_written

    def test_ingest_source_tagged(self, project, store):
        """GIVEN 摄取 WHEN ingest THEN 文章 source='ingest'。"""
        ingest_project(project, store)
        articles = store.list_articles(limit=100)
        assert all(a.source == "ingest" for a in articles)

    def test_ingest_with_vectors_mock(self, project, store, monkeypatch):
        """GIVEN mock embedding+vector WHEN ingest THEN 向量写入。"""
        class MockEmbedding:
            name = "mock"
            def embed(self, texts):
                return [[0.1] * 8 for _ in texts]
        class MockVectorStore:
            def __init__(self):
                self.writes = []
            available = True
            def upsert(self, content_hash, vec, rowid=None):
                self.writes.append((content_hash, rowid))
                return True
            def count(self):
                return len(self.writes)
        vs = MockVectorStore()
        report = ingest_project(project, store, MockEmbedding(), vs)
        assert report.vectors_written == report.articles_written
        assert len(vs.writes) == report.articles_written

    def test_remove_stale(self, tmp_path, store):
        """GIVEN 源文件删除 WHEN remove_stale THEN 记录清理（EI-M3D.3）。"""
        p = tmp_path / "proj-b"
        (p / "docs").mkdir(parents=True)
        (p / "docs" / "spec.md").write_text("# 规范", encoding="utf-8")
        ingest_project(p, store)
        assert store.count_articles() >= 1
        # 删除源文件后清理
        (p / "docs" / "spec.md").unlink()
        removed = remove_stale_articles(p, store)
        assert removed >= 1

    def test_ingest_error_tolerated(self, tmp_path, store):
        """GIVEN 项目缺失 WHEN ingest THEN 空报告不 crash。"""
        report = ingest_project(tmp_path / "nonexistent", store)
        assert report.articles_written == 0
