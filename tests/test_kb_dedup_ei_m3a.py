"""Tests for kb/store.py — write-time dedup + cleanup (EI-M3A)."""

import os
import tempfile

import pytest

from yuleosh.kb.store import KbStore


@pytest.fixture
def store():
    """Create a KbStore with a temporary SQLite DB."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = KbStore(db_path)
    yield s
    s.close()
    os.unlink(db_path)


def _misra(fields_overrides=None):
    fields = {
        "title": "MISRA-10.1: MISRA C-10.1 violation [misra-c2012-10.1]",
        "content": "## MISRA Violation: Rule 10.1\n\nmessage",
        "source": "misra_analysis",
        "source_ref": "src/main.c:5",
        "tags": "misra,required,rule-10-1",
    }
    if fields_overrides:
        fields.update(fields_overrides)
    return fields


# ── EI-M3A.1: write-time dedup ────────────────────────────────────────

class TestWriteTimeDedup:
    def test_misra_same_source_ref_dedup(self, store):
        """GIVEN 同违规(同 file:line)写入两次 WHEN create THEN 只保留一条。"""
        a1 = store.create_article(_misra())
        a2 = store.create_article(_misra())
        assert a1.id == a2.id  # 第二次返回已有记录
        assert store.count_articles() == 1

    def test_misra_different_source_ref_kept(self, store):
        """GIVEN 不同位置违规 WHEN create THEN 各自保留（不误伤）。"""
        a1 = store.create_article(_misra({"source_ref": "src/main.c:5"}))
        a2 = store.create_article(_misra({"source_ref": "src/main.c:10"}))
        assert a1.id != a2.id
        assert store.count_articles() == 2

    def test_misra_different_rule_same_file_kept(self, store):
        """GIVEN 同文件不同规则违规 WHEN create THEN 各自保留。"""
        a1 = store.create_article(_misra({"title": "MISRA-10.1: x"}))
        a2 = store.create_article(_misra({"title": "MISRA-10.3: x"}))
        assert a1.id != a2.id
        assert store.count_articles() == 2

    def test_generic_content_hash_dedup(self, store):
        """GIVEN 非 misra 来源同内容写两次 WHEN create THEN 去重。"""
        a1 = store.create_article({"title": "t", "content": "hello world", "source": "manual"})
        a2 = store.create_article({"title": "t2", "content": "hello  world", "source": "manual"})
        assert a1.id == a2.id  # 去空白后 hash 相同
        assert store.count_articles() == 1

    def test_generic_different_content_kept(self, store):
        """GIVEN 非 misra 来源不同内容 WHEN create THEN 各自保留。"""
        a1 = store.create_article({"title": "t", "content": "aaa", "source": "manual"})
        a2 = store.create_article({"title": "t", "content": "bbb", "source": "manual"})
        assert a1.id != a2.id
        assert store.count_articles() == 2


# ── EI-M3A.3: cleanup_duplicate_articles ──────────────────────────────

class TestCleanupDuplicateArticles:
    def test_empty(self, store):
        result = store.cleanup_duplicate_articles()
        assert result["articles_before"] == 0
        assert result["removed"] == 0

    def test_backfill_and_dedup(self, store):
        """GIVEN 旧库(无 hash) 含重复 WHEN cleanup THEN 回填 hash 并去重。"""
        # 模拟旧行：直接 SQL 插入不带 content_hash
        conn = store._get_conn()
        for i in range(3):
            conn.execute(
                "INSERT INTO kb_articles (title, content, source, source_ref, tags, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"dup-{i}", "same content", "manual", "f.c:1", "", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
            )
        conn.commit()

        result = store.cleanup_duplicate_articles()
        assert result["backfilled"] == 3
        assert result["removed"] == 2
        assert result["kept"] == 1
        assert store.count_articles() == 1

    def test_cleanup_keeps_distinct(self, store):
        """GIVEN 内容各异的文章 WHEN cleanup THEN 不误删。"""
        store.create_article({"title": "a", "content": "unique-a", "source": "manual"})
        store.create_article({"title": "b", "content": "unique-b", "source": "manual"})
        result = store.cleanup_duplicate_articles()
        assert result["removed"] == 0
        assert store.count_articles() == 2


# ── 回归：MISRA 语义键不破坏现有测试夹具 ──────────────────────────────

class TestMisraFixtureCompatibility:
    def test_existing_dedup_test_fixture(self, store):
        """现有 test_kb_dedup_ext 的 _create_misra_article 夹具（默认 content 相同、
        source_ref 不同）创建的文章必须各自保留 —— 语义键按 (source, source_ref)。"""
        from yuleosh.kb.store import KbStore as _KS  # noqa: F401
        a1 = store.create_article(_misra({"source_ref": "file1.c:10"}))
        a2 = store.create_article(_misra({"source_ref": "file2.c:20"}))
        assert a1.id != a2.id
        assert store.count_articles() == 2
