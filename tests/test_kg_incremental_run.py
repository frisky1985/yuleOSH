"""Tests for KG incremental orchestrator (P2-7)."""

import pytest

from yuleosh.knowledge_graph import kg_incremental


def _patch(monkeypatch, **overrides):
    calls = []

    def record(name, retval):
        def _fn(*args, **kwargs):
            calls.append(name)
            if isinstance(retval, Exception):
                raise retval
            return retval
        return _fn

    defaults = {
        "_save_checkpoint": {"nodes": [1], "edges": [2]},
        "incremental_bootstrap": {"mode": "incremental"},
        "kg_ci_append": {"snapshot": "ok"},
        "load_test_results": [{"test": "t1", "status": "pass"}],
        "apply_test_results": {"passed": 1, "verifies_updated": 1},
        "restore_called": [],
    }
    defaults.update(overrides)

    monkeypatch.setattr(kg_incremental, "_save_checkpoint",
                        record("save", defaults["_save_checkpoint"]))
    monkeypatch.setattr(kg_incremental, "incremental_bootstrap",
                        record("build", defaults["incremental_bootstrap"]))
    monkeypatch.setattr(kg_incremental, "kg_ci_append",
                        record("ci_hook", defaults["kg_ci_append"]))
    monkeypatch.setattr(kg_incremental, "load_test_results",
                        record("load_tests", defaults["load_test_results"]))
    monkeypatch.setattr(kg_incremental, "apply_test_results",
                        record("apply_tests", defaults["apply_test_results"]))

    def _restore(store, checkpoint):
        defaults["restore_called"].append(checkpoint)

    monkeypatch.setattr(kg_incremental, "_restore_checkpoint", _restore)
    return calls, defaults


def test_chains_all_steps(monkeypatch):
    calls, _ = _patch(monkeypatch)
    result = kg_incremental.kg_incremental_run(
        object(), "/proj", ["a.c", "b.c"], build_id="b1")

    assert calls == ["save", "build", "ci_hook", "load_tests", "apply_tests"]
    assert result["build_id"] == "b1"
    assert result["changed_files"] == 2
    assert result["verify_delta"]["passed"] == 1
    assert result["rolled_back"] is False


def test_no_verify_skips_test_writeback(monkeypatch):
    calls, _ = _patch(monkeypatch)
    result = kg_incremental.kg_incremental_run(
        object(), "/proj", ["a.c"], with_verify=False)
    assert "load_tests" not in calls
    assert result["verify_delta"] is None


def test_no_changed_files_skips_checkpoint(monkeypatch):
    calls, _ = _patch(monkeypatch)
    kg_incremental.kg_incremental_run(object(), "/proj", None)
    assert "save" not in calls


def test_failure_rolls_back_and_raises(monkeypatch):
    calls, defaults = _patch(
        monkeypatch, kg_ci_append=RuntimeError("ci hook boom"))
    with pytest.raises(RuntimeError, match="ci hook boom"):
        kg_incremental.kg_incremental_run(
            object(), "/proj", ["a.c"], build_id="b2")
    assert defaults["restore_called"], "失败时必须回滚检查点"
    assert defaults["restore_called"][0] == {"nodes": [1], "edges": [2]}
    assert calls == ["save", "build", "ci_hook"]


def test_build_failure_rolls_back(monkeypatch):
    _, defaults = _patch(
        monkeypatch, incremental_bootstrap=RuntimeError("scan boom"))
    with pytest.raises(RuntimeError, match="scan boom"):
        kg_incremental.kg_incremental_run(object(), "/proj", ["a.c"])
    assert defaults["restore_called"]
