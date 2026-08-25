"""Tests for kb/store.py — FTS5 full-text search (EI-M3B)."""

# @tests src/yuleosh/kb/store.py

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


class TestFts5Search:
    def test_chinese_keyword_search(self, store):
        """GIVEN 含中文内容 WHEN search THEN FTS5 trigram 召回。"""
        store.create_article({
            "title": "错误处理需求", "content": "系统必须正确处理错误", "source": "manual",
        })
        store.create_article({
            "title": "其他", "content": "无关内容", "source": "manual",
        })
        results = store.list_articles(search="错误处理")
        assert len(results) == 1
        assert results[0].title == "错误处理需求"

    def test_english_word_search(self, store):
        """GIVEN 英文内容 WHEN search THEN 召回。"""
        store.create_article({
            "title": "uart driver", "content": "UART driver implementation", "source": "manual",
        })
        store.create_article({
            "title": "i2c driver", "content": "I2C driver", "source": "manual",
        })
        results = store.list_articles(search="uart")
        assert len(results) == 1
        assert results[0].title == "uart driver"

    def test_search_in_title_and_content(self, store):
        """GIVEN 关键词在 title 或 content WHEN search THEN 都召回。"""
        store.create_article({"title": "ADC 采集", "content": "adc read", "source": "manual"})
        store.create_article({"title": "other", "content": "含 ADC 逻辑", "source": "manual"})
        results = store.list_articles(search="ADC")
        assert len(results) == 2

    def test_count_matches_search(self, store):
        """GIVEN 搜索 WHEN count THEN 与 list 一致。"""
        for i in range(3):
            store.create_article({
                "title": f"需求{i}", "content": f"刹车失效处理场景{i}", "source": "manual",
            })
        assert store.count_articles(search="刹车失效") == 3
        assert store.count_articles(search="不存在的词") == 0

    def test_fts_syncs_on_insert(self, store):
        """GIVEN 插入后 WHEN 立即搜索 THEN 索引同步（触发器）。"""
        store.create_article({"title": "看门狗", "content": "watchdog timeout", "source": "manual"})
        assert store.count_articles(search="看门狗") == 1

    def test_fts_syncs_on_delete(self, store):
        """GIVEN 删除后 WHEN 搜索 THEN 不再召回（触发器 delete）。"""
        a = store.create_article({"title": "看门狗", "content": "watchdog", "source": "manual"})
        assert store.count_articles(search="看门狗") == 1
        store.delete_article(a.id)
        assert store.count_articles(search="看门狗") == 0

    def test_fts_syncs_on_update(self, store):
        """GIVEN 更新内容后 WHEN 搜索新词 THEN 召回（触发器 update）。"""
        a = store.create_article({"title": "x", "content": "old content", "source": "manual"})
        store.update_article(a.id, {"content": "新的刹车内容"})
        assert store.count_articles(search="刹车") == 1
        assert store.count_articles(search="old") == 0

    def test_special_chars_escaped(self, store):
        """GIVEN 搜索词含 FTS5 特殊字符 WHEN search THEN 不抛异常。"""
        store.create_article({"title": "t", "content": "普通内容", "source": "manual"})
        # 特殊字符不 crash，返回结果（可能为空）
        results = store.list_articles(search='a"b*c:d(e)')
        assert isinstance(results, list)


class TestFtsIndexBackfill:
    def test_legacy_db_backfilled(self):
        """GIVEN 旧库（建表后直插数据，无 FTS 索引）WHEN 重新打开 THEN 回填可检索。"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        # 模拟旧库：先创建 store（建 FTS 表），再 SQL 直插数据（绕过触发器）
        s1 = KbStore(db_path)
        conn = s1._get_conn()
        conn.execute(
            "INSERT INTO kb_articles (title, content, source, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("旧数据", "遗留内容", "manual", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.commit()
        s1.close()

        # 重新打开：_init_db 检测 base=FTS 不一致 → rebuild 回填
        s2 = KbStore(db_path)
        assert s2.count_articles(search="遗留") == 1
        s2.close()
        os.unlink(db_path)
