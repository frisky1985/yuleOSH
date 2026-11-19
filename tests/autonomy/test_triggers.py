"""Triggers 单测：模式、信号收集、工单去重与领取。"""

import json

import pytest

from yuleosh.pipeline.autonomy.triggers import (
    Ticket,
    TicketStore,
    autonomy_mode,
    collect_signals,
    propose_tickets,
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    monkeypatch.delenv("OSH_SESSIONS_DIR", raising=False)
    monkeypatch.delenv("OSH_AUTONOMY_MODE", raising=False)
    monkeypatch.delenv("OSH_AUTONOMY_SLOW_PATH", raising=False)
    return tmp_path


def _write_spec(project):
    specs = project / ".osh" / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    spec = specs / "spec.md"
    spec.write_text("SR-001 SHALL do the thing", encoding="utf-8")
    return spec


def _write_session(project, outcome="unverified", run_id="abc123"):
    sdir = project / ".osh" / "sessions" / run_id
    sdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "name": "run-x",
        "spec_path": str(project / "spec.md"),
        "gate_verdict": {"outcome": outcome, "reason": "evidence incomplete"},
    }
    (sdir / "session.json").write_text(
        json.dumps(payload), encoding="utf-8")
    return sdir


def test_default_mode_is_off(project, monkeypatch):
    assert autonomy_mode() == "off"
    monkeypatch.setenv("OSH_AUTONOMY_MODE", "true")
    assert autonomy_mode() == "auto"
    monkeypatch.setenv("OSH_AUTONOMY_MODE", "observe")
    assert autonomy_mode() == "observe"
    monkeypatch.setenv("OSH_AUTONOMY_MODE", "bogus")
    assert autonomy_mode() == "off"


def test_off_creates_nothing(project):
    _write_spec(project)
    assert propose_tickets(project) == []
    assert not (project / ".osh" / "tickets" / "tickets.jsonl").exists()


def test_observe_creates_pending_once(project, monkeypatch):
    monkeypatch.setenv("OSH_AUTONOMY_MODE", "observe")
    _write_spec(project)
    created = propose_tickets(project)
    assert len(created) == 1
    assert created[0].kind == "spec-change"
    assert created[0].status == "pending"

    # 同一 spec 内容不重复建单
    assert propose_tickets(project) == []

    # 内容变化 → 新 key → 新工单
    spec = project / ".osh" / "specs" / "spec.md"
    spec.write_text("SR-002 SHALL do more", encoding="utf-8")
    assert len(propose_tickets(project)) == 1


def test_auto_mode_creates_accepted(project, monkeypatch):
    monkeypatch.setenv("OSH_AUTONOMY_MODE", "auto")
    _write_spec(project)
    created = propose_tickets(project)
    assert created[0].status == "accepted"


def test_run_regression_signal(project, monkeypatch):
    monkeypatch.setenv("OSH_AUTONOMY_MODE", "auto")
    _write_session(project, outcome="red")
    created = propose_tickets(project)
    assert [t.kind for t in created] == ["run-regression"]
    assert created[0].payload["outcome"] == "red"


def test_green_session_is_not_a_signal(project):
    _write_session(project, outcome="green")
    assert collect_signals(project) == []


def test_slow_path_note(project, monkeypatch):
    monkeypatch.setenv("OSH_AUTONOMY_MODE", "auto")
    monkeypatch.setenv("OSH_AUTONOMY_SLOW_PATH", "1")
    _write_session(project, outcome="unverified")

    def fake_llm(system, user):
        assert "根因" in system
        return {"content": "先修复证据缺口"}

    created = propose_tickets(project, llm_client=fake_llm)
    assert created[0].note == "先修复证据缺口"


def test_ticket_dedupe_and_claim(project):
    store = TicketStore(project)
    first = Ticket(kind="manual", dedupe_key="k1", payload={"spec_path": "s"})
    saved, is_new = store.add(first)
    assert is_new is True
    again, is_new2 = store.add(
        Ticket(kind="manual", dedupe_key="k1", payload={"spec_path": "s"}))
    assert is_new2 is False
    assert again.ticket_id == saved.ticket_id

    accepted = store.accept(saved.ticket_id)
    assert accepted.status == "accepted"
    claimed = store.claim_next()
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert store.claim_next() is None


def test_ticket_store_survives_bad_lines(project):
    store = TicketStore(project)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json}\n", encoding="utf-8")
    assert store.load() == []
