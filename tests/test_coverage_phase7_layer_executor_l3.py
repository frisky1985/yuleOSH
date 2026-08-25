"""Coverage tests for L3 function group in ci.layers.layer_executor.

Target: src/yuleosh/ci/layers/layer_executor.py L452-727
  - run_layer_25 (L452-528): HIL layer. Branches:
      * project_dir from OSH_HOME vs explicit
      * _get_ci_config raises -> cfg None -> default mock mode / paths
      * hw_cfg.mock True  -> _run_hil_mock_tests
      * hw_cfg.mock False + no scripts dir -> skipped stage
      * hw_cfg.mock False + scripts dir   -> _run_hil_real_tests
      * _detect_hil_target / _record_hil_results False -> all_passed False
      * HIL block raises: strict=True  -> fail + error appended
      * HIL block raises: strict=False -> still passes
      * _generate_layer_report truthy / falsy / raising
  - run_layer2 (L536-609): Integration layer. Branches:
      * _cross_compile_stage / _static_analysis_stage / _integration_test_stage
        returning False -> all_passed False
      * run_misra_check False and raising
      * run_sil_tests False and raising
      * tests/asan present -> info stage; absent -> skipped stage
      * _generate_layer_report truthy / falsy / raising
  - run_layer3 (L617-727): System layer. Branches:
      * e2e dir present: pytest rc 0 / 5 (skip) / other (fail),
        FileNotFoundError, TimeoutExpired, generic Exception
      * e2e dir absent -> skipped
      * pyproject.toml present (tomllib and tomli fallback) / absent
      * evidence pack success (fake module) / import failure / raise
      * _notify truthy (success + raising) / falsy
      * _generate_layer_report truthy (success + raising) / falsy

All subprocess/network/tooling interactions are mocked; no real
subprocesses, no multiprocessing, no time-dependent logic.
"""

# @tests src/yuleosh/ci/coverage_pipeline.py

import builtins
import json
import os
import subprocess
import sys
import types
from types import SimpleNamespace
from unittest import mock

import pytest

from yuleosh.ci.layers import layer_executor as le
from yuleosh.ci.layers.layer_executor import run_layer2, run_layer3, run_layer_25

# ── helpers ────────────────────────────────────────────────────────────


def _hw_cfg(mock_mode: bool = True) -> SimpleNamespace:
    """Fake ``ci-config`` hardware_test section."""
    return SimpleNamespace(
        mock=mock_mode,
        boot_pattern="Boot Complete",
        firmware="build/firmware.elf",
        test_scripts_dir="tests/hil",
    )


def _l3_project(tmp_path, e2e: bool = True, pyproject: bool = True) -> str:
    """Build a minimal Layer-3 project tree in *tmp_path*."""
    if e2e:
        (tmp_path / "tests" / "e2e").mkdir(parents=True)
    if pyproject:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nversion = "1.2.3"\n', encoding="utf-8"
        )
    return str(tmp_path)


def _fake_evidence(raise_on_generate: bool = False) -> types.ModuleType:
    """Fake top-level ``evidence`` package for ``from evidence import pack``."""
    fake_pack = types.ModuleType("evidence.pack")

    def generate(project_dir):
        if raise_on_generate:
            raise RuntimeError("evidence generation exploded")

    fake_pack.generate_evidence = generate
    fake_evidence = types.ModuleType("evidence")
    fake_evidence.pack = fake_pack
    return fake_evidence


# ── run_layer_25 ───────────────────────────────────────────────────────


@pytest.fixture
def l25_mocks():
    """Patch every external call made by run_layer_25 (happy defaults)."""
    with (
        mock.patch("yuleosh.ci.runner.git_commit_hash", return_value="abc123"),
        mock.patch("yuleosh.ci.layers.layer_executor.is_strict", return_value=False),
        mock.patch("yuleosh.ci.layers.layer_executor._get_ci_config") as get_cfg,
        mock.patch(
            "yuleosh.ci.layers.layer_executor._detect_hil_target", return_value=True
        ) as detect,
        mock.patch(
            "yuleosh.ci.layers.layer_executor._run_hil_mock_tests", return_value=[]
        ) as mock_tests,
        mock.patch(
            "yuleosh.ci.layers.layer_executor._run_hil_real_tests", return_value=[]
        ) as real_tests,
        mock.patch(
            "yuleosh.ci.layers.layer_executor._record_hil_results", return_value=True
        ) as record,
        mock.patch(
            "yuleosh.ci.layers.layer_executor._save_hil_report", return_value={}
        ) as save_report,
        mock.patch(
            "yuleosh.ci.runner._save_layer_result", return_value="/tmp/l25.json"
        ) as save_res,
    ):
        yield SimpleNamespace(
            get_cfg=get_cfg,
            detect=detect,
            mock_tests=mock_tests,
            real_tests=real_tests,
            record=record,
            save_report=save_report,
            save_res=save_res,
        )


def test_run_layer25_mock_mode_all_pass(tmp_path, l25_mocks):
    """mock=True -> _run_hil_mock_tests; every stage passes -> True."""
    l25_mocks.get_cfg.return_value = SimpleNamespace(
        hardware_test=_hw_cfg(mock_mode=True)
    )
    with mock.patch(
        "yuleosh.ci.layers.layer_executor._generate_layer_report"
    ) as gen:
        ok = run_layer_25(str(tmp_path))

    assert ok is True
    l25_mocks.mock_tests.assert_called_once()
    l25_mocks.real_tests.assert_not_called()
    l25_mocks.record.assert_called_once()
    l25_mocks.save_report.assert_called_once()
    l25_mocks.save_res.assert_called_once()
    gen.assert_called_once_with(str(tmp_path), 25)


def test_run_layer25_cfg_exception_falls_back_to_defaults(tmp_path, l25_mocks):
    """_get_ci_config raises -> cfg None -> mock defaults (mock=True)."""
    l25_mocks.get_cfg.side_effect = RuntimeError("config boom")
    with mock.patch("yuleosh.ci.layers.layer_executor._generate_layer_report", None):
        ok = run_layer_25(str(tmp_path))

    assert ok is True
    # Defaults: boot pattern, firmware path, scripts dir all from the else branch
    args = l25_mocks.mock_tests.call_args.args
    assert args[3] == "Boot Complete"
    assert args[2].endswith(os.path.join("tests", "hil"))


def test_run_layer25_real_mode_no_scripts_skips(tmp_path, l25_mocks):
    """mock=False and no scripts dir -> hil-tests skipped, still passes."""
    l25_mocks.get_cfg.return_value = SimpleNamespace(
        hardware_test=_hw_cfg(mock_mode=False)
    )
    ok = run_layer_25(str(tmp_path))

    assert ok is True
    l25_mocks.mock_tests.assert_not_called()
    l25_mocks.real_tests.assert_not_called()


def test_run_layer25_real_mode_runs_real_tests(tmp_path, l25_mocks):
    """mock=False with tests/hil present -> _run_hil_real_tests."""
    (tmp_path / "tests" / "hil").mkdir(parents=True)
    l25_mocks.get_cfg.return_value = SimpleNamespace(
        hardware_test=_hw_cfg(mock_mode=False)
    )
    ok = run_layer_25(str(tmp_path))

    assert ok is True
    l25_mocks.real_tests.assert_called_once()
    l25_mocks.mock_tests.assert_not_called()


def test_run_layer25_detect_and_record_fail(tmp_path, l25_mocks, monkeypatch):
    """Target detection + result recording fail -> all_passed False."""
    l25_mocks.detect.return_value = False
    l25_mocks.record.return_value = False
    monkeypatch.setattr(le, "_generate_layer_report", None)

    ok = run_layer_25(str(tmp_path))

    assert ok is False


def test_run_layer25_hil_error_strict(tmp_path, l25_mocks):
    """HIL block raises under strict mode -> fail + error appended."""
    l25_mocks.mock_tests.side_effect = RuntimeError("hil exploded")
    l25_mocks.get_cfg.return_value = SimpleNamespace(
        hardware_test=_hw_cfg(mock_mode=True)
    )
    with mock.patch(
        "yuleosh.ci.layers.layer_executor.is_strict", return_value=True
    ):
        ok = run_layer_25(str(tmp_path))

    assert ok is False


def test_run_layer25_hil_error_non_strict(tmp_path, l25_mocks):
    """HIL block raises but strict=False -> still passes."""
    l25_mocks.mock_tests.side_effect = RuntimeError("hil exploded")
    l25_mocks.get_cfg.return_value = SimpleNamespace(
        hardware_test=_hw_cfg(mock_mode=True)
    )
    ok = run_layer_25(str(tmp_path))

    assert ok is True


def test_run_layer25_report_generation_raises(tmp_path, l25_mocks, caplog):
    """_generate_layer_report raises -> warning logged, result unchanged."""
    with mock.patch(
        "yuleosh.ci.layers.layer_executor._generate_layer_report",
        side_effect=ValueError("report boom"),
    ):
        ok = run_layer_25(str(tmp_path))

    assert ok is True
    assert any(
        "Layer 25 report generation failed" in r.message for r in caplog.records
    )


def test_run_layer25_project_dir_from_env(monkeypatch, tmp_path, l25_mocks):
    """project_dir=None -> falls back to OSH_HOME."""
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    ok = run_layer_25()

    assert ok is True
    assert l25_mocks.get_cfg.call_args.args[0] == str(tmp_path)


# ── run_layer2 ─────────────────────────────────────────────────────────


@pytest.fixture
def l2_mocks():
    """Patch every external call made by run_layer2 (happy defaults)."""
    with (
        mock.patch("yuleosh.ci.runner.git_commit_hash", return_value="abc123"),
        mock.patch(
            "yuleosh.ci.layers.layer_executor.is_misra_fail_fast", return_value=False
        ),
        mock.patch("yuleosh.ci.layers.layer_executor.is_strict", return_value=False),
        mock.patch(
            "yuleosh.ci.layers.layer_executor._find_c_sources",
            return_value=(["a.c"], "cross-src", "build"),
        ),
        mock.patch(
            "yuleosh.ci.layers.layer_executor._cross_compile_stage", return_value=True
        ) as cross,
        mock.patch(
            "yuleosh.ci.layers.layer_executor._static_analysis_stage",
            return_value=True,
        ) as static,
        mock.patch(
            "yuleosh.ci.layers.layer_executor.run_misra_check", return_value=True
        ) as misra,
        mock.patch(
            "yuleosh.ci.layers.layer_executor.run_sil_tests", return_value=True
        ) as sil,
        mock.patch(
            "yuleosh.ci.layers.layer_executor._integration_test_stage",
            return_value=True,
        ) as integ,
        mock.patch(
            "yuleosh.ci.runner._save_layer_result", return_value="/tmp/l2.json"
        ) as save,
    ):
        yield SimpleNamespace(
            cross=cross,
            static=static,
            misra=misra,
            sil=sil,
            integ=integ,
            save=save,
        )


def test_run_layer2_all_pass_with_asan(tmp_path, l2_mocks):
    """All stages pass; tests/asan present -> info stage -> True."""
    (tmp_path / "tests" / "asan").mkdir(parents=True)
    with mock.patch(
        "yuleosh.ci.layers.layer_executor._generate_layer_report"
    ) as gen:
        ok = run_layer2(str(tmp_path))

    assert ok is True
    gen.assert_called_once_with(str(tmp_path), 2)
    l2_mocks.save.assert_called_once()
    ci = l2_mocks.save.call_args.args[1]
    assert ci.status == "passed"


def test_run_layer2_no_asan_skipped(tmp_path, l2_mocks):
    """No tests/asan dir -> memory-safety skipped, still passes."""
    ok = run_layer2(str(tmp_path))

    assert ok is True


def test_run_layer2_stage_failures(tmp_path, l2_mocks, monkeypatch):
    """Every stage reports failure -> all_passed False."""
    l2_mocks.cross.return_value = False
    l2_mocks.static.return_value = False
    l2_mocks.misra.return_value = False
    l2_mocks.sil.return_value = False
    l2_mocks.integ.return_value = False
    monkeypatch.setattr(le, "_generate_layer_report", None)

    ok = run_layer2(str(tmp_path))

    assert ok is False
    ci = l2_mocks.save.call_args.args[1]
    assert ci.status == "failed"
    assert "misra-check (full) failed" in ci.errors
    assert "sil-tests failed" in ci.errors


def test_run_layer2_misra_raises(tmp_path, l2_mocks):
    """run_misra_check raises -> error stage + all_passed False."""
    l2_mocks.misra.side_effect = RuntimeError("misra crash")
    ok = run_layer2(str(tmp_path))

    assert ok is False


def test_run_layer2_sil_raises(tmp_path, l2_mocks):
    """run_sil_tests raises -> error stage + all_passed False."""
    l2_mocks.sil.side_effect = RuntimeError("sil crash")
    ok = run_layer2(str(tmp_path))

    assert ok is False


def test_run_layer2_report_raises(tmp_path, l2_mocks, caplog):
    """_generate_layer_report raises -> warning logged, result unchanged."""
    with mock.patch(
        "yuleosh.ci.layers.layer_executor._generate_layer_report",
        side_effect=ValueError("report boom"),
    ):
        ok = run_layer2(str(tmp_path))

    assert ok is True
    assert any(
        "Layer 2 report generation failed" in r.message for r in caplog.records
    )


def test_run_layer2_project_dir_from_env(monkeypatch, tmp_path, l2_mocks):
    """project_dir=None -> falls back to OSH_HOME."""
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    ok = run_layer2()

    assert ok is True
    assert l2_mocks.cross.call_args.args[0] == str(tmp_path)


# ── run_layer3 ─────────────────────────────────────────────────────────


@pytest.fixture
def l3_mocks():
    """Patch every external call made by run_layer3 (happy defaults)."""
    with (
        mock.patch("yuleosh.ci.runner.git_commit_hash", return_value="deadbeef"),
        mock.patch(
            "yuleosh.ci.layers.layer_executor.subprocess.run"
        ) as sub_run,
        mock.patch("yuleosh.ci.run._notify") as notify,
        mock.patch(
            "yuleosh.ci.layers.layer_executor._generate_layer_report"
        ) as gen,
        mock.patch.dict(
            sys.modules, {"evidence": _fake_evidence()}
        ),
    ):
        yield SimpleNamespace(sub_run=sub_run, notify=notify, gen=gen)


def test_run_layer3_all_pass(tmp_path, l3_mocks):
    """E2E rc=0, pyproject version, evidence ok, notify ok, report ok."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.return_value = SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    with mock.patch.dict(sys.modules, {"evidence": _fake_evidence()}):
        ok = run_layer3(project_dir)

    assert ok is True
    l3_mocks.notify.assert_called_once()
    l3_mocks.gen.assert_called_once_with(project_dir, 3)
    result_file = tmp_path / ".osh" / "ci" / "layer3-deadbeef.json"
    assert result_file.exists()
    data = json.loads(result_file.read_text(encoding="utf-8"))
    assert data["status"] == "passed"
    assert any(s["name"] == "e2e-tests" and s["status"] == "passed" for s in data["stages"])
    assert any(s["name"] == "version-check" and s["status"] == "passed" for s in data["stages"])
    assert any(s["name"] == "evidence-pack" and s["status"] == "passed" for s in data["stages"])


def test_run_layer3_e2e_rc5_skipped(tmp_path, l3_mocks):
    """pytest rc=5 (no tests collected) -> skipped, still passes."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.return_value = SimpleNamespace(
        returncode=5, stdout="", stderr=""
    )
    ok = run_layer3(project_dir)

    assert ok is True


def test_run_layer3_e2e_failed(tmp_path, l3_mocks):
    """pytest rc != 0/5 -> failed stage, all_passed False."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.return_value = SimpleNamespace(
        returncode=1, stdout="boom output", stderr=""
    )
    ok = run_layer3(project_dir)

    assert ok is False


def test_run_layer3_e2e_pytest_missing(tmp_path, l3_mocks):
    """subprocess raises FileNotFoundError -> skipped + blocked, False."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.side_effect = FileNotFoundError("pytest")
    ok = run_layer3(project_dir)

    assert ok is False


def test_run_layer3_e2e_timeout(tmp_path, l3_mocks):
    """subprocess raises TimeoutExpired -> skipped + blocked, False."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.side_effect = subprocess.TimeoutExpired(
        cmd=[sys.executable, "-m", "pytest"], timeout=120
    )
    ok = run_layer3(project_dir)

    assert ok is False


def test_run_layer3_e2e_other_error(tmp_path, l3_mocks):
    """Generic exception from subprocess -> error stage, all_passed False."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.side_effect = OSError("pytest died")
    ok = run_layer3(project_dir)

    assert ok is False


def test_run_layer3_no_e2e_dir(tmp_path, l3_mocks):
    """No tests/e2e dir -> skipped, subprocess never invoked, passes."""
    project_dir = _l3_project(tmp_path, e2e=False)
    ok = run_layer3(project_dir)

    assert ok is True
    l3_mocks.sub_run.assert_not_called()


def test_run_layer3_no_pyproject(tmp_path, l3_mocks):
    """No pyproject.toml -> version-check skipped, still passes."""
    project_dir = _l3_project(tmp_path, pyproject=False)
    l3_mocks.sub_run.return_value = SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    ok = run_layer3(project_dir)

    assert ok is True


def test_run_layer3_tomli_fallback(tmp_path, l3_mocks, monkeypatch):
    """tomllib unavailable -> tomli fallback (faked in sys.modules)."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.return_value = SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tomllib":
            raise ModuleNotFoundError("No module named 'tomllib'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    fake_tomli = types.ModuleType("tomli")
    fake_tomli.load = lambda f: {"project": {"version": "9.9.9"}}
    monkeypatch.setitem(sys.modules, "tomli", fake_tomli)

    ok = run_layer3(project_dir)

    assert ok is True
    result_file = tmp_path / ".osh" / "ci" / "layer3-deadbeef.json"
    data = json.loads(result_file.read_text(encoding="utf-8"))
    assert any(
        s["name"] == "version-check" and "9.9.9" in s["detail"]
        for s in data["stages"]
    )


def test_run_layer3_evidence_generation_raises(tmp_path, l3_mocks):
    """evidence generate_evidence raises -> warning stage, still passes."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.return_value = SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    with mock.patch.dict(
        sys.modules, {"evidence": _fake_evidence(raise_on_generate=True)}
    ):
        ok = run_layer3(project_dir)

    assert ok is True


def test_run_layer3_notify_raises(tmp_path, l3_mocks, caplog):
    """_notify raises -> warning logged, result unchanged."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.return_value = SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    l3_mocks.notify.side_effect = RuntimeError("notify down")
    ok = run_layer3(project_dir)

    assert ok is True
    assert any("Notification failed" in r.message for r in caplog.records)


def test_run_layer3_notify_disabled(tmp_path, l3_mocks, monkeypatch):
    """_notify falsy -> notification skipped."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.return_value = SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    monkeypatch.setattr("yuleosh.ci.run._notify", None)

    ok = run_layer3(project_dir)

    assert ok is True
    l3_mocks.notify.assert_not_called()


def test_run_layer3_report_generator_disabled(tmp_path, l3_mocks, monkeypatch):
    """_generate_layer_report falsy -> report generation skipped."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.return_value = SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    monkeypatch.setattr(le, "_generate_layer_report", None)

    ok = run_layer3(project_dir)

    assert ok is True
    l3_mocks.gen.assert_not_called()


def test_run_layer3_report_raises(tmp_path, l3_mocks, caplog):
    """_generate_layer_report raises -> warning logged, result unchanged."""
    project_dir = _l3_project(tmp_path)
    l3_mocks.sub_run.return_value = SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    l3_mocks.gen.side_effect = ValueError("report boom")
    ok = run_layer3(project_dir)

    assert ok is True
    assert any(
        "Layer 3 report generation failed" in r.message for r in caplog.records
    )


def test_run_layer3_project_dir_from_env(monkeypatch, tmp_path, l3_mocks):
    """project_dir=None -> falls back to OSH_HOME."""
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    _l3_project(tmp_path)
    l3_mocks.sub_run.return_value = SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    ok = run_layer3()

    assert ok is True
    assert l3_mocks.sub_run.call_args.args[0] == [
        sys.executable,
        "-m",
        "pytest",
        str(tmp_path / "tests" / "e2e"),
        "-x",
        "-q",
    ]
