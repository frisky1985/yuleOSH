#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""pipeline.session_prune — 会话目录分层保留（T0–T3）。

覆盖边界：
* T0（空目录 / created 中止）整体回收
* T1（session.json / gate-summary.json）+ T2（LLM 产物）永不被裁
* T3（VOLATILE_STEPS 产物）只保留在最近 ``keep_last`` 个 run 里
* ``dry_run`` 默认开启 —— 只出方案，不动磁盘
* 排序按 ``created_at``，不靠目录名或 mtime
"""

import json
from pathlib import Path

import pytest

from yuleosh.pipeline.session_prune import (
    _apply,
    deterministic_evidence_files,
    format_plan,
    plan_prune,
    plan_prune_root,
    prune_sessions,
    prune_sessions_root,
)

# T3 样本：覆盖 `<step_key>.json`、别名、以及补集清单三种来源
_T3_SAMPLES = (
    "c-unit-test.json",            # <step_key>.json
    "critical-safety-report.json",  # gates 别名 (review-critical-safety)
    "ctest-junit.xml",             # 补集 (integration-test)
    "qualification-test.json",     # 补集 (test-qualification 实际产物名)
)
_T1_SAMPLES = ("session.json", "gate-summary.json")
_T2_SAMPLES = ("prd.md", "architecture.md", "final-report.md")


def _make_run(root: Path, run_id: str, *, created_at: str,
              status: str = "completed", extra_names=()) -> Path:
    d = root / run_id
    d.mkdir(parents=True)
    (d / "session.json").write_text(json.dumps({
        "name": run_id, "status": status, "created_at": created_at,
    }), encoding="utf-8")
    for name in (*_T1_SAMPLES[1:], *_T2_SAMPLES, *_T3_SAMPLES, *extra_names):
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    return d


class TestT0Aborted:
    """T0 —— 从未跑起来的会话，整体回收。"""

    def test_empty_dir_is_aborted(self, tmp_path):
        (tmp_path / "empty-one").mkdir()
        plan = plan_prune_root(tmp_path)
        assert plan["aborted"] == ["empty-one"]

    def test_created_status_is_aborted(self, tmp_path):
        d = tmp_path / "never-ran"
        d.mkdir()
        (d / "session.json").write_text(
            json.dumps({"name": "x", "status": "created"}), encoding="utf-8")
        assert plan_prune_root(tmp_path)["aborted"] == ["never-ran"]

    def test_aborted_is_removed_entirely(self, tmp_path):
        """即使中止的 run 里已有 T2 产物，T0 判据优先 —— 它没有有效证据。"""
        d = tmp_path / "aborted-with-prd"
        d.mkdir()
        (d / "session.json").write_text(
            json.dumps({"name": "x", "status": "created"}), encoding="utf-8")
        (d / "prd.md").write_text("draft", encoding="utf-8")

        _apply(plan_prune_root(tmp_path), dry_run=False)
        assert not d.exists()

    def test_completed_run_is_not_aborted(self, tmp_path):
        _make_run(tmp_path, "done", created_at="2026-09-01T00:00:00")
        plan = plan_prune_root(tmp_path)
        assert plan["aborted"] == []
        assert plan["kept_full"] == ["done"]


class TestLayeredRetention:
    """keep_last 决定完整保留几个 run，更早的只裁 T3。"""

    def test_newest_n_kept_fully_older_pruned(self, tmp_path):
        for i in range(5):
            _make_run(tmp_path, f"run{i}",
                      created_at=f"2026-09-0{i + 1}T10:00:00")

        plan = plan_prune_root(tmp_path, keep_last=2)

        # run4/run3 最新两个 → 完整保留；run0~run2 进入裁剪
        assert plan["kept_full"] == ["run4", "run3"]
        assert sorted(plan["pruned"]) == ["run0", "run1", "run2"]

    def test_t1_and_t2_survive_t3_prune(self, tmp_path):
        _make_run(tmp_path, "old", created_at="2026-09-01T10:00:00")
        _make_run(tmp_path, "new", created_at="2026-09-02T10:00:00")

        _apply(plan_prune_root(tmp_path, keep_last=1), dry_run=False)

        survivors = {p.name for p in (tmp_path / "old").iterdir()}
        assert survivors == set(_T1_SAMPLES) | set(_T2_SAMPLES)
        # 最新一个 run 完全没动
        assert len(list((tmp_path / "new").iterdir())) == (
            len(_T1_SAMPLES) + len(_T2_SAMPLES) + len(_T3_SAMPLES))

    def test_keep_last_zero_prunes_all_real_runs(self, tmp_path):
        _make_run(tmp_path, "a", created_at="2026-09-01T10:00:00")
        _make_run(tmp_path, "b", created_at="2026-09-02T10:00:00")
        plan = plan_prune_root(tmp_path, keep_last=0)
        assert plan["kept_full"] == []
        assert sorted(plan["pruned"]) == ["a", "b"]

    def test_keep_last_beyond_count_is_noop(self, tmp_path):
        _make_run(tmp_path, "only", created_at="2026-09-01T10:00:00")
        plan = plan_prune_root(tmp_path, keep_last=10)
        assert plan["pruned"] == {}
        assert plan["kept_full"] == ["only"]

    def test_negative_keep_last_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            plan_prune_root(tmp_path, keep_last=-1)

    def test_ordering_uses_created_at_not_dir_name(self, tmp_path):
        """目录名与时间不一致时，以 created_at 为准。"""
        _make_run(tmp_path, "zzz-old", created_at="2026-01-01T00:00:00")
        _make_run(tmp_path, "aaa-new", created_at="2026-09-01T00:00:00")

        plan = plan_prune_root(tmp_path, keep_last=1)
        assert plan["kept_full"] == ["aaa-new"]
        assert list(plan["pruned"]) == ["zzz-old"]


class TestDryRun:
    """默认不删 —— 调用方必须显式声明。"""

    def test_default_is_dry_run(self, tmp_path):
        _make_run(tmp_path, "old", created_at="2026-09-01T10:00:00")
        _make_run(tmp_path, "new", created_at="2026-09-02T10:00:00")

        result = prune_sessions_root(tmp_path, keep_last=1)

        assert result["dry_run"] is True
        assert (tmp_path / "old" / "c-unit-test.json").exists()

    def test_apply_removes_t3_only(self, tmp_path):
        _make_run(tmp_path, "old", created_at="2026-09-01T10:00:00")
        _make_run(tmp_path, "new", created_at="2026-09-02T10:00:00")

        result = prune_sessions_root(tmp_path, keep_last=1, dry_run=False)

        assert result["dry_run"] is False
        assert not (tmp_path / "old" / "c-unit-test.json").exists()
        assert (tmp_path / "old" / "session.json").exists()
        assert (tmp_path / "new" / "c-unit-test.json").exists()

    def test_missing_root_is_not_an_error(self, tmp_path):
        plan = plan_prune_root(tmp_path / "nope")
        assert plan["exists"] is False
        assert plan["scanned"] == 0
        _apply(plan, dry_run=False)  # 不应抛

    def test_plan_reports_bytes_and_counts(self, tmp_path):
        _make_run(tmp_path, "old", created_at="2026-09-01T10:00:00")
        _make_run(tmp_path, "new", created_at="2026-09-02T10:00:00")
        plan = plan_prune_root(tmp_path, keep_last=1)
        assert plan["files_removed"] == len(_T3_SAMPLES)
        assert plan["bytes_freed"] > 0


class TestEvidenceSelection:
    """T3 判定：来自 VOLATILE_STEPS 映射 + 补集，且排除 T1。"""

    def test_picks_step_artifacts_and_aliases(self, tmp_path):
        d = _make_run(tmp_path, "r", created_at="2026-09-01T10:00:00")
        names = {p.name for p in deterministic_evidence_files(d)}
        for expected in _T3_SAMPLES:
            assert expected in names, expected

    def test_never_selects_summary_layer(self, tmp_path):
        d = _make_run(tmp_path, "r", created_at="2026-09-01T10:00:00")
        names = {p.name for p in deterministic_evidence_files(d)}
        assert names.isdisjoint(_T1_SAMPLES)

    def test_never_selects_llm_products(self, tmp_path):
        d = _make_run(tmp_path, "r", created_at="2026-09-01T10:00:00")
        names = {p.name for p in deterministic_evidence_files(d)}
        assert names.isdisjoint(_T2_SAMPLES)

    def test_missing_files_are_skipped(self, tmp_path):
        d = tmp_path / "bare"
        d.mkdir()
        assert deterministic_evidence_files(d) == []


class TestProjectDirEntry:
    """prune_sessions 走 <project>/.osh/sessions 约定。"""

    def test_targets_project_sessions_dir(self, tmp_path):
        root = tmp_path / "proj" / ".osh" / "sessions"
        _make_run(root, "old", created_at="2026-09-01T10:00:00")
        _make_run(root, "new", created_at="2026-09-02T10:00:00")

        plan = plan_prune(tmp_path / "proj", keep_last=1)
        assert plan["kept_full"] == ["new"]

        prune_sessions(tmp_path / "proj", keep_last=1, dry_run=False)
        assert not (root / "old" / "c-unit-test.json").exists()
        assert (root / "old" / "session.json").exists()


class TestReporting:
    """清理必须显式 —— 方案要能被人读到。"""

    def test_format_reports_dry_run(self, tmp_path):
        root = tmp_path / "proj" / ".osh" / "sessions"
        _make_run(root, "old", created_at="2026-09-01T10:00:00")
        _make_run(root, "new", created_at="2026-09-02T10:00:00")
        text = format_plan(plan_prune(tmp_path / "proj", keep_last=1))
        assert "dry-run" in text
        assert "old" in text

    def test_format_handles_missing_root(self, tmp_path):
        assert "不存在" in format_plan(plan_prune_root(tmp_path / "nope"))
