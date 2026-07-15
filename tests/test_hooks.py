# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleOSH Git hooks (pre-commit, post-merge) and kb ingest-misra."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.hooks.pre_commit import (
    _is_yuleosh_project,
    _get_staged_source_files,
    _parse_cppcheck_violations,
    _extract_rule_id,
    _find_new_violations,
    _classify_misra_category,
    _load_last_snapshot,
    _save_snapshot,
    run_pre_commit,
)
from yuleosh.hooks.post_merge import run_post_merge
from yuleosh.hooks.cli import (
    _find_git_hooks_dir,
    _install_hook,
    cmd_hook_install,
    cmd_hook_run,
    PRE_COMMIT_TEMPLATE,
    POST_MERGE_TEMPLATE,
)
from yuleosh.kb.cli import (
    _handle_ingest_misra,
    _parse_cppcheck_output,
    _extract_rule_id as kb_extract_rule_id,
    _classify_misra_category as kb_classify_category,
    _collect_source_files,
)


# ══════════════════════════════════════════════════════════════════════════
# Pre-commit: helpers
# ══════════════════════════════════════════════════════════════════════════

class TestIsYuleoshProject:
    """tests for _is_yuleosh_project detection."""

    def test_no_project_marker(self, tmp_path: Path):
        """Returns False when no .yuleosh/ or yuleosh.yaml exists."""
        assert _is_yuleosh_project(tmp_path) is False

    def test_dot_yuleosh_dir(self, tmp_path: Path):
        """Returns True when .yuleosh/ dir exists."""
        (tmp_path / ".yuleosh").mkdir()
        assert _is_yuleosh_project(tmp_path) is True

    def test_yuleosh_yaml(self, tmp_path: Path):
        """Returns True when yuleosh.yaml file exists."""
        (tmp_path / "yuleosh.yaml").write_text("project: test\n")
        assert _is_yuleosh_project(tmp_path) is True

    def test_ancestor_dot_yuleosh(self, tmp_path: Path):
        """Returns True when a parent directory has .yuleosh/."""
        (tmp_path / ".yuleosh").mkdir()
        sub = tmp_path / "deep" / "nested"
        sub.mkdir(parents=True)
        assert _is_yuleosh_project(sub) is True


class TestExtractRuleId:
    """tests for MISRA rule ID extraction."""

    def test_misra_c_format(self):
        assert _extract_rule_id("MISRA C2012-10.1 violation") == "10.1"

    def test_misra_dash_format(self):
        assert _extract_rule_id("MISRA C-10.1 violation") == "10.1"

    def test_misra_plain_rule(self):
        assert _extract_rule_id("(error) MISRA 10.1 violation") == "10.1"

    def test_rule_prefix(self):
        assert _extract_rule_id("Rule-12.3 something") == "12.3"
        assert _extract_rule_id("Rule 14.2 something") == "14.2"

    def test_no_rule(self):
        assert _extract_rule_id("no rule here") is None
        assert _extract_rule_id("") is None


class TestClassifyMISRACategory:
    """tests for MISRA rule category classification."""

    def test_required_rules(self):
        assert _classify_misra_category("10.1") == "required"
        assert _classify_misra_category("14.2") == "required"

    def test_advisory_rules(self):
        assert _classify_misra_category("15.1") == "advisory"
        assert _classify_misra_category("20.1") == "advisory"

    def test_none_rule(self):
        assert _classify_misra_category(None) == "advisory"

    def test_invalid_rule(self):
        assert _classify_misra_category("invalid") == "advisory"


class TestParseCppcheckViolations:
    """tests for parsing cppcheck output."""

    SAMPLE_BRACKETED = (
        "[src/main.c:5:3] (error) MISRA C-10.1 violation [misra-c2012-10.1]\n"
        "[src/gpio.h:12:5] (style) Unused variable [unusedVar]\n"
    )

    SAMPLE_LEGACY = (
        "src/main.c:5:3: error: MISRA C-10.1 violation\n"
        "src/uart.c:20:7: warning: Rule-12.3 something\n"
    )

    def test_parse_bracketed(self):
        violations = _parse_cppcheck_violations(self.SAMPLE_BRACKETED)
        assert len(violations) == 2
        assert violations[0]["rule_id"] == "10.1"
        assert violations[0]["file"] == "src/main.c"
        assert violations[0]["line"] == 5

    def test_parse_legacy(self):
        violations = _parse_cppcheck_violations(self.SAMPLE_LEGACY)
        assert len(violations) == 2
        assert violations[0]["file"] == "src/main.c"
        assert violations[1]["rule_id"] == "12.3"

    def test_parse_empty(self):
        assert _parse_cppcheck_violations("") == []
        assert _parse_cppcheck_violations("No violations found.\n") == []

    def test_parse_mixed(self):
        text = self.SAMPLE_BRACKETED + "\n" + self.SAMPLE_LEGACY
        violations = _parse_cppcheck_violations(text)
        assert len(violations) == 4


class TestFindNewViolations:
    """tests for comparing current vs last snapshot."""

    def test_all_new(self):
        current = [{"rule_id": "10.1", "file": "a.c", "line": 1, "message": "x"}]
        last = []
        new = _find_new_violations(current, last)
        assert len(new) == 1

    def test_no_new(self):
        current = [{"rule_id": "10.1", "file": "a.c", "line": 1, "message": "x"}]
        last = [{"rule_id": "10.1", "file": "a.c", "line": 1, "message": "x"}]
        new = _find_new_violations(current, last)
        assert len(new) == 0

    def test_partial_new(self):
        current = [
            {"rule_id": "10.1", "file": "a.c", "line": 1, "message": "x"},
            {"rule_id": "12.3", "file": "b.c", "line": 5, "message": "y"},
        ]
        last = [{"rule_id": "10.1", "file": "a.c", "line": 1, "message": "x"}]
        new = _find_new_violations(current, last)
        assert len(new) == 1
        assert new[0]["rule_id"] == "12.3"


class TestSnapshotPersistence:
    """tests for saving and loading MISRA violation snapshots."""

    def test_load_missing(self, tmp_path: Path):
        assert _load_last_snapshot(tmp_path) == []

    def test_save_and_load(self, tmp_path: Path):
        data = [{"rule_id": "10.1", "file": "a.c", "line": 1, "message": "test"}]
        _save_snapshot(tmp_path, data)
        loaded = _load_last_snapshot(tmp_path)
        assert len(loaded) == 1
        assert loaded[0]["rule_id"] == "10.1"

    def test_load_corrupted(self, tmp_path: Path):
        snap = tmp_path / ".yuleosh" / "ci" / "last-misra-snapshot.json"
        snap.parent.mkdir(parents=True)
        snap.write_text("not valid json")
        assert _load_last_snapshot(tmp_path) == []


# ══════════════════════════════════════════════════════════════════════════
# Pre-commit: integration with mocks
# ══════════════════════════════════════════════════════════════════════════

class TestRunPreCommit:
    """tests for the full run_pre_commit flow."""

    def test_not_yuleosh_project(self, tmp_path: Path):
        """Should exit early (return 0) when not in a yuleOSH project."""
        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            rc = run_pre_commit(cwd=str(tmp_path))
            assert rc == 0

    def test_no_staged_files(self, tmp_path: Path):
        """Should return 0 when no staged files exist."""
        # create project marker
        (tmp_path / ".yuleosh").mkdir()
        with patch("yuleosh.hooks.pre_commit._get_staged_source_files", return_value=[]):
            rc = run_pre_commit(cwd=str(tmp_path))
            assert rc == 0

    @patch("yuleosh.hooks.pre_commit._run_cppcheck")
    @patch("yuleosh.hooks.pre_commit._get_staged_source_files")
    def test_creates_kb_entries(self, mock_get_staged, mock_run, tmp_path: Path):
        """New violations should create KB articles."""
        (tmp_path / ".yuleosh").mkdir()
        mock_get_staged.return_value = ["src/main.c"]
        # Create a temp main.c so the hook can resolve its path
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        main_c = src_dir / "main.c"
        main_c.write_text("int main() { return 0; }")

        mock_run.return_value = "[src/main.c:5:3] (error) MISRA C-10.1 violation [misra-c2012-10.1]"

        rc = run_pre_commit(cwd=str(tmp_path))
        # Should not block the commit
        assert rc == 0

    @patch("yuleosh.hooks.pre_commit._run_cppcheck")
    @patch("yuleosh.hooks.pre_commit._get_staged_source_files")
    def test_no_block_on_new_violations(self, mock_get_staged, mock_run, tmp_path: Path):
        """Hook must NOT block commits even with new violations."""
        (tmp_path / ".yuleosh").mkdir()
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.c").write_text("int main() { return 0; }")

        mock_get_staged.return_value = ["src/main.c"]
        mock_run.return_value = "[src/main.c:5:3] (error) MISRA C-10.1 violation [misra-c2012-10.1]"

        rc = run_pre_commit(cwd=str(tmp_path))
        assert rc == 0  # Must not block


# ══════════════════════════════════════════════════════════════════════════
# Post-merge integration
# ══════════════════════════════════════════════════════════════════════════

class TestRunPostMerge:
    """tests for run_post_merge."""

    def test_not_yuleosh_project(self, tmp_path: Path):
        rc = run_post_merge(cwd=str(tmp_path))
        assert rc == 0

    def test_no_snapshot(self, tmp_path: Path):
        (tmp_path / ".yuleosh").mkdir()
        rc = run_post_merge(cwd=str(tmp_path))
        assert rc == 0


# ══════════════════════════════════════════════════════════════════════════
# Hook CLI (install, run)
# ══════════════════════════════════════════════════════════════════════════

class TestFindGitHooks:
    """tests for _find_git_hooks_dir."""

    def test_no_git(self, tmp_path: Path):
        assert _find_git_hooks_dir(str(tmp_path)) is None

    def test_finds_git(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        hooks = _find_git_hooks_dir(str(tmp_path))
        assert hooks is not None
        assert hooks.name == "hooks"


class TestInstallHook:
    """tests for _install_hook."""

    def test_writes_executable(self, tmp_path: Path):
        installed = _install_hook(tmp_path, "pre-commit", PRE_COMMIT_TEMPLATE)
        assert installed is True
        hook_path = tmp_path / "pre-commit"
        assert hook_path.exists()
        mode = hook_path.stat().st_mode
        assert mode & 0o100  # executable

    def test_idempotent(self, tmp_path: Path):
        _install_hook(tmp_path, "pre-commit", PRE_COMMIT_TEMPLATE)
        # Second install should detect existing yuleOSH hook and skip
        result = _install_hook(tmp_path, "pre-commit", PRE_COMMIT_TEMPLATE)
        assert result is False


class TestCmdHookInstall:
    """tests for cmd_hook_install."""

    def test_no_git_dir(self):
        with tempfile.TemporaryDirectory() as td:
            rc = cmd_hook_install(cwd=td)
            assert rc == 1  # Error — no .git/

    def test_installs_hooks(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        rc = cmd_hook_install(cwd=str(tmp_path))
        assert rc == 0
        pre = tmp_path / ".git" / "hooks" / "pre-commit"
        post = tmp_path / ".git" / "hooks" / "post-merge"
        assert pre.exists()
        assert post.exists()


class TestCmdHookRun:
    """tests for cmd_hook_run."""

    def test_unknown_hook(self):
        rc = cmd_hook_run("unknown")
        assert rc == 1

    def test_pre_commit_dispatch(self, tmp_path: Path):
        (tmp_path / ".yuleosh").mkdir()
        rc = cmd_hook_run("pre-commit")
        # Should work (no staged files = no issues)
        assert rc == 0

    def test_post_merge_dispatch(self, tmp_path: Path):
        rc = cmd_hook_run("post-merge")
        assert rc == 0


# ══════════════════════════════════════════════════════════════════════════
# KB ingest-misra
# ══════════════════════════════════════════════════════════════════════════

class TestKbIngestMisra:
    """tests for the kb ingest-misra command."""

    def test_ingest_dry_run(self):
        """With --dry-run, no KB articles should be created."""
        mock_store = MagicMock()
        mock_args = MagicMock()
        mock_args.input = None
        mock_args.files = ["test.c"]
        mock_args.src_dir = "src"
        mock_args.dry_run = True
        mock_args.kb_sub = "ingest-misra"

        # We need to mock the file discovery and cppcheck
        with patch("yuleosh.kb.cli._collect_source_files", return_value=["test.c"]), \
             patch("yuleosh.kb.cli._run_cppcheck_for_ingest", return_value="[test.c:5:3] (error) MISRA C-10.1 [misra-c2012-10.1]"):

            rc = _handle_ingest_misra(mock_args, mock_store)
            assert rc == 0
            mock_store.create_article.assert_not_called()

    def test_ingest_from_input_file(self, tmp_path: Path):
        """Ingesting from a pre-existing cppcheck output file should create KB entries."""
        mock_store = MagicMock()
        report_file = tmp_path / "misra-report.txt"
        report_file.write_text("[src/main.c:10:5] (error) MISRA C-10.1 violation [misra]\n")

        mock_args = MagicMock()
        mock_args.input = str(report_file)
        mock_args.files = None
        mock_args.src_dir = "src"
        mock_args.dry_run = False
        mock_args.kb_sub = "ingest-misra"

        rc = _handle_ingest_misra(mock_args, mock_store)
        assert rc == 0
        mock_store.create_article.assert_called_once()

    def test_ingest_no_violations(self, tmp_path: Path):
        """No violations should result in no KB entries and return 0."""
        mock_store = MagicMock()
        report_file = tmp_path / "empty-report.txt"
        report_file.write_text("")

        mock_args = MagicMock()
        mock_args.input = str(report_file)
        mock_args.dry_run = False
        mock_args.kb_sub = "ingest-misra"

        rc = _handle_ingest_misra(mock_args, mock_store)
        assert rc == 0
        mock_store.create_article.assert_not_called()

    def test_ingest_input_file_missing(self):
        """Non-existent input file should cause an error."""
        mock_store = MagicMock()
        mock_args = MagicMock()
        mock_args.input = "/nonexistent/report.txt"
        mock_args.kb_sub = "ingest-misra"

        rc = _handle_ingest_misra(mock_args, mock_store)
        assert rc == 1
        mock_store.create_article.assert_not_called()

    def test_classify_category_kb(self):
        assert kb_classify_category("10.1") == "required"
        assert kb_classify_category("20.1") == "advisory"

    def test_extract_rule_id_kb(self):
        assert kb_extract_rule_id("MISRA C2012-10.1 violation") == "misra-c2023-10.1"
        assert kb_extract_rule_id("no rule") is None

    def test_parse_cppcheck_kb(self):
        result = _parse_cppcheck_output("")
        assert result == []


class TestCollectSourceFiles:
    """tests for source file collection."""

    def test_collect_c_files(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.c").write_text("")
        (src / "gpio.h").write_text("")
        (src / "README.md").write_text("")

        files = _collect_source_files(str(src))
        assert len(files) == 2
        assert all(f.endswith((".c", ".h")) for f in files)

    def test_nonexistent_dir(self):
        files = _collect_source_files("/nonexistent")
        assert files == []
