"""AUD-ASPICE-001 NC-03 回归：验证独立性台账 + 测试上下文隔离。

撤销 ``verification_independence`` 的接线（orchestrator 不再记录、session
不再落盘）后，本文件的用例会失败。
"""

# @tests src/yuleosh/pipeline/verification_independence.py, src/yuleosh/pipeline/session.py

from pathlib import Path
from types import SimpleNamespace

from yuleosh.pipeline.verification_independence import (
    LEVEL_DEGRADED,
    LEVEL_ISOLATED,
    LEVEL_NONE,
    classify,
    channel_for,
    record,
    source_body_leak,
    summarize,
)


class TestChannelMapping:
    def test_unknown_step_is_not_a_verification_step(self):
        assert channel_for("prd") is None
        assert classify("prd") is None

    def test_deterministic_and_toolchain_steps_are_isolated(self):
        for key in ("test-case-gen", "c-unit-test", "c-coverage-gate"):
            assert classify(key, "completed")["level"] == LEVEL_ISOLATED

    def test_external_agent_is_isolated(self):
        assert classify("claude-review", "completed")["level"] == LEVEL_ISOLATED

    def test_same_model_review_is_degraded(self):
        verdict = classify("arch-review", "completed")
        assert verdict["level"] == LEVEL_DEGRADED
        assert "independent review channel absent" in verdict["reason"]


class TestClassifyOutcomes:
    def test_skipped_step_is_none(self):
        verdict = classify("c-unit-test", "skipped")
        assert verdict["level"] == LEVEL_NONE
        assert verdict["step_status"] == "skipped"

    def test_failed_step_is_none(self):
        assert classify("c-unit-test", "failed")["level"] == LEVEL_NONE

    def test_artifact_marked_skipped_is_none(self):
        artifact = {"skipped": True, "reason": "claude CLI not installed"}
        verdict = classify("claude-review", "completed", artifact)
        assert verdict["level"] == LEVEL_NONE
        assert verdict["reason"] == "claude CLI not installed"

    def test_artifact_status_skipped_is_none(self):
        artifact = {"status": "skipped", "reason": "mock mode"}
        assert classify("codex-verify", "completed", artifact)["level"] == LEVEL_NONE


class TestRecordAndSummarize:
    def test_record_writes_ledger(self, tmp_path):
        session = SimpleNamespace(verification_independence={})
        report = tmp_path / "r.json"
        report.write_text('{"status": "passed"}', encoding="utf-8")

        verdict = record(session, "c-unit-test", "completed", report)
        assert verdict["level"] == LEVEL_ISOLATED
        assert session.verification_independence["c-unit-test"]["level"] == LEVEL_ISOLATED

    def test_record_ignores_non_verification_step(self):
        session = SimpleNamespace(verification_independence={})
        assert record(session, "development", "completed") is None
        assert session.verification_independence == {}

    def test_record_creates_ledger_when_missing(self):
        session = SimpleNamespace()
        record(session, "test-case-gen", "completed")
        assert session.verification_independence["test-case-gen"]["level"] == LEVEL_ISOLATED

    def test_summarize_counts_levels(self):
        session = SimpleNamespace(verification_independence={
            "c-unit-test": {"level": LEVEL_ISOLATED},
            "arch-review": {"level": LEVEL_DEGRADED},
            "claude-review": {"level": LEVEL_NONE},
        })
        summary = summarize(session)
        assert summary["counts"] == {
            LEVEL_ISOLATED: 1, LEVEL_DEGRADED: 1, LEVEL_NONE: 1,
        }
        assert summary["degraded"] == ["arch-review"]
        assert summary["not_verified"] == ["claude-review"]


class TestSourceBodyLeak:
    SRC = """#include <stdio.h>

int led_tick(int state) {
    int next = state ? 0 : 1;
    printf("tick %d\\n", next);
    return next;
}
"""

    def test_clean_artifact_has_no_leak(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "led.c").write_text(self.SRC, encoding="utf-8")
        artifact = tmp_path / "test-cases.json"
        artifact.write_text('{"test_cases": [{"name": "blink 1s"}]}', encoding="utf-8")
        assert source_body_leak(artifact, tmp_path) == []

    def test_copied_body_is_detected(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "led.c").write_text(self.SRC, encoding="utf-8")
        artifact = tmp_path / "test-cases.json"
        artifact.write_text(
            '{"snippet": "{\\n    int next = state ? 0 : 1;\\n'
            '    printf(\\"tick %d\\\\n\\", next);\\n    return next;\\n}"}',
            encoding="utf-8",
        )
        assert source_body_leak(artifact, tmp_path) == ["src/led.c"]

    def test_artifacts_dir_is_not_scanned(self, tmp_path):
        staging = tmp_path / "artifacts" / "generated-code" / "x" / "src"
        staging.mkdir(parents=True)
        (staging / "led.c").write_text(self.SRC, encoding="utf-8")
        artifact = tmp_path / "test-cases.json"
        artifact.write_text(self.SRC, encoding="utf-8")
        assert source_body_leak(artifact, tmp_path) == []


class TestSessionSerialisation:
    def test_session_json_records_independence(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_SESSIONS_DIR", str(tmp_path / "sessions"))
        spec = tmp_path / "spec.md"
        spec.write_text("# spec\n\n### SR-001\n- The system SHALL blink.\n", encoding="utf-8")
        session = PipelineSession("independence", str(spec))

        record(session, "arch-review", "completed")
        data = session.to_dict()
        assert data["verification_independence"]["arch-review"]["level"] == LEVEL_DEGRADED

        session._save()
        saved = (Path(session.session_dir) / "session.json").read_text(encoding="utf-8")
        assert "verification_independence" in saved
