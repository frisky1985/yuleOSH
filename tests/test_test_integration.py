#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Regression tests for the integration-test step's C/CMake fallback.

These mock subprocess.run so they don't require a real cmake/ctest toolchain.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.step_handlers.test_integration import step_integration_test


def _make_project(tmp_path: Path, with_cmake: bool = True) -> Path:
    if with_cmake:
        (tmp_path / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.13)\nproject(t C)\n"
        )
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.md").write_text("# Spec\n- WHEN x THEN y\n")
    return tmp_path


def test_integration_test_configures_cmake_when_no_build_dir(monkeypatch, tmp_path):
    """C/CMake project (CMakeLists.txt) with no usable build dir: the step
    must cmake -S -B configure a fresh build/, then run ctest -L integration,
    and report passed (not skipped)."""
    proj = _make_project(tmp_path, with_cmake=True)
    monkeypatch.setenv("OSH_HOME", str(proj))

    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(("CALL", list(cmd) if cmd else cmd))
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        r = R()
        if len(cmd) >= 2 and cmd[:2] == ["cmake", "-S"]:
            bd = cmd[cmd.index("-B") + 1]
            Path(bd).mkdir(parents=True, exist_ok=True)
            (Path(bd) / "CTestTestfile.cmake").write_text("")
            calls.append(("configure", list(cmd)))
        elif cmd[0] == "cmake" and len(cmd) > 1 and cmd[1] == "--build":
            calls.append(("build", list(cmd)))
        elif cmd[0] == "ctest":
            r.stdout = "100% tests passed, 0 tests failed out of 1"
            calls.append(("ctest", list(cmd)))
        elif "pytest" in cmd:
            r.returncode = 5
            r.stdout = "no tests ran"
            calls.append(("pytest", list(cmd)))
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)

    s = PipelineSession(name="t", spec_path=proj / "docs" / "spec.md", run_id="rt")
    out = step_integration_test(s)
    d = json.load(open(out))

    assert d["status"] == "passed", d
    assert d["test_runner"] == "ctest-integration", d["test_runner"]
    kinds = [c[0] for c in calls]
    assert "configure" in kinds, calls
    assert "ctest" in kinds, calls
    ctest_call = [c for c in calls if c[0] == "ctest"][0][1]
    assert "-L" in ctest_call and "integration" in ctest_call, ctest_call


def test_integration_test_skips_without_cmake_and_no_build(monkeypatch, tmp_path):
    """Python-style project: no CMakeLists.txt and no build dir → must stay
    skipped, never try to invoke cmake."""
    proj = _make_project(tmp_path, with_cmake=False)
    monkeypatch.setenv("OSH_HOME", str(proj))

    cmake_called = []

    def fake_run(cmd, *args, **kwargs):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        r = R()
        if "pytest" in cmd:
            r.returncode = 5
            r.stdout = "no tests ran"
        if cmd and cmd[0] == "cmake":
            cmake_called.append(list(cmd))
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)

    s = PipelineSession(name="t", spec_path=proj / "docs" / "spec.md", run_id="rt")
    out = step_integration_test(s)
    d = json.load(open(out))

    assert d["status"] == "skipped", d
    assert cmake_called == [], "cmake must not be invoked for non-C projects"
