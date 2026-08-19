# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for P3 反馈环 + 蒸馏元信息 — 注入埋点 / 步骤结果回采 / 自动生效.

Covers: record_injection（usage_log + last_used_at）、apply_step_result
（passed +0.05 / failed -0.1 / 封顶 0.95 / 保底 0.05 / 幂等结算）、
trust<0.1 自动归档、knowledge_injection 埋点接线、蒸馏元信息注入
（[蒸馏于 日期 · 验证 N 次 · trust X]）、蒸馏后自动生效（验收 #5）。
"""

import pytest

from yuleosh.memory.feedback import (
    ARCHIVE_TRUST_THRESHOLD,
    FEEDBACK_TRUST_MAX,
    FEEDBACK_TRUST_MIN,
    apply_step_result,
    record_injection,
)
from yuleosh.memory.store import MemoryStore


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "memory.db"
    s = MemoryStore(db_path=str(db))
    yield s
    s.close()


# ── 注入埋点 ────────────────────────────────────────────────────────────

def test_record_injection_writes_usage(store):
    f = store.remember("UART DMA 使用通道 3", entity="uart")
    n = record_injection([f["id"]], "development", store=store)
    assert n == 1
    rows = store.list_usage(fact_id=f["id"])
    assert len(rows) == 1
    assert rows[0]["step"] == "development"
    assert rows[0]["status"] == "injected"
    # last_used_at 已更新
    assert store.get_fact(f["id"])["last_used_at"]


def test_record_injection_ignores_empty(store):
    assert record_injection([], "development", store=store) == 0
    assert record_injection([1], "", store=store) == 0


def test_record_injection_missing_fact_nonfatal(store):
    # FK 约束会拒绝不存在的 fact —— 埋点必须非致命（模拟异常路径）
    assert record_injection([999999], "development", store=store) == 0


# ── 步骤结果回采 ────────────────────────────────────────────────────────

def test_apply_step_result_passed_bumps_trust(store):
    f = store.remember("UART DMA 使用通道 3", entity="uart", trust=0.5)
    record_injection([f["id"]], "development", store=store)
    n = apply_step_result("development", "passed", store=store)
    assert n == 1
    updated = store.get_fact(f["id"])
    assert updated["trust"] == pytest.approx(0.55)
    assert updated["verified_count"] == 1
    # usage 行已结算 → 幂等
    assert apply_step_result("development", "passed", store=store) == 0
    assert store.get_fact(f["id"])["trust"] == pytest.approx(0.55)


def test_apply_step_result_failed_lowers_trust(store):
    f = store.remember("UART DMA 使用通道 3", entity="uart", trust=0.5)
    record_injection([f["id"]], "development", store=store)
    apply_step_result("development", "failed", store=store)
    updated = store.get_fact(f["id"])
    assert updated["trust"] == pytest.approx(0.4)
    assert updated["verified_count"] == 1


def test_apply_step_result_retry_lowers_trust(store):
    f = store.remember("fact", entity="e", trust=0.5)
    record_injection([f["id"]], "code-review", store=store)
    apply_step_result("code-review", "retry", store=store)
    assert store.get_fact(f["id"])["trust"] == pytest.approx(0.4)


def test_apply_step_result_clamps(store):
    f1 = store.remember("high fact", entity="e1", trust=0.94)
    f2 = store.remember("low fact", entity="e2", trust=0.06)
    record_injection([f1["id"], f2["id"]], "step-a", store=store)
    apply_step_result("step-a", "passed", store=store)
    assert store.get_fact(f1["id"])["trust"] == pytest.approx(FEEDBACK_TRUST_MAX)
    assert store.get_fact(f2["id"])["trust"] == pytest.approx(0.11)
    record_injection([f2["id"]], "step-b", store=store)
    apply_step_result("step-b", "failed", store=store)
    assert store.get_fact(f2["id"])["trust"] == pytest.approx(FEEDBACK_TRUST_MIN)


def test_trust_below_threshold_archives(store):
    f = store.remember("fragile fact", entity="e", trust=0.08)
    record_injection([f["id"]], "step-x", store=store)
    apply_step_result("step-x", "failed", store=store)
    updated = store.get_fact(f["id"])
    assert updated["trust"] == pytest.approx(FEEDBACK_TRUST_MIN)
    assert updated["status"] == "archived"
    assert updated["trust"] < ARCHIVE_TRUST_THRESHOLD


def test_apply_step_result_invalid_status(store):
    assert apply_step_result("step", "skipped", store=store) == 0


def test_apply_step_result_only_own_step(store):
    f = store.remember("fact", entity="e", trust=0.5)
    record_injection([f["id"]], "development", store=store)
    assert apply_step_result("code-review", "failed", store=store) == 0
    assert store.get_fact(f["id"])["trust"] == pytest.approx(0.5)


# ── knowledge_injection 埋点接线（P3 自动触发）──────────────────────────

def test_knowledge_injection_records_usage(monkeypatch, tmp_path):
    from yuleosh.pipeline.knowledge_injection import assemble_pipeline_knowledge
    from yuleosh.pipeline.knowledge_injection import PipelineKnowledgeConfig

    db = tmp_path / "mem.db"
    s = MemoryStore(db_path=str(db))
    s.remember("UART DMA driver uses channel 3", entity="uart",
               category="architecture")
    s.close()
    monkeypatch.setenv("YULEOSH_MEMORY_DB", str(db))

    cfg = PipelineKnowledgeConfig(inject_memory=True, inject_rag=False,
                                  inject_skills=False, inject_active=False)
    ctx = assemble_pipeline_knowledge(step_key="development",
                                      prompt="generate UART DMA driver",
                                      config=cfg)
    assert "UART DMA driver uses channel 3" in ctx
    s = MemoryStore(db_path=str(db))
    rows = s.list_usage(step="development")
    assert len(rows) == 1
    assert rows[0]["status"] == "injected"
    s.close()


def test_knowledge_injection_no_step_key_no_usage(monkeypatch, tmp_path):
    from yuleosh.pipeline.knowledge_injection import assemble_pipeline_knowledge
    from yuleosh.pipeline.knowledge_injection import PipelineKnowledgeConfig

    db = tmp_path / "mem.db"
    s = MemoryStore(db_path=str(db))
    s.remember("UART DMA driver uses channel 3", entity="uart",
               category="architecture")
    s.close()
    monkeypatch.setenv("YULEOSH_MEMORY_DB", str(db))

    cfg = PipelineKnowledgeConfig(inject_memory=True, inject_rag=False,
                                  inject_skills=False, inject_active=False)
    assemble_pipeline_knowledge(step_key="",
                                prompt="generate UART DMA driver",
                                config=cfg)
    s = MemoryStore(db_path=str(db))
    assert s.list_usage() == []
    s.close()


# ── 蒸馏元信息注入（P2 附带，验收 #5 自动生效）─────────────────────────

def test_distilled_fact_appears_with_metadata(store):
    from yuleosh.memory.llm_context import MemoryContextAssembler

    store.remember("coverage gate 默认阈值 70%", entity="coverage",
                   category="process", trust=0.82,
                   source="session-abc", source_reliability="llm",
                   distilled_at="2026-08-19T21:00:00+00:00")
    store.increment_verified(store.list_facts()[0]["id"])
    store.increment_verified(store.list_facts()[0]["id"])
    store.increment_verified(store.list_facts()[0]["id"])

    a = MemoryContextAssembler(store=store)
    items = a.retrieve("coverage gate 阈值")
    ctx = a.format_context(items)
    assert "coverage gate 默认阈值 70%" in ctx
    assert "[蒸馏于 2026-08-19" in ctx
    assert "验证 3 次" in ctx
    assert "trust 0.82" in ctx


def test_distilled_fact_auto_effective_via_injection(monkeypatch, tmp_path):
    """验收 #5: 蒸馏落库后，knowledge_injection 组装结果包含新 fact。"""
    from yuleosh.memory.distill import Distiller, mock_distill_llm
    from yuleosh.pipeline.knowledge_injection import (
        MEMORY_HEADER,
        PipelineKnowledgeConfig,
        assemble_pipeline_knowledge,
    )

    db = tmp_path / "mem.db"
    s = MemoryStore(db_path=str(db))
    s.log_session("经验：coverage gate 需要根 CMakeLists.txt。", session_key="s1")
    s.close()
    monkeypatch.setenv("YULEOSH_MEMORY_DB", str(db))

    # 蒸馏
    s = MemoryStore(db_path=str(db))
    d = Distiller(store=s, project_dir=tmp_path, llm_fn=mock_distill_llm)
    summary = d.distill(days=1)
    s.close()
    assert summary["inserted"] >= 1

    # 自动生效：注入组装包含蒸馏出的 fact
    cfg = PipelineKnowledgeConfig(inject_memory=True, inject_rag=False,
                                  inject_skills=False, inject_active=False)
    ctx = assemble_pipeline_knowledge(step_key="development",
                                      prompt="coverage gate",
                                      config=cfg)
    assert MEMORY_HEADER in ctx
    assert "CMakeLists" in ctx
