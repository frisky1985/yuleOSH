"""Tests for 行为护栏体系 (2026-08-13, 老板拍板 1+2+3+4).

覆盖:
  B1 (0️⃣): 回归回滚后 deploy 报告 deployed 清空 + has_deployed_code()==False
  B2 (1️⃣): 备份持久化落盘 .yuleosh/guardrail/backup-<run_id>/, 可恢复
  B3 (2️⃣): 门禁失败 + 部署生效 + 备份在 → 回滚 → 重跑通过 → 保持回滚
  B4 (2️⃣): 门禁失败 + 回滚后重跑仍失败 → undo 恢复部署 (gate_failed_independent)
  B5 (2️⃣): 无部署 / 无备份 / 非行为门禁 → 不联动 (返回 {})
  B6 (4️⃣): OSH_GUARD_PROTECT_SRC=1 且 src 有 git 未提交改动 → 跳过部署
  B7 (4️⃣): not_verified_reason 显式化
  B8 (3️⃣): PytestRunner / GoRunner 真实执行 + 结果解析
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.pipeline.deploy_state import has_deployed_code
from yuleosh.pipeline.guardrail import (
    CCTestRunner,
    ChangeSet,
    GoRunner,
    PytestRunner,
    TestResult,
    backup_dir,
    find_latest_change_set,
    load_change_set,
    maybe_rollback_on_gate_failure,
    save_change_set,
)
from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.step_handlers.execution import step_codegen_deploy

pytestmark = pytest.mark.skipif(
    not (shutil.which("gcc") and shutil.which("cmake") and shutil.which("ctest")),
    reason="need gcc + cmake + ctest",
)


def _make_cmake_project(tmp_path) -> Path:
    """Minimal CMake C project at tmp_path root: app.c with 2 functions."""
    proj = tmp_path
    (proj / "src").mkdir(parents=True)
    (proj / "tests").mkdir(parents=True)
    (proj / "src" / "app.c").write_text(
        "int add(int a, int b) { return a + b; }\n"
        "int sub(int a, int b) { return a - b; }\n",
        encoding="utf-8",
    )
    (proj / "tests" / "test_app.c").write_text(
        '#include "app.h"\n'
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "    int fails = 0;\n"
        "    if (add(2, 3) != 5) { printf(\"FAIL add\\n\"); fails++; }\n"
        "    if (sub(5, 3) != 2) { printf(\"FAIL sub\\n\"); fails++; }\n"
        "    printf(\"%d failures\\n\", fails);\n"
        "    return fails;\n"
        "}\n",
        encoding="utf-8",
    )
    (proj / "src" / "app.h").write_text(
        "#ifndef APP_H\n#define APP_H\nint add(int a, int b);\n"
        "int sub(int a, int b);\n#endif\n",
        encoding="utf-8",
    )
    (proj / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(test C)\n"
        "enable_testing()\n"
        "add_library(app STATIC src/app.c)\n"
        "target_include_directories(app PUBLIC src)\n"
        "add_executable(test_app tests/test_app.c)\n"
        "target_link_libraries(test_app app)\n"
        "add_test(NAME app_tests COMMAND test_app)\n",
        encoding="utf-8",
    )
    return proj


def _configure(proj: Path):
    build = proj / "build"
    build.mkdir(exist_ok=True)
    subprocess.run(["cmake", "-S", str(proj), "-B", str(build)],
                   capture_output=True, text=True, timeout=120, check=True)


def _session(tmp_path, name="deploy-test"):
    spec = tmp_path / "spec.md"
    spec.write_text("SHALL: keep behavior\n")
    with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
        return PipelineSession(name=name, spec_path=str(spec))


def _gen_tree(proj: Path, name: str, app_c: str) -> Path:
    gen = proj / "artifacts" / "generated-code" / name
    src_gen = gen / "src"
    src_gen.mkdir(parents=True)
    (src_gen / "app.c").write_text(app_c, encoding="utf-8")
    (src_gen / "app.h").write_text(
        "#ifndef APP_H\n#define APP_H\nint add(int a, int b);\n"
        "int sub(int a, int b);\n#endif\n",
        encoding="utf-8",
    )
    (gen / "codegen-report.md").write_text(
        "# Code Generation Report\n\n> Status: ✅ verified\n", encoding="utf-8",
    )
    return gen


def _deploy_and_make_report(proj: Path, session, app_c: str) -> dict:
    """部署回归版代码, 返回 report dict (行为护栏应已回滚)。"""
    _gen_tree(proj, session.name, app_c)
    out = step_codegen_deploy(session)
    return json.loads(Path(out).read_text())


class TestDeployReportConsistency:
    """B1: 回归回滚后报告一致 (0️⃣ 修 bug)。"""

    def test_regression_rollback_clears_deployed(self, tmp_path):
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        session = _session(tmp_path, "deploy-regress")
        report = _deploy_and_make_report(
            proj, session,
            "int add(int a, int b) { return a + b; }\n"
            "int sub(int a, int b) { return a + b; }\n",  # sub 回归
        )
        assert report["status"] == "deployed_behavior_regression"
        assert report["deployed"] == []  # 0️⃣ 回滚后清空
        # has_deployed_code 视为无部署 → 后续审查 honest-skip
        assert has_deployed_code(proj) is False
        # src 恢复基线
        assert "a - b" in (proj / "src" / "app.c").read_text()


class TestChangeSetPersistence:
    """B2: 备份持久化落盘 (1️⃣)。"""

    def test_save_and_load_change_set(self, tmp_path):
        proj = tmp_path
        (proj / "src").mkdir(parents=True)
        orig = b"int x = 1;\n"
        (proj / "src" / "app.c").write_bytes(orig)
        changeset: ChangeSet = {
            "src/app.c": orig,          # 覆盖
            "src/new.c": None,          # 新增
        }
        deployed_after = {
            "src/app.c": b"int x = 2;\n",
            "src/new.c": b"int y = 3;\n",
        }
        bdir = save_change_set(proj, "run-abc123", changeset, deployed_after)
        assert bdir == backup_dir(proj, "run-abc123")
        assert bdir.exists()

        loaded = load_change_set(proj, "run-abc123")
        assert loaded is not None
        assert loaded["src/app.c"] == orig
        assert loaded["src/new.c"] is None  # 新增文件回滚=删除

        # find_latest 能定位
        found = find_latest_change_set(proj)
        assert found is not None
        run_id, cs = found
        assert run_id == "run-abc123"
        assert cs["src/app.c"] == orig

    def test_guardrail_backup_written_by_deploy(self, tmp_path):
        """codegen-deploy 部署后备份落盘 (门禁联动前提)。"""
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        session = _session(tmp_path, "deploy-bak")
        _gen_tree(proj, session.name,
                  "int add(int a, int b) { return a + b; }\n"
                  "int sub(int a, int b) { return a - b; }\n")
        out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "deployed"
        # 备份目录存在且可加载
        assert report.get("guardrail_backup")
        bdir = Path(report["guardrail_backup"])
        assert bdir.exists()
        loaded = load_change_set(proj, session.run_id)
        assert loaded is not None
        assert "src/app.c" in loaded
        # 部署前基线内容被备份
        orig = loaded["src/app.c"]
        assert orig is not None
        assert b"int sub(int a, int b) { return a - b; }" in orig


class FakeRunner:
    """可控 runner — 模拟门禁复跑结果。"""

    def __init__(self, status="passed"):
        self.status = status
        self.name = "fake"
        self.calls = 0

    def run(self, project_dir, force_rebuild=False) -> TestResult:
        self.calls += 1
        return TestResult(
            runner="fake", status=self.status,
            passed=1 if self.status == "passed" else 0,
            failed=0 if self.status == "passed" else 1,
        )


class TestGateLinkageRollback:
    """B3/B4: 门禁联动回滚 (2️⃣ 方案 A)。"""

    def _deployed_project(self, tmp_path, name="deploy-gate") -> tuple[Path, PipelineSession]:
        """部署良好代码 (护栏通过, 备份落盘), 返回 (proj, session)。"""
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        session = _session(tmp_path, name)
        _gen_tree(proj, session.name,
                  "int add(int a, int b) { return a + b; }\n"
                  "int sub(int a, int b) { return a - b; }\n")
        out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "deployed"
        return proj, session

    def test_gate_failure_rolls_back_and_verifies(self, tmp_path):
        """B3: 门禁失败 → 回滚 → 复跑 passed → 保持回滚 + deploy 报告更新。"""
        proj, session = self._deployed_project(tmp_path)

        gate_result = TestResult(
            runner="ctest", status="failed", passed=0, failed=1,
        )
        fake = FakeRunner(status="passed")  # 回滚后基线通过
        linkage = maybe_rollback_on_gate_failure(
            session, "c-unit-test", gate_result, runner=fake,
        )
        assert linkage["action"] == "rolled_back"
        assert fake.calls == 1
        # src 回滚到基线 (部署前内容 = 正确 sub)
        assert "a - b" in (proj / "src" / "app.c").read_text()
        # deploy 报告更新: 已回滚 + 视为无部署
        from yuleosh.pipeline.deploy_state import load_deploy_report
        report = load_deploy_report(proj)
        assert report is not None
        assert report["status"] == "deployed_behavior_regression"
        assert report["deployed"] == []
        assert has_deployed_code(proj) is False

    def test_gate_failure_baseline_also_fails_undo(self, tmp_path):
        """B4: 回滚后基线也失败 → 非部署问题 → undo 恢复部署。"""
        proj, session = self._deployed_project(tmp_path)
        # src 改成回归版 (门禁失败)
        (proj / "src" / "app.c").write_text(
            "int add(int a, int b) { return a + b; }\n"
            "int sub(int a, int b) { return a + b; }\n",
            encoding="utf-8",
        )
        gate_result = TestResult(
            runner="ctest", status="failed", passed=0, failed=1,
        )
        fake = FakeRunner(status="failed")  # 回滚后基线仍失败
        linkage = maybe_rollback_on_gate_failure(
            session, "c-unit-test", gate_result, runner=fake,
        )
        assert linkage["action"] == "gate_failed_independent"
        # src 恢复部署版 (undo) — 部署版 = 正确 sub (a-b)
        assert "a - b" in (proj / "src" / "app.c").read_text()
        # deploy 报告不动 (仍 deployed — 非部署问题, 标 RED 人工介入)
        from yuleosh.pipeline.deploy_state import load_deploy_report
        report = load_deploy_report(proj)
        assert report is not None
        assert report["status"] == "deployed"

    def test_no_deploy_no_linkage(self, tmp_path):
        """B5a: 无部署 (planning 模式) → 不联动。"""
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        session = _session(tmp_path, "deploy-none")
        gate_result = TestResult(runner="ctest", status="failed", failed=1)
        fake = FakeRunner()
        linkage = maybe_rollback_on_gate_failure(
            session, "c-unit-test", gate_result, runner=fake,
        )
        assert linkage == {}
        assert fake.calls == 0  # 没跑复跑

    def test_no_backup_no_linkage(self, tmp_path):
        """B5b: 有部署但无备份 → 不联动 (基线/环境问题, 不是部署回归)。"""
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        session = _session(tmp_path, "deploy-nobak")
        # 伪造 deploy 报告但没有 guardrail 备份
        report_dir = proj / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "codegen-deploy.json").write_text(
            json.dumps({"status": "deployed", "deployed": ["src/app.c"]}),
            encoding="utf-8",
        )
        gate_result = TestResult(runner="ctest", status="failed", failed=1)
        fake = FakeRunner()
        linkage = maybe_rollback_on_gate_failure(
            session, "c-unit-test", gate_result, runner=fake,
        )
        assert linkage == {}
        assert fake.calls == 0

    def test_non_behavior_gate_no_linkage(self, tmp_path):
        """B5c: 非行为门禁 (c-coverage-gate) → 不联动 (反模式)。"""
        proj, _session_obj = self._deployed_project(tmp_path)
        gate_result = TestResult(runner="gcovr", status="failed", failed=1)
        fake = FakeRunner()
        linkage = maybe_rollback_on_gate_failure(
            _session_obj, "c-coverage-gate", gate_result, runner=fake,
        )
        assert linkage == {}
        assert fake.calls == 0
        # src 没被动
        assert "a - b" in (proj / "src" / "app.c").read_text()

    def test_gate_passed_no_linkage(self, tmp_path):
        """B5d: 门禁通过 → 不联动。"""
        _proj, session = self._deployed_project(tmp_path)
        gate_result = TestResult(runner="ctest", status="passed", failed=0)
        fake = FakeRunner()
        linkage = maybe_rollback_on_gate_failure(
            session, "c-unit-test", gate_result, runner=fake,
        )
        assert linkage == {}
        assert fake.calls == 0


class TestSrcProtection:
    """B6: OSH_GUARD_PROTECT_SRC (4️⃣)。"""

    def test_protect_src_skips_deploy_when_uncommitted(self, tmp_path):
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        # 初始化 git 并做 src 未提交改动
        subprocess.run(["git", "init", "-q"], cwd=proj, check=False)
        subprocess.run(["git", "add", "-A"], cwd=proj, check=False)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-qm", "init"],
            cwd=proj, check=False,
        )
        (proj / "src" / "app.c").write_text(
            "int add(int a, int b) { return a + b; }\n"
            "int sub(int a, int b) { return a - b; }\n"
            "int user_patch = 42;\n",  # 用户手动改动
            encoding="utf-8",
        )
        session = _session(tmp_path, "deploy-protect")
        _gen_tree(proj, session.name,
                  "int add(int a, int b) { return a + b; }\n"
                  "int sub(int a, int b) { return a - b; }\n")
        with mock.patch.dict(os.environ, {"OSH_GUARD_PROTECT_SRC": "1"}):
            out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "skipped_src_protected"
        assert report["deployed"] == []
        # 用户改动保留
        assert "user_patch" in (proj / "src" / "app.c").read_text()

    def test_protect_src_off_no_skip(self, tmp_path):
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        subprocess.run(["git", "init", "-q"], cwd=proj, check=False)
        subprocess.run(["git", "add", "-A"], cwd=proj, check=False)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-qm", "init"],
            cwd=proj, check=False,
        )
        (proj / "src" / "app.c").write_text(
            "int add(int a, int b) { return a + b; }\n"
            "int sub(int a, int b) { return a - b; }\n"
            "int user_patch = 42;\n",
            encoding="utf-8",
        )
        session = _session(tmp_path, "deploy-noprotect")
        _gen_tree(proj, session.name,
                  "int add(int a, int b) { return a + b; }\n"
                  "int sub(int a, int b) { return a - b; }\n")
        # 默认 OSH_GUARD_PROTECT_SRC=0 → 正常部署
        out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "deployed"
        # 用户改动被覆盖 (保护关闭是显式选择)
        assert "user_patch" not in (proj / "src" / "app.c").read_text()


class TestNotVerifiedExplicit:
    """B7: not_verified 显式化 (4️⃣)。"""

    def test_guard_disabled_reason(self, tmp_path):
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        session = _session(tmp_path, "deploy-noverify")
        _gen_tree(proj, session.name,
                  "int add(int a, int b) { return a + b; }\n"
                  "int sub(int a, int b) { return a - b; }\n")
        with mock.patch.dict(os.environ, {"OSH_BEHAVIOR_GUARD": "0"}):
            out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        guard = report["behavior_guardrail"]
        assert guard["verdict"] == "not_verified"
        assert "guard disabled" in (guard["not_verified_reason"] or "")


class TestPyGoRunners:
    """B8: PytestRunner / GoRunner (3️⃣)。"""

    def _py_project(self, tmp_path, test_body: str) -> Path:
        proj = tmp_path
        (proj / "tests").mkdir(parents=True)
        (proj / "tests" / "test_demo.py").write_text(test_body, encoding="utf-8")
        return proj

    def test_pytest_runner_passes(self, tmp_path):
        proj = self._py_project(tmp_path,
            "def test_ok():\n    assert 1 + 1 == 2\n"
            "def test_ok2():\n    assert 2 * 2 == 4\n")
        result = PytestRunner().run(proj)
        assert result.status == "passed"
        assert result.passed == 2
        assert result.failed == 0

    def test_pytest_runner_fails(self, tmp_path):
        proj = self._py_project(tmp_path,
            "def test_ok():\n    assert 1 + 1 == 2\n"
            "def test_bad():\n    assert 1 + 1 == 3\n")
        result = PytestRunner().run(proj)
        assert result.status == "failed"
        assert result.passed == 1
        assert result.failed == 1

    def test_pytest_runner_no_tests_dir(self, tmp_path):
        result = PytestRunner().run(tmp_path)  # 无 tests/ 目录
        # pytest 会报 error (no tests) — 如实 failed 或 unknown
        assert result.status in ("failed", "unknown")

    def test_go_runner_skips_without_gomod(self, tmp_path):
        result = GoRunner().run(tmp_path)
        assert result.status == "skipped"
        assert "No go.mod" in result.output

    @pytest.mark.skipif(shutil.which("go") is None, reason="go not installed")
    def test_go_runner_passes(self, tmp_path):
        proj = tmp_path
        (proj / "go.mod").write_text("module demo\n\ngo 1.21\n", encoding="utf-8")
        (proj / "demo_test.go").write_text(
            "package demo\n\nimport \"testing\"\n\n"
            "func TestOk(t *testing.T) { if 1+1 != 2 { t.Fail() } }\n",
            encoding="utf-8",
        )
        result = GoRunner().run(proj)
        assert result.status == "passed"
        assert result.failed == 0

    def test_cctest_runner_protocol_compliance(self, tmp_path):
        """TestRunner 协议: CCTestRunner/PytestRunner/GoRunner 都有 name + run。"""
        for runner in (CCTestRunner(), PytestRunner(), GoRunner()):
            assert runner.name
            r = runner.run(tmp_path)
            assert isinstance(r, TestResult)
            assert r.status in ("passed", "failed", "skipped", "unknown")
