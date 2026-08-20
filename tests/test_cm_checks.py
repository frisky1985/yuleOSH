# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
CM Gate 单测（第九轮决策 2026-08-19, 角色=小仓）— knowledge_graph/cm_checks.py。

覆盖 4 项确定性 CM 检查：
  1. workspace_clean        工作区清洁（warning 不阻断）
  2. commit_convention      提交规范（conventional commits 前缀 + 产物范围）
  3. generated_artifacts_leak  生成产物泄漏（阻断）
  4. deploy_guardrail       部署护栏（deploy-changes.json 证据链）

无 git 仓库 → 全部 skipped 容错。
"""

import json
import subprocess
from pathlib import Path

import pytest

from yuleosh.knowledge_graph.cm_checks import (
    LEAK_PATTERNS,
    check_commit_convention,
    check_deploy_guardrail,
    check_generated_artifacts_leak,
    check_workspace_clean,
    run_cm_checks,
)


def _git(repo: Path, *args: str) -> None:
    """Run git in a repo (test helper)."""
    subprocess.run(
        ["git", *args], cwd=str(repo), check=True,
        capture_output=True, text=True,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A fresh git repo with one conventional commit."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    _git(tmp_path, "add", "main.c")
    _git(tmp_path, "commit", "-q", "-m", "feat(core): add main")
    return tmp_path


class TestWorkspaceClean:
    """CM 检查 1: 工作区清洁 — warning 不阻断（防他 agent 并行文件误伤）。"""

    def test_clean_repo_passed(self, git_repo):
        result = check_workspace_clean(git_repo)
        assert result["status"] == "passed"
        assert result["changed_files"] == []
        assert result["untracked_files"] == []

    def test_uncommitted_change_warning_not_blocking(self, git_repo):
        (git_repo / "main.c").write_text("int main(void) { return 1; }\n", encoding="utf-8")
        result = check_workspace_clean(git_repo)
        assert result["status"] == "warning"  # 不阻断
        assert "main.c" in result["changed_files"]

    def test_untracked_file_warning(self, git_repo):
        (git_repo / "notes.md").write_text("wip", encoding="utf-8")
        result = check_workspace_clean(git_repo)
        assert result["status"] == "warning"
        assert "notes.md" in result["untracked_files"]

    def test_not_a_git_repo_skipped(self, tmp_path):
        result = check_workspace_clean(tmp_path)
        assert result["status"] == "skipped"


class TestCommitConvention:
    """CM 检查 2: 提交规范 — conventional commits 前缀。"""

    def test_conventional_commit_passed(self, git_repo):
        result = check_commit_convention(git_repo)
        assert result["status"] == "passed"
        assert result["head_subject"].startswith("feat(")

    def test_bad_prefix_failed(self, git_repo):
        (git_repo / "main.c").write_text("int main(void) { return 2; }\n", encoding="utf-8")
        _git(git_repo, "add", "main.c")
        _git(git_repo, "commit", "-q", "-m", "fixing stuff without prefix")
        result = check_commit_convention(git_repo)
        assert result["status"] == "failed"
        assert any("conventional commits" in v for v in result["violations"])

    def test_unknown_type_failed(self, git_repo):
        (git_repo / "main.c").write_text("int main(void) { return 3; }\n", encoding="utf-8")
        _git(git_repo, "add", "main.c")
        _git(git_repo, "commit", "-q", "-m", "wip(core): not a real type")
        result = check_commit_convention(git_repo)
        assert result["status"] == "failed"
        assert any("不在允许集合" in v for v in result["violations"])

    def test_commit_with_artifact_path_failed(self, git_repo):
        (git_repo / "artifacts").mkdir()
        (git_repo / "artifacts" / "build.bin").write_bytes(b"\x00\x01")
        _git(git_repo, "add", "artifacts/build.bin")
        _git(git_repo, "commit", "-q", "-m", "feat(core): add artifact")
        result = check_commit_convention(git_repo)
        assert result["status"] == "failed"
        assert any("生成产物" in v for v in result["violations"])

    def test_commit_with_osh_specs_passed(self, git_repo):
        # .osh/specs/ 是规范真相源 (LEAK_EXCLUDE_PREFIXES), commit 含它不算泄漏
        (git_repo / ".osh" / "specs" / "core").mkdir(parents=True)
        (git_repo / ".osh" / "specs" / "core" / "spec.md").write_text(
            "# Core Spec\n", encoding="utf-8"
        )
        _git(git_repo, "add", "-f", ".osh/specs/core/spec.md")
        _git(git_repo, "commit", "-q", "-m", "docs(core): update spec")
        result = check_commit_convention(git_repo)
        assert result["status"] == "passed"
        assert result["violations"] == []

    def test_no_commits_skipped(self, tmp_path):
        _git(tmp_path, "init", "-q")
        result = check_commit_convention(tmp_path)
        assert result["status"] == "skipped"


class TestGeneratedArtifactsLeak:
    """CM 检查 3: 生成产物泄漏 — 阻断。"""

    def test_no_leak_passed(self, git_repo):
        result = check_generated_artifacts_leak(git_repo)
        assert result["status"] == "passed"
        assert result["leaked_files"] == []

    def test_tracked_artifact_failed(self, git_repo):
        (git_repo / "htmlcov").mkdir()
        (git_repo / "htmlcov" / "index.html").write_text("<html></html>", encoding="utf-8")
        _git(git_repo, "add", "htmlcov/index.html")
        _git(git_repo, "commit", "-q", "-m", "chore: add coverage report")
        result = check_generated_artifacts_leak(git_repo)
        assert result["status"] == "failed"
        assert any("htmlcov" in f for f in result["leaked_files"])

    def test_pycache_leak_detected(self, git_repo):
        (git_repo / "__pycache__").mkdir()
        (git_repo / "__pycache__" / "x.pyc").write_bytes(b"\x00")
        _git(git_repo, "add", "__pycache__/x.pyc")
        _git(git_repo, "commit", "-q", "-m", "chore: pyc")
        result = check_generated_artifacts_leak(git_repo)
        assert result["status"] == "failed"


class TestDeployGuardrail:
    """CM 检查 4: 部署护栏 — deploy-changes.json 证据链。"""

    def test_no_deploy_skipped(self, git_repo, tmp_path):
        # 无 codegen-deploy 报告 → 无部署动作 → skipped
        result = check_deploy_guardrail(git_repo, tmp_path)
        assert result["status"] == "skipped"

    def test_deploy_without_evidence_failed(self, git_repo, tmp_path):
        # 有部署报告（status=deployed）但无 deploy-changes.json → failed
        report_dir = git_repo / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "codegen-deploy.json").write_text(
            json.dumps({"status": "deployed"}), encoding="utf-8")
        result = check_deploy_guardrail(git_repo, tmp_path)
        assert result["status"] == "failed"
        assert "evidence chain broken" in result["summary"]

    def test_deploy_with_evidence_passed(self, git_repo, tmp_path):
        report_dir = git_repo / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "codegen-deploy.json").write_text(
            json.dumps({"status": "deployed"}), encoding="utf-8")
        changes = tmp_path / "deploy-changes.json"
        changes.write_text(json.dumps({"files": ["src/app/main.c"]}), encoding="utf-8")
        result = check_deploy_guardrail(git_repo, tmp_path)
        assert result["status"] == "passed"
        assert result["deploy_changes_present"] is True

    def test_deploy_evidence_empty_failed(self, git_repo, tmp_path):
        report_dir = git_repo / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "codegen-deploy.json").write_text(
            json.dumps({"status": "deployed"}), encoding="utf-8")
        changes = tmp_path / "deploy-changes.json"
        changes.write_text("[]", encoding="utf-8")
        result = check_deploy_guardrail(git_repo, tmp_path)
        assert result["status"] == "failed"
        assert "empty" in result["summary"]


class TestRunCmChecks:
    """聚合语义: 任一 failed → failed；warning 仅记录；全 skipped → skipped。"""

    def test_aggregate_passed_on_clean_repo(self, git_repo, tmp_path):
        result = run_cm_checks(git_repo, tmp_path)
        assert result["status"] == "passed"
        assert result["failed_checks"] == []

    def test_aggregate_failed_when_leak(self, git_repo, tmp_path):
        (git_repo / ".osh").mkdir()
        (git_repo / ".osh" / "session.json").write_text("{}", encoding="utf-8")
        _git(git_repo, "add", ".osh/session.json")
        _git(git_repo, "commit", "-q", "-m", "chore: session")
        result = run_cm_checks(git_repo, tmp_path)
        assert result["status"] == "failed"
        assert "generated_artifacts_leak" in result["failed_checks"]

    def test_aggregate_warning_not_blocking(self, git_repo, tmp_path):
        (git_repo / "wip.c").write_text("// wip", encoding="utf-8")
        result = run_cm_checks(git_repo, tmp_path)
        assert result["status"] == "warning"
        assert result["failed_checks"] == []
        assert "workspace_clean" in result["warning_checks"]

    def test_aggregate_all_skipped_non_git(self, tmp_path):
        result = run_cm_checks(tmp_path)
        assert result["status"] == "skipped"

    def test_leak_patterns_cover_generated_dirs(self):
        assert "artifacts/" in LEAK_PATTERNS
        assert ".osh/" in LEAK_PATTERNS
        assert "htmlcov/" in LEAK_PATTERNS
        assert "__pycache__/" in LEAK_PATTERNS
        assert ".benchmarks/" in LEAK_PATTERNS
