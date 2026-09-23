#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""sessions 根解析与测试隔离（``OSH_SESSIONS_DIR``，2026-09-23）。

背景：sessions 根原为 ``<OSH_HOME>/.osh/sessions``，而 test_api.py 在模块
导入期就把 ``OSH_HOME`` 钉到仓库根（进程级）。于是每个构造过
``PipelineSession`` 的测试都往仓库自己的 ``.osh/sessions`` 漏一个目录 ——
实测累积 3611 个（占历史上出现过的全部 session 的 99.6%）。

``OSH_SESSIONS_DIR`` 单独重定向 sessions 根、**不动 OSH_HOME**，所以
test_api.py 依赖的相对路径解析不受影响。本文件既是优先级契约，也是
「跑测试不往仓库里写」这条不变量的回归守卫。
"""

import os
import shutil
from pathlib import Path

import pytest

from yuleosh.pipeline.session import PipelineSession, resolve_sessions_root

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestResolution:
    """``OSH_SESSIONS_DIR`` > ``OSH_HOME`` > cwd 的优先级。"""

    def test_default_is_osh_home_sessions(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OSH_SESSIONS_DIR", raising=False)
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        assert resolve_sessions_root() == tmp_path / ".osh" / "sessions"

    def test_explicit_wins_over_osh_home(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OSH_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("OSH_SESSIONS_DIR", str(tmp_path / "volume"))
        assert resolve_sessions_root() == tmp_path / "volume"

    def test_blank_explicit_is_ignored(self, monkeypatch, tmp_path):
        """空串/空白不算「显式设置」—— 否则 CI 传空变量会静默改根。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.setenv("OSH_SESSIONS_DIR", "   ")
        assert resolve_sessions_root() == tmp_path / ".osh" / "sessions"


class TestWritersHonourOverride:
    """写入侧：PipelineSession 与 subprocess_executor 必须同源。"""

    def test_pipeline_session_writes_under_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OSH_SESSIONS_DIR", str(tmp_path / "volume"))
        session = PipelineSession(name="probe", spec_path="spec.md", run_id="rid1")
        assert Path(session.session_dir) == tmp_path / "volume" / "rid1"
        assert Path(session.session_dir).is_dir()

    def test_subprocess_executor_honours_override(self, monkeypatch, tmp_path):
        from yuleosh.engine.subprocess_executor import _resolve_session_dir

        monkeypatch.setenv("OSH_SESSIONS_DIR", str(tmp_path / "volume"))
        got = _resolve_session_dir(str(tmp_path / "proj"), run_id="rid2")
        assert got == tmp_path / "volume" / "rid2"

    def test_writers_agree_on_same_run(self, monkeypatch, tmp_path):
        """主进程侧写 artifacts.json、worker 侧写产物 —— 目录必须一致。"""
        from yuleosh.engine.subprocess_executor import _resolve_session_dir

        monkeypatch.setenv("OSH_SESSIONS_DIR", str(tmp_path / "volume"))
        session = PipelineSession(name="probe", spec_path="spec.md", run_id="agree")
        assert Path(session.session_dir) == _resolve_session_dir(
            str(tmp_path), run_id="agree")

    def test_default_name_fallback_still_works(self, monkeypatch, tmp_path):
        from yuleosh.engine.subprocess_executor import _resolve_session_dir

        monkeypatch.delenv("OSH_SESSIONS_DIR", raising=False)
        monkeypatch.delenv("OSH_HOME", raising=False)
        got = _resolve_session_dir(str(tmp_path))
        assert got.parent == tmp_path / ".osh" / "sessions"
        assert got.name.startswith("agent-pipeline-")


class TestReadersHonourOverride:
    """读取侧：三个 API 模块共用同一个解析，避免读写不一致。"""

    def test_api_modules_share_one_resolver(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OSH_SESSIONS_DIR", str(tmp_path / "volume"))
        from yuleosh.api import artifacts, logs
        from yuleosh.api import tests as tests_api

        expected = tmp_path / "volume"
        assert artifacts._sessions_root() == expected
        assert logs._sessions_root() == expected
        assert tests_api._sessions_root() == expected

    def test_artifacts_still_walks_for_sub_project_roots(self, monkeypatch,
                                                        tmp_path):
        """显式根不该关掉子项目发现 —— 多项目面板依赖它。"""
        monkeypatch.setenv("OSH_SESSIONS_DIR", str(tmp_path / ".osh" / "sessions"))
        sub = tmp_path / "sub" / "beta-app" / ".osh" / "sessions"
        sub.mkdir(parents=True)
        monkeypatch.setattr("yuleosh.api.artifacts.OSH_HOME", str(tmp_path))

        from yuleosh.api import artifacts

        assert sub in artifacts._sessions_roots()


class TestNoRepoLeak:
    """回归守卫：跑测试不能往仓库自己的 .osh/sessions 写目录。"""

    @staticmethod
    def _repo_sessions() -> set[str]:
        root = REPO_ROOT / ".osh" / "sessions"
        return {p.name for p in root.iterdir()} if root.is_dir() else set()

    def test_conftest_redirects_sessions_root(self):
        explicit = os.environ.get("OSH_SESSIONS_DIR", "").strip()
        assert explicit, "conftest 必须设置 OSH_SESSIONS_DIR 做泄漏隔离"
        assert not Path(explicit).is_relative_to(REPO_ROOT), (
            "测试用的 sessions 根必须落在仓库之外")

    def test_creating_a_session_leaves_repo_untouched(self):
        before = self._repo_sessions()
        session = PipelineSession(name="leak-probe", spec_path="spec.md")
        session._save()
        leaked = self._repo_sessions() - before
        assert not leaked, f"泄漏到仓库 sessions: {sorted(leaked)}"

    def test_temp_root_keeps_project_layout(self):
        """conftest 的临时根须保持 <project>/.osh/sessions 层级。

        ``PipelineSession.to_dict`` 与 ``api.artifacts._project_for_session``
        都靠向上三层反推 project_dir —— 层级塌了就会得到错的 project_dir。
        """
        session = PipelineSession(name="shape-probe", spec_path="spec.md")
        sdir = Path(session.session_dir)
        assert sdir.parent.name == "sessions"
        assert sdir.parent.parent.name == ".osh"
        assert sdir.parent.parent.parent.is_dir()
        assert sdir.parent.parent.parent != sdir

    def test_argparse_entry_importable(self):
        """``python -m yuleosh.pipeline.session_prune`` 必须可用。"""
        from yuleosh.pipeline.session_prune import main

        assert callable(main)


class TestRootsWalkCache:
    """``_sessions_roots()`` 的遍历缓存 —— 只提速，不改语义。"""

    @staticmethod
    def _count_walks(monkeypatch) -> dict:
        from yuleosh.api import artifacts

        calls = {"n": 0}
        real = artifacts._discover_nested_session_roots

        def counting(home):
            calls["n"] += 1
            return real(home)

        monkeypatch.setattr(artifacts, "_discover_nested_session_roots", counting)
        return calls

    @staticmethod
    def _setup(monkeypatch, tmp_path):
        from yuleosh.api import artifacts

        root = tmp_path / ".osh" / "sessions"
        root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(artifacts, "OSH_HOME", str(tmp_path))
        monkeypatch.setenv("OSH_SESSIONS_DIR", str(root))
        artifacts._ROOTS_CACHE.clear()
        return artifacts

    def test_repeated_calls_walk_once(self, monkeypatch, tmp_path):
        artifacts = self._setup(monkeypatch, tmp_path)
        calls = self._count_walks(monkeypatch)

        first = artifacts._sessions_roots()
        artifacts._sessions_roots()
        artifacts._sessions_roots()

        assert calls["n"] == 1
        assert first == [tmp_path / ".osh" / "sessions"]

    def test_env_bypasses_cache(self, monkeypatch, tmp_path):
        artifacts = self._setup(monkeypatch, tmp_path)
        monkeypatch.setenv("OSH_NO_ROOTS_CACHE", "1")
        calls = self._count_walks(monkeypatch)

        artifacts._sessions_roots()
        artifacts._sessions_roots()

        assert calls["n"] == 2

    def test_disappearing_root_invalidates_cache(self, monkeypatch, tmp_path):
        """根被删掉必须立刻反映 —— 否则面板会一直显示已清理的 run。"""
        artifacts = self._setup(monkeypatch, tmp_path)
        calls = self._count_walks(monkeypatch)

        artifacts._sessions_roots()
        assert calls["n"] == 1

        shutil.rmtree(tmp_path / ".osh" / "sessions")
        artifacts._sessions_roots()
        assert calls["n"] == 2

    def test_nested_roots_are_still_discovered(self, monkeypatch, tmp_path):
        artifacts = self._setup(monkeypatch, tmp_path)
        sub = tmp_path / "sub" / "beta-app" / ".osh" / "sessions"
        sub.mkdir(parents=True)
        self._count_walks(monkeypatch)

        assert sub in artifacts._sessions_roots()

    def test_cache_is_bounded(self, monkeypatch, tmp_path):
        artifacts = self._setup(monkeypatch, tmp_path)
        monkeypatch.setattr(artifacts, "_ROOTS_CACHE_MAX", 2)
        for i in range(5):
            home = tmp_path / f"h{i}"
            home.mkdir()
            monkeypatch.setattr(artifacts, "OSH_HOME", str(home))
            artifacts._sessions_roots()
        assert len(artifacts._ROOTS_CACHE) <= 2


@pytest.mark.parametrize("step_key", ["spec-check", "codegen-deploy"])
def test_reusable_steps_still_share_a_root(step_key, monkeypatch, tmp_path):
    """可复用步骤不改变 sessions 根语义（回归护栏）。"""
    monkeypatch.setenv("OSH_SESSIONS_DIR", str(tmp_path / "vol"))
    session = PipelineSession(name=f"s-{step_key}", spec_path="spec.md")
    assert Path(session.session_dir).parent == tmp_path / "vol"
