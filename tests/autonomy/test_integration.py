"""Watchdog ↔ _maybe_rework、Recall ↔ prompt 的集成单测（无真实 LLM）。"""

import json

from yuleosh.pipeline import orchestrator, prompts


class FakeSession:
    def __init__(self, sdir):
        self.name = "sess"
        self.session_dir = str(sdir)
        self.rework_rounds = {}
        self.errors = []


def _write_review(sdir, key, status, findings):
    (sdir / f"{key}.json").write_text(
        json.dumps({"status": status, "static_findings": findings}),
        encoding="utf-8",
    )


def test_watchdog_escalates_repeated_findings(tmp_path, monkeypatch):
    monkeypatch.setenv("OSH_WATCHDOG_MAX_STALLS", "2")
    findings = [{"severity": "major", "rule": "DRIFT", "message": "same issue"}]
    _write_review(tmp_path, "arch-review", "retry", findings)
    session = FakeSession(tmp_path)
    calls = []

    def fake_execute(session, step_idx, step_key, agent, name, handler,
                     spec_path, project_dir, from_step, callback=None):
        calls.append(step_key)
        # 复评仍返回完全相同的 findings —— 无实质进展
        if step_key == "arch-review":
            _write_review(tmp_path, "arch-review", "retry", findings)
        return None

    monkeypatch.setattr(orchestrator, "_execute_step", fake_execute)
    registered = [
        (0, "architecture", "Claude", "架构设计", object),
        (1, "arch-review", "小克", "架构审查", object),
    ]

    did = orchestrator._maybe_rework(
        session, registered, 1, "arch-review", "spec.md", str(tmp_path), 0)

    assert did is True
    # 第 1 轮返工后复发 → streak=2 → 提前升级，不再跑第 2 轮
    assert calls == ["architecture", "arch-review"]
    assert session.rework_rounds["arch-review"] == 1
    assert any("watchdog" in e for e in session.errors)


def test_recall_hint_reaches_producer_prompt(monkeypatch):
    from yuleosh.pipeline.autonomy.recall import clear_hint, set_hint

    set_hint("## 历史运行提示（同 spec 指纹）\n- 上次 arch-review 失败")
    try:
        system, _ = prompts.build_prd_prompt(
            "SR-001 SHALL work", "spec.md", [], [])
    finally:
        clear_hint()
    assert "历史运行提示" in system
    assert "arch-review" in system
