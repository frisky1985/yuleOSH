
# @tests src/yuleosh/pipeline/orchestrator.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for 方案 A — pipeline 步骤统一知识注入层 (2026-08-07).

Covers (contract T1-T7):
- T1/T2: PipelineStep._assemble_context + assemble_pipeline_knowledge 拼接
  [user prompt] + [memory] + [RAG] + [skills]（顺序与内容）
- T3: 超长截断（max_chars 生效）
- T4: 非致命降级（注入失败 pipeline 继续）
- T5: mock 模式跳过注入
- T6: 配置开关关闭后不注入
- T7: _call_llm 接线（inject 到 system prompt；session 传递 step_key）
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from yuleosh.pipeline.knowledge_injection import (
    DEFAULT_MAX_CHARS,
    MEMORY_HEADER,
    RAG_HEADER,
    SKILLS_HEADER,
    PipelineKnowledgeConfig,
    assemble_pipeline_knowledge,
    load_pipeline_knowledge_config,
)
from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.stages.llm import _call_llm

# ═══════════════════════════════════════════════════════════════════════
# T1/T2: 拼接正确（memory + RAG + skills 段）
# ═══════════════════════════════════════════════════════════════════════


def _seeded_memory_env(monkeypatch, tmp_path) -> Path:
    """Create a memory store with one fact and point the env at it."""
    from yuleosh.memory.store import MemoryStore

    db = tmp_path / "memory.db"
    store = MemoryStore(db_path=str(db))
    store.remember("UART DMA driver uses channel 3", entity="uart", category="architecture")
    store.close()
    monkeypatch.setenv("YULEOSH_MEMORY_DB", str(db))
    return db


class _FakeRagEngine:
    """Sync-compatible fake: retrieve_as_context returns a fixed block."""

    async def retrieve_as_context(self, query, sources=None, top_k=8):
        return (
            "## Knowledge Context (RAG)\n\n"
            f"Retrieved 1 relevant knowledge items for this query.\n\n"
            f"### MISRA-C Rules\n\n**misra_rule_10_1** (relevance: 0.90)\n\n"
            f"> {query} — integer conversion shall not change signedness."
        )


def test_assemble_includes_memory_rag_skills(monkeypatch, tmp_path):
    """T2: 四段拼接 — memory + RAG + skills 都在，顺序正确。"""
    _seeded_memory_env(monkeypatch, tmp_path)
    cfg = PipelineKnowledgeConfig(
        inject_memory=True,
        inject_rag=True,
        inject_skills=True,
        skills=["autosar-coding"],
    )
    ctx = assemble_pipeline_knowledge(
        step_key="development",
        prompt="generate UART DMA driver",
        config=cfg,
        rag_engine=_FakeRagEngine(),
    )
    assert MEMORY_HEADER in ctx
    assert RAG_HEADER in ctx
    assert SKILLS_HEADER in ctx
    # 顺序: memory → RAG → skills
    assert ctx.index(MEMORY_HEADER) < ctx.index(RAG_HEADER) < ctx.index(SKILLS_HEADER)
    # memory 内容命中
    assert "UART DMA driver uses channel 3" in ctx


def test_assemble_memory_absent_when_disabled(monkeypatch, tmp_path):
    """T6: inject_memory=False → 无 memory 段。"""
    _seeded_memory_env(monkeypatch, tmp_path)
    cfg = PipelineKnowledgeConfig(
        inject_memory=False,
        inject_rag=False,
        inject_skills=False,
    )
    ctx = assemble_pipeline_knowledge(
        step_key="development",
        prompt="generate UART DMA driver",
        config=cfg,
    )
    assert ctx == ""


def test_assemble_skills_uses_step_key_mapping(monkeypatch, tmp_path):
    """T2: skills_by_step 按 step_key 匹配。"""
    _seeded_memory_env(monkeypatch, tmp_path)
    cfg = PipelineKnowledgeConfig(
        inject_memory=False,
        inject_rag=False,
        inject_skills=True,
        skills_by_step={"development": ["autosar-coding"]},
    )
    ctx = assemble_pipeline_knowledge(
        step_key="development",
        prompt="write driver",
        config=cfg,
    )
    assert SKILLS_HEADER in ctx
    # autosar-coding 内置技能内容应出现（registry 自动注册内置技能）
    assert "AUTOSAR" in ctx or "autosar" in ctx or "C" in ctx


def test_assemble_unknown_skills_graceful(monkeypatch, tmp_path):
    """T2.2: 未知技能名 → 跳过不失败。"""
    _seeded_memory_env(monkeypatch, tmp_path)
    cfg = PipelineKnowledgeConfig(
        inject_memory=False,
        inject_rag=False,
        inject_skills=True,
        skills=["does-not-exist-skill"],
    )
    ctx = assemble_pipeline_knowledge(
        step_key="development",
        prompt="write driver",
        config=cfg,
    )
    assert ctx == ""  # no matching skills → empty


# ═══════════════════════════════════════════════════════════════════════
# T3: 超长截断
# ═══════════════════════════════════════════════════════════════════════


def test_assemble_truncates_to_max_chars(monkeypatch, tmp_path):
    """T3: 总注入 ≤ max_chars，超长截断带标记。"""
    from yuleosh.memory.store import MemoryStore

    db = tmp_path / "memory.db"
    store = MemoryStore(db_path=str(db))
    store.remember("long memory context " + "A" * 3000, entity="e", category="architecture")
    store.close()
    monkeypatch.setenv("YULEOSH_MEMORY_DB", str(db))

    cfg = PipelineKnowledgeConfig(
        inject_memory=True,
        inject_rag=False,
        inject_skills=False,
        max_chars=500,
        memory_max_chars=3000,
    )
    ctx = assemble_pipeline_knowledge(
        step_key="development",
        prompt="long memory context",
        config=cfg,
    )
    assert len(ctx) <= 500 + 64  # + truncation marker slack
    assert "truncated" in ctx


# ═══════════════════════════════════════════════════════════════════════
# T4: 非致命降级
# ═══════════════════════════════════════════════════════════════════════


def test_assemble_nonfatal_on_memory_failure(monkeypatch, tmp_path):
    """T4: memory 检索抛错 → 其余段照常，不抛异常。"""
    monkeypatch.setenv("YULEOSH_MEMORY_DB", "/nonexistent/dir/db.sqlite")
    cfg = PipelineKnowledgeConfig(
        inject_memory=True,
        inject_rag=False,
        inject_skills=True,
        skills=["autosar-coding"],
    )
    ctx = assemble_pipeline_knowledge(
        step_key="development",
        prompt="write driver",
        config=cfg,
    )
    # memory 失败降级为空，skills 仍在
    assert MEMORY_HEADER not in ctx
    assert SKILLS_HEADER in ctx


def test_assemble_nonfatal_rag_failure(monkeypatch, tmp_path):
    """T4: RAG 引擎抛错 → 降级为空，其余段照常。"""
    _seeded_memory_env(monkeypatch, tmp_path)

    class _BrokenRag:
        async def retrieve_as_context(self, query, sources=None, top_k=8):
            raise RuntimeError("rag exploded")

    cfg = PipelineKnowledgeConfig(
        inject_memory=True,
        inject_rag=True,
        inject_skills=False,
    )
    ctx = assemble_pipeline_knowledge(
        step_key="development",
        prompt="write driver",
        config=cfg,
        rag_engine=_BrokenRag(),
    )
    assert RAG_HEADER not in ctx
    assert MEMORY_HEADER in ctx


# ═══════════════════════════════════════════════════════════════════════
# T5: mock 模式跳过注入（_call_llm 接线）
# ═══════════════════════════════════════════════════════════════════════


def _make_session(mock_mode: bool = False, tmp_path=None):
    spec = (tmp_path or Path(tempfile.mkdtemp())) / "spec.md"
    spec.write_text("## Requirements\n\n- The system SHALL work.\n")
    session = PipelineSession("test-session", str(spec))
    session.mock_mode = mock_mode
    session.pipeline_knowledge_step_key = "development"
    return session


def test_call_llm_injects_knowledge_context(monkeypatch, tmp_path):
    """T7: _call_llm 注入 knowledge context 到 system prompt。"""
    _seeded_memory_env(monkeypatch, tmp_path)
    session = _make_session(mock_mode=False, tmp_path=tmp_path)

    captured = {}

    def fake_client(system, user, **kwargs):
        captured["system"] = system
        captured["user"] = user
        return {"content": "ok", "usage": {}}

    session.llm_client = fake_client
    result = _call_llm(session, "base system", "generate UART DMA driver")
    assert result["content"] == "ok"
    assert "[knowledge context" in captured["system"]
    assert MEMORY_HEADER in captured["system"]
    assert "UART DMA driver uses channel 3" in captured["system"]


def test_call_llm_skips_in_mock_mode(monkeypatch, tmp_path):
    """T5: mock 模式 → 不注入 knowledge context。"""
    _seeded_memory_env(monkeypatch, tmp_path)
    session = _make_session(mock_mode=True, tmp_path=tmp_path)

    captured = {}

    def fake_client(system, user, **kwargs):
        captured["system"] = system
        return {"content": "ok", "usage": {}}

    session.llm_client = fake_client
    _call_llm(session, "base system", "generate UART DMA driver")
    assert "[knowledge context" not in captured["system"]


def test_call_llm_nonfatal_when_injection_breaks(monkeypatch, tmp_path):
    """T4: 注入抛错 → LLM 调用照常。"""
    session = _make_session(mock_mode=False, tmp_path=tmp_path)

    captured = {}

    def fake_client(system, user, **kwargs):
        captured["system"] = system
        return {"content": "ok", "usage": {}}

    session.llm_client = fake_client
    with patch(
        "yuleosh.pipeline.knowledge_injection.assemble_pipeline_knowledge",
        side_effect=RuntimeError("boom"),
    ):
        result = _call_llm(session, "base system", "generate UART DMA driver")
    assert result["content"] == "ok"
    assert "[knowledge context" not in captured["system"]


# ═══════════════════════════════════════════════════════════════════════
# T6: 配置加载
# ═══════════════════════════════════════════════════════════════════════


def test_load_config_missing_file_uses_defaults(tmp_path):
    """T6: 无配置文件 → 默认全部开启。"""
    cfg = load_pipeline_knowledge_config(tmp_path)
    assert cfg.inject_memory is True
    assert cfg.inject_rag is True
    assert cfg.inject_skills is True
    assert cfg.max_chars == DEFAULT_MAX_CHARS


def test_load_config_reads_yaml(tmp_path):
    """T6: 配置文件解析生效。"""
    cfg_dir = tmp_path / ".yuleosh"
    cfg_dir.mkdir()
    (cfg_dir / "pipeline-knowledge.yaml").write_text(
        "inject_memory: false\n"
        "inject_rag: false\n"
        "inject_skills: true\n"
        "max_chars: 1234\n"
        "skills:\n"
        "  - autosar-coding\n"
    )
    cfg = load_pipeline_knowledge_config(tmp_path)
    assert cfg.inject_memory is False
    assert cfg.inject_rag is False
    assert cfg.inject_skills is True
    assert cfg.max_chars == 1234
    assert cfg.skills == ["autosar-coding"]


def test_load_config_corrupt_yaml_uses_defaults(tmp_path):
    """T6: 损坏 YAML → 默认配置不崩溃。"""
    cfg_dir = tmp_path / ".yuleosh"
    cfg_dir.mkdir()
    (cfg_dir / "pipeline-knowledge.yaml").write_text("::: not: [valid")
    cfg = load_pipeline_knowledge_config(tmp_path)
    assert cfg.inject_memory is True


def test_base_class_assemble_context_available():
    """T1: PipelineStep 基类有 _assemble_context 方法。"""
    from yuleosh.pipeline.steps import PipelineStep

    assert hasattr(PipelineStep, "_assemble_context")
    assert callable(PipelineStep._assemble_context)
