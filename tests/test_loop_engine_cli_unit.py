"""Unit tests for yuleosh.loop_engine.cli (v3.4.2b Wave 2a).

Exercises the `yuleosh loop ...` CLI commands with a mocked engine and
event bus — fully offline:

  - _build_engine (handler registration success + per-loop failure paths)
  - _get_kg_store (success / ImportError)
  - cmd_status (json + full/empty text sections)
  - cmd_run (event-type mapping, unknown loop, ValueError fallback, output)
  - cmd_config (view defaults / set with type parsing / audit)
  - cmd_dead_letter (list / retry / clear)
  - cmd_audit (list flat + filters / query)
  - cmd_rollback (success / skip / failure / no handlers / audit)
  - _load_config / _save_config
  - build_loop_subparser (all subcommand args)
  - handle_loop_command dispatch
"""

# @tests src/yuleosh/loop_engine/spec_delta_gen.py

import io
import os
import sys
import json
from types import SimpleNamespace

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.loop_engine import cli as LC
from yuleosh.loop_engine.event_bus import LoopEventType, LoopEvent


# ── Fakes ──────────────────────────────────────────────────────────────

class FakeResult:
    def __init__(self, success=True, action_taken="ok", evidence_ref="",
                 rollback_possible=True, details=None):
        self.success = success
        self.action_taken = action_taken
        self.evidence_ref = evidence_ref
        self.rollback_possible = rollback_possible
        self.details = details or {}


class FakeHandler:
    def __init__(self, name="FakeHandler", events=("ci.failure",),
                 handle_result=None, rollback_result=None, **kwargs):
        # kwargs: kg_store / rca_engine / knowledge_store passed by _build_engine
        self.name = name
        self._events = events
        self.handle_result = handle_result or FakeResult()
        self.rollback_result = rollback_result or FakeResult(
            action_taken="rollback not implemented")

    def subscribed_events(self):
        return [LoopEventType(e) for e in self._events]

    def handle(self, event):
        return self.handle_result

    def rollback(self, event):
        return self.rollback_result


class FakeEngine:
    def __init__(self, event_bus=None, status=None):
        self.event_bus = event_bus
        self._handlers = {}
        self.started = False
        self._status = status or {}
        self.rollback_sequence = None

    def register_handler(self, handler):
        self._handlers[handler.__class__.__name__] = handler

    def start(self):
        self.started = True
        return self

    @property
    def status(self):
        return self._status

    def run_loop_once(self, loop_name, **kwargs):
        handler = self._handlers.get(loop_name)
        if handler is None:
            raise ValueError(f"Loop handler '{loop_name}' not registered. "
                             f"Available: {list(self._handlers.keys())}")
        return handler.handle(LoopEvent(
            event_type=LoopEventType("ci.failure"), source="cli", data=kwargs))


def _status_payload(**overrides):
    payload = {
        "running": True,
        "handlers": {
            "Loop1DefectToReqHandler": {
                "subscribed_events": ["ci.failure"], "can_handle": True},
        },
        "event_bus_stats": {
            "total_emitted": 10, "total_handled": 8, "total_failed": 1,
            "total_deduped": 2, "total_retried": 1,
            "source_validator": {"enabled": True, "has_secret": True,
                                 "whitelist": ["a", "b"]},
            "rate_limiter": {"enabled": True, "default_rate": 50.0,
                             "buckets": {"ci": {"tokens": 5.0, "rate": 1.0,
                                                "dropped": 0}}},
            "dead_letter": {"count": 3, "max_retries": 3},
            "audit": {"total_records": 7, "max_entries": 5000},
        },
    }
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def _loop_env(monkeypatch, tmp_path):
    """Mock engine factory + loop_bus so no real engine starts."""
    monkeypatch.setattr(LC, "loop_bus", SimpleNamespace(
        history=lambda limit=5: [{
            "event_type": "ci.failure", "priority": 5, "event_id": "ev-12345678",
            "signature": None}],
        emit=lambda *a, **kw: None,
    ))
    monkeypatch.setattr(LC, "LoopEngine", FakeEngine)
    monkeypatch.setattr("yuleosh.knowledge_graph.get_store",
                        lambda: SimpleNamespace())
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    return tmp_path


def _mk_bus(**overrides):
    bus = SimpleNamespace(
        history=lambda limit=5: [],
        dead_letter=SimpleNamespace(
            list=lambda limit=50: [],
            count=lambda: 0,
            retry_all=lambda cb: (0, 0),
            clear=lambda: 0,
        ),
        audit_log=SimpleNamespace(
            list=lambda **kw: [],
            query=lambda eid: None,
            record_action=lambda **kw: None,
        ),
    )
    for k, v in overrides.items():
        setattr(bus, k, v)
    return bus


# ── _build_engine ──────────────────────────────────────────────────────

class TestBuildEngine:
    def test_all_handlers_registered(self, _loop_env, monkeypatch):
        """GIVEN handler imports succeed WHEN build THEN 4 handlers."""
        class H1(FakeHandler):
            pass

        class H2(FakeHandler):
            pass

        class H3(FakeHandler):
            pass

        class H4(FakeHandler):
            pass

        monkeypatch.setattr(
            "yuleosh.loop_engine.feedback_handlers.Loop1DefectToReqHandler", H1)
        monkeypatch.setattr(
            "yuleosh.loop_engine.feedback_handlers.Loop2FieldToFMEAHandler", H2)
        monkeypatch.setattr(
            "yuleosh.loop_engine.feedback_handlers.Loop3KPIToImproveHandler", H3)
        monkeypatch.setattr(
            "yuleosh.loop_engine.feedback_handlers.Loop4KGSelfEvolveHandler", H4)
        engine = LC._build_engine()
        assert engine.started is True
        assert len(engine._handlers) == 4

    def test_all_handlers_fail(self, _loop_env, monkeypatch):
        """GIVEN handler imports raising WHEN build THEN no handlers + warnings."""
        def boom(*a, **kw):
            raise ImportError("no module")

        monkeypatch.setattr(
            "yuleosh.loop_engine.feedback_handlers.Loop1DefectToReqHandler",
            boom)
        monkeypatch.setattr(
            "yuleosh.loop_engine.feedback_handlers.Loop2FieldToFMEAHandler",
            boom)
        monkeypatch.setattr(
            "yuleosh.loop_engine.feedback_handlers.Loop3KPIToImproveHandler",
            boom)
        monkeypatch.setattr(
            "yuleosh.loop_engine.feedback_handlers.Loop4KGSelfEvolveHandler",
            boom)
        engine = LC._build_engine()
        assert engine._handlers == {}
        assert engine.started is True

    def test_loop3_missing_rca(self, _loop_env, monkeypatch):
        """GIVEN RCAEngine import fails WHEN build THEN loop3 skipped."""
        class H1(FakeHandler):
            pass

        monkeypatch.setattr(
            "yuleosh.loop_engine.feedback_handlers.Loop1DefectToReqHandler", H1)

        def boom(*a, **kw):
            raise ImportError("no rca")

        monkeypatch.setattr("yuleosh.loop_engine.rca_engine.RCAEngine", boom)
        engine = LC._build_engine()
        assert "H1" in engine._handlers
        assert "Loop3KPIToImproveHandler" not in engine._handlers
        assert "Loop2FieldToFMEAHandler" in engine._handlers

    def test_loop2_km_store_fail(self, _loop_env, monkeypatch):
        """GIVEN KBStore import fails WHEN build THEN loop2+3+4 skipped."""
        class H1(FakeHandler):
            pass

        monkeypatch.setattr(
            "yuleosh.loop_engine.feedback_handlers.Loop1DefectToReqHandler", H1)
        monkeypatch.setattr(
            "yuleosh.knowledge_management.store.KBStore",
            lambda: (_ for _ in ()).throw(ImportError("no kb")))
        engine = LC._build_engine()
        assert "H1" in engine._handlers  # registered under class name
        assert "Loop2FieldToFMEAHandler" not in engine._handlers
        # real Loop3/Loop4 constructors work offline and still register
        assert "Loop3KPIToImproveHandler" in engine._handlers
        assert "Loop4KGSelfEvolveHandler" in engine._handlers


# ── _get_kg_store ──────────────────────────────────────────────────────

class TestGetKgStore:
    def test_success(self, monkeypatch):
        """GIVEN get_store importable WHEN _get_kg_store THEN store."""
        monkeypatch.setattr(
            "yuleosh.knowledge_graph.get_store", lambda: "store-obj")
        assert LC._get_kg_store() == "store-obj"

    def test_import_error_inner(self, monkeypatch):
        """GIVEN get_store raising WHEN _get_kg_store THEN None."""
        def boom():
            raise ImportError("no kg")

        monkeypatch.setattr("yuleosh.knowledge_graph.get_store", boom)
        assert LC._get_kg_store() is None

    def test_import_error(self, monkeypatch):
        """GIVEN get_store raising ImportError WHEN _get_kg_store THEN None."""
        def boom():
            raise ImportError("no kg")

        monkeypatch.setattr("yuleosh.knowledge_graph.get_store", boom)
        assert LC._get_kg_store() is None


# ── cmd_status ─────────────────────────────────────────────────────────

class TestStatus:
    def test_json_output(self, _loop_env, capsys, monkeypatch):
        """GIVEN --json WHEN status THEN JSON printed."""
        monkeypatch.setattr(
            LC, "_build_engine",
            lambda: SimpleNamespace(status=_status_payload()))
        LC.cmd_status(SimpleNamespace(json=True))
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["running"] is True

    def test_text_full(self, _loop_env, capsys, monkeypatch):
        """GIVEN full status WHEN status THEN all sections printed."""
        monkeypatch.setattr(
            LC, "_build_engine",
            lambda: SimpleNamespace(status=_status_payload()))
        LC.cmd_status(SimpleNamespace(json=False))
        out = capsys.readouterr().out
        assert "Loop Engineering Status" in out
        assert "EventBus:" in out
        assert "Source Validation" in out
        assert "Rate Limiting" in out
        assert "Dead Letter Queue" in out
        assert "Audit Log" in out
        assert "Token Buckets" in out
        assert "Registered Handlers" in out
        assert "Recent Events" in out
        assert "ci.failure" in out

    def test_text_minimal(self, _loop_env, capsys, monkeypatch):
        """GIVEN empty stats WHEN status THEN minimal sections."""
        payload = _status_payload(**{
            "event_bus_stats": {
                "total_emitted": 0, "total_handled": 0, "total_failed": 0,
                "total_deduped": 0, "total_retried": 0,
                "source_validator": {},
                "rate_limiter": {"enabled": False, "buckets": {}},
                "dead_letter": {},
                "audit": {},
            },
            "handlers": {},
        })
        monkeypatch.setattr(
            LC, "_build_engine",
            lambda: SimpleNamespace(status=payload))
        LC.cmd_status(SimpleNamespace(json=False))
        out = capsys.readouterr().out
        assert "No handlers registered" in out
        assert "⚠️" in out  # stopped icon fallback for missing sections


# ── cmd_run ────────────────────────────────────────────────────────────

class TestRun:
    def _engine_with(self, handler):
        engine = FakeEngine()
        engine._handlers[handler.name] = handler
        return engine

    def test_loop1_event_mapping(self, _loop_env, capsys, monkeypatch):
        """GIVEN loop1 name WHEN run THEN CI_FAILURE event + result output."""
        engine = self._engine_with(FakeHandler(
            name="loop1_defect_to_req",
            handle_result=FakeResult(success=True, action_taken="linked",
                                     evidence_ref="ev-1", details={"k": "v"})))
        monkeypatch.setattr(LC, "_build_engine", lambda: engine)
        LC.cmd_run(SimpleNamespace(loop_name="loop1_defect_to_req",
                                   test="test_foo", req="RS-1", error=None,
                                   source="cli"))
        out = capsys.readouterr().out
        assert "Loop Run: loop1_defect_to_req" in out
        assert "ci.failure" in out
        assert "SUCCESS" in out
        assert "linked" in out
        assert "ev-1" in out
        assert '"k": "v"' in out

    def test_loop2_3_4_mapping(self, _loop_env, monkeypatch):
        """GIVEN loop2/3/4 names WHEN run THEN correct event types."""
        for name, et in [("loop2_field_to_fmea", "field.defect"),
                         ("loop3_kpi_to_improve", "kpi.breach"),
                         ("loop4_kg_self_evolve", "kg.low_confidence")]:
            engine = FakeEngine()
            engine._handlers[name] = FakeHandler(name=name)
            monkeypatch.setattr(LC, "_build_engine", lambda: engine)
            LC.cmd_run(SimpleNamespace(loop_name=name, test=None, req=None,
                                       error=None, source="cli"))
            # no crash; event type resolution exercised

    def test_unknown_loop_with_registered_handlers(self, _loop_env, capsys,
                                                   monkeypatch):
        """GIVEN unknown loop WHEN run THEN usage error + exit 1."""
        monkeypatch.setattr(
            "yuleosh.loop_engine.feedback_handlers.base.get_registered_handlers",
            lambda: {"Loop1DefectToReqHandler": FakeHandler})
        with pytest.raises(SystemExit) as e:
            LC.cmd_run(SimpleNamespace(loop_name="nope", test=None, req=None,
                                       error=None, source="cli"))
        assert e.value.code == 1
        assert "Unknown loop" in capsys.readouterr().out

    def test_value_error_fallback(self, _loop_env, capsys, monkeypatch):
        """GIVEN run_loop_once raising WHEN handler by name THEN handled."""
        handler = FakeHandler(name="Loop1DefectToReqHandler",
                              handle_result=FakeResult(success=True,
                                                       action_taken="direct"))
        engine = FakeEngine()
        engine._handlers[handler.name] = handler
        monkeypatch.setattr(LC, "_build_engine", lambda: engine)
        LC.cmd_run(SimpleNamespace(loop_name="Loop1DefectToReqHandler",
                                   test=None, req=None, error=None,
                                   source="cli"))
        out = capsys.readouterr().out
        assert "direct" in out

    def test_value_error_no_handler_exits(self, _loop_env, capsys,
                                          monkeypatch):
        """GIVEN no matching handler WHEN run THEN exit 1."""
        monkeypatch.setattr(LC, "_build_engine", lambda: FakeEngine())
        with pytest.raises(SystemExit) as e:
            LC.cmd_run(SimpleNamespace(loop_name="ghost", test=None, req=None,
                                       error=None, source="cli"))
        assert e.value.code == 1

    def test_failure_result(self, _loop_env, capsys, monkeypatch):
        """GIVEN failing result WHEN run THEN FAILURE printed."""
        engine = self._engine_with(FakeHandler(
            name="Loop1DefectToReqHandler",
            handle_result=FakeResult(success=False, action_taken="failed")))
        monkeypatch.setattr(LC, "_build_engine", lambda: engine)
        LC.cmd_run(SimpleNamespace(loop_name="Loop1DefectToReqHandler",
                                   test=None, req=None, error="boom",
                                   source="cli"))
        assert "FAILURE" in capsys.readouterr().out


# ── cmd_config ─────────────────────────────────────────────────────────

class TestConfig:
    def test_view_defaults(self, _loop_env, tmp_path, capsys):
        """GIVEN no config file WHEN config THEN defaults shown."""
        LC.cmd_config(SimpleNamespace(set=None))
        out = capsys.readouterr().out
        assert "Loop Configuration" in out
        assert "dedup_window_seconds" in out
        assert "dead_letter_max_retries" in out
        assert "audit_max_entries" in out
        assert "default" in out

    def test_view_merged_from_file(self, _loop_env, tmp_path, capsys):
        """GIVEN config file WHEN config THEN merged values + file source."""
        cfg = tmp_path / ".yuleosh" / "loop_config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"dedup_window_seconds": 600}))
        LC.cmd_config(SimpleNamespace(set=None))
        out = capsys.readouterr().out
        assert "600" in out
        assert "file" in out

    def test_set_bool(self, _loop_env, tmp_path, capsys):
        """GIVEN bool value WHEN set THEN parsed as bool."""
        LC.cmd_config(SimpleNamespace(set="loop1_enabled=false"))
        cfg = json.loads((tmp_path / ".yuleosh" / "loop_config.json").read_text())
        assert cfg["loop1_enabled"] is False
        assert "Config updated" in capsys.readouterr().out

    def test_set_int_float_str(self, _loop_env, tmp_path):
        """GIVEN int/float/string values WHEN set THEN parsed."""
        LC.cmd_config(SimpleNamespace(set="dedup_window_seconds=600"))
        LC.cmd_config(SimpleNamespace(set="dead_letter_backoff=2.5"))
        LC.cmd_config(SimpleNamespace(set="log_level=DEBUG"))
        cfg = json.loads((tmp_path / ".yuleosh" / "loop_config.json").read_text())
        assert cfg["dedup_window_seconds"] == 600
        assert cfg["dead_letter_backoff"] == 2.5
        assert cfg["log_level"] == "DEBUG"

    def test_set_key_only_empty_value(self, _loop_env, tmp_path):
        """GIVEN key without value WHEN set THEN empty string stored."""
        LC.cmd_config(SimpleNamespace(set="some_key"))
        cfg = json.loads((tmp_path / ".yuleosh" / "loop_config.json").read_text())
        assert cfg["some_key"] == ""

    def test_set_records_audit(self, _loop_env, tmp_path, monkeypatch):
        """GIVEN set WHEN audit record THEN recorded."""
        recorded = []
        bus = _mk_bus()
        bus.audit_log.record_action = lambda **kw: recorded.append(kw)
        monkeypatch.setattr(LC, "loop_bus", bus)
        LC.cmd_config(SimpleNamespace(set="dedup_window_seconds=100"))
        assert recorded and recorded[0]["action"] == "config_changed"
        assert recorded[0]["details"]["new_value"] == 100

    def test_set_audit_failure_logged(self, _loop_env, tmp_path, monkeypatch,
                                      caplog):
        """GIVEN audit raising WHEN set THEN warning logged, config still saved."""
        import logging
        bus = _mk_bus()
        bus.audit_log.record_action = lambda **kw: (_ for _ in ()).throw(
            RuntimeError("audit down"))
        monkeypatch.setattr(LC, "loop_bus", bus)
        with caplog.at_level(logging.WARNING):
            LC.cmd_config(SimpleNamespace(set="x=1"))
        assert any("Audit record failed" in r.message for r in caplog.records)
        cfg = json.loads((tmp_path / ".yuleosh" / "loop_config.json").read_text())
        assert cfg["x"] == 1


# ── cmd_dead_letter ────────────────────────────────────────────────────

class TestDeadLetter:
    def test_list_empty(self, _loop_env, capsys, monkeypatch):
        """GIVEN empty DLQ WHEN list THEN empty message."""
        monkeypatch.setattr(LC, "loop_bus", _mk_bus())
        LC.cmd_dead_letter(SimpleNamespace(dl_sub="list", limit=50, json=False))
        assert "empty" in capsys.readouterr().out

    def test_list_nonempty(self, _loop_env, capsys, monkeypatch):
        """GIVEN entries WHEN list THEN table printed."""
        bus = _mk_bus()
        bus.dead_letter.list = lambda limit=50: [
            {"event_id": "ev-1234567890", "event_type": "ci.failure",
             "source": "ci", "retry_count": 1, "max_retries": 3,
             "failure_reason": "timeout happened"}] * 1
        monkeypatch.setattr(LC, "loop_bus", bus)
        LC.cmd_dead_letter(SimpleNamespace(dl_sub="list", limit=50, json=False))
        out = capsys.readouterr().out
        assert "Dead Letter Queue" in out
        assert "timeout" in out

    def test_list_json(self, _loop_env, capsys, monkeypatch):
        """GIVEN --json WHEN list THEN JSON printed."""
        bus = _mk_bus()
        bus.dead_letter.list = lambda limit=50: [{"event_id": "e1"}]
        monkeypatch.setattr(LC, "loop_bus", bus)
        LC.cmd_dead_letter(SimpleNamespace(dl_sub="list", limit=50, json=True))
        assert json.loads(capsys.readouterr().out)[0]["event_id"] == "e1"

    def test_retry_empty(self, _loop_env, capsys, monkeypatch):
        """GIVEN empty DLQ WHEN retry THEN nothing to retry."""
        monkeypatch.setattr(LC, "loop_bus", _mk_bus())
        LC.cmd_dead_letter(SimpleNamespace(dl_sub="retry"))
        assert "nothing to retry" in capsys.readouterr().out

    def test_retry_nonempty(self, _loop_env, capsys, monkeypatch):
        """GIVEN entries WHEN retry THEN callback emits + summary."""
        bus = _mk_bus()
        bus.dead_letter.count = lambda: 2
        bus.dead_letter.retry_all = lambda cb: (2, 0)
        bus.dead_letter.list = lambda limit=50: []
        emitted = []
        bus.emit = lambda *a, **kw: emitted.append((a, kw))
        monkeypatch.setattr(LC, "loop_bus", bus)
        LC.cmd_dead_letter(SimpleNamespace(dl_sub="retry"))
        out = capsys.readouterr().out
        assert "Retry complete: 2 succeeded" in out

    def test_clear(self, _loop_env, capsys, monkeypatch):
        """GIVEN entries WHEN clear THEN cleared message."""
        bus = _mk_bus()
        bus.dead_letter.count = lambda: 5
        bus.dead_letter.clear = lambda: 5
        monkeypatch.setattr(LC, "loop_bus", bus)
        LC.cmd_dead_letter(SimpleNamespace(dl_sub="clear"))
        assert "Cleared 5 entries" in capsys.readouterr().out


# ── cmd_audit ──────────────────────────────────────────────────────────

def _audit_entry(eid="ev-1234567890"):
    return {
        "timestamp": "2026-07-17T00:00:00", "event_id": eid,
        "event_type": "ci.failure", "action": "handle", "source": "ci",
        "priority": 5, "duration_ms": 12.5, "retry_count": 0,
        "rollback_status": "none", "source_fingerprint": "fp",
        "signature": "sig1234567890",
        "handler_results": [{"handler": "Loop1DefectToReqHandler",
                             "status": "success"}],
    }


class TestAudit:
    def test_list_none(self, _loop_env, capsys, monkeypatch):
        """GIVEN no entries WHEN audit THEN no records message."""
        monkeypatch.setattr(LC, "loop_bus", _mk_bus())
        LC.cmd_audit(SimpleNamespace(audit_sub=None, limit=50, event_type=None,
                                     since=None, until=None, handler=None,
                                     json=False))
        assert "No audit records" in capsys.readouterr().out

    def test_list_entries(self, _loop_env, capsys, monkeypatch):
        """GIVEN entries WHEN audit THEN ACC-505 table printed."""
        bus = _mk_bus()
        bus.audit_log.list = lambda **kw: [_audit_entry()]
        monkeypatch.setattr(LC, "loop_bus", bus)
        LC.cmd_audit(SimpleNamespace(audit_sub=None, limit=50, event_type=None,
                                     since=None, until=None, handler=None,
                                     json=False))
        out = capsys.readouterr().out
        assert "Audit Log" in out
        assert "Loop1DefectToReqHandler" in out
        assert "success" in out

    def test_list_filters_displayed(self, _loop_env, capsys, monkeypatch):
        """GIVEN filters + no entries WHEN audit THEN filter summary."""
        monkeypatch.setattr(LC, "loop_bus", _mk_bus())
        LC.cmd_audit(SimpleNamespace(audit_sub=None, limit=50,
                                     event_type="ci.failure",
                                     since="2026-01-01", until=None,
                                     handler="H", json=False))
        out = capsys.readouterr().out
        assert "type=ci.failure" in out
        assert "since=2026-01-01" in out
        assert "handler=H" in out

    def test_list_json(self, _loop_env, capsys, monkeypatch):
        """GIVEN --json WHEN audit THEN JSON printed."""
        bus = _mk_bus()
        bus.audit_log.list = lambda **kw: [_audit_entry()]
        monkeypatch.setattr(LC, "loop_bus", bus)
        LC.cmd_audit(SimpleNamespace(audit_sub=None, limit=50, event_type=None,
                                     since=None, until=None, handler=None,
                                     json=True))
        assert json.loads(capsys.readouterr().out)[0]["event_id"].startswith("ev-")

    def test_list_sub(self, _loop_env, capsys, monkeypatch):
        """GIVEN audit list sub WHEN audit THEN same table."""
        bus = _mk_bus()
        bus.audit_log.list = lambda **kw: []
        monkeypatch.setattr(LC, "loop_bus", bus)
        LC.cmd_audit(SimpleNamespace(audit_sub="list", limit=50,
                                     event_type=None, since=None, until=None,
                                     handler=None, json=False))
        assert "No audit records" in capsys.readouterr().out

    def test_query_found(self, _loop_env, capsys, monkeypatch):
        """GIVEN existing event WHEN query THEN details printed."""
        bus = _mk_bus()
        bus.audit_log.query = lambda eid: _audit_entry(eid)
        monkeypatch.setattr(LC, "loop_bus", bus)
        LC.cmd_audit(SimpleNamespace(audit_sub="query", event_id="ev-1",
                                     json=False))
        out = capsys.readouterr().out
        assert "Audit Entry: ev-1" in out
        assert "Handler Results" in out
        assert "Loop1DefectToReqHandler" in out

    def test_query_not_found(self, _loop_env, capsys, monkeypatch):
        """GIVEN missing event WHEN query THEN not-found message."""
        monkeypatch.setattr(LC, "loop_bus", _mk_bus())
        LC.cmd_audit(SimpleNamespace(audit_sub="query", event_id="ev-x",
                                     json=False))
        assert "not found" in capsys.readouterr().out

    def test_query_json(self, _loop_env, capsys, monkeypatch):
        """GIVEN --json WHEN query THEN JSON entry."""
        bus = _mk_bus()
        bus.audit_log.query = lambda eid: _audit_entry(eid)
        monkeypatch.setattr(LC, "loop_bus", bus)
        LC.cmd_audit(SimpleNamespace(audit_sub="query", event_id="ev-1",
                                     json=True))
        assert json.loads(capsys.readouterr().out)["action"] == "handle"

    def test_query_json_missing(self, _loop_env, capsys, monkeypatch):
        """GIVEN missing entry + --json WHEN query THEN empty dict."""
        monkeypatch.setattr(LC, "loop_bus", _mk_bus())
        LC.cmd_audit(SimpleNamespace(audit_sub="query", event_id="ev-x",
                                     json=True))
        assert capsys.readouterr().out == "{}\n"


# ── cmd_rollback ───────────────────────────────────────────────────────

class TestRollback:
    def test_all_success(self, _loop_env, capsys, monkeypatch):
        """GIVEN handlers rolling back WHEN rollback THEN restored count."""
        h1 = FakeHandler(name="Loop1DefectToReqHandler",
                         rollback_result=FakeResult(action_taken="rolled back"))
        h2 = FakeHandler(name="Loop2FieldToFMEAHandler",
                         rollback_result=FakeResult(action_taken="rolled back"))
        engine = FakeEngine()
        engine._handlers = {h1.name: h1, h2.name: h2}
        monkeypatch.setattr(LC, "_build_engine", lambda: engine)
        LC.cmd_rollback(SimpleNamespace(journal_id="JRNL-1"))
        out = capsys.readouterr().out
        assert "restored 2 entity/entities" in out
        assert "Rollback: JRNL-1" in out

    def test_skip_and_failure(self, _loop_env, capsys, monkeypatch):
        """GIVEN skip + exception WHEN rollback THEN partial failures."""
        h_skip = FakeHandler(name="SkipHandler",
                             rollback_result=FakeResult(success=False,
                                                        action_taken="skipped"))
        h_err = FakeHandler(name="ErrHandler")
        h_err.rollback = lambda event: (_ for _ in ()).throw(
            RuntimeError("rollback exploded"))
        engine = FakeEngine()
        engine._handlers = {h_skip.name: h_skip, h_err.name: h_err}
        monkeypatch.setattr(LC, "_build_engine", lambda: engine)
        LC.cmd_rollback(SimpleNamespace(journal_id="JRNL-2"))
        out = capsys.readouterr().out
        assert "skipped" in out
        assert "rollback failed" in out
        # no handler succeeded -> "no entities were restored" branch
        assert "no entities were restored" in out

    def test_no_handlers_then_rebuild_empty(self, _loop_env, capsys,
                                            monkeypatch):
        """GIVEN empty _handlers twice WHEN rollback THEN warning."""
        engine1 = FakeEngine()
        engine2 = FakeEngine()
        monkeypatch.setattr(LC, "_build_engine",
                            lambda: engine1 if engine1._handlers == {} else engine2)
        # first build returns engine1 (empty), rebuild returns engine2 (empty)
        LC.cmd_rollback(SimpleNamespace(journal_id="JRNL-3"))
        out = capsys.readouterr().out
        assert "No registered handlers" in out
        assert "no entities were restored" in out

    def test_audit_recorded(self, _loop_env, capsys, monkeypatch):
        """GIVEN successful rollback WHEN audit THEN record_action called."""
        h1 = FakeHandler(name="H1",
                         rollback_result=FakeResult(action_taken="ok"))
        engine = FakeEngine()
        engine._handlers = {h1.name: h1}
        recorded = []
        bus = _mk_bus()
        bus.audit_log.record_action = lambda **kw: recorded.append(kw)
        monkeypatch.setattr(LC, "loop_bus", bus)
        monkeypatch.setattr(LC, "_build_engine", lambda: engine)
        LC.cmd_rollback(SimpleNamespace(journal_id="JRNL-4"))
        assert recorded and recorded[0]["action"] == "rollback"
        assert recorded[0]["result"] == "success"
        assert recorded[0]["journal_id"] == "JRNL-4"

    def test_audit_failure_logged(self, _loop_env, capsys, monkeypatch,
                                  caplog):
        """GIVEN audit raising WHEN rollback THEN warning + still completes."""
        import logging
        h1 = FakeHandler(name="H1",
                         rollback_result=FakeResult(action_taken="ok"))
        engine = FakeEngine()
        engine._handlers = {h1.name: h1}
        bus = _mk_bus()
        bus.audit_log.record_action = lambda **kw: (_ for _ in ()).throw(
            RuntimeError("audit down"))
        monkeypatch.setattr(LC, "loop_bus", bus)
        monkeypatch.setattr(LC, "_build_engine", lambda: engine)
        with caplog.at_level(logging.WARNING):
            LC.cmd_rollback(SimpleNamespace(journal_id="JRNL-5"))
        assert any("Audit record failed" in r.message for r in caplog.records)


# ── config file helpers ────────────────────────────────────────────────

class TestConfigFileHelpers:
    def test_load_config_missing(self, tmp_path):
        """GIVEN missing file WHEN _load_config THEN empty dict."""
        assert LC._load_config(str(tmp_path / "nope.json")) == {}

    def test_load_config_corrupt(self, tmp_path):
        """GIVEN corrupt file WHEN _load_config THEN empty dict."""
        p = tmp_path / "c.json"
        p.write_text("{{bad")
        assert LC._load_config(str(p)) == {}

    def test_load_config_valid(self, tmp_path):
        """GIVEN valid file WHEN _load_config THEN parsed dict."""
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"a": 1}))
        assert LC._load_config(str(p)) == {"a": 1}

    def test_save_config(self, tmp_path):
        """GIVEN config WHEN _save_config THEN file written."""
        path = str(tmp_path / "sub" / "c.json")
        LC._save_config(path, {"x": 1})
        assert json.loads(open(path).read()) == {"x": 1}


# ── parser + dispatch ──────────────────────────────────────────────────

class TestParser:
    def _parser(self):
        import argparse
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        LC.build_loop_subparser(sub)
        return parser

    def test_status_args(self):
        """GIVEN status parse THEN loop_sub + json flag."""
        args = self._parser().parse_args(["loop", "status", "--json"])
        assert args.loop_sub == "status" and args.json is True

    def test_run_args(self):
        """GIVEN run parse THEN loop_name + options."""
        args = self._parser().parse_args(
            ["loop", "run", "loop1_defect_to_req", "--test", "t",
             "--req", "RS-1", "--error", "e", "--source", "s"])
        assert args.loop_name == "loop1_defect_to_req"
        assert args.test == "t" and args.req == "RS-1"
        assert args.error == "e" and args.source == "s"

    def test_config_args(self):
        """GIVEN config parse THEN set option."""
        args = self._parser().parse_args(["loop", "config", "--set", "a=1"])
        assert args.loop_sub == "config" and args.set == "a=1"

    def test_dead_letter_args(self):
        """GIVEN dead-letter parse THEN sub + flags."""
        args = self._parser().parse_args(
            ["loop", "dead-letter", "list", "--limit", "5", "--json"])
        assert args.dl_sub == "list" and args.limit == 5 and args.json is True
        args2 = self._parser().parse_args(["loop", "dead-letter", "retry"])
        assert args2.dl_sub == "retry"

    def test_audit_args(self):
        """GIVEN audit parse THEN flat + list + query variants."""
        args = self._parser().parse_args(
            ["loop", "audit", "--limit", "5", "--type", "ci.failure",
             "--handler", "H"])
        assert args.loop_sub == "audit"
        assert args.audit_sub is None  # flat mode
        args2 = self._parser().parse_args(
            ["loop", "audit", "query", "ev-1", "--json"])
        assert args2.audit_sub == "query" and args2.event_id == "ev-1"

    def test_rollback_args(self):
        """GIVEN rollback parse THEN journal_id."""
        args = self._parser().parse_args(["loop", "rollback", "JRNL-1"])
        assert args.journal_id == "JRNL-1"


class TestDispatch:
    def _mk_args(self, loop_sub, **extra):
        kw = dict(loop_sub=loop_sub)
        kw.update(extra)
        return SimpleNamespace(**kw)

    def test_dispatch_status(self, _loop_env, capsys, monkeypatch):
        """GIVEN status WHEN dispatch THEN cmd_status invoked."""
        monkeypatch.setattr(
            LC, "_build_engine",
            lambda: SimpleNamespace(status=_status_payload()))
        LC.handle_loop_command(self._mk_args("status", json=False))
        assert "Loop Engineering Status" in capsys.readouterr().out

    def test_dispatch_run(self, _loop_env, capsys, monkeypatch):
        """GIVEN run WHEN dispatch THEN cmd_run invoked."""
        engine = FakeEngine()
        h = FakeHandler(name="Loop1DefectToReqHandler",
                        handle_result=FakeResult(action_taken="ran"))
        engine._handlers[h.name] = h
        monkeypatch.setattr(LC, "_build_engine", lambda: engine)
        LC.handle_loop_command(self._mk_args(
            "run", loop_name="Loop1DefectToReqHandler", test=None, req=None,
            error=None, source="cli"))
        assert "ran" in capsys.readouterr().out

    def test_dispatch_config(self, _loop_env, capsys):
        """GIVEN config WHEN dispatch THEN cmd_config invoked."""
        LC.handle_loop_command(self._mk_args("config", set=None))
        assert "Loop Configuration" in capsys.readouterr().out

    def test_dispatch_dead_letter(self, _loop_env, capsys, monkeypatch):
        """GIVEN dead-letter WHEN dispatch THEN cmd_dead_letter invoked."""
        monkeypatch.setattr(LC, "loop_bus", _mk_bus())
        LC.handle_loop_command(self._mk_args("dead-letter", dl_sub="list",
                                             limit=50, json=False))
        assert "empty" in capsys.readouterr().out

    def test_dispatch_audit(self, _loop_env, capsys, monkeypatch):
        """GIVEN audit WHEN dispatch THEN cmd_audit invoked."""
        monkeypatch.setattr(LC, "loop_bus", _mk_bus())
        LC.handle_loop_command(self._mk_args(
            "audit", audit_sub=None, limit=50, event_type=None, since=None,
            until=None, handler=None, json=False))
        assert "No audit records" in capsys.readouterr().out

    def test_dispatch_rollback(self, _loop_env, capsys, monkeypatch):
        """GIVEN rollback WHEN dispatch THEN cmd_rollback invoked."""
        engine = FakeEngine()
        h = FakeHandler(name="H", rollback_result=FakeResult(action_taken="ok"))
        engine._handlers[h.name] = h
        monkeypatch.setattr(LC, "_build_engine", lambda: engine)
        LC.handle_loop_command(self._mk_args("rollback", journal_id="J-1"))
        assert "restored 1 entity" in capsys.readouterr().out

    def test_dispatch_unknown(self, _loop_env, capsys):
        """GIVEN unknown sub WHEN dispatch THEN usage + exit 1."""
        with pytest.raises(SystemExit) as e:
            LC.handle_loop_command(self._mk_args("bogus"))
        assert e.value.code == 1
        assert "Usage" in capsys.readouterr().out
