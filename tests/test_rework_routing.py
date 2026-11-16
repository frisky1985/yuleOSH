"""AUD-ASPICE-001 NC-01 回归：评审 → 生产者返工路由。

撤销 ``orchestrator._maybe_rework`` 调用或 ``prompts._rework_suffix`` 后，
本文件的相关用例失败。
"""

# @tests src/yuleosh/pipeline/rework.py, src/yuleosh/pipeline/orchestrator.py, src/yuleosh/pipeline/prompts.py

import json
from pathlib import Path
from types import SimpleNamespace

from yuleosh.pipeline import orchestrator, prompts, rework


class FakeSession:
    def __init__(self, sdir: Path):
        self.name = "sess"
        self.session_dir = str(sdir)
        self.rework_rounds: dict[str, int] = {}


def write_artifact(sdir: Path, key: str, status: str, findings=None):
    payload = {"status": status}
    if findings is not None:
        payload["static_findings"] = findings
    (sdir / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")


class TestRoutes:
    def test_routes_map_review_to_producer(self):
        assert rework.route_for("arch-review") == "architecture"
        assert rework.route_for("prd-review") == "prd"
        assert rework.route_for("misra-review") == "development"
        assert rework.route_for("final-report") is None


class TestFindingsExtraction:
    def test_only_blocking_severities_are_returned(self, tmp_path):
        p = tmp_path / "arch-review.json"
        p.write_text(json.dumps({
            "status": "retry",
            "static_findings": [
                {"severity": "critical", "message": "a"},
                {"severity": "major", "message": "b"},
                {"severity": "minor", "message": "c"},
                {"severity": "info", "message": "d"},
            ],
        }), encoding="utf-8")
        got = rework.read_blocking_findings(p)
        assert [f["message"] for f in got] == ["a", "b"]

    def test_missing_artifact_returns_empty(self, tmp_path):
        assert rework.read_blocking_findings(tmp_path / "nope.json") == []


class TestPlanRework:
    def test_plan_increments_rounds_and_renders_directive(self, tmp_path):
        write_artifact(tmp_path, "arch-review", "retry", [
            {"severity": "major", "rule": "ARCH-DRIFT-HAL", "message": "缺少 HAL"},
        ])
        session = FakeSession(tmp_path)
        plan = rework.plan_rework(session, "arch-review", tmp_path / "arch-review.json")

        assert plan["producer"] == "architecture"
        assert plan["round"] == 1
        assert session.rework_rounds["arch-review"] == 1
        assert "ARCH-DRIFT-HAL" in plan["context"]
        assert "缺少 HAL" in plan["context"]

    def test_rounds_are_capped(self, tmp_path):
        write_artifact(tmp_path, "arch-review", "retry", [
            {"severity": "major", "message": "still broken"},
        ])
        session = FakeSession(tmp_path)
        path = tmp_path / "arch-review.json"
        for _ in range(rework.MAX_REWORK_ROUNDS):
            assert rework.plan_rework(session, "arch-review", path) is not None
        assert session.rework_rounds["arch-review"] == rework.MAX_REWORK_ROUNDS
        assert rework.plan_rework(session, "arch-review", path) is None

    def test_no_findings_means_no_rework(self, tmp_path):
        write_artifact(tmp_path, "arch-review", "retry", [])
        session = FakeSession(tmp_path)
        assert rework.plan_rework(
            session, "arch-review", tmp_path / "arch-review.json") is None


class TestOrchestratorReworkLoop:
    def test_retry_triggers_producer_rerun_then_review(self, tmp_path, monkeypatch):
        write_artifact(tmp_path, "arch-review", "retry", [
            {"severity": "major", "rule": "ARCH-DRIFT-HAL", "message": "缺少 HAL"},
        ])
        session = FakeSession(tmp_path)
        calls = []

        def fake_execute(session, step_idx, step_key, agent, name, handler,
                         spec_path, project_dir, from_step, callback=None):
            calls.append(step_key)
            # 首次评审由流水线执行（不在本次调用内）；这里 fake 收到的第一次
            # arch-review 就是返工后的复评，应直接通过。
            if step_key == "arch-review" and calls.count("arch-review") >= 1:
                write_artifact(tmp_path, "arch-review", "passed", [])
            return None

        monkeypatch.setattr(orchestrator, "_execute_step", fake_execute)
        registered = [
            (0, "architecture", "Claude", "架构设计", object),
            (1, "arch-review", "小克", "架构审查", object),
        ]

        did = orchestrator._maybe_rework(
            session, registered, 1, "arch-review", "spec.md", str(tmp_path), 0)

        assert did is True
        assert calls == ["architecture", "arch-review"]
        assert session.rework_rounds["arch-review"] == 1
        assert rework.directive() == ""  # 环境变量已清理

    def test_passed_review_does_not_rework(self, tmp_path, monkeypatch):
        write_artifact(tmp_path, "arch-review", "passed", [])
        session = FakeSession(tmp_path)
        monkeypatch.setattr(orchestrator, "_execute_step",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
        registered = [(0, "arch-review", "小克", "架构审查", object)]
        assert orchestrator._maybe_rework(
            session, registered, 0, "arch-review", "s.md", str(tmp_path), 0) is False


class TestPromptInjection:
    def test_architecture_prompt_carries_rework_directive(self, monkeypatch):
        monkeypatch.setenv(rework.REWORK_FINDINGS_ENV,
                           "## 返工要求\n1. [ARCH-DRIFT-HAL] 缺少 HAL")
        system, _user = prompts.build_architecture_prompt(
            spec_content="spec",
            spec_name="spec.md",
            session_name="sess",
            directories=[],
            source_files=[],
            tech_stack=["C"],
            source_tree_str="",
            key_file_snippets=[],
        )
        assert "ARCH-DRIFT-HAL" in system
        assert "返工要求" in system

    def test_prompt_unchanged_without_rework(self, monkeypatch):
        monkeypatch.delenv(rework.REWORK_FINDINGS_ENV, raising=False)
        system, _user = prompts.build_architecture_prompt(
            spec_content="spec",
            spec_name="spec.md",
            session_name="sess",
            directories=[],
            source_files=[],
            tech_stack=["C"],
            source_tree_str="",
            key_file_snippets=[],
        )
        assert "返工要求" not in system
