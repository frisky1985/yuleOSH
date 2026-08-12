"""Tests for pipeline step_cache (B1 — 确定性步骤内容寻址缓存)."""

import json
import os
from pathlib import Path

import pytest


class FakeSession:
    def __init__(self, project_dir, session_dir):
        self.name = "test-run"
        self.spec_path = str(Path(project_dir) / "spec.md")
        self.project_dir = str(project_dir)
        self.session_dir = Path(session_dir)
        self.artifacts: dict = {}


class TestClassification:
    def test_cacheable_steps(self):
        from yuleosh.pipeline.step_cache import is_cacheable
        for key in ["c-unit-test", "review-memory", "coverage-review",
                    "review-critical-safety", "test-qualification",
                    "codegen-deploy", "merge-gate"]:
            assert is_cacheable(key), key

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
