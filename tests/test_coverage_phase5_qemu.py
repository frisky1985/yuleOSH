"""Phase 5 coverage boost — QEMU step handler + C coverage gate.

Target modules (2026-08-09 baseline):
  - src/yuleosh/pipeline/step_handlers/test_qemu.py        30.4% → 直测全部内部方法
  - src/yuleosh/pipeline/step_handlers/c_coverage_gate.py  36.7% → 4 个 phase + 配置/结果工具

风格：直测函数/分支，subprocess 只 patch ``run``（保留真实异常类），
不依赖真实 QEMU/CMake。

发现（Phase 5）: test_qemu._evaluate_output 中 ``"qemu:" in output_upper``
是死代码 —— output_upper 已 upper()，小写字面量永远匹配不到，qemu 崩溃
检测分支从不生效。已修产品代码（小写比较），见源码注释根因。
"""

import json
import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError

# =====================================================================
# 工具：构造最小 PipelineSession（OSH_HOME 指向 tmp_path）
# =====================================================================

def _make_session(tmp_path, name="phase5-qemu", **attrs):
    # 关键：session 目录基于 OSH_HOME 生成，必须指向 tmp_path，
    # 否则多个测试会共用 CWD 下的 .osh/ 目录造成互相污染。
    os.environ["OSH_HOME"] = str(tmp_path)
    s = PipelineSession(name=name, spec_path=str(tmp_path / "spec.md"))
    s.context = {}
    for k, v in attrs.items():
        setattr(s, k, v)
    return s


# =====================================================================
# QemuTestHandler — 基础行为
# =====================================================================

class TestQemuBasic:
    def test_step_name(self):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        assert QemuTestHandler.step_name == "qemu-run"

    def test_should_skip_no_elf(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        h = QemuTestHandler()
        with mock.patch.object(h, "_find_elf_files", return_value=[]):
            assert h.should_skip(session) is True

    def test_should_skip_with_elf(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        h = QemuTestHandler()
        with mock.patch.object(h, "_find_elf_files", return_value=[Path("a.elf")]):
            assert h.should_skip(session) is False

    def test_pre_check_found(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        h = QemuTestHandler()
        with mock.patch.object(h, "_find_qemu", return_value="/usr/bin/qemu-system-arm"):
            assert h.pre_check(session) is True

    def test_pre_check_missing(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        h = QemuTestHandler()
        with mock.patch.object(h, "_find_qemu", return_value=None):
            assert h.pre_check(session) is False


# =====================================================================
# QemuTestHandler.execute — 成功/失败/产物
# =====================================================================

class TestQemuExecute:
    def test_execute_all_passed(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        h = QemuTestHandler()
        elf = tmp_path / "build" / "app.elf"
        elf.parent.mkdir(parents=True)
        elf.write_bytes(b"\x7fELF")
        with mock.patch.object(h, "_find_qemu", return_value="qemu-system-arm"), \
             mock.patch.object(h, "_find_elf_files", return_value=[elf]), \
             mock.patch.object(h, "_resolve_target",
                               return_value={"qemu_machine": "pc", "qemu_cpu": "max",
                                             "default_timeout": 5}), \
             mock.patch.object(h, "_run_single_test", return_value={
                 "elf": "app.elf", "passed": True, "elapsed": 0.1,
                 "returncode": 0, "error": None,
                 "assertion_failures": [], "log": "TEST PASS", "command": "qemu"}):
            result_path = h.execute(session)
        out = json.loads(Path(result_path).read_text())
        assert out["all_passed"] is True
        assert out["test_count"] == 1
        assert out["passed_count"] == 1
        assert out["summary"] == "All QEMU tests passed"
        assert out["qemu_binary"] == "qemu-system-arm"

    def test_execute_failure_raises(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        h = QemuTestHandler()
        elf = tmp_path / "build" / "app.elf"
        elf.parent.mkdir(parents=True)
        elf.write_bytes(b"\x7fELF")
        with mock.patch.object(h, "_find_qemu", return_value="qemu-system-arm"), \
             mock.patch.object(h, "_find_elf_files", return_value=[elf]), \
             mock.patch.object(h, "_resolve_target", return_value={}), \
             mock.patch.object(h, "_run_single_test", return_value={
                 "elf": "app.elf", "passed": False, "elapsed": 0.1,
                 "returncode": 1, "error": "Test assertions failed",
                 "assertion_failures": ["See log for details"], "log": "TEST FAIL"}), \
             pytest.raises(PipelineStepError) as ei:
            h.execute(session)
        assert "1/1 failed" in str(ei.value)
        # 失败时也写产物
        out = json.loads((session.session_dir / "qemu-test-results.json").read_text())
        assert out["all_passed"] is False
        assert out["failed_count"] == 1
        assert "1 test(s) failed" in out["summary"]

    def test_execute_missing_qemu(self, tmp_path):
        """execute 找不到 qemu 二进制也应产出 not-found 报告并失败。"""
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        h = QemuTestHandler()
        elf = tmp_path / "build" / "app.elf"
        elf.parent.mkdir(parents=True)
        elf.write_bytes(b"\x7fELF")
        with mock.patch.object(h, "_find_qemu", return_value=None), \
             mock.patch.object(h, "_find_elf_files", return_value=[elf]), \
             mock.patch.object(h, "_resolve_target", return_value={}), \
             mock.patch.object(h, "_run_single_test", return_value={
                 "elf": "app.elf", "passed": True, "elapsed": 0.0,
                 "returncode": 0, "error": None,
                 "assertion_failures": [], "log": ""}):
            result_path = h.execute(session)
        out = json.loads(Path(result_path).read_text())
        assert out["qemu_binary"] == "not-found"


# =====================================================================
# QemuTestHandler — 内部工具
# =====================================================================

class TestQemuHelpers:
    def test_find_qemu_via_which(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        h = QemuTestHandler()
        proc = mock.MagicMock(returncode=0, stdout="/usr/bin/qemu-system-arm\n")
        with mock.patch("yuleosh.pipeline.step_handlers.test_qemu.subprocess.run",
                        return_value=proc):
            assert h._find_qemu() == "/usr/bin/qemu-system-arm"

    def test_find_qemu_via_shutil_fallback(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        h = QemuTestHandler()
        proc = mock.MagicMock(returncode=1, stdout="")
        with mock.patch("yuleosh.pipeline.step_handlers.test_qemu.subprocess.run",
                        return_value=proc), \
             mock.patch("shutil.which",
                        return_value="/opt/qemu/qemu-system-arm"):
            assert h._find_qemu() == "/opt/qemu/qemu-system-arm"

    def test_find_qemu_none(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        h = QemuTestHandler()
        proc = mock.MagicMock(returncode=1, stdout="")
        with mock.patch("yuleosh.pipeline.step_handlers.test_qemu.subprocess.run",
                        return_value=proc), \
             mock.patch("shutil.which",
                        return_value=None):
            assert h._find_qemu() is None

    def test_find_qemu_which_exception(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        h = QemuTestHandler()
        with mock.patch("yuleosh.pipeline.step_handlers.test_qemu.subprocess.run",
                        side_effect=FileNotFoundError), \
             mock.patch("shutil.which",
                        return_value=None):
            assert h._find_qemu() is None

    def test_find_elf_files_all_locations(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path, name="phase5-elf")
        project_dir = session.session_dir.parent.parent
        (project_dir / "tests" / "fixtures" / "prebuilt").mkdir(parents=True)
        (project_dir / "build").mkdir(parents=True)
        (project_dir / ".yuleosh" / "pipeline" / "l2").mkdir(parents=True)
        (project_dir / "tests" / "fixtures" / "prebuilt" / "a.elf").write_bytes(b"\x7fELF")
        (project_dir / "build" / "b.elf").write_bytes(b"\x7fELF")
        (project_dir / ".yuleosh" / "pipeline" / "l2" / "c.elf").write_bytes(b"\x7fELF")
        (session.session_dir / "d.elf").write_bytes(b"\x7fELF")
        h = QemuTestHandler()
        found = h._find_elf_files(session)
        assert {p.name for p in found} == {"a.elf", "b.elf", "c.elf", "d.elf"}

    def test_find_elf_files_empty(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path, name="phase5-elf2")
        h = QemuTestHandler()
        assert h._find_elf_files(session) == []

    def test_resolve_target_from_context(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        session.context = {"target": "cortex-m4"}
        h = QemuTestHandler()
        cfg = h._resolve_target(session)
        assert cfg["qemu_cpu"] == "cortex-m4"

    def test_resolve_target_from_arch_attr(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path, arch="arm926")
        h = QemuTestHandler()
        cfg = h._resolve_target(session)
        assert cfg["qemu_cpu"] == "arm926"

    def test_resolve_target_detect_project_fallback(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        h = QemuTestHandler()
        fake_info = {"target": "cortex-m7", "cross_compile": {"target": ""}}
        with mock.patch("yuleosh.project_detection.detect_project",
                        return_value=fake_info):
            cfg = h._resolve_target(session)
        assert cfg["qemu_cpu"] == "max"  # cortex-m7

    def test_resolve_target_detect_project_cross(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        h = QemuTestHandler()
        fake_info = {"target": "", "cross_compile": {"target": "cortex-m3"}}
        with mock.patch("yuleosh.project_detection.detect_project",
                        return_value=fake_info):
            cfg = h._resolve_target(session)
        assert cfg["qemu_cpu"] == "cortex-m3"

    def test_resolve_target_default(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        h = QemuTestHandler()
        with mock.patch("yuleosh.project_detection.detect_project",
                        return_value={"target": "", "cross_compile": {}}):
            cfg = h._resolve_target(session)
        assert cfg["qemu_cpu"] == "cortex-m3"

    def test_resolve_target_import_error(self, tmp_path):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        session = _make_session(tmp_path)
        h = QemuTestHandler()
        with mock.patch("yuleosh.project_detection.detect_project",
                        side_effect=ImportError("no project_detection")):
            cfg = h._resolve_target(session)
        assert cfg["qemu_cpu"] == "cortex-m3"


# =====================================================================
# QemuTestHandler._run_single_test / _evaluate_output
# =====================================================================

class TestQemuSingleTest:
    def _handler(self):
        from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler
        return QemuTestHandler()

    def test_run_success(self, tmp_path):
        h = self._handler()
        elf = tmp_path / "app.elf"
        elf.write_bytes(b"\x7fELF")
        proc = mock.MagicMock(returncode=0, stdout="TEST PASS", stderr="")
        with mock.patch("yuleosh.pipeline.step_handlers.test_qemu.subprocess.run",
                        return_value=proc):
            r = h._run_single_test("qemu", elf, "pc", "max", 10)
        assert r["passed"] is True
        assert r["returncode"] == 0
        assert r["error"] is None
        assert r["command"].startswith("qemu -machine pc")

    def test_run_fail_pattern(self, tmp_path):
        h = self._handler()
        elf = tmp_path / "app.elf"
        elf.write_bytes(b"\x7fELF")
        proc = mock.MagicMock(returncode=1, stdout="TEST FAIL", stderr="")
        with mock.patch("yuleosh.pipeline.step_handlers.test_qemu.subprocess.run",
                        return_value=proc):
            r = h._run_single_test("qemu", elf, "pc", "max", 10)
        assert r["passed"] is False
        assert r["assertion_failures"] == ["See log for details"]

    def test_run_timeout(self, tmp_path):
        h = self._handler()
        elf = tmp_path / "app.elf"
        elf.write_bytes(b"\x7fELF")
        with mock.patch("yuleosh.pipeline.step_handlers.test_qemu.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("qemu", 10)):
            r = h._run_single_test("qemu", elf, "pc", "max", 10)
        assert r["passed"] is False
        assert r["returncode"] == -1
        assert "timed out" in r["error"]

    def test_run_file_not_found(self, tmp_path):
        h = self._handler()
        elf = tmp_path / "app.elf"
        elf.write_bytes(b"\x7fELF")
        with mock.patch("yuleosh.pipeline.step_handlers.test_qemu.subprocess.run",
                        side_effect=FileNotFoundError("no qemu")):
            r = h._run_single_test("qemu", elf, "pc", "max", 10)
        assert r["passed"] is False
        assert "QEMU binary not found" in r["error"]
        assert r["elapsed"] == 0.0

    # _evaluate_output 全分支
    def test_evaluate_fail_pattern_wins(self):
        h = self._handler()
        assert h._evaluate_output("TEST PASS\nHard Fault") is False

    def test_evaluate_pass_pattern(self):
        h = self._handler()
        assert h._evaluate_output("Boot Complete") is True

    def test_evaluate_exit_zero(self):
        h = self._handler()
        assert h._evaluate_output("some log EXIT: 0") is True

    def test_evaluate_exit_nonzero(self):
        h = self._handler()
        assert h._evaluate_output("EXIT: 3") is False

    def test_evaluate_qemu_error(self):
        h = self._handler()
        assert h._evaluate_output("qemu: fatal error in cpu") is False

    def test_evaluate_default_passed(self):
        h = self._handler()
        assert h._evaluate_output("just some output") is True


# =====================================================================
# c_coverage_gate.coverage_gate_step — 主流程
# =====================================================================

class TestCoverageGateStep:
    def test_mock_mode_skipped(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        session = _make_session(tmp_path, name="cg-mock", mock_mode=True)
        result_path = ccg.coverage_gate_step(session)
        out = json.loads(Path(result_path).read_text())
        assert out["skipped"] is True
        assert out["gate_passed"] is False  # 假绿修复：mock 不伪装通过
        assert out["c_fail_under"] == 70

    def _phase_dicts(self):
        return {
            "build": {"success": True, "build_dir": "/tmp/build"},
            "test": {"success": True, "method": "ctest"},
            "gcovr": {"success": True, "method": "gcovr"},
            "gate": {"success": True, "line_rate": 88.0},
        }

    def test_full_pass(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        session = _make_session(tmp_path, name="cg-pass")
        phases = self._phase_dicts()
        with mock.patch.object(ccg, "_phase_build_coverage", return_value=phases["build"]), \
             mock.patch.object(ccg, "_phase_run_tests", return_value=phases["test"]), \
             mock.patch.object(ccg, "_phase_run_gcovr", return_value=phases["gcovr"]), \
             mock.patch.object(ccg, "_phase_check_gate", return_value=phases["gate"]):
            result_path = ccg.coverage_gate_step(session)
        out = json.loads(Path(result_path).read_text())
        assert out["gate_passed"] is True
        assert out["phases"]["gate"]["line_rate"] == 88.0

    def test_build_failure_raises(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        session = _make_session(tmp_path, name="cg-buildfail")
        with mock.patch.object(ccg, "_phase_build_coverage",
                               return_value={"success": False, "error": "Build failed"}), \
             pytest.raises(PipelineStepError) as ei:
            ccg.coverage_gate_step(session)
        assert "build phase failed" in str(ei.value)

    def test_gcovr_failure_raises(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        session = _make_session(tmp_path, name="cg-gcovrfail")
        phases = self._phase_dicts()
        phases["gcovr"] = {"success": False, "error": "gcovr broken"}
        with mock.patch.object(ccg, "_phase_build_coverage", return_value=phases["build"]), \
             mock.patch.object(ccg, "_phase_run_tests", return_value=phases["test"]), \
             mock.patch.object(ccg, "_phase_run_gcovr", return_value=phases["gcovr"]), \
             pytest.raises(PipelineStepError) as ei:
            ccg.coverage_gate_step(session)
        assert "gcovr phase failed" in str(ei.value)

    def test_gate_failure_raises(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        session = _make_session(tmp_path, name="cg-gatefail")
        phases = self._phase_dicts()
        phases["gate"] = {"success": False, "error": "line rate 50 < 70"}
        with mock.patch.object(ccg, "_phase_build_coverage", return_value=phases["build"]), \
             mock.patch.object(ccg, "_phase_run_tests", return_value=phases["test"]), \
             mock.patch.object(ccg, "_phase_run_gcovr", return_value=phases["gcovr"]), \
             mock.patch.object(ccg, "_phase_check_gate", return_value=phases["gate"]), \
             pytest.raises(PipelineStepError) as ei:
            ccg.coverage_gate_step(session)
        assert "line rate 50 < 70" in str(ei.value)

    def test_unexpected_exception_wrapped(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        session = _make_session(tmp_path, name="cg-exc")
        with mock.patch.object(ccg, "_phase_build_coverage",
                               side_effect=RuntimeError("boom")), \
             pytest.raises(PipelineStepError) as ei:
            ccg.coverage_gate_step(session)
        assert "boom" in str(ei.value)


# =====================================================================
# c_coverage_gate — 四个 phase helpers
# =====================================================================

class TestPhaseBuildCoverage:
    def test_existing_coverage_build(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        cov_dir = tmp_path / "cmake-build-coverage"
        (cov_dir / "CMakeFiles").mkdir(parents=True)
        # 需要 gcno 才能让 _coverage_build_stale 判定非 stale —
        # 只有 gcda 时 newest_obj==0 → 误判 stale → 删掉重建 → 真跑 cmake 失败
        (cov_dir / "CMakeFiles" / "a.gcno").write_bytes(b"x")
        (cov_dir / "CMakeFiles" / "a.gcda").write_bytes(b"x")
        results = {}
        with mock.patch.object(ccg, "_get_fail_under", return_value=75):
            r = ccg._phase_build_coverage(str(tmp_path), results)
        assert r["success"] is True
        assert "Existing coverage build found" in r["note"]
        assert results["c_fail_under"] == 75

    def test_existing_plain_build(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        (tmp_path / "build").mkdir()
        (tmp_path / "build" / "b.gcno").write_bytes(b"x")
        results = {}
        r = ccg._phase_build_coverage(str(tmp_path), results)
        assert r["success"] is True
        assert r["note"] == "Using existing build"

    def test_fresh_cmake_build_success(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        results = {}
        cmake = mock.MagicMock(returncode=0)
        build = mock.MagicMock(returncode=0)
        with mock.patch.object(ccg.subprocess, "run",
                               side_effect=[cmake, build]):
            r = ccg._phase_build_coverage(str(tmp_path), results)
        assert r["success"] is True
        assert r["note"] == "Fresh coverage build"

    def test_fresh_cmake_build_fail(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        results = {}
        cmake = mock.MagicMock(returncode=0)
        build = mock.MagicMock(returncode=1, stdout="err", stderr="")
        with mock.patch.object(ccg.subprocess, "run",
                               side_effect=[cmake, build]):
            r = ccg._phase_build_coverage(str(tmp_path), results)
        assert r["success"] is False
        assert "Build failed (rc=1)" in r["error"]

    def test_cmake_timeout(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        results = {}
        with mock.patch.object(ccg.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("cmake", 120)):
            r = ccg._phase_build_coverage(str(tmp_path), results)
        assert r["success"] is False
        assert "timed out" in r["error"]

    def test_cmake_not_found(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        results = {}
        with mock.patch.object(ccg.subprocess, "run",
                               side_effect=FileNotFoundError("cmake")):
            r = ccg._phase_build_coverage(str(tmp_path), results)
        assert r["success"] is False
        assert "CMake not found" in r["error"]

    def test_cmake_generic_exception(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        results = {}
        with mock.patch.object(ccg.subprocess, "run",
                               side_effect=PermissionError("denied")):
            r = ccg._phase_build_coverage(str(tmp_path), results)
        assert r["success"] is False
        assert "denied" in r["error"]


class TestPhaseRunTests:
    def test_no_build_dir(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        r = ccg._phase_run_tests(str(tmp_path), {"phases": {}})
        assert r["success"] is False

    def test_ctest_success(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        (tmp_path / "build").mkdir()
        proc = mock.MagicMock(returncode=0, stdout="ok")
        with mock.patch.object(ccg.subprocess, "run", return_value=proc):
            r = ccg._phase_run_tests(str(tmp_path),
                                     {"phases": {"build": {"build_dir": str(tmp_path / "build")}}})
        assert r["success"] is True
        assert r["method"] == "ctest"

    def test_ctest_partial_with_gcda(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        build = tmp_path / "build"
        build.mkdir()
        (build / "t.gcda").write_bytes(b"x")
        proc = mock.MagicMock(returncode=2, stdout="some failed")
        with mock.patch.object(ccg.subprocess, "run", return_value=proc):
            r = ccg._phase_run_tests(str(tmp_path),
                                     {"phases": {"build": {"build_dir": str(build)}}})
        assert r["success"] is True
        assert r["method"] == "ctest_partial"

    def test_ctest_fail_no_gcda(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        build = tmp_path / "build"
        build.mkdir()
        proc = mock.MagicMock(returncode=2, stdout="", stderr="fail")
        with mock.patch.object(ccg.subprocess, "run", return_value=proc):
            r = ccg._phase_run_tests(str(tmp_path),
                                     {"phases": {"build": {"build_dir": str(build)}}})
        assert r["success"] is False
        assert r["method"] == "ctest"

    def test_ctest_missing_pytest_fallback(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        build = tmp_path / "build"
        build.mkdir()
        pytest_ok = mock.MagicMock(returncode=0, stdout="passed")
        with mock.patch.object(ccg.subprocess, "run",
                               side_effect=[FileNotFoundError("ctest"), pytest_ok]):
            r = ccg._phase_run_tests(str(tmp_path),
                                     {"phases": {"build": {"build_dir": str(build)}}})
        assert r["success"] is True
        assert r["method"] == "pytest"

    def test_ctest_missing_pytest_exception(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        build = tmp_path / "build"
        build.mkdir()
        with mock.patch.object(ccg.subprocess, "run",
                               side_effect=[FileNotFoundError("ctest"),
                                            RuntimeError("py broke")]):
            r = ccg._phase_run_tests(str(tmp_path),
                                     {"phases": {"build": {"build_dir": str(build)}}})
        assert r["success"] is False
        assert r["method"] == "fallback"

    def test_ctest_timeout(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        build = tmp_path / "build"
        build.mkdir()
        with mock.patch.object(ccg.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("ctest", 300)):
            r = ccg._phase_run_tests(str(tmp_path),
                                     {"phases": {"build": {"build_dir": str(build)}}})
        assert r["success"] is False
        assert "timed out" in r["error"]

    def test_ctest_generic_exception(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        build = tmp_path / "build"
        build.mkdir()
        with mock.patch.object(ccg.subprocess, "run",
                               side_effect=OSError("nope")):
            r = ccg._phase_run_tests(str(tmp_path),
                                     {"phases": {"build": {"build_dir": str(build)}}})
        assert r["success"] is False


class TestPhaseRunGcovr:
    def _results(self, build_dir):
        return {"phases": {"build": {"build_dir": build_dir}}}

    def test_no_build_dir_script_success(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        tools = tmp_path / "tools"
        tools.mkdir()
        (tools / "run_c_coverage.sh").write_text("#!/bin/bash\n")
        reports = tmp_path / ".yuleosh" / "reports"
        reports.mkdir(parents=True)
        (reports / "c-coverage.json").write_text("{}")
        proc = mock.MagicMock(returncode=0, stdout="done")
        with mock.patch.object(ccg.subprocess, "run", return_value=proc):
            r = ccg._phase_run_gcovr(str(tmp_path), self._results(""))
        assert r["success"] is True
        assert r["method"].endswith("run_c_coverage.sh")

    def test_no_build_dir_script_fail(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        tools = tmp_path / "tools"
        tools.mkdir()
        (tools / "run_c_coverage.sh").write_text("#!/bin/bash\n")
        with mock.patch.object(ccg.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("bash", 600)):
            r = ccg._phase_run_gcovr(str(tmp_path), self._results(""))
        assert r["success"] is False
        assert "No build dir" in r["error"]

    def test_yuleosh_generator(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        build = tmp_path / "build"
        build.mkdir()
        with mock.patch("yuleosh.ci.gcov_coverage.generate_c_coverage_report",
                        return_value=str(tmp_path / "gen.json")):
            (tmp_path / "gen.json").write_text("{}")
            r = ccg._phase_run_gcovr(str(tmp_path), self._results(str(build)))
        assert r["success"] is True
        assert r["method"] == "yuleosh_gcov_coverage"

    def test_yuleosh_generator_import_error(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        build = tmp_path / "build"
        build.mkdir()
        # 模拟 yuleosh.ci.gcov_coverage 导入失败 → 走 gcovr 分支
        with mock.patch.dict("sys.modules", {"yuleosh.ci.gcov_coverage": None}), \
             mock.patch.object(ccg.subprocess, "run",
                               return_value=mock.MagicMock(returncode=0, stdout="")):
            r = ccg._phase_run_gcovr(str(tmp_path), self._results(str(build)))
        assert r["success"] is False  # gcovr 无输出文件

    def test_gcovr_direct_success(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        build = tmp_path / "build"
        build.mkdir()
        reports = tmp_path / ".yuleosh" / "reports"
        reports.mkdir(parents=True)
        (reports / "c-coverage.json").write_text("x" * 100)  # >50 bytes
        with mock.patch("yuleosh.ci.gcov_coverage.generate_c_coverage_report",
                        return_value=None), \
             mock.patch.object(ccg.subprocess, "run",
                               return_value=mock.MagicMock(returncode=0, stdout="")):
            r = ccg._phase_run_gcovr(str(tmp_path), self._results(str(build)))
        assert r["success"] is True
        assert r["method"] == "gcovr"

    def test_gcovr_broad_retry(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        build = tmp_path / "build"
        build.mkdir()
        reports = tmp_path / ".yuleosh" / "reports"
        reports.mkdir(parents=True)
        (reports / "c-coverage.json").write_text("{}")  # 第一次 <50 bytes
        with mock.patch("yuleosh.ci.gcov_coverage.generate_c_coverage_report",
                        return_value=None), \
             mock.patch.object(ccg.subprocess, "run",
                               return_value=mock.MagicMock(returncode=0, stdout="")):
            r = ccg._phase_run_gcovr(str(tmp_path), self._results(str(build)))
        assert r["success"] is True
        assert r["method"] == "gcovr_broad"

    def test_gcovr_not_installed(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        build = tmp_path / "build"
        build.mkdir()
        with mock.patch("yuleosh.ci.gcov_coverage.generate_c_coverage_report",
                        return_value=None), \
             mock.patch.object(ccg.subprocess, "run",
                               side_effect=FileNotFoundError("gcovr")):
            r = ccg._phase_run_gcovr(str(tmp_path), self._results(str(build)))
        assert r["success"] is False
        assert "gcovr not installed" in r["error"]


class TestPhaseCheckGate:
    def test_gate_script_found(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        tools = tmp_path / "tools"
        tools.mkdir()
        (tools / "check_coverage_gate.py").write_text("print('Lines: 88.5%')\n")
        proc = mock.MagicMock(returncode=0,
                              stdout="Lines: 88.5%\nBranches: 70%\n",
                              stderr="")
        results = {}
        with mock.patch.object(ccg.subprocess, "run", return_value=proc):
            r = ccg._phase_check_gate(str(tmp_path), results)
        assert r["success"] is True
        assert results["line_rate"] == 88.5
        assert results["branch_rate"] == 70.0

    def test_gate_script_fail_parse_rates(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        tools = tmp_path / "tools"
        tools.mkdir()
        (tools / "check_coverage_gate.py").write_text("bad")
        proc = mock.MagicMock(returncode=1, stdout="Lines: 50%", stderr="boom")
        results = {}
        with mock.patch.object(ccg.subprocess, "run", return_value=proc):
            r = ccg._phase_check_gate(str(tmp_path), results)
        assert r["success"] is False
        assert results["line_rate"] == 50.0

    def test_gate_script_exception_then_fallback(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        tools = tmp_path / "tools"
        tools.mkdir()
        (tools / "check_coverage_gate.py").write_text("x")
        results = {}
        with mock.patch.object(ccg.subprocess, "run",
                               side_effect=OSError("denied")), \
             mock.patch("yuleosh.ci.stages.run_c_coverage_check",
                        return_value=True), \
             mock.patch("yuleosh.ci.result.CIResult") as mci:
            inst = mci.return_value
            inst.stages = [{"key": "c-coverage-gate",
                            "detail": "line_rate=92.1 branch_rate=80.0"}]
            r = ccg._phase_check_gate(str(tmp_path), results)
        assert r["success"] is True
        assert r["method"] == "yuleosh_ci_c_coverage_check"
        assert results["line_rate"] == 92.1

    def test_fallback_import_error(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        results = {}
        # stages 为 None 时 from ... import 会抛 ImportError
        with mock.patch.dict("sys.modules", {"yuleosh.ci.stages": None}):
            r = ccg._phase_check_gate(str(tmp_path), results)
        assert r["success"] is False

    def test_fallback_exception(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        results = {}
        with mock.patch("yuleosh.ci.stages.run_c_coverage_check",
                        side_effect=RuntimeError("ci broke")), \
             mock.patch("yuleosh.ci.result.CIResult",
                        return_value=mock.MagicMock(stages=[])):
            r = ccg._phase_check_gate(str(tmp_path), results)
        assert r["success"] is False
        assert "ci broke" in r["error"]


class TestCoverageGateConfig:
    def test_get_fail_under_coverage_style(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        cfg_dir = tmp_path / ".yuleosh"
        cfg_dir.mkdir()
        (cfg_dir / "ci-config.yaml").write_text("coverage:\n  c_fail_under: 65\n")
        assert ccg._get_fail_under(str(tmp_path)) == 65

    def test_get_fail_under_ci_style(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        (tmp_path / ".yuleosh.yaml").write_text(
            "ci:\n  coverage:\n    c_fail_under: 80\n")
        assert ccg._get_fail_under(str(tmp_path)) == 80

    def test_get_fail_under_default(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        assert ccg._get_fail_under(str(tmp_path)) == 70

    def test_get_fail_under_bad_yaml(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        (tmp_path / ".yuleosh.yaml").write_text("coverage: [unclosed\n")
        assert ccg._get_fail_under(str(tmp_path)) == 70

    def test_write_results(self, tmp_path):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as ccg
        session = _make_session(tmp_path, name="cg-write")
        p = ccg._write_results(session, {"gate_passed": True, "x": Path("/tmp/y")})
        data = json.loads(Path(p).read_text())
        assert data["gate_passed"] is True
        assert data["x"] == "/tmp/y"  # default=str 序列化 Path
