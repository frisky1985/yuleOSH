"""AUD-ASPICE-001 B5 回归：4xx 短路 / POSIX 自检 / P0 阻断 / CL3 度量 / 推断标注。"""

# @tests src/yuleosh/llm/providers/base.py, src/yuleosh/codegen/compilers.py,
#        src/yuleosh/pipeline/p0.py, src/yuleosh/ci/kpi/history.py,
#        src/yuleosh/pipeline/step_handlers/sys_layer.py

import json
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuleosh.ci.kpi.history import summarize
from yuleosh.codegen import compilers
from yuleosh.llm.providers.base import LLMFatalError, is_fatal_http_error
from yuleosh.pipeline.p0 import describe, violations


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", code, "err", {}, None)


class TestF03FatalHttpErrors:
    @pytest.mark.parametrize("code", [400, 401, 402, 403, 404, 422])
    def test_auth_and_quota_errors_are_fatal(self, code):
        assert is_fatal_http_error(_http_error(code)) is True

    @pytest.mark.parametrize("code", [408, 429, 500, 502, 503])
    def test_transient_errors_are_retryable(self, code):
        assert is_fatal_http_error(_http_error(code)) is False

    def test_non_http_exception_is_not_fatal(self):
        assert is_fatal_http_error(TimeoutError("x")) is False

    def test_fatal_error_carries_code(self):
        err = LLMFatalError("non-retryable HTTP 402")
        assert "402" in str(err)


class TestF02PosixMacro:
    C_POSIX = """#include <time.h>
int f(void) {
    struct timespec ts;
    return clock_gettime(CLOCK_MONOTONIC, &ts);
}
"""
    C_PLAIN = """int f(void) { return 0; }
"""

    def _run(self, tmp_path, content, platform, monkeypatch):
        src = tmp_path / "a.c"
        src.write_text(content, encoding="utf-8")
        captured = {}

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return _Proc()

        monkeypatch.setattr(compilers.subprocess, "run", fake_run)
        compilers.verify_c([src], project_root=tmp_path, platform=platform)
        return captured["cmd"]

    def test_posix_calls_get_macro_on_host(self, tmp_path, monkeypatch):
        cmd = self._run(tmp_path, self.C_POSIX, "HOST_SIM", monkeypatch)
        assert "-D_POSIX_C_SOURCE=200809L" in cmd

    def test_posix_calls_do_not_get_macro_on_bare_metal(self, tmp_path, monkeypatch):
        cmd = self._run(tmp_path, self.C_POSIX, "BARE_METAL_MCU", monkeypatch)
        assert "-D_POSIX_C_SOURCE=200809L" not in cmd

    def test_plain_code_never_gets_macro(self, tmp_path, monkeypatch):
        cmd = self._run(tmp_path, self.C_PLAIN, "HOST_SIM", monkeypatch)
        assert not any("_POSIX_C_SOURCE" in part for part in cmd)


class TestNC12P0Blocking:
    def test_skipped_p0_step_is_a_violation(self):
        items = violations([("prd", "skipped", "")])
        assert items == [{"step": "prd", "status": "skipped", "detail": ""}]
        assert "prd=skipped" in describe(items)

    def test_failed_p0_step_is_a_violation(self):
        assert violations([("architecture", "failed", "boom")])

    def test_resume_skip_is_exempt(self):
        items = violations([("prd", "skipped", "resume: before --from-step")])
        assert items == []

    def test_completed_p0_step_is_fine(self):
        assert violations([("prd", "completed", "")]) == []

    def test_non_p0_step_is_ignored(self):
        assert violations([("hwe-analysis", "skipped", "")]) == []

    def test_llm_unavailable_artifact_downgrades_step_to_skipped(
        self, tmp_path, monkeypatch
    ):
        """LLM provider 402 → prd 降级产物 status=skipped，步骤不得停留 completed。"""
        from yuleosh.pipeline.orchestrator import _propagate_step_verdict
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session = PipelineSession("vp", str(tmp_path / "spec.md"))
        session.add_step("prd", "Hermes", "产品需求分析")
        art = tmp_path / "prd.json"
        art.write_text(json.dumps({
            "step": "prd",
            "status": "skipped",
            "category": "llm_provider_unavailable",
            "reason": "non-retryable HTTP 402",
        }), encoding="utf-8")

        _propagate_step_verdict(session, 0, "prd", str(art))

        assert session.steps[0]["status"] == "skipped"
        assert "llm_provider_unavailable" in session.steps[0]["detail"]
        assert violations(
            [("prd", session.steps[0]["status"], session.steps[0]["detail"])]
        )


class TestNC13RunHistory:
    def _make_run(self, root: Path, name: str, started: str,
                  outcome: str, blockers=()):
        run_dir = root / name
        run_dir.mkdir(parents=True)
        (run_dir / "session.json").write_text(json.dumps({
            "name": name,
            "status": "completed",
            "started_at": started,
            "gate_verdict": {
                "outcome": outcome,
                "blocking_gates": list(blockers),
            },
            "errors": [],
        }), encoding="utf-8")

    def test_success_rate_and_gate_distribution(self, tmp_path):
        self._make_run(tmp_path, "r1", "2026-11-01T10:00:00", "green")
        self._make_run(tmp_path, "r2", "2026-11-02T10:00:00", "unverified",
                       [{"gate": "G4", "status": "not-run"}])
        self._make_run(tmp_path, "r3", "2026-11-03T10:00:00", "green")

        report = summarize(tmp_path, window=10)
        assert report["runs"] == 3
        assert report["green"] == 2
        assert report["success_rate_pct"] == 66.7
        assert report["outcomes"] == {"green": 2, "unverified": 1}
        assert report["gate_failures"] == {"G4:not-run": 1}

    def test_window_limits_recent_runs(self, tmp_path):
        self._make_run(tmp_path, "r1", "2026-11-01T10:00:00", "red")
        self._make_run(tmp_path, "r2", "2026-11-02T10:00:00", "green")
        report = summarize(tmp_path, window=1)
        assert report["runs"] == 1
        assert report["green"] == 1

    def test_empty_history_is_zero_not_error(self, tmp_path):
        report = summarize(tmp_path / "missing", window=10)
        assert report["runs"] == 0
        assert report["success_rate_pct"] == 0.0


class TestD03InferenceLabelling:
    def test_keyword_hit_is_not_marked_inferred(self):
        from yuleosh.pipeline.step_handlers.sys_layer import _infer_verification_method

        method, inferred = _infer_verification_method("系统应提供操作界面")
        assert method.startswith("演示")
        assert inferred is False

    def test_fallback_is_marked_inferred(self):
        from yuleosh.pipeline.step_handlers.sys_layer import _infer_verification_method

        method, inferred = _infer_verification_method("xyz 无关键词描述")
        assert method.startswith("测试")
        assert inferred is True

    def test_verification_doc_flags_inferred_items(self, tmp_path):
        from yuleosh.pipeline.step_handlers.sys_layer import (
            SYS_REQUIREMENTS,
            step_sys_requirements,
            step_sys_verification,
        )

        spec = tmp_path / "docs" / "spec.md"
        spec.parent.mkdir(parents=True)
        spec.write_text(
            "# demo\n\n### SR-001\n- The system SHALL synchronise xyz widgets.\n",
            encoding="utf-8")
        session = SimpleNamespace(project_dir=str(tmp_path), spec_path=str(spec))
        step_sys_requirements(session)
        assert (tmp_path / SYS_REQUIREMENTS).is_file()
        out = step_sys_verification(session)
        doc = Path(out).read_text(encoding="utf-8")
        assert "推断" in doc
        assert "待确认的推断项" in doc


class _FakeEmitter:
    """最小 StepStreamEmitter 替身（只记录 close / chunk）。"""

    def __init__(self):
        self.chunks = []
        self.closed = False
        self.is_closed = False
        self.model = ""
        self.provider = ""

    def on_stream_start(self):
        self.is_closed = False

    def on_chunk(self, text):
        self.chunks.append(text)

    def close(self):
        self.closed = True
        self.is_closed = True


class TestF03LegacyClientShortCircuit:
    """AUD-ASPICE-001 F-03：legacy `chat_completion` 与流式降级路径也不得重试 4xx。"""

    def test_402_is_not_retried_in_legacy_chat(self, monkeypatch):
        import urllib.error
        import urllib.request

        from yuleosh.llm import client as client_mod
        from yuleosh.llm.providers.base import LLMFatalError

        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.delenv("YULEOSH_LLM_UNIFIED", raising=False)
        monkeypatch.setattr(client_mod, "_local_llm_fallback_enabled", lambda: False)
        monkeypatch.setattr(client_mod, "_pipeline_emitter", lambda: None)

        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            raise urllib.error.HTTPError(
                req.full_url, 402, "Payment Required", {}, None
            )

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        with pytest.raises(LLMFatalError):
            client_mod.chat_completion("sys", "user", retries=3)
        assert len(calls) == 1, f"fatal 402 must not retry, got {len(calls)} calls"

    def test_stream_fatal_error_is_not_degraded(self, monkeypatch):
        from yuleosh.llm import client as client_mod
        from yuleosh.llm import streaming
        from yuleosh.llm.providers.base import LLMFatalError

        def fake_stream(*_args, **_kwargs):
            raise LLMFatalError("non-retryable HTTP 402")

        monkeypatch.setattr(streaming, "stream_request", fake_stream)
        emitter = _FakeEmitter()

        with pytest.raises(LLMFatalError):
            client_mod._stream_legacy_chat(
                url="https://api.deepseek.com/v1/chat/completions",
                headers={},
                body={"messages": []},
                timeout=5,
                retries=3,
                model="deepseek-chat",
                emitter=emitter,
            )
        assert emitter.closed is True
