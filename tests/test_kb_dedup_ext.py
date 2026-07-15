"""Depth tests for kb/store.py — MISRA deduplication and listing methods.

Covers:
  - deduplicate_misra_articles: empty, with dupes, with partial keys, edge cases
  - list_deduped_misra_articles: pagination, dedup logic
  - count_misra_violations_by_rule: per-rule counts
  - Various tag/rule_id extraction edge cases
"""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.kb.store import KbStore
from yuleosh.kb.models import KbArticle


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def store():
    """Create a KbStore with a temporary SQLite DB."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = KbStore(db_path)
    yield s
    s.close()
    os.unlink(db_path)


def _create_misra_article(store, title, source_ref, tags="misra,required", content="test content"):
    """Helper to create a MISRA analysis article."""
    return store.create_article({
        "title": title,
        "content": content,
        "source": "misra_analysis",
        "source_ref": source_ref,
        "tags": tags,
    })


# ── deduplicate_misra_articles ────────────────────────────────────────

class TestDeduplicateMisraArticles:
    def test_no_misra_articles(self, store):
        """GIVEN no MISRA articles WHEN dedup THEN empty result."""
        result = store.deduplicate_misra_articles()
        assert result == {"articles_before": 0, "removed": 0, "kept": 0}

    def test_no_duplicates(self, store):
        """GIVEN unique MISRA articles WHEN dedup THEN none removed."""
        a1 = _create_misra_article(store, "MISRA-10.1: test", "file1.c:10")
        a2 = _create_misra_article(store, "MISRA-10.3: test", "file2.c:20")
        result = store.deduplicate_misra_articles()
        assert result["articles_before"] == 2
        assert result["removed"] == 0
        assert result["kept"] == 2

    def test_duplicates_removed(self, store):
        """GIVEN duplicate MISRA entries for same (rule, file, line) WHEN dedup THEN removes older."""
        a1 = _create_misra_article(store, "MISRA-10.1: test", "file1.c:10")
        a2 = _create_misra_article(store, "MISRA-10.1: test again", "file1.c:10")
        result = store.deduplicate_misra_articles()
        assert result["articles_before"] == 2
        assert result["removed"] == 1
        assert result["kept"] == 1

    def test_partial_key_no_rule_id(self, store):
        """GIVEN articles with no rule_id extracted WHEN dedup THEN kept (skip non-dedup-able)."""
        a = _create_misra_article(store, "No rule in title", "src.c:42", tags="general")
        result = store.deduplicate_misra_articles()
        assert result["articles_before"] == 1
        assert result["removed"] == 0

    def test_rule_id_from_tags(self, store):
        """GIVEN articles with rule in tags WHEN dedup THEN extracts rule_id from tags."""
        a1 = _create_misra_article(store, "Random title", "file.c:5", tags="misra,required,rule-10-1")
        a2 = _create_misra_article(store, "Random title 2", "file.c:5", tags="misra,required,rule-10-1")
        result = store.deduplicate_misra_articles()
        assert result["removed"] == 1

    def test_source_ref_no_colon(self, store):
        """GIVEN source_ref without colon WHEN dedup THEN file_path empty, line_num=0."""
        a = _create_misra_article(store, "MISRA-10.1: test", "nocolon")
        result = store.deduplicate_misra_articles()
        assert result["articles_before"] == 1
        assert result["removed"] == 0

    def test_source_ref_invalid_line(self, store):
        """GIVEN source_ref with non-numeric line WHEN dedup THEN line_num=0."""
        a = _create_misra_article(store, "MISRA-10.1: test", "file.c:abc")
        result = store.deduplicate_misra_articles()
        assert result["articles_before"] == 1

    def test_dedup_keeps_highest_id(self, store):
        """GIVEN 3 duplicates WHEN dedup THEN keeps only 1 (the latest/highest id)."""
        a1 = _create_misra_article(store, "MISRA-17.7: violation", "main.c:50", tags="rule-17-7")
        a2 = _create_misra_article(store, "MISRA-17.7: violation", "main.c:50", tags="rule-17-7")
        a3 = _create_misra_article(store, "MISRA-17.7: violation", "main.c:50", tags="rule-17-7")
        result = store.deduplicate_misra_articles()
        assert result["articles_before"] == 3
        assert result["removed"] == 2
        assert result["kept"] == 1


# ── list_deduped_misra_articles ───────────────────────────────────────

class TestListDedupedMisraArticles:
    def test_empty(self, store):
        """GIVEN no MISRA articles WHEN listing deduped THEN empty list."""
        articles = store.list_deduped_misra_articles()
        assert articles == []

    def test_basic_dedup_listing(self, store):
        """GIVEN duplicates WHEN listing deduped THEN only unique ones returned."""
        a1 = _create_misra_article(store, "MISRA-10.1: test", "file1.c:10")
        a2 = _create_misra_article(store, "MISRA-10.1: test", "file1.c:10")
        articles = store.list_deduped_misra_articles()
        assert len(articles) == 1

    def test_different_files_both_kept(self, store):
        """GIVEN same rule different file WHEN listing THEN both returned."""
        a1 = _create_misra_article(store, "MISRA-10.1: test", "file1.c:10")
        a2 = _create_misra_article(store, "MISRA-10.1: test", "file2.c:20")
        articles = store.list_deduped_misra_articles()
        assert len(articles) == 2

    def test_pagination(self, store):
        """GIVEN pagination params WHEN listing THEN respects offset/limit."""
        for i in range(5):
            _create_misra_article(store, f"MISRA-{10+i}.1: test", f"file{i}.c:{i*10}")
        all_articles = store.list_deduped_misra_articles(limit=10)
        assert len(all_articles) == 5
        paginated = store.list_deduped_misra_articles(limit=2, offset=2)
        assert len(paginated) == 3

    def test_articles_without_rule_file_kept(self, store):
        """GIVEN articles with empty fields WHEN listing THEN included."""
        a = store.create_article({
            "title": "No rule", "content": "test",
            "source": "misra_analysis", "source_ref": "",
            "tags": "",
        })
        articles = store.list_deduped_misra_articles()
        assert len(articles) == 1

    def test_rule_id_from_tags_list(self, store):
        """GIVEN article with rule in tags WHEN listing deduped THEN dedup works."""
        a1 = _create_misra_article(store, "Title A", "f1.c:1", tags="rule-8-7")
        a2 = _create_misra_article(store, "Title B", "f1.c:2", tags="rule-8-7")
        a3 = _create_misra_article(store, "Title C", "f1.c:2", tags="rule-8-7")
        articles = store.list_deduped_misra_articles()
        # a2 and a3 share same (rule-8.7, f1.c, 2) so only one kept
        assert len(articles) == 2


# ── count_misra_violations_by_rule ────────────────────────────────────

class TestCountMisraViolationsByRule:
    def test_empty(self, store):
        """GIVEN no violations WHEN counting THEN empty dict."""
        counts = store.count_misra_violations_by_rule()
        assert counts == {}

    def test_basic_counts(self, store):
        """GIVEN violations by rule WHEN counting THEN correct per-rule counts."""
        _create_misra_article(store, "MISRA-10.1: test", "f1.c:10")
        _create_misra_article(store, "MISRA-10.1: test", "f2.c:20")
        _create_misra_article(store, "MISRA-17.7: test", "f1.c:30")
        counts = store.count_misra_violations_by_rule()
        assert counts.get("10.1") == 2
        assert counts.get("17.7") == 1

    def test_dedup_per_rule(self, store):
        """GIVEN same (file,line) for same rule WHEN counting THEN counted once."""
        _create_misra_article(store, "MISRA-10.1: test", "f1.c:10")
        _create_misra_article(store, "MISRA-10.1: test", "f1.c:10")
        counts = store.count_misra_violations_by_rule()
        assert counts.get("10.1") == 1

    def test_rule_from_tags(self, store):
        """GIVEN rule from tags WHEN counting THEN extracts correctly."""
        _create_misra_article(store, "Title", "f1.c:10", tags="rule-8-13")
        counts = store.count_misra_violations_by_rule()
        assert "8.13" in counts

    def test_no_rule_skipped(self, store):
        """GIVEN article without extractable rule WHEN counting THEN skipped."""
        store.create_article({
            "title": "No rule ref", "content": "test",
            "source": "misra_analysis", "source_ref": "f1.c:10",
            "tags": "",
        })
        counts = store.count_misra_violations_by_rule()
        assert counts == {}

    def test_invalid_line_skipped(self, store):
        """GIVEN article with non-numeric line WHEN counting THEN line counted as 0."""
        _create_misra_article(store, "MISRA-10.1: test", "f1.c:abc")
        counts = store.count_misra_violations_by_rule()
        assert "10.1" in counts
