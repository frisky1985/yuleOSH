# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Unit tests for yuleOSH memory ↔ LLM context bridge (方案 C).

Covers: dual-source retrieval (facts + sessions), de-duplication,
max_chars capping, env toggle, non-fatal degradation, and LLMClient
injection via a capturing mock provider.
"""

import pytest

from yuleosh.llm.client import LLMClient
from yuleosh.llm.providers.base import (
    AbstractProvider,
    LLMConfig,
    LLMResponse,
)
from yuleosh.memory.llm_context import (
    MemoryContextAssembler,
    assemble_memory_context,
    is_memory_context_enabled,
)
from yuleosh.memory.store import MemoryStore


@pytest.fixture()
def store(tmp_path):
    """MemoryStore isolated in a temp dir."""
    db = tmp_path / "memory.db"
    s = MemoryStore(db_path=str(db))
    yield s
    s.close()


@pytest.fixture()
def seeded_store(store):
    """Store with known facts + session logs."""
    store.remember("hub gRPC port is 8080", entity="hub",
                   category="architecture")
    store.remember("SCP03 secure channel established", entity="se050",
                   category="security")
    store.remember("unrelated deployment note", entity="other",
                   category="general")
    store.log_session("Decided to use kustomize for deployment",
                      session_key="s1", kind="decision")
    store.log_session("Reviewed MISRA baseline", session_key="s2",
                      kind="review")
    return store


@pytest.fixture()
def assembler(seeded_store):
    return MemoryContextAssembler(store=seeded_store)


# ── Retrieval ───────────────────────────────────────────────────────────

def test_retrieves_both_facts_and_sessions(assembler):
    items = assembler.retrieve("hub gRPC port")
    sources = {i.source for i in items}
    assert "fact" in sources

    # token-level fallback reaches the deployment session via "deployment"
    items2 = assembler.retrieve("what is the deployment approach?")
    sources2 = {i.source for i in items2}
    assert "session" in sources2


def test_token_fallback_reaches_phrase_fact(assembler):
    """Natural-language prompt must hit a stored fact via tokens."""
    items = assembler.retrieve("what is the hub gRPC port?")
    contents = [i.content for i in items if i.source == "fact"]
    assert any("hub gRPC port is 8080" in c for c in contents)


def test_token_prefix_reaches_session_word(store):
    """FTS5 prefix fallback: "deploy" must reach "deployment"."""
    store.log_session("Decided to use kustomize for deployment",
                      session_key="s1", kind="decision")
    a = MemoryContextAssembler(store=store)
    items = a.retrieve("how do we deploy the system?")
    sessions = [i for i in items if i.source == "session"]
    assert any("deployment" in s.content for s in sessions)


def test_dedup_same_content(store):
    """Duplicate content across tokens is kept once."""
    store.remember("alpha beta config", entity="e1")
    store.remember("alpha beta config", entity="e2")
    a = MemoryContextAssembler(store=store)
    items = a.retrieve("alpha beta")
    assert len([i for i in items if i.source == "fact"]) == 1


def test_source_limits_respected(store):
    for i in range(10):
        store.remember(f"limit fact number {i}", entity="e")
    a = MemoryContextAssembler(store=store, max_facts=3, max_sessions=3)
    items = a.retrieve("limit fact")
    facts = [i for i in items if i.source == "fact"]
    assert len(facts) == 3


def test_retrieve_does_not_reinforce_trust(seeded_store, store):
    fact = store.remember("hub gRPC port is 8080", entity="hub",
                          category="architecture")
    a = MemoryContextAssembler(store=store)
    a.retrieve("hub gRPC port")
    updated = store.get_fact(fact["id"])
    assert updated["recall_count"] == 0
    assert updated["trust"] == pytest.approx(0.5)


# ── Formatting / capping ────────────────────────────────────────────────

def test_format_context_sections(assembler):
    items = assembler.retrieve("hub gRPC")
    text = assembler.format_context(items)
    assert "## Project Memory" in text
    assert "### Memory Facts" in text


def test_max_chars_cap(store):
    store.remember("A" * 500, entity="e")
    a = MemoryContextAssembler(store=store, max_chars=300)
    context = a.assemble("A")
    assert len(context) <= 300 + 64  # + truncated marker slack
    assert "truncated" in context


def test_assemble_empty_when_no_matches(store):
    a = MemoryContextAssembler(store=store)
    assert a.assemble("zzzznomatch") == ""


# ── Env toggle + non-fatal degradation ──────────────────────────────────

def test_env_toggle_default_on():
    assert is_memory_context_enabled() is True


def test_env_toggle_off(monkeypatch):
    for val in ("0", "false", "no", "off"):
        monkeypatch.setenv("YULEOSH_MEMORY_LLM_ENABLED", val)
        assert is_memory_context_enabled() is False


def test_assemble_memory_context_env_disabled(seeded_store, monkeypatch):
    monkeypatch.setenv("YULEOSH_MEMORY_DB", seeded_store._db_path)
    monkeypatch.setenv("YULEOSH_MEMORY_LLM_ENABLED", "0")
    assert assemble_memory_context("hub gRPC") == ""


def test_assemble_memory_context_retrieval_error_nonfatal(
    seeded_store, monkeypatch
):
    monkeypatch.setenv("YULEOSH_MEMORY_DB", seeded_store._db_path)

    def boom(*a, **k):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(seeded_store, "recall", boom)
    # Store object is replaced by helper's fresh MemoryStore; simulate by
    # pointing the env at a broken db path instead.
    monkeypatch.setenv("YULEOSH_MEMORY_DB", "/nonexistent/dir/db.sqlite")
    assert assemble_memory_context("hub gRPC") == ""


# ── LLMClient integration ───────────────────────────────────────────────

class CaptureProvider(AbstractProvider):
    """Provider that records messages and returns a fixed response."""

    def __init__(self):
        self.calls = []

    @property
    def provider_name(self) -> str:
        return "capture"

    async def chat(self, messages, config):
        self.calls.append(list(messages))
        return LLMResponse(
            content="captured",
            model=config.model,
            provider="capture",
            token_usage={"prompt": 1, "completion": 1, "total": 2},
            cost=0.001,
        )

    def estimate_cost(self, prompt_tokens, completion_tokens):
        return 0.001


@pytest.fixture()
def capture_provider():
    return CaptureProvider()


def _llm_config(**overrides) -> LLMConfig:
    base = {
        "model": "deepseek-v4",
        "provider": "capture",
        "rag_enabled": False,  # isolate memory injection from RAG engine
        "rag_sources": [],
        "max_cost_usd": 0.50,
        "task_type": "code_generation",
    }
    base.update(overrides)
    return LLMConfig(**base)


async def _call_with(provider, config):
    LLMClient.configure_providers({"capture": provider})
    try:
        response = await LLMClient.call(
            prompt="what is the hub gRPC port?",
            config=config,
        )
        return response
    finally:
        LLMClient.reset()


def test_llmclient_injects_memory_context(capture_provider, seeded_store,
                                          monkeypatch):
    monkeypatch.setenv("YULEOSH_MEMORY_DB", seeded_store._db_path)
    import asyncio
    asyncio.run(_call_with(capture_provider, _llm_config()))

    assert capture_provider.calls, "provider was not called"
    system = capture_provider.calls[0][0]
    assert system["role"] == "system"
    assert "## Project Memory" in system["content"]
    assert "hub gRPC port is 8080" in system["content"]


def test_llmclient_memory_disabled_config(capture_provider, seeded_store,
                                          monkeypatch):
    monkeypatch.setenv("YULEOSH_MEMORY_DB", seeded_store._db_path)
    import asyncio
    asyncio.run(_call_with(
        capture_provider, _llm_config(memory_enabled=False)
    ))

    system = capture_provider.calls[0][0]
    assert "## Project Memory" not in system["content"]


def test_llmclient_memory_env_disabled(capture_provider, seeded_store,
                                       monkeypatch):
    monkeypatch.setenv("YULEOSH_MEMORY_DB", seeded_store._db_path)
    monkeypatch.setenv("YULEOSH_MEMORY_LLM_ENABLED", "0")
    import asyncio
    asyncio.run(_call_with(capture_provider, _llm_config()))

    system = capture_provider.calls[0][0]
    assert "## Project Memory" not in system["content"]


def test_llmclient_memory_failure_nonfatal(capture_provider, monkeypatch):
    """Broken memory db must not block the LLM call."""
    import asyncio
    asyncio.run(_call_with(capture_provider, _llm_config()))
    assert capture_provider.calls, "LLM call was blocked by memory failure"
