# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Performance benchmarks for KB deduplication logic in kb/store.py.

Tests measure execution time of deduplicate_misra_articles() at various
data sizes (100, 1,000, 10,000 articles) using time.perf_counter().

Baseline requirement: 10,000 articles must complete within 5 seconds.
The dedup is currently O(n) over articles with O(n) per-article extraction
(no nested loop), so should be well under 5s even at 10k.
"""

import os
import time
import tempfile
import pytest

from yuleosh.kb.store import KbStore


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


def _create_misra_article(store, title, source_ref, tags="misra,required"):
    """Helper to create a MISRA analysis article."""
    return store.create_article({
        "title": title,
        "content": "test content",
        "source": "misra_analysis",
        "source_ref": source_ref,
        "tags": tags,
    })


def _populate_misra_articles(store, count: int, dup_ratio: float = 0.3):
    """Populate store with `count` MISRA articles.

    dup_ratio controls fraction of articles that are duplicates of existing
    entries (simulating CI runs producing repeated violations).
    """
    import random
    import string

    unique_count = int(count * (1 - dup_ratio))
    dup_count = count - unique_count

    rule_ids = [
        "10.1", "10.3", "11.2", "11.5", "12.1", "12.5",
        "13.2", "14.3", "14.4", "15.1", "15.7", "16.1",
        "16.6", "17.1", "17.4", "17.7", "17.8", "18.1",
        "18.4", "18.8", "19.1", "20.1", "20.7", "21.1",
        "21.10", "21.12", "21.18", "22.1", "22.2", "22.3",
    ]
    files = [f"src/module_{i}/file_{j}.c" for i in range(20) for j in range(5)]

    # Create unique articles
    unique_pairs = []
    for i in range(unique_count):
        rule = random.choice(rule_ids)
        file = random.choice(files)
        line = random.randint(1, 500)
        unique_pairs.append((rule, file, line))

    for rule, file, line in unique_pairs:
        title = f"MISRA-{rule}: violation at {file}:{line}"
        source_ref = f"{file}:{line}"
        _create_misra_article(store, title, source_ref)

    # Create duplicates (re-use some unique pairs)
    for _ in range(dup_count):
        rule, file, line = random.choice(unique_pairs)
        title = f"MISRA-{rule}: violation at {file}:{line}"
        source_ref = f"{file}:{line}"
        _create_misra_article(store, title, source_ref)


# ── Performance tests ─────────────────────────────────────────────────

class TestDedupPerformance:
    """Performance measurements for deduplication at various scales."""

    @pytest.mark.perf
    def test_dedup_100_articles(self, store):
        """GIVEN 100 MISRA articles WHEN dedup THEN completes quickly."""
        _populate_misra_articles(store, 100)

        start = time.perf_counter()
        result = store.deduplicate_misra_articles()
        elapsed = time.perf_counter() - start

        assert result["articles_before"] == 100
        print(f"\n  ✅ 100 articles: {elapsed:.4f}s (removed={result['removed']}, kept={result['kept']})")

        # Should be near-instant for 100 articles
        assert elapsed < 1.0, f"100 articles took {elapsed:.4f}s (threshold: 1.0s)"

    @pytest.mark.perf
    def test_dedup_1000_articles(self, store):
        """GIVEN 1,000 MISRA articles WHEN dedup THEN completes in reasonable time."""
        _populate_misra_articles(store, 1000)

        start = time.perf_counter()
        result = store.deduplicate_misra_articles()
        elapsed = time.perf_counter() - start

        print(f"\n  ✅ 1,000 articles: {elapsed:.4f}s (removed={result['removed']}, kept={result['kept']})")

        # Should still be fast for 1,000
        assert elapsed < 2.0, f"1,000 articles took {elapsed:.4f}s (threshold: 2.0s)"

    @pytest.mark.perf
    def test_dedup_10000_articles(self, store):
        """GIVEN 10,000 MISRA articles WHEN dedup THEN completes within 5 seconds.

        This is the baseline performance requirement — verify that the O(n)
        dedup approach can handle 10,000 records without excessive memory
        or time overhead.
        """
        _populate_misra_articles(store, 10000)

        start = time.perf_counter()
        result = store.deduplicate_misra_articles()
        elapsed = time.perf_counter() - start

        print(f"\n  ✅ 10,000 articles: {elapsed:.4f}s (removed={result['removed']}, kept={result['kept']})")

        # Baseline: 10k records should complete within 5 seconds
        assert elapsed <= 5.0, (
            f"10,000 articles took {elapsed:.4f}s (threshold: 5.0s). "
            "This exceeds the performance baseline. Consider optimization: "
            "the dedup is already O(n), but the regex extraction per article "
            "could be sped up with compiled regex patterns stored as class "
            "attributes instead of re-compiling every call."
        )

    @pytest.mark.perf
    def test_dedup_no_duplicates_1000(self, store):
        """GIVEN 1,000 unique MISRA articles (no duplicates) WHEN dedup THEN fast."""
        _populate_misra_articles(store, 1000, dup_ratio=0.0)

        start = time.perf_counter()
        result = store.deduplicate_misra_articles()
        elapsed = time.perf_counter() - start

        print(f"\n  ✅ 1,000 unique articles (no dupes): {elapsed:.4f}s")
        assert elapsed < 2.0

    @pytest.mark.perf
    def test_dedup_all_duplicates_100(self, store):
        """GIVEN 100 identical articles WHEN dedup THEN removes 99 efficiently."""
        rule = "MISRA-10.1: same violation"
        for _ in range(100):
            _create_misra_article(store, rule, "same_file.c:42")

        start = time.perf_counter()
        result = store.deduplicate_misra_articles()
        elapsed = time.perf_counter() - start

        print(f"\n  ✅ 100 identical articles: {elapsed:.4f}s (removed={result['removed']})")
        assert result["removed"] == 99
        assert result["kept"] == 1
        assert elapsed < 1.0

    @pytest.mark.perf
    def test_list_deduped_perf_1000(self, store):
        """GIVEN 1,000 articles WHEN listing deduped THEN fast."""
        _populate_misra_articles(store, 1000)

        start = time.perf_counter()
        articles = store.list_deduped_misra_articles(limit=500)
        elapsed = time.perf_counter() - start

        print(f"\n  ✅ list_deduped (1k articles, limit=500): {elapsed:.4f}s (returned={len(articles)})")
        assert elapsed < 2.0

    @pytest.mark.perf
    def test_count_by_rule_perf_1000(self, store):
        """GIVEN 1,000 articles WHEN counting by rule THEN fast."""
        _populate_misra_articles(store, 1000)

        start = time.perf_counter()
        counts = store.count_misra_violations_by_rule()
        elapsed = time.perf_counter() - start

        print(f"\n  ✅ count_by_rule (1k articles): {elapsed:.4f}s (rules={len(counts)})")
        assert elapsed < 2.0
