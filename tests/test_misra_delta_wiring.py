"""MISRA 增量扫描接线测试（brainstorm-yuleosh-efficiency-20260808 §1.3）。

验证:
- 三源并集变更集（committed diff + 工作区未提交 + 未跟踪新文件）
- 头文件反向依赖展开（改 .h 必须扫到 include 它的 .c/.cpp，跨文件宏不漏扫）
- L1 走 delta / L2 走 full 的接线
- 增量模式正确性：只扫相关集，不退化回全量
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from yuleosh.ci.stages.review import (  # noqa: E402
    _collect_delta_files,
    _expand_header_dependents,
)


@pytest.fixture
def git_repo(tmp_path):
    """Create a real git repo with one committed C file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    return repo


def _commit_all(repo: Path, msg: str):
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", msg], cwd=repo, check=True)


class TestCollectDeltaFiles:
    def test_committed_diff_source(self, git_repo):
        """已提交的变更（git diff HEAD~1）必须被收集。"""
        src = git_repo / "src"
        src.mkdir()
        (src / "a.c").write_text("int a;\n")
        (src / "a.h").write_text("#define X 1\n")
        _commit_all(git_repo, "initial")
        (src / "b.c").write_text("int b;\n")
        _commit_all(git_repo, "add b.c")

        changed = _collect_delta_files(str(git_repo))
        assert "src/b.c" in changed
        assert "src/a.c" not in changed  # 未变

    def test_working_tree_source(self, git_repo):
        """工作区未提交（staged+unstaged）必须被收集。"""
        src = git_repo / "src"
        src.mkdir()
        (src / "a.c").write_text("int a;\n")
        _commit_all(git_repo, "initial")
        # unstaged modification
        (src / "a.c").write_text("int a;\nint a2;\n")
        changed = _collect_delta_files(str(git_repo))
        assert "src/a.c" in changed

    def test_untracked_new_file_source(self, git_repo):
        """未跟踪新文件必须被收集（git ls-files --others）。"""
        src = git_repo / "src"
        src.mkdir()
        (src / "a.c").write_text("int a;\n")
        _commit_all(git_repo, "initial")
        # new untracked file
        (src / "new.c").write_text("int new;\n")
        changed = _collect_delta_files(str(git_repo))
        assert "src/new.c" in changed

    def test_only_c_cpp_h_filtered(self, git_repo):
        """非 C/C++/H 文件（如 .py/.md）不得进入扫描集。"""
        (git_repo / "a.c").write_text("int a;\n")
        (git_repo / "a.py").write_text("print(1)\n")
        (git_repo / "README.md").write_text("# hi\n")
        _commit_all(git_repo, "initial")
        (git_repo / "a.py").write_text("print(2)\n")
        (git_repo / "b.c").write_text("int b;\n")
        changed = _collect_delta_files(str(git_repo))
        assert "a.py" not in changed
        assert "README.md" not in changed
        assert "b.c" in changed

    def test_no_git_dir_returns_empty(self, tmp_path):
        """非 git 目录：三源都失败 → 空集（调用方回退 full）。"""
        assert _collect_delta_files(str(tmp_path)) == []

    def test_docs_only_latest_commit_does_not_hide_c_change(self, git_repo):
        """2026-08-16 盲区修复：先提交 C 变更、再单独提交 docs 时，
        HEAD~1 只含 docs → 旧实现空扫。必须回看最近 N 个提交找到 C 变更。"""
        src = git_repo / "src"
        src.mkdir()
        (src / "a.c").write_text("int a;\n")
        _commit_all(git_repo, "initial")
        # 提交 1：C 变更
        (src / "a.c").write_text("int a;\nint a2;\n")
        _commit_all(git_repo, "feat: change a.c")
        # 提交 2：仅 docs（把 C 变更挤出 HEAD~1 窗口）
        (git_repo / "README.md").write_text("# doc\n")
        _commit_all(git_repo, "docs: readme")

        changed = _collect_delta_files(str(git_repo))
        assert "src/a.c" in changed, (
            f"C change hidden by docs-only HEAD~1; delta={changed}"
        )

    def test_shallow_history_falls_back_gracefully(self, git_repo):
        """提交数不足 N 时（如只有 1 个提交），HEAD~N 失败不得影响
        working tree 源——未提交变更仍须被收集。"""
        src = git_repo / "src"
        src.mkdir()
        (src / "only.c").write_text("int only;\n")
        _commit_all(git_repo, "initial")
        # 只有 1 个提交 → HEAD~1 不存在；working tree 有未提交 C 变更
        (src / "only.c").write_text("int only;\nint only2;\n")
        changed = _collect_delta_files(str(git_repo))
        assert "src/only.c" in changed


class TestExpandHeaderDependents:
    def _setup(self, git_repo):
        src = git_repo / "src"
        src.mkdir()
        (src / "impl.c").write_text('#include "config.h"\nint x;\n')
        (src / "other.c").write_text('#include <config.h>\nint y;\n')
        (src / "unrelated.c").write_text("int z;\n")
        (src / "config.h").write_text("#define CFG 1\n")
        _commit_all(git_repo, "initial")
        return src

    def test_changed_header_expands_dependents(self, git_repo):
        """改 .h → 反向依赖的 .c/.cpp 全部进入扫描集（跨文件宏不漏扫）。"""
        src = self._setup(git_repo)
        (src / "config.h").write_text("#define CFG 2\n")
        changed = _collect_delta_files(str(git_repo))
        assert changed == ["src/config.h"]
        expanded = _expand_header_dependents(str(git_repo), changed)
        assert "src/impl.c" in expanded
        assert "src/other.c" in expanded
        assert "src/unrelated.c" not in expanded

    def test_changed_c_no_header_expansion_needed(self, git_repo):
        """改 .c → 只扫变更文件本身，不额外扩头文件依赖。"""
        src = self._setup(git_repo)
        (src / "impl.c").write_text('#include "config.h"\nint x2;\n')
        changed = _collect_delta_files(str(git_repo))
        assert changed == ["src/impl.c"]
        expanded = _expand_header_dependents(str(git_repo), changed)
        assert expanded == ["src/impl.c"]

    def test_no_headers_unchanged(self, git_repo):
        """无 .h 变更时原样返回。"""
        src = self._setup(git_repo)
        (src / "unrelated.c").write_text("int z2;\n")
        changed = _collect_delta_files(str(git_repo))
        assert _expand_header_dependents(str(git_repo), changed) == changed

    def test_header_with_no_dependents_keeps_itself(self, git_repo):
        """孤头文件（无 .c 引用）仍保留在扫描集，不静默丢弃。"""
        src = git_repo / "src"
        src.mkdir()
        (src / "lonely.h").write_text("#define L 1\n")
        _commit_all(git_repo, "initial")
        (src / "lonely.h").write_text("#define L 2\n")
        changed = _collect_delta_files(str(git_repo))
        expanded = _expand_header_dependents(str(git_repo), changed)
        assert "src/lonely.h" in expanded


# ===================================================================
# 接线验证：L1 delta / L2 full（layer_executor）
# ===================================================================


class TestLayerWiring:
    def test_layer1_uses_delta(self):
        """L1 misra-check 必须接线 delta（增量）。"""
        from yuleosh.ci.layers import layer_executor
        src = Path(layer_executor.__file__).read_text()
        assert 'mode="delta"' in src
        # L1 不允许残留 full 接线（全量归 L2）
        assert 'run_misra_check(pd, ci, mode="full")' not in src.replace(
            'run_misra_check(project_dir, ci, mode="full")', ""
        )

    def test_layer2_uses_full(self):
        """L2 保留全量扫描（mode="full"）。"""
        from yuleosh.ci.layers import layer_executor
        src = Path(layer_executor.__file__).read_text()
        assert 'run_misra_check(project_dir, ci, mode="full")' in src

    def test_run_misra_check_delta_uses_collector(self):
        """run_misra_check delta 分支调用三源收集 + 头文件展开。"""
        from yuleosh.ci.stages import review
        src = Path(review.__file__).read_text()
        assert "_collect_delta_files(project_dir)" in src
        assert "_expand_header_dependents(project_dir, changed)" in src
