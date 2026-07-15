# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Extended tests for post-merge hook: full flow, helpers, error paths."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.hooks.post_merge import (
    _classify_misra_category,
    _is_yuleosh_project,
    _load_snapshot,
    _get_existing_kb_signatures,
    run_post_merge,
    SNAPSHOT_RELPATH,
)


# ══════════════════════════════════════════════════════════════════════════
# _classify_misra_category
# ══════════════════════════════════════════════════════════════════════════

class TestClassifyMisraCategory:
    def test_none_returns_advisory(self):
        assert _classify_misra_category(None) == "advisory"

    def test_unknown_string_returns_advisory(self):
        assert _classify_misra_category("not-a-number") == "advisory"

    def test_rule_below_15_returns_required(self):
        assert _classify_misra_category("10.1") == "required"

    def test_rule_at_14_9_returns_required(self):
        assert _classify_misra_category("14.9") == "required"

    def test_rule_at_15_returns_advisory(self):
        assert _classify_misra_category("15.0") == "advisory"

    def test_rule_above_15_returns_advisory(self):
        assert _classify_misra_category("17.7") == "advisory"

    def test_rule_with_dir_prefix(self):
        """dir-X.Y strings raise ValueError and return advisory."""
        assert _classify_misra_category("dir-4.2") == "advisory"


# ══════════════════════════════════════════════════════════════════════════
# _load_snapshot
# ══════════════════════════════════════════════════════════════════════════

class TestLoadSnapshot:
    def test_snapshot_not_found(self, tmp_path: Path):
        assert _load_snapshot(tmp_path) == []

    def test_invalid_json(self, tmp_path: Path):
        snap = tmp_path / SNAPSHOT_RELPATH
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text("not valid json")
        assert _load_snapshot(tmp_path) == []

    def test_valid_snapshot(self, tmp_path: Path):
        snap = tmp_path / SNAPSHOT_RELPATH
        snap.parent.mkdir(parents=True, exist_ok=True)
        data = [{"rule_id": "10.1", "file": "src/main.c", "line": 42}]
        snap.write_text(json.dumps(data))
        result = _load_snapshot(tmp_path)
        assert result == data

    def test_empty_array(self, tmp_path: Path):
        snap = tmp_path / SNAPSHOT_RELPATH
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text("[]")
        assert _load_snapshot(tmp_path) == []


# ══════════════════════════════════════════════════════════════════════════
# _get_existing_kb_signatures
# ══════════════════════════════════════════════════════════════════════════

class TestGetExistingKbSignatures:
    def test_empty_store(self):
        store = MagicMock()
        store.list_articles.return_value = []
        assert _get_existing_kb_signatures(store) == set()

    def test_articles_with_source_ref(self):
        store = MagicMock()
        art1 = MagicMock(title="MISRA-10.1: violation", source_ref="src/main.c:42", tags="misra,required")
        art2 = MagicMock(title="MISRA-17.7: issue", source_ref="src/foo.c:99", tags="misra,advisory")
        store.list_articles.return_value = [art1, art2]

        sigs = _get_existing_kb_signatures(store)
        assert "10.1:src/main.c:42" in sigs
        assert "17.7:src/foo.c:99" in sigs
        assert len(sigs) == 2

    def test_article_without_source_ref(self):
        store = MagicMock()
        art = MagicMock(title="MISRA-10.1: violation", source_ref="", tags=None)
        store.list_articles.return_value = [art]
        sigs = _get_existing_kb_signatures(store)
        assert "10.1:" in sigs or len(sigs) == 1


# ══════════════════════════════════════════════════════════════════════════
# run_post_merge — full flow
# ══════════════════════════════════════════════════════════════════════════

class TestRunPostMergeFull:
    def test_with_snapshot_creates_articles(self, tmp_path: Path):
        """When a snapshot exists and KB is empty, articles should be created."""
        (tmp_path / ".yuleosh").mkdir()

        # Create snapshot
        snap = tmp_path / SNAPSHOT_RELPATH
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps([
            {"rule_id": "10.1", "file": "src/main.c", "line": 42,
             "message": "rule X", "severity": "style"},
            {"rule_id": "17.7", "file": "src/foo.c", "line": 99,
             "message": "rule Y", "severity": "warning"},
        ]))

        with patch("yuleosh.hooks.post_merge.KbStore") as MockKbStore:
            mock_store = MagicMock()
            mock_store.list_articles.return_value = []
            MockKbStore.return_value = mock_store

            rc = run_post_merge(cwd=str(tmp_path))
            assert rc == 0
            # Should have created 2 articles
            assert mock_store.create_article.call_count == 2

            # Verify first article content
            call1 = mock_store.create_article.call_args_list[0]
            args1 = call1[0][0]  # positional dict arg
            assert "MISRA-10.1" in args1["title"]
            assert "misra,required" in args1["tags"]
            assert "src/main.c" in args1["content"]
            assert "42" in args1["source_ref"]

    def test_snapshot_all_in_kb(self, tmp_path: Path):
        """When all violations are already in KB, no articles created."""
        (tmp_path / ".yuleosh").mkdir()

        snap = tmp_path / SNAPSHOT_RELPATH
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps([
            {"rule_id": "10.1", "file": "src/main.c", "line": 42,
             "message": "rule X", "severity": "style"},
        ]))

        with patch("yuleosh.hooks.post_merge.KbStore") as MockKbStore:
            mock_store = MagicMock()
            # Return an article that matches the signature
            existing = MagicMock(
                title="MISRA-10.1: rule X",
                source_ref="src/main.c:42",
                tags="misra,required",
            )
            mock_store.list_articles.return_value = [existing]
            MockKbStore.return_value = mock_store

            rc = run_post_merge(cwd=str(tmp_path))
            assert rc == 0
            mock_store.create_article.assert_not_called()

    def test_exception_in_store(self, tmp_path: Path):
        """When KbStore raises, return 1."""
        (tmp_path / ".yuleosh").mkdir()

        snap = tmp_path / SNAPSHOT_RELPATH
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps([
            {"rule_id": "10.1", "file": "src/main.c", "line": 42, "message": "rule X", "severity": "style"},
        ]))

        with patch("yuleosh.hooks.post_merge.KbStore") as MockKbStore:
            MockKbStore.side_effect = RuntimeError("DB down")
            rc = run_post_merge(cwd=str(tmp_path))
            assert rc == 1

    def test_snapshot_unknown_rule_id(self, tmp_path: Path):
        """When rule_id is missing, use 'unknown'."""
        (tmp_path / ".yuleosh").mkdir()

        snap = tmp_path / SNAPSHOT_RELPATH
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps([
            {"file": "src/main.c", "line": 42, "message": "unknown rule", "severity": "style"},
        ]))

        with patch("yuleosh.hooks.post_merge.KbStore") as MockKbStore:
            mock_store = MagicMock()
            mock_store.list_articles.return_value = []
            MockKbStore.return_value = mock_store

            rc = run_post_merge(cwd=str(tmp_path))
            assert rc == 0
            mock_store.create_article.assert_called_once()
            args0 = mock_store.create_article.call_args[0][0]
            assert "MISRA-unknown" in args0["title"]
            assert "misra,advisory" in args0["tags"]
