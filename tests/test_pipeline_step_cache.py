"""Tests for pipeline step_cache (B1 — 确定性步骤内容寻址缓存)."""

# @tests src/yuleosh/pipeline/orchestrator.py

import json
import os
from pathlib import Path
from unittest import mock

import pytest


class FakeSession:
    def __init__(self, project_dir, session_dir):
        self.name = "test-run"
        self.spec_path = str(Path(project_dir) / "spec.md")
        self.project_dir = str(project_dir)
        self.session_dir = Path(session_dir)
        self.artifacts: dict = {}


class TestClassification:
    def test_reusable_steps(self):
        from yuleosh.pipeline.step_cache import is_cacheable
        # 2026-09-22 政策调整: 只有「输入/生成物」类 (spec / 代码 / 规则)
        # 可跨 run 复用; 验证结果类改为每轮必跑 (见 test_verification_* )。
        for key in ["spec-check", "codegen-deploy"]:
            assert is_cacheable(key), key

    def test_verification_steps_never_reused(self):
        """验证结果类 (SWE.4/5/6 证据) 不可跨 run 复用 — 2026-09-22 复盘。

        回归: integration-test / misra-review 命中上一轮缓存 (status=skipped),
        G7 (SWE.5 集成) 被判 skipped 而 run 仍报 completed —— 表面完成,
        实际本轮零验证证据。
        """
        from yuleosh.pipeline.step_cache import is_cacheable, must_rerun
        for key in ["c-unit-test", "coverage-review", "misra-review",
                    "review-critical-safety", "test-qualification",
                    "merge-gate", "qemu-verify",
                    "integration-test", "fault-injection"]:
            assert must_rerun(key), key
            assert not is_cacheable(key), key

    def test_reusable_steps_not_marked_rerun(self):
        from yuleosh.pipeline.step_cache import must_rerun
        for key in ["spec-check", "codegen-deploy"]:
            assert not must_rerun(key), key

    def test_llm_steps_never_cacheable(self):
        from yuleosh.pipeline.step_cache import is_cacheable
        for key in ["super-analysis", "prd", "architecture", "development",
                    "code-review", "final-report", "test-planning"]:
            assert not is_cacheable(key), key

    def test_is_llm_step(self):
        from yuleosh.pipeline.step_cache import is_llm_step
        assert is_llm_step("architecture")
        assert not is_llm_step("c-unit-test")


class TestCacheEnabled:
    def test_default_enabled(self, monkeypatch):
        from yuleosh.pipeline.step_cache import cache_enabled
        monkeypatch.delenv("OSH_NO_CACHE", raising=False)
        assert cache_enabled() is True

    def test_disabled(self, monkeypatch):
        from yuleosh.pipeline.step_cache import cache_enabled
        monkeypatch.setenv("OSH_NO_CACHE", "1")
        assert cache_enabled() is False


class TestFingerprint:
    def _session(self, tmp_path):
        (tmp_path / "spec.md").write_text("# spec")
        return FakeSession(tmp_path, tmp_path / ".osh" / "sessions" / "s1")

    def test_same_input_same_fp(self, tmp_path):
        from yuleosh.pipeline.step_cache import compute_fingerprint
        s1 = self._session(tmp_path)
        s2 = self._session(tmp_path)
        assert compute_fingerprint(s1, "c-unit-test") == compute_fingerprint(s2, "c-unit-test")

    def test_different_step_key_different_fp(self, tmp_path):
        from yuleosh.pipeline.step_cache import compute_fingerprint
        s = self._session(tmp_path)
        assert compute_fingerprint(s, "c-unit-test") != compute_fingerprint(s, "review-memory")

    def test_src_change_invalidates(self, tmp_path):
        from yuleosh.pipeline.step_cache import compute_fingerprint
        s = self._session(tmp_path)
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "main.c").write_text("int main(void){return 0;}\n")
        fp1 = compute_fingerprint(s, "c-unit-test")
        (src / "main.c").write_text("int main(void){return 1;}\n")
        fp2 = compute_fingerprint(s, "c-unit-test")
        assert fp1 != fp2

    def test_spec_change_invalidates(self, tmp_path):
        from yuleosh.pipeline.step_cache import compute_fingerprint
        s = self._session(tmp_path)
        fp1 = compute_fingerprint(s, "c-unit-test")
        (tmp_path / "spec.md").write_text("# spec changed")
        fp2 = compute_fingerprint(s, "c-unit-test")
        assert fp1 != fp2

    def test_doc_artifact_change_does_not_invalidate(self, tmp_path):
        """文档 artifact (LLM 输出) 变化不应使代码步骤失效 — 2026-08-12 修正。

        初版指纹含全部 artifacts → LLM 文档每次 run 都变 → 确定性步骤
        永远 miss。修正后指纹只含代码/配置/状态。
        """
        from yuleosh.pipeline.step_cache import compute_fingerprint
        s = self._session(tmp_path)
        art = tmp_path / ".osh" / "sessions" / "s1" / "architecture.md"
        art.parent.mkdir(parents=True)
        art.write_text("# arch v1")
        s.artifacts["architecture"] = str(art)
        fp1 = compute_fingerprint(s, "review-memory")
        art.write_text("# arch v2")
        fp2 = compute_fingerprint(s, "review-memory")
        assert fp1 == fp2

    def test_deploy_report_change_invalidates(self, tmp_path):
        """锚定报告变化 → 审查步骤失效 (codegen 部署状态是审查的输入)。"""
        from yuleosh.pipeline.step_cache import compute_fingerprint
        s = self._session(tmp_path)
        rep = tmp_path / ".yuleosh" / "reports" / "codegen-deploy.json"
        rep.parent.mkdir(parents=True)
        rep.write_text('{"status": "deployed", "deployed": ["src/app.c"]}')
        fp1 = compute_fingerprint(s, "review-memory")
        rep.write_text('{"status": "skipped_codegen_failed", "deployed": []}')
        fp2 = compute_fingerprint(s, "review-memory")
        assert fp1 != fp2


class TestStoreLookupRestore:
    def _session(self, tmp_path):
        (tmp_path / "spec.md").write_text("# spec")
        sess_dir = tmp_path / ".osh" / "sessions" / "s1"
        sess_dir.mkdir(parents=True)
        return FakeSession(tmp_path, sess_dir)

    def test_store_lookup_restore_roundtrip(self, tmp_path):
        from yuleosh.pipeline.step_cache import (
            compute_fingerprint, lookup, store, restore,
        )
        s = self._session(tmp_path)

        # 首次: 产物写入 session dir
        out = s.session_dir / "memory-review.json"
        out.write_text(json.dumps({"status": "passed", "step": "review-memory"}))

        fp = compute_fingerprint(s, "review-memory")
        assert lookup(tmp_path, "review-memory", fp) is None   # 尚未入库

        store(tmp_path, "review-memory", fp, out)
        assert lookup(tmp_path, "review-memory", fp) is not None

        # 第二次 session: 恢复产物
        sess2 = tmp_path / ".osh" / "sessions" / "s2"
        sess2.mkdir(parents=True)
        s2 = FakeSession(tmp_path, sess2)
        restored = restore(tmp_path, "review-memory", fp, s2)
        assert Path(restored).exists()
        assert json.loads(Path(restored).read_text())["status"] == "passed"

    def test_missing_output_not_stored(self, tmp_path):
        from yuleosh.pipeline.step_cache import (
            compute_fingerprint, lookup, store,
        )
        s = self._session(tmp_path)
        fp = compute_fingerprint(s, "review-memory")
        store(tmp_path, "review-memory", fp, tmp_path / "nope.json")
        assert lookup(tmp_path, "review-memory", fp) is None

    def test_failed_output_not_stored(self, tmp_path):
        """失败产物 (status 属 FAILED_STATUSES) 不得入缓存 — r21c 复盘。

        回归: codegen-deploy skipped_codegen_failed 曾被 store 入库,
        r21c 指纹命中复用失败结果, codegen 从未重跑 (codex-verify RED)。
        """
        from yuleosh.pipeline.step_cache import (
            compute_fingerprint, lookup, store,
        )
        s = self._session(tmp_path)
        out = s.session_dir / "codegen-deploy.json"
        out.write_text(json.dumps({
            "status": "skipped_codegen_failed", "deployed": [],
        }))
        fp = compute_fingerprint(s, "codegen-deploy")
        store(tmp_path, "codegen-deploy", fp, out)
        assert lookup(tmp_path, "codegen-deploy", fp) is None

    def test_failed_cache_considered_miss(self, tmp_path):
        """历史脏缓存: 已入库的失败产物必须被 lookup 判为 miss — r21c 复盘。

        即使旧版本代码已把失败结果 store 进缓存, 新 lookup 也不能复用。
        """
        from yuleosh.pipeline.step_cache import (
            _cache_root, compute_fingerprint, lookup,
        )
        s = self._session(tmp_path)
        fp = compute_fingerprint(s, "codegen-deploy")
        # 手工构造失败缓存 (模拟旧版本已入库的脏数据)
        d = _cache_root(tmp_path) / "codegen-deploy" / fp / "output"
        d.mkdir(parents=True)
        (d / "codegen-deploy.json").write_text(json.dumps({
            "status": "skipped_codegen_failed", "deployed": [],
        }))
        assert lookup(tmp_path, "codegen-deploy", fp) is None

    def test_skipped_output_still_cacheable(self, tmp_path):
        """合法跳过 (skipped/empty) 仍可缓存 — 输入未变时复用跳过结论正确。"""
        from yuleosh.pipeline.step_cache import (
            compute_fingerprint, lookup, store,
        )
        s = self._session(tmp_path)
        out = s.session_dir / "codegen-deploy.json"
        out.write_text(json.dumps({
            "status": "skipped", "deployed": [], "skipped_empty": ["src"],
        }))
        fp = compute_fingerprint(s, "codegen-deploy")
        store(tmp_path, "codegen-deploy", fp, out)
        assert lookup(tmp_path, "codegen-deploy", fp) is not None


class TestPurgeVerificationCache:
    """2026-09-22: 每轮 pipeline 启动清空验证结果类缓存。"""

    def _seed(self, tmp_path, step_key, fingerprint="abc123"):
        from yuleosh.pipeline.step_cache import _cache_root
        d = _cache_root(tmp_path) / step_key / fingerprint / "output"
        d.mkdir(parents=True)
        (d / f"{step_key}.json").write_text(json.dumps({"status": "passed"}))
        return d.parent

    def test_purge_removes_verification_entries_keeps_reusable(self, tmp_path):
        from yuleosh.pipeline.step_cache import purge_verification_cache
        fresh = [self._seed(tmp_path, k) for k in ("integration-test", "misra-review")]
        reusable = self._seed(tmp_path, "spec-check")
        res = purge_verification_cache(tmp_path)
        assert res["skipped"] is False
        assert res["removed"] == 2
        assert set(res["purged"]) == {"integration-test", "misra-review"}
        assert not any(d.exists() for d in fresh)
        assert reusable.exists(), "可复用类 (spec/代码) 缓存不得被清理"

    def test_purge_dry_run_keeps_files(self, tmp_path):
        from yuleosh.pipeline.step_cache import purge_step_cache
        d = self._seed(tmp_path, "c-unit-test")
        res = purge_step_cache(tmp_path, {"c-unit-test"}, dry_run=True)
        assert res["removed"] == 1
        assert res["dry_run"] is True
        assert d.exists()

    def test_purge_without_cache_root_is_noop(self, tmp_path):
        from yuleosh.pipeline.step_cache import purge_verification_cache
        res = purge_verification_cache(tmp_path)
        assert res["removed"] == 0
        assert res["purged"] == []

    def test_env_switch_skips_purge(self, tmp_path, monkeypatch):
        """OSH_KEEP_VERIFICATION_CACHE=1 → 跳过清理 (旧行为, 仅调试)。"""
        from yuleosh.pipeline.step_cache import purge_verification_cache
        d = self._seed(tmp_path, "qemu-verify")
        monkeypatch.setenv("OSH_KEEP_VERIFICATION_CACHE", "1")
        res = purge_verification_cache(tmp_path)
        assert res["skipped"] is True
        assert d.exists()

    def test_purged_step_no_longer_hits_cache(self, tmp_path):
        """清理后同指纹不再命中 → 验证步骤必然真实重跑。"""
        from yuleosh.pipeline.step_cache import (
            compute_fingerprint, lookup, purge_verification_cache, store,
        )
        (tmp_path / "spec.md").write_text("# spec")
        sess_dir = tmp_path / ".osh" / "sessions" / "s1"
        sess_dir.mkdir(parents=True)
        s = FakeSession(tmp_path, sess_dir)
        out = sess_dir / "integration-test.json"
        out.write_text(json.dumps({"status": "passed"}))
        fp = compute_fingerprint(s, "integration-test")
        store(tmp_path, "integration-test", fp, out)
        assert lookup(tmp_path, "integration-test", fp) is not None
        purge_verification_cache(tmp_path)
        assert lookup(tmp_path, "integration-test", fp) is None


class TestRunStartPurgeIntegration:
    """run_pipeline 启动即清空验证缓存 → 验证步骤必真实重跑 (2026-09-22)。

    回归护栏: integration-test / misra-review 曾命中上一轮缓存 (status=skipped),
    使 G7 (SWE.5 集成) 被判 skipped, 而 run 仍报 completed。
    """

    def _run(self, tmp_path, steps, spec_path, monkeypatch, name="purge-it"):
        from contextlib import ExitStack
        from yuleosh.pipeline.orchestrator import run_pipeline
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("OSH_KEEP_VERIFICATION_CACHE", raising=False)
        monkeypatch.delenv("OSH_NO_CACHE", raising=False)
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch("yuleosh.pipeline.run.PIPELINE_STEPS", steps))
            stack.enter_context(
                mock.patch("yuleosh.pipeline.run._check_llm_key",
                           return_value="sk-test"))
            stack.enter_context(mock.patch(
                "yuleosh.pipeline.orchestrator._detect_and_bootstrap",
                return_value=None))
            stack.enter_context(mock.patch(
                "yuleosh.pipeline.orchestrator.load_agent_constraints",
                return_value=("", "builtin_fallback")))
            stack.enter_context(mock.patch(
                "yuleosh.pipeline.orchestrator.load_agent_constraints_by_role",
                return_value={}))
            stack.enter_context(mock.patch(
                "yuleosh.ci.profile.validate_active_profile",
                return_value=(True, "ok")))
            stack.enter_context(mock.patch(
                "yuleosh.ci.profile.get_current_profile",
                return_value="safety"))
            stack.enter_context(mock.patch(
                "yuleosh.ci.profile.filter_steps_for_profile",
                side_effect=lambda s, p, d: s))
            return run_pipeline(str(spec_path), name=name)

    def _seed_cache(self, tmp_path, step_key, status="skipped"):
        """按真实指纹预置一条历史缓存 (模拟上一轮留下的验证产物)。"""
        from yuleosh.pipeline.step_cache import compute_fingerprint, store
        spec = tmp_path / "spec.md"
        sess_dir = tmp_path / ".osh" / "sessions" / "prev"
        sess_dir.mkdir(parents=True, exist_ok=True)
        s = FakeSession(tmp_path, sess_dir)
        fp = compute_fingerprint(s, step_key)
        out = sess_dir / f"{step_key}.json"
        out.write_text(json.dumps({"status": status, "step": step_key}))
        store(tmp_path, step_key, fp, out)
        return fp

    def test_verification_step_reruns_despite_cached_artifact(
            self, tmp_path, monkeypatch):
        """integration-test 有历史缓存也必须真实重跑, 且缓存被清除。"""
        from yuleosh.pipeline.step_cache import lookup
        spec = tmp_path / "spec.md"
        spec.write_text("# Spec\n\n## REQ-001\n\n- The system SHALL run\n")
        fp = self._seed_cache(tmp_path, "integration-test", status="passed")
        assert lookup(tmp_path, "integration-test", fp) is not None

        calls = []

        def _handler(session):
            calls.append(1)
            out = Path(session.session_dir) / "integration-test.json"
            out.write_text(json.dumps(
                {"status": "passed", "step": "integration-test"}))
            return str(out)

        session = self._run(
            tmp_path,
            [("integration-test", "小克", "接口集成测试", _handler)],
            spec, monkeypatch,
        )
        assert calls == [1], "验证步骤必须真实执行, 不得复用缓存"
        assert not session.steps[0].get("cached")
        assert lookup(tmp_path, "integration-test", fp) is None, \
            "历史验证缓存应已被清空"

    def test_reusable_step_still_reuses_cache(self, tmp_path, monkeypatch):
        """spec/代码类 (REUSABLE_STEPS) 仍按指纹复用, 不清、不重跑。"""
        from yuleosh.pipeline.step_cache import lookup
        spec = tmp_path / "spec.md"
        spec.write_text("# Spec\n\n## REQ-001\n\n- The system SHALL run\n")
        fp = self._seed_cache(tmp_path, "spec-check", status="passed")

        calls = []

        def _handler(session):  # pragma: no cover - 命中缓存时不应被调用
            calls.append(1)
            out = Path(session.session_dir) / "spec-check.json"
            out.write_text(json.dumps({"status": "passed"}))
            return str(out)

        session = self._run(
            tmp_path,
            [("spec-check", "小明", "OpenSpec 合规检查", _handler)],
            spec, monkeypatch,
        )
        assert calls == [], "可复用步骤应命中缓存"
        assert session.steps[0].get("cached") is True
        assert lookup(tmp_path, "spec-check", fp) is not None


class TestOrchestratorIntegration:
    def test_cache_hit_marks_step_cached(self, tmp_path, monkeypatch):
        """集成: 构造已入库的缓存, 跑 orchestrator 步骤循环应命中 cached。"""
        from yuleosh.pipeline import step_cache
        from yuleosh.pipeline.orchestrator import _find_previous_session  # noqa: F401

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        # 项目 src
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "main.c").write_text("int main(void){return 0;}\n")
        (tmp_path / "spec.md").write_text("# spec")

        # 构造 session + 首次产物入库
        sess_dir = tmp_path / ".osh" / "sessions" / "s1"
        sess_dir.mkdir(parents=True)
        s = FakeSession(tmp_path, sess_dir)
        fp = step_cache.compute_fingerprint(s, "spec-check")
        out = sess_dir / "spec-check.json"
        out.write_text(json.dumps({"status": "passed", "step": "spec-check"}))
        step_cache.store(tmp_path, "spec-check", fp, out)

        # 命中
        assert step_cache.lookup(tmp_path, "spec-check", fp) is not None
        s2_dir = tmp_path / ".osh" / "sessions" / "s2"
        s2_dir.mkdir(parents=True)
        s2 = FakeSession(tmp_path, s2_dir)
        restored = step_cache.restore(tmp_path, "spec-check", fp, s2)
        assert Path(restored).name == "spec-check.json"
        assert json.loads(Path(restored).read_text())["status"] == "passed"
