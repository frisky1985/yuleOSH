"""Unit tests for yuleosh.ci.stages.autosar (v3.4.2 Wave 1 C5).

Covers:
  - run_autosar_build(): missing project, layer selection (mcal/ecual/
    services/all), skip paths, compile success/fail/timeout/compiler missing,
    verbose flag
  - run_autosar_cross_build(): missing project, docker path, missing
    cross-compiler, build success/fail/timeout, unknown target fallback
  - _cross_build_via_docker(): success/fail/timeout/docker missing
  - run_autosar_misra_check(): missing project, cppcheck fallback, layer
    skips, violation parsing, fail_on_warning, timeout
  - _run_misra_fallback(): skip paths, success, exception
  - run_autosar_full_ci(): orchestration + verdicts
  - run_arxml_compliance_check(): no arxml skip, parse pass/fail
  - STAGES_REGISTRY + register_autosar_stages()
"""

# @tests src/yuleosh/ci/run.py

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.ci.stages import autosar as A


def _make_layer(project: Path, layer: str, n_files: int = 2) -> None:
    src = project / "src" / layer
    src.mkdir(parents=True)
    for i in range(n_files):
        (src / f"mod{i}.c").write_text("int f(void){return 0;}\n")


@pytest.fixture
def project(tmp_path):
    return tmp_path


# ── run_autosar_build ─────────────────────────────────────────────────

class TestRunAutosarBuild:
    def test_missing_project(self, tmp_path):
        """GIVEN missing project dir WHEN build THEN error dict."""
        r = A.run_autosar_build(str(tmp_path / "ghost"))
        assert r["status"] == "error"
        assert "not found" in r["message"]

    def test_all_layers_default(self, project):
        """GIVEN project with all layers WHEN build THEN all built."""
        for layer in ("mcal", "ecual", "services"):
            _make_layer(project, layer, 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which",
                        return_value="/usr/bin/gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
                r = A.run_autosar_build(str(project))
        assert r["_meta"]["all_pass"] is True
        for layer in ("mcal", "ecual", "services"):
            assert r[layer]["status"] == "pass"
        assert m_run.call_count == 3

    def test_mcal_only(self, project):
        """GIVEN mcal_only WHEN build THEN only mcal built."""
        for layer in ("mcal", "ecual"):
            _make_layer(project, layer, 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which",
                        return_value="gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
                r = A.run_autosar_build(str(project), mcal_only=True)
        assert "mcal" in r and "ecual" not in r
        assert r["_meta"]["layers_requested"] == ["mcal"]

    def test_missing_layer_skipped(self, project):
        """GIVEN layer without source dir WHEN build THEN skip result."""
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
                r = A.run_autosar_build(str(project))
        assert r["mcal"]["status"] == "skip"
        assert "Source dir not found" in r["mcal"]["reason"]

    def test_layer_without_sources_skipped(self, project):
        """GIVEN layer dir without .c/.cpp files WHEN build THEN skip."""
        (project / "src" / "mcal").mkdir(parents=True)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
                r = A.run_autosar_build(str(project))
        assert r["mcal"]["status"] == "skip"
        assert "No .c/.cpp files found" in r["mcal"]["reason"]

    def test_compile_failure(self, project):
        """GIVEN compiler errors WHEN build THEN layer fail + error details."""
        _make_layer(project, "mcal", 2)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(
                    returncode=1, stdout="error", stderr="syntax error")
                r = A.run_autosar_build(str(project))
        assert r["mcal"]["status"] == "fail"
        assert r["mcal"]["failed"] == 2
        assert r["_meta"]["all_pass"] is False

    def test_cpp_sources_collected(self, project):
        """GIVEN layer with .cpp sources WHEN build THEN g++ used + compiled.

        C++ 泛化 (2026-08-21 A1 dogfood): rglob 只收 .c 会漏 .cpp。
        """
        src = project / "src" / "mcal"
        src.mkdir(parents=True)
        (src / "motor.cpp").write_text("namespace motor { int f(){return 0;} }\n")
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="g++"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
                r = A.run_autosar_build(str(project))
        assert r["mcal"]["status"] == "pass"
        assert r["mcal"]["compiled"] == 1
        # g++ 编译命令必须带 -std=c++17
        call_args = m_run.call_args[0][0]
        assert "g++" in call_args[0]
        assert "-std=c++17" in call_args

    def test_compile_warning_ok(self, project):
        """GIVEN warnings but rc=0 WHEN build THEN pass + warning counted."""
        _make_layer(project, "mcal", 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(
                    returncode=0, stdout="", stderr="warning: unused")
                r = A.run_autosar_build(str(project))
        assert r["mcal"]["status"] == "pass"
        assert r["mcal"]["warnings"] == 1

    def test_compile_timeout(self, project):
        """GIVEN compiler timeout WHEN build THEN error recorded."""
        _make_layer(project, "mcal", 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run",
                            side_effect=subprocess.TimeoutExpired("gcc", 120)):
                r = A.run_autosar_build(str(project))
        assert r["mcal"]["status"] == "fail"
        assert r["mcal"]["failed"] == 1

    def test_compiler_missing(self, project):
        """GIVEN compiler not found WHEN build THEN fail result returned."""
        _make_layer(project, "mcal", 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run",
                            side_effect=FileNotFoundError):
                r = A.run_autosar_build(str(project))
        assert r["mcal"]["status"] == "fail"
        assert "Compiler not found" in r["mcal"]["error"]

    def test_verbose_flag(self, project):
        """GIVEN verbose=True WHEN build THEN -v appended to cmd."""
        _make_layer(project, "mcal", 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
                A.run_autosar_build(str(project), verbose=True)
        cmd = m_run.call_args[0][0]
        assert "-v" in cmd

    def test_custom_build_dir(self, project):
        """GIVEN custom build_dir WHEN build THEN out dir honored."""
        _make_layer(project, "mcal", 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
                A.run_autosar_build(str(project), build_dir="out_x")
        assert (project / "out_x" / "mcal").is_dir()


# ── run_autosar_cross_build ───────────────────────────────────────────

class TestRunAutosarCrossBuild:
    def test_missing_project(self, tmp_path):
        """GIVEN missing project WHEN cross-build THEN error dict."""
        r = A.run_autosar_cross_build(str(tmp_path / "ghost"))
        assert r["status"] == "error"

    def test_docker_path(self, project):
        """GIVEN docker_image WHEN cross-build THEN docker helper used."""
        with mock.patch("yuleosh.ci.stages.autosar._cross_build_via_docker") as m_dock:
            m_dock.return_value = {"status": "pass"}
            r = A.run_autosar_cross_build(str(project), docker_image="arm:latest")
        assert r["status"] == "pass"
        m_dock.assert_called_once()

    def test_cross_compiler_missing(self, project):
        """GIVEN no cross compiler WHEN cross-build THEN fail result."""
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value=None):
            r = A.run_autosar_cross_build(str(project))
        assert r["status"] == "fail"
        assert "not found" in r["error"]

    def test_cross_build_success(self, project):
        """GIVEN cross compiler + sources WHEN cross-build THEN pass."""
        for layer in ("mcal", "ecual", "services"):
            _make_layer(project, layer, 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which",
                        return_value="/toolchain/arm-none-eabi-gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
                r = A.run_autosar_cross_build(str(project))
        assert r["_meta"]["all_pass"] is True
        assert r["_meta"]["target"] == "arm-cortex-m7"
        assert all(r[layer]["status"] == "pass" for layer in ("mcal", "ecual", "services"))

    def test_cross_build_failure(self, project):
        """GIVEN compile errors WHEN cross-build THEN layer fail."""
        _make_layer(project, "mcal", 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which",
                        return_value="arm-none-eabi-gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(
                    returncode=1, stdout="", stderr="boom")
                r = A.run_autosar_cross_build(str(project))
        assert r["mcal"]["status"] == "fail"
        assert r["_meta"]["all_pass"] is False

    def test_cross_build_timeout(self, project):
        """GIVEN compiler timeout WHEN cross-build THEN error."""
        _make_layer(project, "mcal", 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which",
                        return_value="arm-none-eabi-gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run",
                            side_effect=subprocess.TimeoutExpired("gcc", 120)):
                r = A.run_autosar_cross_build(str(project))
        assert r["mcal"]["status"] == "fail"
        assert r["mcal"]["errors"] == 1

    def test_unknown_target_falls_back(self, project):
        """GIVEN unknown target WHEN cross-build THEN cortex-m7 flags used."""
        _make_layer(project, "mcal", 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which",
                        return_value="arm-none-eabi-gcc"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
                r = A.run_autosar_cross_build(str(project), target="weird-cpu")
        assert "-mcpu=cortex-m7" in m_run.call_args[0][0]
        assert r["_meta"]["target"] == "weird-cpu"


# ── _cross_build_via_docker ───────────────────────────────────────────

class TestCrossBuildViaDocker:
    def test_docker_success(self, project):
        """GIVEN docker run succeeds WHEN helper THEN pass result."""
        with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
            m_run.return_value = mock.MagicMock(returncode=0, stdout="done", stderr="")
            r = A._cross_build_via_docker(str(project), "arm-cortex-m7",
                                          ["-mcpu=cortex-m7"], "build_arm", "img")
        assert r["status"] == "pass"
        assert r["output"] == "done"
        assert "docker" in m_run.call_args[0][0]

    def test_docker_failure(self, project):
        """GIVEN docker run rc!=0 WHEN helper THEN fail result."""
        with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
            m_run.return_value = mock.MagicMock(returncode=1, stdout="", stderr="no space")
            r = A._cross_build_via_docker(str(project), "t", [], "b", "img")
        assert r["status"] == "fail"
        assert r["errors"] == "no space"

    def test_docker_timeout(self, project):
        """GIVEN docker timeout WHEN helper THEN timeout error."""
        with mock.patch("yuleosh.ci.stages.autosar.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("docker", 300)):
            r = A._cross_build_via_docker(str(project), "t", [], "b", "img")
        assert r["status"] == "fail"
        assert "timed out" in r["error"]

    def test_docker_missing(self, project):
        """GIVEN docker binary missing WHEN helper THEN error."""
        with mock.patch("yuleosh.ci.stages.autosar.subprocess.run",
                        side_effect=FileNotFoundError):
            r = A._cross_build_via_docker(str(project), "t", [], "b", "img")
        assert r["status"] == "fail"
        assert "Docker not found" in r["error"]


# ── run_autosar_misra_check ───────────────────────────────────────────

class TestRunAutosarMisraCheck:
    def test_missing_project(self, tmp_path):
        """GIVEN missing project WHEN misra THEN error dict."""
        r = A.run_autosar_misra_check(str(tmp_path / "ghost"))
        assert r["status"] == "error"

    def test_fallback_when_no_cppcheck(self, project):
        """GIVEN cppcheck unavailable WHEN misra THEN fallback used."""
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value=None):
            with mock.patch("yuleosh.ci.stages.autosar._run_misra_fallback") as m_fb:
                m_fb.return_value = {"status": "warn"}
                r = A.run_autosar_misra_check(str(project))
        assert r == {"status": "warn"}
        m_fb.assert_called_once()

    def test_layer_skip(self, project):
        """GIVEN missing layer sources WHEN misra THEN skip results."""
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="/bin/cppcheck"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
                r = A.run_autosar_misra_check(str(project))
        assert r["mcal"]["status"] == "skip"
        assert r["_meta"]["layers_checked"] == []

    def test_parses_violations(self, project):
        """GIVEN cppcheck output WHEN misra THEN violations counted."""
        _make_layer(project, "mcal", 1)
        out = ("[error] misra violation Rule 10.1\n"
               "warning: misra style issue\n"
               "some other line\n")
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="/bin/cppcheck"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout=out, stderr="")
                r = A.run_autosar_misra_check(str(project))
        assert r["mcal"]["status"] == "fail"  # 1 error → layer fails
        assert r["mcal"]["misra_errors"] == 1
        assert r["mcal"]["misra_warnings"] == 1
        assert r["_meta"]["total_errors"] == 1

    def test_fail_on_warning(self, project):
        """GIVEN fail_on_warning + warnings WHEN misra THEN layer fails."""
        _make_layer(project, "mcal", 1)
        out = "warning: misra thing\n"
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="/bin/cppcheck"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout=out, stderr="")
                r = A.run_autosar_misra_check(str(project), fail_on_warning=True)
        assert r["mcal"]["status"] == "fail"

    def test_custom_cppcheck_args(self, project):
        """GIVEN cppcheck_args WHEN misra THEN appended to cmd."""
        _make_layer(project, "mcal", 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="/bin/cppcheck"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run") as m_run:
                m_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
                A.run_autosar_misra_check(str(project), cppcheck_args=["--xml"])
        assert "--xml" in m_run.call_args[0][0]

    def test_timeout(self, project):
        """GIVEN cppcheck timeout WHEN misra THEN layer fail error."""
        _make_layer(project, "mcal", 1)
        with mock.patch("yuleosh.ci.stages.autosar.shutil.which", return_value="/bin/cppcheck"):
            with mock.patch("yuleosh.ci.stages.autosar.subprocess.run",
                            side_effect=subprocess.TimeoutExpired("cppcheck", 300)):
                r = A.run_autosar_misra_check(str(project))
        assert r["mcal"]["status"] == "fail"
        assert "timed out" in r["mcal"]["error"]


# ── _run_misra_fallback ───────────────────────────────────────────────

class TestMisraFallback:
    def test_skip_missing_layer(self, project):
        """GIVEN missing layer WHEN fallback THEN skip."""
        r = A._run_misra_fallback(str(project), ["mcal"])
        assert r["mcal"]["status"] == "skip"

    def test_success(self, project):
        """GIVEN sources + built-in misra pass WHEN fallback THEN pass."""
        _make_layer(project, "mcal", 1)
        fake_ci = mock.MagicMock()
        with mock.patch("yuleosh.ci.result.CIResult", return_value=fake_ci):
            with mock.patch("yuleosh.ci.stages.review.run_misra_check",
                            return_value=True):
                r = A._run_misra_fallback(str(project), ["mcal"])
        assert r["mcal"]["status"] == "pass"
        assert r["_meta"]["tool"] == "yuleosh-builtin-misra"

    def test_exception_warn(self, project):
        """GIVEN built-in misra raises WHEN fallback THEN warn result."""
        _make_layer(project, "mcal", 1)
        with mock.patch("yuleosh.ci.result.CIResult",
                        side_effect=RuntimeError("broken")):
            r = A._run_misra_fallback(str(project), ["mcal"])
        assert r["mcal"]["status"] == "warn"
        assert "broken" in r["mcal"]["error"]


# ── run_autosar_full_ci ───────────────────────────────────────────────

class TestRunAutosarFullCi:
    def test_all_pass(self, project):
        """GIVEN all stages pass WHEN full_ci THEN l3 pass."""
        with mock.patch("yuleosh.ci.stages.autosar.run_autosar_build",
                        return_value={"_meta": {"all_pass": True}}):
            with mock.patch("yuleosh.ci.stages.autosar.run_autosar_cross_build",
                            return_value={"_meta": {"all_pass": True}}):
                with mock.patch("yuleosh.ci.stages.autosar.run_autosar_misra_check",
                                return_value={"_meta": {"total_errors": 0}}):
                    r = A.run_autosar_full_ci(str(project))
        assert r["layer3_system_verification"]["status"] == "pass"
        assert r["_meta"]["all_pass"] is True

    def test_misra_failure(self, project):
        """GIVEN misra errors WHEN full_ci THEN l3 fail."""
        with mock.patch("yuleosh.ci.stages.autosar.run_autosar_build",
                        return_value={"_meta": {"all_pass": True}}):
            with mock.patch("yuleosh.ci.stages.autosar.run_autosar_cross_build",
                            return_value={"_meta": {"all_pass": True}}):
                with mock.patch("yuleosh.ci.stages.autosar.run_autosar_misra_check",
                                return_value={"_meta": {"total_errors": 3}}):
                    r = A.run_autosar_full_ci(str(project))
        assert r["layer3_system_verification"]["status"] == "fail"
        assert r["_meta"]["all_pass"] is False


# ── run_arxml_compliance_check ────────────────────────────────────────

class TestArxmlCompliance:
    def test_no_arxml_skip(self, project):
        """GIVEN no ARXML files WHEN compliance THEN skip result."""
        r = A.run_arxml_compliance_check(str(project))
        assert r["status"] == "skip"
        assert "No ARXML files found" in r["reason"]

    def test_parse_pass(self, project):
        """GIVEN ARXML parses WHEN compliance THEN pass with counts."""
        arxml = project / "cfg.arxml"
        arxml.write_text("<AUTOSAR/>")
        fake_parser = mock.MagicMock()
        swc = mock.MagicMock()
        swc.short_name = "BrakeSWC"
        swc.ports = [1, 2]
        swc.runnables = [1]
        fake_parser.parse_swc.return_value = [swc]
        with mock.patch("yuleosh.autosar.parser.ARXMLParser", return_value=fake_parser):
            r = A.run_arxml_compliance_check(str(project), arxml_path=str(arxml))
        assert r["status"] == "pass"
        details = r["details"]["cfg.arxml"]
        assert details["swc_count"] == 1
        assert details["ports_total"] == 2
        assert details["runnables_total"] == 1

    def test_parse_error(self, project):
        """GIVEN ARXML parse failure WHEN compliance THEN fail detail."""
        arxml = project / "bad.arxml"
        arxml.write_text("<>")
        fake_parser = mock.MagicMock()
        fake_parser.parse_swc.side_effect = RuntimeError("bad xml")
        with mock.patch("yuleosh.autosar.parser.ARXMLParser", return_value=fake_parser):
            r = A.run_arxml_compliance_check(str(project), arxml_path=str(arxml))
        assert r["details"]["bad.arxml"]["status"] == "fail"
        assert r["details"]["bad.arxml"]["error"] == "bad xml"


# ── Registry ──────────────────────────────────────────────────────────

class TestRegistry:
    def test_registry_contents(self):
        """GIVEN STAGES_REGISTRY THEN all 5 stages registered."""
        assert set(A.STAGES_REGISTRY) == {
            "autosar-build", "autosar-cross-compile", "autosar-misra-check",
            "autosar-full-ci", "arxml-compliance",
        }

    def test_register_merges(self):
        """GIVEN existing registry WHEN register THEN stages merged in-place."""
        existing = {"other": lambda: None}
        result = A.register_autosar_stages(existing)
        assert result is existing
        assert "autosar-build" in result
        assert "other" in result
