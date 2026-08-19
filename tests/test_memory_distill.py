# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for P1 反思蒸馏器 — yuleosh memory distill (2026-08-19).

Covers: session 文本收集（日志 + 目录产物）、LLM 候选解析、确定性去重
（含幂等）、批量落库、dry-run、mock 抽取、CLI 接线、store 蒸馏支持方法。
"""

import argparse
import json
from datetime import UTC, datetime, timedelta

import pytest

from yuleosh.memory.distill import (
    DistillCandidate,
    Distiller,
    _extract_json_array,
    load_last_candidates,
    mock_distill_llm,
    similarity,
)
from yuleosh.memory.store import MemoryStore


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "memory.db"
    s = MemoryStore(db_path=str(db))
    yield s
    s.close()


def _fake_llm_factory(payloads):
    """LLM fn returning canned JSON (possibly per call)."""
    if isinstance(payloads, (list, tuple)):
        calls = list(payloads)

        def fn(prompt):
            raw = calls.pop(0) if calls else "[]"
            return raw

        return fn
    return lambda prompt: payloads


def _cand(content, entity="", kind="fact", trust=0.7, **kw):
    return DistillCandidate(content=content, entity=entity, kind=kind,
                            trust=trust, **kw)


# ── 基础工具 ────────────────────────────────────────────────────────────

def test_similarity_normalizes():
    assert similarity("Coverage gate 阈值 70%", "coverage gate 阈值 70%") > 0.9
    assert similarity("完全不同的内容 abc", "xyz 无关句子") < 0.3


def test_extract_json_array_tolerates_noise():
    raw = '好的，我来提炼：\n[{"content": "a", "kind": "fact"}, {"content": "b"}]\n完毕'
    items = _extract_json_array(raw)
    assert len(items) == 2
    assert items[0]["content"] == "a"


def test_extract_json_array_wrapper_object():
    raw = '{"candidates": [{"content": "x"}]}'
    items = _extract_json_array(raw)
    assert len(items) == 1
    assert items[0]["content"] == "x"


def test_extract_json_array_garbage():
    assert _extract_json_array("no json here") == []
    assert _extract_json_array("") == []


def test_mock_distill_llm_returns_json():
    prompt = "---BEGIN---\n经验：coverage gate 需要根 CMakeLists.txt。\n---END---"
    raw = mock_distill_llm(prompt)
    items = json.loads(raw)
    assert items
    assert items[0]["content"].startswith("经验")


# ── store 蒸馏支持方法 ──────────────────────────────────────────────────

def test_store_remember_many_transaction(store):
    created = store.remember_many([
        {"content": "fact one", "entity": "e1", "trust": 0.8},
        {"content": "fact two", "entity": "e2"},
    ])
    assert len(created) == 2
    assert store.stats()["facts"] == 2
    assert created[0]["distilled_at"]  # 蒸馏产物自动打标


def test_store_find_similar(store):
    store.remember("coverage gate 阈值 70%", entity="coverage")
    hits = store.find_similar("Coverage gate 阈值 70%", entity="coverage")
    assert len(hits) == 1
    # 不同 entity 不算重复
    assert store.find_similar("coverage gate 阈值 70%", entity="other") == []
    # 内容差异大不算重复
    assert store.find_similar("完全不同的东西", entity="coverage") == []


def test_store_archive_unarchive(store):
    f = store.remember("temp fact", entity="e")
    assert store.archive_fact(f["id"])["status"] == "archived"
    assert store.list_facts() == []  # 默认排除 archived
    assert len(store.list_facts(include_archived=True)) == 1
    assert store.recall("temp") == []  # recall 排除 archived
    assert store.unarchive_fact(f["id"])["status"] == "active"
    assert len(store.list_facts()) == 1


def test_store_list_session_logs_days(store):
    store.log_session("recent note", session_key="s1")
    # 把另一条 backdate 到 2 天前
    store.log_session("old note", session_key="s2")
    old = (datetime.now(UTC) - timedelta(days=2)
           ).isoformat(timespec="seconds")
    store._get_conn().execute(
        "UPDATE session_logs SET created_at = ? WHERE session_key = 's2'",
        (old,))
    store._get_conn().commit()
    rows = store.list_session_logs(days=1)
    assert len(rows) == 1
    assert rows[0]["session_key"] == "s1"
    rows = store.list_session_logs(days=None, limit=10)
    assert len(rows) == 2


# ── 输入收集 ────────────────────────────────────────────────────────────

def test_collect_session_texts_from_logs(store):
    store.log_session("经验：复用 stub HAL 提升覆盖率", session_key="s1",
                      kind="decision")
    d = Distiller(store=store, project_dir="/nonexistent")
    texts = d.collect_session_texts(days=1)
    assert texts
    assert "复用 stub HAL" in texts[0]


def test_collect_session_dir_text(tmp_path):
    sess = tmp_path / ".osh" / "sessions" / "run-abc"
    sess.mkdir(parents=True)
    (sess / "prd.md").write_text("PRD 要求防夹功能支持手动释放。", encoding="utf-8")
    (sess / "final-report.md").write_text("最终报告：pipeline 全绿。", encoding="utf-8")
    (sess / "session.json").write_text('{"name": "x"}', encoding="utf-8")
    db = tmp_path / "memory.db"
    store = MemoryStore(db_path=str(db))
    d = Distiller(store=store, project_dir=tmp_path)
    texts = d.collect_session_texts(days=1)
    assert any("PRD 要求防夹" in t for t in texts)
    # session.json 不参与
    joined = "\n".join(texts)
    assert "session.json" not in joined
    assert "final-report" in joined
    store.close()


# ── LLM 抽取 ────────────────────────────────────────────────────────────

def test_extract_candidates_parses(store):
    d = Distiller(store=store, llm_fn=_fake_llm_factory(json.dumps([
        {"content": "coverage gate 默认阈值 70%", "entity": "coverage",
         "category": "process", "kind": "fact", "trust": 0.8},
        {"content": "坑：mock provider 会被 budget check 跳过",
         "entity": "llm", "kind": "lesson", "trust": 0.5},
    ], ensure_ascii=False)))
    cands = d.extract_candidates(["some text"], days=1)
    assert len(cands) == 2
    assert cands[0].entity == "coverage"
    assert cands[0].kind == "fact"
    assert cands[1].kind == "lesson"


def test_extract_candidates_skips_invalid(store):
    d = Distiller(store=store, llm_fn=_fake_llm_factory(json.dumps([
        {"content": "", "kind": "fact"},
        {"content": "valid one", "kind": "bogus-kind"},
        "not-a-dict",
    ])))
    cands = d.extract_candidates(["x"], days=1)
    assert len(cands) == 1
    assert cands[0].content == "valid one"
    assert cands[0].kind == "fact"  # 非法 kind 回退 fact


def test_extract_candidates_llm_error_nonfatal(store):
    def boom(prompt):
        raise RuntimeError("api down")

    d = Distiller(store=store, llm_fn=boom)
    cands = d.extract_candidates(["x"], days=1)
    assert cands == []


# ── 去重 / 幂等 ─────────────────────────────────────────────────────────

def test_dedupe_identical_candidates(store):
    d = Distiller(store=store)
    cands = [_cand("coverage gate 阈值 70%", "coverage"),
             _cand("coverage gate 阈值 70%", "coverage")]
    kept, dropped = d.dedupe(cands)
    assert len(kept) == 1
    assert len(dropped) == 1


def test_dedupe_against_existing_fact(store):
    store.remember("coverage gate 阈值 70%", entity="coverage")
    d = Distiller(store=store)
    kept, dropped = d.dedupe([_cand("Coverage gate 阈值 70%", "coverage")])
    assert kept == []
    assert len(dropped) == 1  # 幂等：不重复写入


def test_dedupe_different_entity_kept(store):
    store.remember("coverage gate 阈值 70%", entity="coverage")
    d = Distiller(store=store)
    kept, dropped = d.dedupe([_cand("coverage gate 阈值 70%", "other")])
    assert len(kept) == 1
    assert dropped == []


# ── 主流程 ──────────────────────────────────────────────────────────────

def test_distill_persists_and_idempotent(store, tmp_path):
    store.log_session("经验：coverage gate 需要根 CMakeLists.txt。",
                      session_key="s1", kind="decision")
    store.log_session("坑：mock provider 会被 budget check 跳过。",
                      session_key="s2", kind="review")
    d = Distiller(store=store, project_dir=tmp_path,
                  llm_fn=mock_distill_llm)
    s1 = d.distill(days=1)
    assert s1["candidates"] >= 1
    assert s1["inserted"] >= 1
    assert s1["deduped"] == 0
    assert store.stats()["facts"] == s1["inserted"]
    # 幂等：重跑不重复写入
    s2 = d.distill(days=1)
    assert s2["inserted"] == 0
    assert s2["deduped"] == s2["candidates"]
    assert store.stats()["facts"] == s1["inserted"]


def test_distill_dry_run_no_write(store, tmp_path):
    store.log_session("决定：用 kustomize 部署。", session_key="s1")
    d = Distiller(store=store, project_dir=tmp_path,
                  llm_fn=mock_distill_llm)
    s = d.distill(days=1, dry_run=True)
    assert s["dry_run"] is True
    assert s["inserted"] == 0
    assert store.stats()["facts"] == 0
    assert s["candidates"] >= 1


def test_distill_no_session_text(store, tmp_path):
    d = Distiller(store=store, project_dir=tmp_path,
                  llm_fn=mock_distill_llm)
    s = d.distill(days=1)
    assert s["chunks"] == 0
    assert s["candidates"] == 0
    assert "no session text" in s["note"]


def test_distill_writes_candidates_json(store, tmp_path):
    store.log_session("经验：可复用经验一条。", session_key="s1")
    d = Distiller(store=store, project_dir=tmp_path,
                  llm_fn=mock_distill_llm)
    d.distill(days=1)
    cands = load_last_candidates(tmp_path)
    assert cands
    assert cands[0].content


# ── CLI 接线 ────────────────────────────────────────────────────────────

def test_cli_distill_subcommand(monkeypatch, tmp_path):
    from yuleosh.memory.cli import build_memory_subparser, handle_memory_command

    db = tmp_path / "cli-mem.db"
    monkeypatch.setenv("YULEOSH_MEMORY_DB", str(db))
    s = MemoryStore(db_path=str(db))
    s.log_session("经验：CLI 蒸馏应可用。", session_key="s1")
    s.close()

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    build_memory_subparser(sub)
    args = parser.parse_args(["memory", "distill", "--days", "1",
                              "--project", str(tmp_path), "--mock"])
    rc = handle_memory_command(args)
    assert rc == 0
    s = MemoryStore(db_path=str(db))
    assert s.stats()["facts"] >= 1
    s.close()
