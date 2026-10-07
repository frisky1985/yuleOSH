"""A1/A2 regression: interrupted pipeline must be marked failed AND persisted.

# @tests src/yuleosh/pipeline/orchestrator.py::run_pipeline (terminal-status fix)

A1: 当某步返回 "failed"/"block" 中断时, run 终态必须标 "failed"(此前主循环只置
    局部 flag 并 break, 未更新 session.status, 导致收尾误标 "completed", Dashboard
    把失败 run 显示成「成功」, 违反交付可信红线)。
A2: failed 终态必须写盘(此前 `if session.status != "failed"` 跳过 _save, 使
    session.json 永远停在初始 "created")。
"""

import json

import pytest


def test_pipeline_failed_step_marks_run_failed_and_persists(monkeypatch, tmp_path):
    """首步返回 'failed' → run status == 'failed' (A1) 且 session.json 落盘 'failed' (A2)。"""
    monkeypatch.setenv("YULEOSH_LLM_LOCAL_MODEL", "qwen:latest")
    from yuleosh.pipeline import orchestrator as orch

    # 让首步即失败; 跳过 bootstrap / constraints 副作用, 聚焦收尾状态判定。
    monkeypatch.setattr(orch, "_execute_step", lambda *a, **k: "failed")
    monkeypatch.setattr(orch, "_detect_and_bootstrap", lambda pr: None)
    monkeypatch.setattr(orch, "load_agent_constraints", lambda pr: ("", None))
    monkeypatch.setattr(orch, "load_agent_constraints_by_role", lambda pr: {})

    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    session = orch.run_pipeline(str(spec), name="a1a2-test", mock=True)
    assert session is not None, "run_pipeline must return the session object"

    # A1: 中断 run 必须标 failed, 不得是 created / completed
    assert session.status == "failed", f"expected 'failed', got {session.status!r}"

    # A2: failed 必须落盘, session.json 不得停在 'created'
    written = json.loads(
        (session.session_dir / "session.json").read_text(encoding="utf-8")
    )
    assert written["status"] == "failed", (
        f"session.json status not persisted as failed: {written['status']!r}"
    )


def test_pipeline_blocked_step_marks_run_failed(monkeypatch, tmp_path):
    """首步返回 'block'(阻断门禁) → run 同样必须标 'failed', 不得 completed。"""
    monkeypatch.setenv("YULEOSH_LLM_LOCAL_MODEL", "qwen:latest")
    from yuleosh.pipeline import orchestrator as orch

    monkeypatch.setattr(orch, "_execute_step", lambda *a, **k: "block")
    monkeypatch.setattr(orch, "_detect_and_bootstrap", lambda pr: None)
    monkeypatch.setattr(orch, "load_agent_constraints", lambda pr: ("", None))
    monkeypatch.setattr(orch, "load_agent_constraints_by_role", lambda pr: {})

    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    session = orch.run_pipeline(str(spec), name="a1a2-block-test", mock=True)
    assert session is not None
    assert session.status == "failed", f"expected 'failed' on block, got {session.status!r}"
