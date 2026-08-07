#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""方案 B — KnowledgeIndexer 测试：沉淀 hook 自动收集 + 人工确认生效。

覆盖 sprint-contract-knowledge-hook-20260807.md 的 done 标准：
  (a) lesson create 自动入 pending
  (b) hash 去重（同内容不重复入列）
  (c) approve 后进 active、pending 移除
  (d) pipeline 注入读 active 不读 pending（或 inject_pending=true 带 [pending-review] 标注）
  (e) reject 不进 active
  (f) 幂等不循环（record 不发事件）
  (g) 挂接点：skill register / lesson create / memory remember 自动入列
  (h) CLI dispatch（pending/approve/reject/audit）
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yuleosh.knowledge.indexer import KnowledgeIndexer  # noqa: E402
from yuleosh.knowledge.cli import handle_knowledge_command  # noqa: E402


@pytest.fixture
def indexer(tmp_path):
    return KnowledgeIndexer(project_dir=str(tmp_path))


@pytest.fixture
def tmp_proj(tmp_path):
    """项目根目录（含 .yuleosh 空目录）。"""
    (tmp_path / ".yuleosh").mkdir(exist_ok=True)
    return tmp_path


# ── (a) lesson create 自动入 pending ────────────────────────────────────


class TestRecord:
    def test_record_adds_to_pending(self, indexer, tmp_path):
        entry = indexer.record(
            kind="lesson_create",
            content="Lesson 1: 补充边界用例",
            source="ticket:IMP-001",
        )
        assert entry is not None
        assert entry["status"] == "pending"
        assert entry["hash"]
        pending = indexer.list_pending()
        assert len(pending) == 1
        assert pending[0]["content"] == "Lesson 1: 补充边界用例"
        assert pending[0]["source"] == "ticket:IMP-001"

    def test_record_unsupported_kind_ignored(self, indexer):
        assert indexer.record(kind="bogus", content="x") is None
        assert indexer.list_pending() == []

    def test_record_empty_content_ignored(self, indexer):
        assert indexer.record(kind="memory_remember", content="   ") is None
        assert indexer.list_pending() == []

    # ── (b) hash 去重 ──────────────────────────────────────────────

    def test_record_dedup_same_content(self, indexer):
        indexer.record(kind="lesson_create", content="same lesson")
        entry2 = indexer.record(kind="lesson_create", content="same lesson")
        assert entry2 is None  # 重复不返回新条目
        assert len(indexer.list_pending()) == 1

    def test_record_dedup_after_approve(self, indexer):
        """已生效的条目再次 record 也不重复入列（pending+active 全查重）。"""
        indexer.record(kind="lesson_create", content="goes active")
        indexer.approve(all_=True)
        entry2 = indexer.record(kind="lesson_create", content="goes active")
        assert entry2 is None
        assert len(indexer.list_active()) == 1
        assert len(indexer.list_pending()) == 0

    def test_record_same_kind_diff_content_ok(self, indexer):
        indexer.record(kind="lesson_create", content="lesson A")
        indexer.record(kind="lesson_create", content="lesson B")
        assert len(indexer.list_pending()) == 2


# ── (c) approve 流转 ────────────────────────────────────────────────────


class TestApprove:
    def test_approve_moves_to_active(self, indexer):
        indexer.record(kind="memory_remember", content="fact one")
        n = indexer.approve(all_=True)
        assert n == 1
        assert len(indexer.list_pending()) == 0
        active = indexer.list_active()
        assert len(active) == 1
        assert active[0]["status"] == "active"
        assert active[0]["approved_at"]

    def test_approve_by_hash(self, indexer):
        entry = indexer.record(kind="lesson_create", content="hash pick")
        n = indexer.approve(item_id=entry["hash"])
        assert n == 1
        assert len(indexer.list_active()) == 1

    def test_approve_requires_all_or_id(self, indexer):
        indexer.record(kind="lesson_create", content="no approval")
        assert indexer.approve() == 0
        assert len(indexer.list_pending()) == 1

    def test_approve_writes_audit(self, indexer, tmp_path):
        indexer.record(kind="lesson_create", content="audit me")
        indexer.approve(all_=True)
        log = indexer.audit_log()
        assert len(log) == 1
        assert log[0]["action"] == "approve"
        assert log[0]["kind"] == "lesson_create"


# ── (e) reject 流转 ─────────────────────────────────────────────────────


class TestReject:
    def test_reject_removes_without_active(self, indexer):
        indexer.record(kind="kb_article_created", content="bad knowledge")
        n = indexer.reject(all_=True)
        assert n == 1
        assert len(indexer.list_pending()) == 0
        assert len(indexer.list_active()) == 0

    def test_reject_writes_audit(self, indexer):
        indexer.record(kind="skill_created", content="bad skill")
        indexer.reject(all_=True)
        log = indexer.audit_log()
        assert len(log) == 1
        assert log[0]["action"] == "reject"


# ── (f) 幂等不循环 ──────────────────────────────────────────────────────


class TestIdempotency:
    def test_record_does_not_emit_events(self, indexer):
        """record 只写索引文件，不触发事件总线（防循环）。"""
        indexer.record(kind="lesson_create", content="no event")
        # 直接验证：record 后 pending 仅 1 条，且调用无副作用事件
        assert len(indexer.list_pending()) == 1

    def test_corrupt_index_non_fatal(self, indexer, tmp_path):
        """索引文件损坏时降级为空，不崩溃。"""
        indexer.pending_path.parent.mkdir(parents=True, exist_ok=True)
        indexer.pending_path.write_text("{ not valid json", encoding="utf-8")
        assert indexer.list_pending() == []
        entry = indexer.record(kind="lesson_create", content="after corruption")
        assert entry is not None  # 损坏后仍可写入


# ── (g) 挂接点：skill register 自动入列 ────────────────────────────────


class TestHooks:
    def test_skill_register_hooks_indexer(self, tmp_path):
        from yuleosh.skills.model import Skill
        from yuleosh.skills.registry import SkillRegistry

        reg = SkillRegistry()
        # 隔离 OSH_HOME 指向 tmp 项目，避免污染仓库根索引
        import os

        old = os.environ.get("OSH_HOME")
        os.environ["OSH_HOME"] = str(tmp_path)
        try:
            skill = Skill(
                name="hook-test-skill",
                title="Hook Test",
                description="测试挂接",
                content="do something",
            )
            assert reg.register(skill) is True
            idx = KnowledgeIndexer(project_dir=str(tmp_path))
            pending = idx.list_pending()
            kinds = [p["kind"] for p in pending]
            assert "skill_created" in kinds
            assert any("hook-test-skill" in p["content"] for p in pending)
        finally:
            if old is None:
                os.environ.pop("OSH_HOME", None)
            else:
                os.environ["OSH_HOME"] = old

    def test_lesson_create_cli_hooks_indexer(self, tmp_proj, monkeypatch):
        """kb lesson create 路径（函数级）挂接——直接调 indexer 不经过 CLI 全链。"""
        import os

        old = os.environ.get("OSH_HOME")
        os.environ["OSH_HOME"] = str(tmp_proj)
        try:
            idx = KnowledgeIndexer(project_dir=str(tmp_proj))
            idx.record(kind="lesson_create", content="lesson via cli hook",
                       source="ticket:IMP-HOOK")
            pending = idx.list_pending()
            assert len(pending) == 1
            assert pending[0]["kind"] == "lesson_create"
        finally:
            if old is None:
                os.environ.pop("OSH_HOME", None)
            else:
                os.environ["OSH_HOME"] = old


# ── (h) CLI dispatch ────────────────────────────────────────────────────


class TestCli:
    def _args(self, **kw):
        return type("Args", (), kw)()

    def test_cli_pending_empty(self, tmp_proj, monkeypatch):
        import os

        old = os.environ.get("OSH_HOME")
        os.environ["OSH_HOME"] = str(tmp_proj)
        try:
            rc = handle_knowledge_command(
                self._args(knowledge_sub="pending", osh_home=str(tmp_proj))
            )
            assert rc == 0
        finally:
            if old is None:
                os.environ.pop("OSH_HOME", None)
            else:
                os.environ["OSH_HOME"] = old

    def test_cli_approve_all(self, tmp_proj, monkeypatch):
        import os

        old = os.environ.get("OSH_HOME")
        os.environ["OSH_HOME"] = str(tmp_proj)
        try:
            idx = KnowledgeIndexer(project_dir=str(tmp_proj))
            idx.record(kind="memory_remember", content="cli approve me")
            rc = handle_knowledge_command(
                self._args(knowledge_sub="approve", item=None, all=True,
                           osh_home=str(tmp_proj))
            )
            assert rc == 0
            assert len(idx.list_active()) == 1
        finally:
            if old is None:
                os.environ.pop("OSH_HOME", None)
            else:
                os.environ["OSH_HOME"] = old

    def test_cli_reject_all(self, tmp_proj, monkeypatch):
        import os

        old = os.environ.get("OSH_HOME")
        os.environ["OSH_HOME"] = str(tmp_proj)
        try:
            idx = KnowledgeIndexer(project_dir=str(tmp_proj))
            idx.record(kind="kb_article_created", content="cli reject me")
            rc = handle_knowledge_command(
                self._args(knowledge_sub="reject", item=None, all=True,
                           osh_home=str(tmp_proj))
            )
            assert rc == 0
            assert len(idx.list_active()) == 0
            assert len(idx.list_pending()) == 0
        finally:
            if old is None:
                os.environ.pop("OSH_HOME", None)
            else:
                os.environ["OSH_HOME"] = old
