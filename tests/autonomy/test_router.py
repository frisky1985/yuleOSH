"""Router 单测：用注入的 runner 验证工单状态回写（不调真实 LLM）。"""

from types import SimpleNamespace

from yuleosh.pipeline.autonomy.router import Router, default_spec_path
from yuleosh.pipeline.autonomy.triggers import Ticket, TicketStore


def _spec(project):
    spec = project / "spec.md"
    spec.write_text("SR-001 SHALL work", encoding="utf-8")
    return spec


def _ticket(spec, status="accepted"):
    return Ticket(kind="manual", dedupe_key=f"k:{spec}",
                  payload={"spec_path": str(spec)}, status=status)


def test_default_spec_path(tmp_path):
    assert default_spec_path(tmp_path) is None
    spec = _spec(tmp_path)
    assert default_spec_path(tmp_path) == str(spec)


def test_green_ticket_is_done(tmp_path):
    spec = _spec(tmp_path)
    store = TicketStore(tmp_path)
    store.add(_ticket(spec))

    def runner(spec_path, project_dir):
        assert spec_path == str(spec)
        return SimpleNamespace(
            status="completed", run_id="r1", errors=[],
            gate_verdict={"outcome": "green", "reason": "all gates passed"},
        )

    results = Router(tmp_path, store=store, runner=runner).run_once()
    assert results[0]["status"] == "done"
    assert results[0]["run_id"] == "r1"
    assert store.list("done")[0].ticket_id == results[0]["ticket_id"]


def test_unverified_ticket_is_flagged(tmp_path):
    spec = _spec(tmp_path)
    store = TicketStore(tmp_path)
    store.add(_ticket(spec))

    def runner(spec_path, project_dir):
        return SimpleNamespace(
            status="completed", run_id="r2", errors=[],
            gate_verdict={"outcome": "unverified", "reason": "gates incomplete"},
        )

    results = Router(tmp_path, store=store, runner=runner).run_once()
    assert results[0]["status"] == "unverified"
    assert store.list("unverified")


def test_red_or_failed_ticket_is_failed(tmp_path):
    spec = _spec(tmp_path)
    store = TicketStore(tmp_path)
    store.add(_ticket(spec))

    def runner(spec_path, project_dir):
        return SimpleNamespace(
            status="failed", run_id="r3", errors=["boom"],
            gate_verdict={"outcome": "red", "reason": "session status = failed"},
        )

    results = Router(tmp_path, store=store, runner=runner).run_once()
    assert results[0]["status"] == "failed"


def test_missing_spec_marks_failed_without_running(tmp_path):
    store = TicketStore(tmp_path)
    store.add(Ticket(kind="manual", dedupe_key="k",
                     payload={"spec_path": str(tmp_path / "nope.md")},
                     status="accepted"))
    called = []

    def runner(spec_path, project_dir):
        called.append(spec_path)
        raise AssertionError("must not run")

    results = Router(tmp_path, store=store, runner=runner).run_once()
    assert results[0]["status"] == "failed"
    assert called == []


def test_runner_crash_marks_ticket_failed(tmp_path):
    spec = _spec(tmp_path)
    store = TicketStore(tmp_path)
    store.add(_ticket(spec))

    def runner(spec_path, project_dir):
        raise RuntimeError("llm exploded")

    results = Router(tmp_path, store=store, runner=runner).run_once()
    assert results[0]["status"] == "failed"
    assert "llm exploded" in results[0]["note"]


def test_run_once_is_noop_without_accepted(tmp_path):
    store = TicketStore(tmp_path)
    store.add(Ticket(kind="manual", dedupe_key="k",
                     payload={"spec_path": "s"}, status="pending"))
    assert Router(tmp_path, store=store,
                  runner=lambda *a: None).run_once() == []
