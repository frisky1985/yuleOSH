# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Pipeline knowledge injection — per-step unified LLM context assembly.

Every pipeline step's LLM call may be augmented with three knowledge
sources (plus the active knowledge index from 方案 B):

1. **Project memory** — facts + session history via
   :func:`yuleosh.memory.llm_context.assemble_memory_context`.
2. **RAG rules** — retrieved knowledge chunks via
   :func:`yuleosh.llm.rag.engine.RAGEngine.retrieve_as_context`.
3. **Skills** — matched skill blocks via
   :func:`yuleosh.skills.prompt.render_skills`.
4. **Active knowledge index** — human-approved lessons/articles/facts
   (``.yuleosh/knowledge-active.json``, 方案 B). Pending items are only
   included with a ``[pending-review]`` marker when ``inject_pending`` is
   enabled.

Design rules (方案 A contract, 2026-08-07):

- Total injected context is capped by ``max_chars`` (default 4000).
- Any retrieval failure degrades non-fatally: the failing source is
  skipped with a warning and the LLM call proceeds.
- Mock mode skips injection entirely (handled by the caller, see
  ``stages/llm.py::_call_llm``).
- Configuration lives in ``.yuleosh/pipeline-knowledge.yaml`` (optional).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("pipeline.knowledge_injection")

CONFIG_RELPATH = ".yuleosh/pipeline-knowledge.yaml"

# Section headers — stable markers used by tests and by 方案 B.
MEMORY_HEADER = "## Pipeline Memory"
RAG_HEADER = "## Pipeline RAG Context"
SKILLS_HEADER = "## Pipeline Skills"
ACTIVE_HEADER = "## Active Knowledge"

# Default total budget (方案 A contract: ≤ 4000 chars).
DEFAULT_MAX_CHARS = 4000


@dataclass
class PipelineKnowledgeConfig:
    """Per-project injection switches (from pipeline-knowledge.yaml)."""

    inject_memory: bool = True
    inject_rag: bool = True
    inject_skills: bool = True
    inject_active: bool = True
    inject_pending: bool = False
    max_chars: int = DEFAULT_MAX_CHARS
    rag_sources: list[str] | None = None
    # Skills: global names plus per-step overrides (step_key → names).
    skills: list[str] = field(default_factory=list)
    skills_by_step: dict[str, list[str]] = field(default_factory=dict)
    memory_max_chars: int = 1500
    rag_max_chars: int = 1500

    @classmethod
    def from_dict(cls, data: dict | None) -> PipelineKnowledgeConfig:
        """Build a config from a parsed YAML dict (missing keys → defaults)."""
        if not data or not isinstance(data, dict):
            return cls()
        cfg = cls(
            inject_memory=bool(data.get("inject_memory", True)),
            inject_rag=bool(data.get("inject_rag", True)),
            inject_skills=bool(data.get("inject_skills", True)),
            inject_active=bool(data.get("inject_active", True)),
            inject_pending=bool(data.get("inject_pending", False)),
            max_chars=int(data.get("max_chars", DEFAULT_MAX_CHARS) or DEFAULT_MAX_CHARS),
            rag_sources=data.get("rag_sources") or None,
            skills=list(data.get("skills", []) or []),
            skills_by_step=dict(data.get("skills_by_step", {}) or {}),
            memory_max_chars=int(data.get("memory_max_chars", 1500) or 1500),
            rag_max_chars=int(data.get("rag_max_chars", 1500) or 1500),
        )
        return cfg


def load_pipeline_knowledge_config(project_dir: str | Path) -> PipelineKnowledgeConfig:
    """Load ``.yuleosh/pipeline-knowledge.yaml`` under ``project_dir``.

    Missing file / parse error → default config (all injections on).
    """
    cfg_path = Path(project_dir) / CONFIG_RELPATH
    if not cfg_path.exists():
        return PipelineKnowledgeConfig()
    try:
        import yaml as _yaml

        raw = _yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        return PipelineKnowledgeConfig.from_dict(raw)
    except Exception as e:  # noqa: BLE001 — config must never break pipeline
        log.warning("pipeline-knowledge.yaml unreadable, using defaults: %s", e)
        return PipelineKnowledgeConfig()


def _resolve_skill_names(
    step_key: str, config: PipelineKnowledgeConfig
) -> list[str]:
    """Skill names for a step: per-step override + global list."""
    names: list[str] = []
    per_step = config.skills_by_step.get(step_key)
    if per_step:
        names.extend(per_step)
    names.extend(config.skills)
    # De-dupe preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _sync_rag_context(
    query: str,
    sources: list[str] | None,
    rag_engine=None,
    top_k: int = 8,
) -> str:
    """Run the async RAG retrieval in a sync context (pipeline is sync).

    ``retrieve_as_context`` is ``async def`` but performs only in-memory
    computation (no real awaits inside ``retrieve``); ``asyncio.run`` is
    safe in the sync CLI pipeline. A running-loop RuntimeError degrades
    to "" (non-fatal).
    """
    if rag_engine is None:
        from yuleosh.llm.rag.engine import get_default_engine

        rag_engine = get_default_engine()
    try:
        return asyncio.run(rag_engine.retrieve_as_context(query, sources=sources, top_k=top_k))
    except RuntimeError:
        # A loop is already running (e.g. embedded async host) — skip RAG.
        log.warning("RAG injection skipped: event loop already running")
        return ""
    except Exception as e:  # noqa: BLE001 — non-fatal by design
        log.warning("RAG injection failed (non-fatal): %s", e)
        return ""


def _track_memory_usage(prompt: str, step_key: str) -> None:
    """P3 埋点：记录本次注入的 fact_ids + step_key（usage_log）。

    与文本组装分离 —— 只在有 step_key 时额外做一次 retrieve 取 fact_ids。
    失败非致命（记忆注入链路永不阻断）。
    """
    try:
        from yuleosh.memory.feedback import record_injection
        from yuleosh.memory.llm_context import MemoryContextAssembler

        items = MemoryContextAssembler().retrieve(prompt)
        fact_ids = [i.item_id for i in items if i.source == "fact"]
        if fact_ids:
            record_injection(fact_ids, step_key)
    except Exception as e:  # noqa: BLE001 — 埋点永不阻断注入
        log.warning("Memory usage tracking failed (non-fatal): %s", e)


def _assemble_memory(prompt: str, config: PipelineKnowledgeConfig,
                     step_key: str = "") -> str:
    """Project memory section (non-fatal)."""
    try:
        from yuleosh.memory.llm_context import assemble_memory_context

        ctx = assemble_memory_context(query=prompt, max_chars=config.memory_max_chars)
        if not ctx:
            return ""
        if step_key:
            _track_memory_usage(prompt, step_key)
        return f"{MEMORY_HEADER}\n\n{ctx}"
    except Exception as e:  # noqa: BLE001
        log.warning("Memory injection failed (non-fatal): %s", e)
        return ""


def _assemble_rag(prompt: str, config: PipelineKnowledgeConfig, rag_engine=None) -> str:
    """RAG rules section (non-fatal)."""
    if not config.inject_rag:
        return ""
    try:
        ctx = _sync_rag_context(prompt, config.rag_sources, rag_engine=rag_engine)
        if not ctx:
            return ""
        # RAG already emits "## Knowledge Context (RAG)" — normalize to our header
        # so tests can rely on stable markers.
        body = ctx
        if body.startswith("## Knowledge Context (RAG)"):
            parts = body.split("\n", 1)
            body = parts[1] if len(parts) > 1 else ""
        return f"{RAG_HEADER}\n{body}".rstrip()
    except Exception as e:  # noqa: BLE001
        log.warning("RAG injection failed (non-fatal): %s", e)
        return ""


def _assemble_skills(step_key: str, config: PipelineKnowledgeConfig) -> str:
    """Skills section (non-fatal)."""
    if not config.inject_skills:
        return ""
    try:
        from yuleosh.skills.prompt import render_skills

        names = _resolve_skill_names(step_key, config)
        if not names:
            return ""
        rendered = render_skills(names)
        if not rendered:
            return ""
        return f"{SKILLS_HEADER}\n\n{rendered}".rstrip()
    except Exception as e:  # noqa: BLE001
        log.warning("Skills injection failed (non-fatal): %s", e)
        return ""


def _assemble_active(config: PipelineKnowledgeConfig, project_dir: str | Path) -> str:
    """Active knowledge index section (方案 B, non-fatal).

    Reads ``.yuleosh/knowledge-active.json`` (human-approved items).
    When ``inject_pending`` is enabled, pending items are appended with a
    ``[pending-review]`` marker so the LLM treats them as unverified.
    """
    if not config.inject_active:
        return ""
    try:
        from yuleosh.knowledge.indexer import KnowledgeIndexer

        indexer = KnowledgeIndexer(project_dir=Path(project_dir))
        lines: list[str] = []
        active = indexer.list_active()
        for item in active:
            kind = item.get("kind", "knowledge")
            content = str(item.get("content", "")).strip()
            if content:
                lines.append(f"- [{kind}] {content}")
        if config.inject_pending:
            pending = indexer.list_pending()
            for item in pending:
                kind = item.get("kind", "knowledge")
                content = str(item.get("content", "")).strip()
                if content:
                    lines.append(f"- [pending-review][{kind}] {content}")
        if not lines:
            return ""
        return f"{ACTIVE_HEADER}\n\n" + "\n".join(lines)
    except ImportError:
        # 方案 B module not present (older install) — degrade silently.
        return ""
    except Exception as e:  # noqa: BLE001 — never block the pipeline
        log.warning("Active knowledge injection failed (non-fatal): %s", e)
        return ""


def assemble_pipeline_knowledge(
    *,
    step_key: str,
    spec_content: str = "",
    prompt: str = "",
    config: PipelineKnowledgeConfig | None = None,
    project_dir: str | Path | None = None,
    rag_engine=None,
) -> str:
    """Assemble the unified knowledge context for a pipeline step.

    Order: memory → RAG → skills → active index. Total output is capped at
    ``config.max_chars`` (truncated with a marker). Any source failure
    degrades to that source's absence. Returns "" when nothing matches.
    """
    if config is None:
        if project_dir is not None:
            config = load_pipeline_knowledge_config(project_dir)
        else:
            config = PipelineKnowledgeConfig()

    sections: list[str] = []
    if config.inject_memory:
        sections.append(_assemble_memory(prompt, config, step_key=step_key))
    if config.inject_rag:
        sections.append(_assemble_rag(prompt, config, rag_engine=rag_engine))
    if config.inject_skills:
        sections.append(_assemble_skills(step_key, config))
    if project_dir is not None:
        sections.append(_assemble_active(config, project_dir))

    body = "\n\n".join(s for s in sections if s).strip()
    if not body:
        return ""
    if len(body) <= config.max_chars:
        return body
    return body[: config.max_chars].rstrip() + "\n…[knowledge context truncated by max_chars]"
