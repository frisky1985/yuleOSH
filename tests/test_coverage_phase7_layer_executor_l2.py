"""Coverage tests — phase 7, L2: layer_executor Layer-1 function group.

Targets (src/yuleosh/ci/layers/layer_executor.py L168-444):
  - _run_embedded_misra_check
  - _run_go_layer1
  - _run_python_layer1
  - _run_layer1_impl
  - run_layer1

All subprocess/signal/git interactions are mocked; no real time deps.
"""

import os
import signal
import subprocess
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

from yuleosh.ci.layers import layer_executor as le
from yuleosh.ci.layers.layer_config import _LayerTimeout
from yuleosh.ci.result import CIResult

# Stage names as they appear in _run_layer1_impl -> the module-level func
# bound in layer_executor's namespace (patched at that path).
_C_STAGE_FUNCS = {
    "methodology-gate": "run_methodology_gate",
    "yaml-validation": "run_yaml_validation",
    "spec-validation": "run_spec_validation",
    "architecture-review": "run_architecture_review",
    "requirements-trace": "run_requirements_trace",
    "plan-lint": "run_plan_lint",
    "docsync-gate": "run_docsync_gate",
    "clang-tidy": "run_clang_tidy",
    "unit-tests": "run_unit_tests",
    "coverage": "run_coverage_check",
    "coverage-regression": "run_coverage_regression",
    "c-coverage": "run_c_coverage",
    "c-coverage-gate": "run_c_coverage_check",
}


@contextmanager
def _patch_c_stages(overrides=None):
    """Patch every C-path stage handler to return True (or override)."""
    overrides = overrides or {}
    patchers: dict[str, mock._patch] = {
        name: mock.patch(
            f"yuleosh.ci.layers.layer_executor.{func}", return_value=True
        )
        for name, func in _C_STAGE_FUNCS.items()
    }
    # The misra stage entry is a lambda calling run_misra_check(pd, ci, mode="delta")
    patchers["misra-check"] = mock.patch(
        "yuleosh.ci.layers.layer_executor.run_misra_check", return_value=True
    )
    mocks: dict[str, mock.MagicMock] = {}
    for name, p in patchers.items():
        mocks[name] = p.start()
    try:
        for name, val in overrides.items():
            if isinstance(val, Exception):
                mocks[name].side_effect = val
            else:
                mocks[name].return_value = val
        yield
    finally:
        for p in reversed(list(patchers.values())):
            p.stop()


@contextmanager
def _patch_go_layer1(build=True, vet=True, test=True, misra=True, vet_raises=None):
    """Patch the three Go handlers + the MISRA gate used by _run_go_layer1."""
    with (
        mock.patch("yuleosh.ci.layers.layer_executor._run_go_build", return_value=build),
        mock.patch(
            "yuleosh.ci.layers.layer_executor._run_go_vet",
            side_effect=vet_raises,
            return_value=vet,
        ),
        mock.patch("yuleosh.ci.layers.layer_executor._run_go_test", return_value=test),
        mock.patch(
            "yuleosh.ci.layers.layer_executor.run_misra_check", return_value=misra
        ),
    ):
        yield


def _patch_run_layer1_env(impl=True, impl_exc=None, notify=None, report=None):
    """Common patches for the public run_layer1() wrapper."""
    if impl_exc is not None:
        impl_mock = mock.patch(
            "yuleosh.ci.layers.layer_executor._run_layer1_impl", side_effect=impl_exc
        )
    else:
        impl_mock = mock.patch(
            "yuleosh.ci.layers.layer_executor._run_layer1_impl", return_value=impl
        )
    return [
        mock.patch("yuleosh.ci.runner.git_commit_hash", return_value="abc1234"),
        impl_mock,
        mock.patch("yuleosh.ci.run._notify", notify),
        mock.patch("yuleosh.ci.layers.layer_executor._generate_layer_report", report),
    ]


@contextmanager
def _run_layer1_context(impl=True, impl_exc=None, notify=None, report=None):
    patchers = _patch_run_layer1_env(impl, impl_exc, notify, report)
    for p in patchers:
        p.start()
    try:
        yield
    finally:
        for p in reversed(patchers):
            p.stop()


# ══════════════════════════════════════════════════════════════════════
# _run_embedded_misra_check (L168-185)
# ══════════════════════════════════════════════════════════════════════


class TestRunEmbeddedMisraCheck:
    def test_passed(self):
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor.run_misra_check", return_value=True
        ) as m:
            assert le._run_embedded_misra_check("/tmp/x", ci) is True
        m.assert_called_once_with("/tmp/x", ci, mode="delta")
        assert ci.errors == []

    def test_failed(self):
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor.run_misra_check", return_value=False
        ):
            assert le._run_embedded_misra_check("/tmp/x", ci) is False
        assert ci.errors == ["misra-check failed"]

    def test_exception(self):
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor.run_misra_check",
            side_effect=RuntimeError("boom"),
        ):
            assert le._run_embedded_misra_check("/tmp/x", ci) is False
        assert ci.stages[-1] == {
            "name": "misra-check",
            "status": "error",
            "detail": "boom",
            "timestamp": ci.stages[-1]["timestamp"],
        }
        assert ci.errors == ["misra-check: boom"]


# ══════════════════════════════════════════════════════════════════════
# _run_go_layer1 (L188-216)
# ══════════════════════════════════════════════════════════════════════


class TestRunGoLayer1:
    def test_all_pass(self):
        ci = CIResult(1, "abc")
        with _patch_go_layer1():
            assert le._run_go_layer1("/tmp/x", ci, 30) is True
        assert ci.errors == []
        assert ci.stages == []

    def test_build_failed(self):
        ci = CIResult(1, "abc")
        with _patch_go_layer1(build=False):
            assert le._run_go_layer1("/tmp/x", ci, 30) is False
        assert "go-build failed" in ci.errors

    def test_handler_exception(self):
        ci = CIResult(1, "abc")
        with _patch_go_layer1(vet_raises=RuntimeError("vet boom")):
            assert le._run_go_layer1("/tmp/x", ci, 30) is False
        assert "go-vet: vet boom" in ci.errors
        assert ci.stages[-1]["name"] == "go-vet"
        assert ci.stages[-1]["status"] == "error"

    def test_misra_failed(self):
        ci = CIResult(1, "abc")
        with _patch_go_layer1(misra=False):
            assert le._run_go_layer1("/tmp/x", ci, 30) is False
        assert ci.errors == ["misra-check failed"]


# ══════════════════════════════════════════════════════════════════════
# _run_python_layer1 (L224-258)
# ══════════════════════════════════════════════════════════════════════


class TestRunPythonLayer1:
    def _patch_run(self, exc=None, rc=0):
        if exc is not None:
            return mock.patch(
                "yuleosh.ci.layers.layer_executor.subprocess.run", side_effect=exc
            )
        result = SimpleNamespace(returncode=rc, stdout="out" * 200, stderr="err")
        return mock.patch(
            "yuleosh.ci.layers.layer_executor.subprocess.run", return_value=result
        )

    def test_pytest_pass(self):
        ci = CIResult(1, "abc")
        with self._patch_run(rc=0), mock.patch(
            "yuleosh.ci.layers.layer_executor.run_misra_check", return_value=True
        ):
            assert le._run_python_layer1("/tmp/x", ci, 30) is True
        assert ci.stages[-1]["status"] == "passed"
        assert ci.errors == []

    def test_pytest_failed(self):
        ci = CIResult(1, "abc")
        with self._patch_run(rc=3), mock.patch(
            "yuleosh.ci.layers.layer_executor.run_misra_check", return_value=True
        ):
            assert le._run_python_layer1("/tmp/x", ci, 30) is False
        assert ci.stages[-1]["status"] == "failed"
        assert ci.stages[-1]["detail"] == ("out" * 200)[:500]

    def test_pytest_not_installed(self):
        ci = CIResult(1, "abc")
        with self._patch_run(exc=FileNotFoundError()), mock.patch(
            "yuleosh.ci.layers.layer_executor.run_misra_check", return_value=True
        ):
            assert le._run_python_layer1("/tmp/x", ci, 30) is True
        assert ci.stages[-1]["status"] == "skipped"
        assert "pytest not installed" in ci.stages[-1]["detail"]

    def test_pytest_timeout(self):
        ci = CIResult(1, "abc")
        exc = subprocess.TimeoutExpired(cmd=["python", "-m", "pytest"], timeout=30)
        with self._patch_run(exc=exc), mock.patch(
            "yuleosh.ci.layers.layer_executor.run_misra_check", return_value=True
        ):
            assert le._run_python_layer1("/tmp/x", ci, 30) is True
        assert ci.stages[-1]["status"] == "skipped"
        assert "pytest timed out" in ci.stages[-1]["detail"]

    def test_misra_failed(self):
        ci = CIResult(1, "abc")
        with self._patch_run(rc=0), mock.patch(
            "yuleosh.ci.layers.layer_executor.run_misra_check", return_value=False
        ):
            assert le._run_python_layer1("/tmp/x", ci, 30) is False
        assert ci.errors == ["misra-check failed"]


# ══════════════════════════════════════════════════════════════════════
# _run_layer1_impl (L266-326)
# ══════════════════════════════════════════════════════════════════════


class TestRunLayer1Impl:
    def test_go_dispatch(self, tmp_path):
        (tmp_path / "go.mod").write_text("module demo\n")
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor._run_go_layer1", return_value=True
        ) as m:
            assert le._run_layer1_impl(str(tmp_path), ci, 30) is True
        m.assert_called_once_with(str(tmp_path), ci, 30)

    def test_mixed_dispatch(self, tmp_path):
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor._detect_project_language",
            return_value="mixed",
        ), mock.patch(
            "yuleosh.ci.layers.layer_executor._run_go_layer1", return_value=False
        ) as m:
            assert le._run_layer1_impl(str(tmp_path), ci, 30) is False
        m.assert_called_once_with(str(tmp_path), ci, 30)

    def test_python_dispatch(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor._run_python_layer1", return_value=False
        ) as m:
            assert le._run_layer1_impl(str(tmp_path), ci, 30) is False
        m.assert_called_once_with(str(tmp_path), ci, 30)

    def test_c_all_pass(self, tmp_path):
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor._get_ci_config",
            return_value=mock.MagicMock(),
        ), mock.patch(
            "yuleosh.ci.layers.layer_executor.validate_misra_profiles",
            return_value=[],
        ), _patch_c_stages():
            assert le._run_layer1_impl(str(tmp_path), ci, 30) is True
        assert ci.errors == []
        assert len(ci.stages) == 0  # stages only recorded on failure/error

    def test_c_profile_error_aborts(self, tmp_path):
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor._get_ci_config",
            return_value=mock.MagicMock(),
        ), mock.patch(
            "yuleosh.ci.layers.layer_executor.validate_misra_profiles",
            return_value=["❌ active_profile 'x' not found. Available profiles: y"],
        ):
            assert le._run_layer1_impl(str(tmp_path), ci, 30) is False
        assert ci.stages[-1]["status"] == "failed"
        assert "active_profile" in ci.errors[0]

    def test_c_profile_warning_proceeds(self, tmp_path):
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor._get_ci_config",
            return_value=mock.MagicMock(),
        ), mock.patch(
            "yuleosh.ci.layers.layer_executor.validate_misra_profiles",
            return_value=["⚠️  active_profile 'x' has no block_on rules"],
        ), _patch_c_stages():
            assert le._run_layer1_impl(str(tmp_path), ci, 30) is True
        assert ci.stages[0]["status"] == "warning"
        assert ci.errors == ["⚠️  active_profile 'x' has no block_on rules"]

    def test_c_profile_validation_exception(self, tmp_path):
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor._get_ci_config",
            side_effect=FileNotFoundError("no config"),
        ), _patch_c_stages():
            assert le._run_layer1_impl(str(tmp_path), ci, 30) is True
        assert ci.errors == []

    def test_c_stage_failure(self, tmp_path):
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor._get_ci_config",
            return_value=mock.MagicMock(),
        ), mock.patch(
            "yuleosh.ci.layers.layer_executor.validate_misra_profiles",
            return_value=[],
        ), _patch_c_stages(overrides={"methodology-gate": False}):
            assert le._run_layer1_impl(str(tmp_path), ci, 30) is False
        assert "methodology-gate failed" in ci.errors

    def test_c_stage_exception(self, tmp_path):
        ci = CIResult(1, "abc")
        with mock.patch(
            "yuleosh.ci.layers.layer_executor._get_ci_config",
            return_value=mock.MagicMock(),
        ), mock.patch(
            "yuleosh.ci.layers.layer_executor.validate_misra_profiles",
            return_value=[],
        ), _patch_c_stages(overrides={"clang-tidy": RuntimeError("tidy boom")}):
            assert le._run_layer1_impl(str(tmp_path), ci, 30) is False
        assert "clang-tidy: tidy boom" in ci.errors
        assert ci.stages[-1]["status"] == "error"


# ══════════════════════════════════════════════════════════════════════
# run_layer1 (L329-444) — public wrapper
# ══════════════════════════════════════════════════════════════════════


class TestRunLayer1Public:
    def test_ok_with_notify_and_report(self, tmp_path):
        notify = mock.Mock()
        report = mock.Mock()
        with _run_layer1_context(notify=notify, report=report):
            result = le.run_layer1(project_dir=str(tmp_path), timeout=5)
        assert result is True
        notify.assert_called_once()
        assert notify.call_args.kwargs["layer"] == 1
        assert notify.call_args.kwargs["status"] == "passed"
        report.assert_called_once_with(str(tmp_path), 1)
        assert (tmp_path / ".osh" / "ci" / "layer1-abc1234.json").exists()

    def test_defaults_from_env(self, tmp_path):
        with mock.patch.dict(
            os.environ,
            {"OSH_HOME": str(tmp_path), "CI_LAYER1_TIMEOUT": "123"},
            clear=False,
        ), _run_layer1_context():
            result = le.run_layer1()
        assert result is True
        assert (tmp_path / ".osh" / "ci" / "layer1-abc1234.json").exists()

    def test_invalid_timeout_env_falls_back_to_30(self, tmp_path):
        with mock.patch.dict(
            os.environ,
            {"OSH_HOME": str(tmp_path), "CI_LAYER1_TIMEOUT": "not-a-number"},
            clear=False,
        ), _run_layer1_context():
            result = le.run_layer1()
        assert result is True

    def test_timeout_via_alarm_handler(self, tmp_path):
        captured = {}

        def fake_signal(signum, handler):
            captured["handler"] = handler
            return signal.SIG_DFL

        def fake_alarm(seconds):
            if seconds:
                captured["handler"](signal.SIGALRM, None)
            return 0

        with mock.patch(
            "yuleosh.ci.layers.layer_executor.signal.signal", side_effect=fake_signal
        ), mock.patch(
            "yuleosh.ci.layers.layer_executor.signal.alarm", side_effect=fake_alarm
        ), _run_layer1_context():
            result = le.run_layer1(project_dir=str(tmp_path), timeout=5)
        assert result is False

    def test_impl_raises_layer_timeout(self, tmp_path):
        with _run_layer1_context(impl_exc=_LayerTimeout("boom")):
            result = le.run_layer1(project_dir=str(tmp_path), timeout=5)
        assert result is False

    def test_impl_raises_generic_exception(self, tmp_path):
        with _run_layer1_context(impl_exc=RuntimeError("boom")):
            result = le.run_layer1(project_dir=str(tmp_path), timeout=5)
        assert result is False

    def test_alarm_setup_failure(self, tmp_path):
        with mock.patch(
            "yuleosh.ci.layers.layer_executor.signal.alarm",
            side_effect=OverflowError("alarm too big"),
        ), _run_layer1_context():
            result = le.run_layer1(project_dir=str(tmp_path), timeout=5)
        assert result is False

    def test_notify_failure_is_swallowed(self, tmp_path):
        notify = mock.Mock(side_effect=RuntimeError("notify down"))
        with _run_layer1_context(notify=notify):
            result = le.run_layer1(project_dir=str(tmp_path), timeout=5)
        assert result is True

    def test_report_failure_is_swallowed(self, tmp_path):
        report = mock.Mock(side_effect=RuntimeError("report down"))
        with _run_layer1_context(report=report):
            result = le.run_layer1(project_dir=str(tmp_path), timeout=5)
        assert result is True
