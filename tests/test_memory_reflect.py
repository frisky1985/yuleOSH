
# @tests src/yuleosh/memory/store.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for P2 反思器 — yuleosh memory reflect (2026-08-19).

Covers: 冲突检测（数字矛盾 / 否定翻转）、来源可靠性解决（human > external
> llm；默认新胜；旧 trust>0.8 保留旧降权新）、过时归档（未使用 + 超阈值）、
应用动作、dry-run、CLI 接线。
"""

import argparse
import json
from datetime import UTC, datetime, timedelta

import pytest

from yuleosh.memory.distill import DistillCandidate
from yuleosh.memory.reflect import Reflector, _detect_conflict
from yuleosh.memory.store import MemoryStore


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "memory.db"
    s = MemoryStore(db_path=str(db))
    yield s
    s.close()


def _cand(content, entity="", reliability="llm", trust=0.7, **kw):
    return DistillCandidate(content=content, entity=entity,
                            source_reliability=reliability, trust=trust, **kw)


# ── 冲突检测 ────────────────────────────────────────────────────────────

def test_detect_conflict_numeric(store):
    fact = {"entity": "coverage", "content": "coverage gate 阈值 70%"}
    assert _detect_conflict(_cand("coverage gate 阈值 80%", "coverage"), fact)
    # 同内容（重复）不算冲突
    assert not _detect_conflict(_cand("coverage gate 阈值 70%", "coverage"), fact)
    # 不同 entity 不算冲突
    assert not _detect_conflict(_cand("coverage gate 阈值 80%", "other"), fact)


def test_detect_conflict_negation_flip(store):
    fact = {"entity": "hal", "content": "支持手动释放模式"}
    assert _detect_conflict(_cand("不支持手动释放模式", "hal"), fact)
    assert not _detect_conflict(_cand("支持手动释放模式", "hal"), fact)


def test_detect_conflict_irrelevant_not_conflict(store):
    fact = {"entity": "uart", "content": "UART DMA 使用通道 3"}
    assert not _detect_conflict(_cand("UART 波特率 115200", "uart"), fact)


def test_detect_conflicts_only_same_entity(store):
    store.remember("coverage gate 阈值 70%", entity="coverage")
    store.remember("UART DMA 使用通道 3", entity="uart")
    r = Reflector(store=store)
    conflicts = r.detect_conflicts([
        _cand("coverage gate 阈值 80%", "coverage"),
        _cand("UART DMA 使用通道 3", "uart"),  # 重复非冲突
    ])
    assert len(conflicts) == 1
    assert conflicts[0]["candidate"].entity == "coverage"


def test_detect_conflicts_llm_judge_enhancement(store):
    store.remember("旧说法", entity="e1")
    r = Reflector(store=store, llm_judge=lambda c, f: c.content == "新说法")
    conflicts = r.detect_conflicts([_cand("新说法", "e1")])
    assert len(conflicts) == 1


# ── 冲突解决 ────────────────────────────────────────────────────────────

def test_resolve_default_new_wins(store):
    f = store.remember("coverage gate 阈值 70%", entity="coverage", trust=0.5)
    r = Reflector(store=store)
    actions = r.resolve([{"candidate": _cand("coverage gate 阈值 80%", "coverage"),
                          "fact": store.get_fact(f["id"])}])
    types = [a["type"] for a in actions]
    assert "archive_old" in types
    assert "insert_new" in types


def test_resolve_keep_old_when_high_trust(store):
    f = store.remember("coverage gate 阈值 70%", entity="coverage", trust=0.9)
    r = Reflector(store=store)
    actions = r.resolve([{"candidate": _cand("coverage gate 阈值 80%", "coverage"),
                          "fact": store.get_fact(f["id"])}])
    assert actions[0]["type"] == "downgrade_new"
    assert all(a["type"] != "archive_old" for a in actions)


def test_resolve_human_beats_llm(store):
    # 旧 fact 是 LLM 自产，新候选是人类反馈 → 新胜
    f = store.remember("coverage gate 阈值 70%", entity="coverage",
                       trust=0.9, source_reliability="llm")
    r = Reflector(store=store)
    actions = r.resolve([{"candidate": _cand("coverage gate 阈值 80%", "coverage",
                                             reliability="human"),
                          "fact": store.get_fact(f["id"])}])
    types = [a["type"] for a in actions]
    assert "archive_old" in types
    assert "insert_new" in types


def test_resolve_old_reliability_wins(store):
    # 旧 fact 是外部验证，新候选 LLM 自产 → 保留旧降权新
    f = store.remember("coverage gate 阈值 70%", entity="coverage",
                       trust=0.5, source_reliability="external")
    r = Reflector(store=store)
    actions = r.resolve([{"candidate": _cand("coverage gate 阈值 80%", "coverage",
                                             reliability="llm"),
                          "fact": store.get_fact(f["id"])}])
    assert actions[0]["type"] == "downgrade_new"


# ── 过时检测 ────────────────────────────────────────────────────────────

def test_detect_obsolete_archives_never_used(store):
    f = store.remember("老旧的未使用记忆", entity="old")
    old_created = (datetime.now(UTC) - timedelta(days=40)
                   ).isoformat(timespec="seconds")
    store._get_conn().execute(
        "UPDATE memory_facts SET created_at = ? WHERE id = ?",
        (old_created, f["id"]))
    store._get_conn().commit()
    r = Reflector(store=store)
    obsolete = r.detect_obsolete(max_age_days=30)
    assert len(obsolete) == 1
    assert obsolete[0]["type"] == "archive_obsolete"
    assert obsolete[0]["fact_id"] == f["id"]


def test_detect_obsolete_skips_used(store):
    f = store.remember("使用过的记忆", entity="used")
    store.record_usage(f["id"], step="development", status="injected")
    r = Reflector(store=store)
    assert r.detect_obsolete(max_age_days=30) == []


def test_detect_obsolete_skips_recent(store):
    store.remember("新记忆", entity="new")
    r = Reflector(store=store)
    assert r.detect_obsolete(max_age_days=30) == []


# ── 应用动作 ────────────────────────────────────────────────────────────

def test_reflect_applies_actions(store):
    f = store.remember("coverage gate 阈值 70%", entity="coverage", trust=0.5)
    r = Reflector(store=store)
    summary = r.reflect([_cand("coverage gate 阈值 80%", "coverage")],
                        max_age_days=30)
    assert summary["conflicts"] == 1
    assert summary["archived"] == 1
    assert summary["inserted"] == 1
    # 旧 fact 已归档，新 fact 生效
    assert store.get_fact(f["id"])["status"] == "archived"
    active = store.list_facts(entity="coverage")
    assert len(active) == 1
    assert "80%" in active[0]["content"]


def test_reflect_downgrade_applies(store):
    f = store.remember("coverage gate 阈值 70%", entity="coverage", trust=0.9)
    r = Reflector(store=store)
    summary = r.reflect([_cand("coverage gate 阈值 80%", "coverage")],
                        max_age_days=30)
    assert summary["downgraded"] == 1
    assert store.get_fact(f["id"])["status"] == "active"  # 旧保留
    active = store.list_facts(entity="coverage")
    assert len(active) == 2
    downgraded = next(x for x in active if "80%" in x["content"])
    assert downgraded["trust"] <= 0.4  # 降权


def test_reflect_archives_obsolete(store):
    f = store.remember("老旧的未使用记忆", entity="old")
    old_created = (datetime.now(UTC) - timedelta(days=40)
                   ).isoformat(timespec="seconds")
    store._get_conn().execute(
        "UPDATE memory_facts SET created_at = ? WHERE id = ?",
        (old_created, f["id"]))
    store._get_conn().commit()
    r = Reflector(store=store)
    summary = r.reflect([], max_age_days=30)
    assert summary["obsolete"] == 1
    assert summary["archived"] == 1
    assert store.get_fact(f["id"])["status"] == "archived"


def test_reflect_dry_run_no_write(store):
    store.remember("coverage gate 阈值 70%", entity="coverage", trust=0.5)
    r = Reflector(store=store)
    summary = r.reflect([_cand("coverage gate 阈值 80%", "coverage")],
                        max_age_days=30, dry_run=True)
    assert summary["dry_run"] is True
    assert summary["archived"] == 0
    assert len(store.list_facts(entity="coverage")) == 1


# ── CLI 接线 ────────────────────────────────────────────────────────────

def test_cli_reflect_subcommand(monkeypatch, tmp_path):
    from yuleosh.memory.cli import build_memory_subparser, handle_memory_command

    db = tmp_path / "cli-mem.db"
    monkeypatch.setenv("YULEOSH_MEMORY_DB", str(db))
    s = MemoryStore(db_path=str(db))
    s.remember("coverage gate 阈值 70%", entity="coverage", trust=0.5)
    s.close()
    # 写候选文件（reflect 复用）
    cands_dir = tmp_path / ".yuleosh"
    cands_dir.mkdir(exist_ok=True)
    (cands_dir / "last-distill-candidates.json").write_text(
        json.dumps([_cand("coverage gate 阈值 80%", "coverage").to_dict()],
                   ensure_ascii=False), encoding="utf-8")

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    build_memory_subparser(sub)
    args = parser.parse_args(["memory", "reflect", "--project", str(tmp_path)])
    rc = handle_memory_command(args)
    assert rc == 0
    s = MemoryStore(db_path=str(db))
    assert len(s.list_facts(entity="coverage")) == 1
    assert "80%" in s.list_facts(entity="coverage")[0]["content"]
    s.close()
