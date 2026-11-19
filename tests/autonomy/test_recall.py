"""Recall 单测：spec 指纹、历史聚合、session 回写。"""

from types import SimpleNamespace

from yuleosh.pipeline.autonomy.recall import (
    RecallStore,
    clear_hint,
    directive,
    failed_signatures,
    record_session,
    set_hint,
    spec_fingerprint,
    suggest_hint,
)


def test_fingerprint_ignores_whitespace(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("SR-001  SHALL work\n\n  done", encoding="utf-8")
    b.write_text("SR-001 SHALL   work done\n", encoding="utf-8")
    assert spec_fingerprint(a) == spec_fingerprint(b)
    assert spec_fingerprint(a) != ""


def test_fingerprint_missing_file(tmp_path):
    assert spec_fingerprint(tmp_path / "nope.md") == ""
    assert spec_fingerprint(None) == ""


def test_record_query_suggest(tmp_path):
    store = RecallStore(tmp_path)
    assert store.record("fp1", run_id="r1", outcome="unverified",
                        reason="gate incomplete",
                        failures=["arch-review:retry:drift"]) is True
    assert store.record("fp1", run_id="r2", outcome="unverified",
                        reason="gate incomplete",
                        failures=["arch-review:retry:drift"]) is True
    assert store.record("fp1", run_id="r3", outcome="green") is True

    runs = store.query("fp1")
    assert [r["run_id"] for r in runs] == ["r3", "r2", "r1"]

    suggestion = store.suggest("fp1")
    assert suggestion["outcomes"] == {"green": 1, "unverified": 2}
    assert suggestion["top_failures"][0]["count"] == 2
    assert "arch-review:retry:drift" in suggestion["hint"]


def test_record_without_fingerprint_is_noop(tmp_path):
    store = RecallStore(tmp_path)
    assert store.record("", run_id="x") is False
    assert store.query("") == []


def test_failed_signatures_from_session():
    session = SimpleNamespace(steps=[
        {"name": "arch-review", "status": "retry", "errors": ["drift"]},
        {"name": "prd", "status": "completed", "errors": []},
    ])
    assert failed_signatures(session) == ["arch-review:retry:drift"]


def test_record_session_writes_outcome(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("SR-001 SHALL do it", encoding="utf-8")
    session = SimpleNamespace(
        spec_path=str(spec), run_id="run1", name="sess", status="completed",
        gate_verdict={"outcome": "green", "reason": "all gates passed"},
        steps=[],
    )
    assert record_session(tmp_path, session) is True
    suggestion = RecallStore(tmp_path).suggest(spec_fingerprint(spec))
    assert suggestion["runs"][0]["outcome"] == "green"


def test_hint_env_roundtrip(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("SR-001 SHALL do it", encoding="utf-8")
    RecallStore(tmp_path).record(
        spec_fingerprint(spec), run_id="r1", outcome="red", failures=["x"])
    hint = suggest_hint(tmp_path, spec)
    assert "历史运行提示" in hint

    set_hint(hint)
    assert directive() == hint
    clear_hint()
    assert directive() == ""
