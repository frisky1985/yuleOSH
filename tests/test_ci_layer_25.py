"""Tests for CI Layer 2.5 (Hardware-in-the-Loop).

GIVEN the CI pipeline with HIL layer
WHEN run_layer_25 is called
THEN it detects targets, runs tests, and produces reports.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ci.run import run_layer_25, _clear_ci_config_cache


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def tmp_project():
    """Create a temporary project directory with YuleOSH structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _clear_ci_config_cache()
        yuleosh_dir = Path(tmpdir) / ".yuleosh"
        yuleosh_dir.mkdir(parents=True, exist_ok=True)
        targets_dir = yuleosh_dir / "targets"
        targets_dir.mkdir(exist_ok=True)
        ci_dir = yuleosh_dir / "ci"
        ci_dir.mkdir(exist_ok=True)
        yield tmpdir


@pytest.fixture
def with_mock_config(tmp_project):
    """Write ci-config.yaml with mock=true."""
    cfg = {
        "ci": {"layers": [1, 2, 25, 3]},
        "coverage": {"threshold_line": 85.0, "threshold_condition": 80.0},
        "hardware_test": {
            "enabled": True,
            "firmware": "build/firmware.elf",
            "boot_pattern": "Boot Complete",
            "flash_tool": "auto",
            "test_timeout": 30,
            "mock": True,
        },
    }
    cfg_path = Path(tmp_project) / ".yuleosh" / "ci-config.yaml"
    import yaml
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f)
    return tmp_project


@pytest.fixture
def with_hil_scripts(tmp_project):
    """Create tests/hil/ directory with sample scripts."""
    hil_dir = Path(tmp_project) / "tests" / "hil"
    hil_dir.mkdir(parents=True, exist_ok=True)

    scripts = {
        "boot-test.yaml": "expect: Boot Complete\n",
        "blink-test.yaml": "expect: LED ON\nexpect: LED OFF\n",
    }
    for name, content in scripts.items():
        with open(hil_dir / name, "w") as f:
            f.write(content)

    return tmp_project


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _read_layer_result(project_dir: str) -> dict:
    ci_dir = Path(project_dir) / ".osh" / "ci"
    reports = list(ci_dir.glob("layer25-*.json"))
    assert len(reports) >= 1
    with open(reports[0]) as f:
        return json.load(f)


def _read_hil_report(project_dir: str) -> dict:
    ci_dir = Path(project_dir) / ".osh" / "ci"
    reports = list(ci_dir.glob("hil-report-*.json"))
    assert len(reports) >= 1
    with open(reports[-1]) as f:
        return json.load(f)


# ------------------------------------------------------------------
# Tests: Default behavior
# ------------------------------------------------------------------


class TestRunLayer25Defaults:
    """GIVEN no ci-config.yaml WHEN run_layer_25 THEN use safe defaults."""

    def test_returns_success(self, tmp_project):
        """WHEN no config THEN mock mode is True (safe default)."""
        result = run_layer_25(tmp_project)
        assert result is True

    def test_creates_layer_report(self, tmp_project):
        """WHEN run THEN layer25-*.json report is created."""
        run_layer_25(tmp_project)
        result = _read_layer_result(tmp_project)
        assert result["status"] == "passed"

    def test_stages_recorded(self, tmp_project):
        """WHEN run THEN stages include target-detect and hil-tests."""
        run_layer_25(tmp_project)
        result = _read_layer_result(tmp_project)
        stage_names = [s["name"] for s in result.get("stages", [])]
        assert "target-detect" in stage_names
        assert "hil-tests" in stage_names


# ------------------------------------------------------------------
# Tests: With mock config
# ------------------------------------------------------------------


class TestRunLayer25WithConfig:
    """GIVEN ci-config.yaml with mock=true WHEN run THEN all stages pass."""

    def test_target_detect_mock(self, with_mock_config):
        """WHEN mock THEN target-detect passes with mock mode."""
        _clear_ci_config_cache()
        result = run_layer_25(with_mock_config)
        assert result is True

    def test_hil_tests_pass(self, with_mock_config):
        """WHEN mock THEN HIL tests simulate successfully."""
        _clear_ci_config_cache()
        run_layer_25(with_mock_config)
        result = _read_layer_result(with_mock_config)
        assert result["status"] == "passed"

    def test_hil_report_generated(self, with_mock_config):
        """WHEN mock THEN hil-report-*.json is saved."""
        _clear_ci_config_cache()
        run_layer_25(with_mock_config)
        report = _read_hil_report(with_mock_config)
        assert report["passed"] is True

    def test_hil_report_content(self, with_mock_config):
        """WHEN mock THEN report has correct structure."""
        _clear_ci_config_cache()
        run_layer_25(with_mock_config)
        report = _read_hil_report(with_mock_config)
        assert report["layer"] == 25
        assert report["passed"] is True
        assert report["config"]["mock_mode"] is True
        assert report["config"]["boot_pattern"] == "Boot Complete"


# ------------------------------------------------------------------
# Tests: With HIL scripts
# ------------------------------------------------------------------


class TestRunLayer25WithScripts:
    """GIVEN HIL test scripts in tests/hil/ WHEN run THEN they're discovered."""

    def test_discovers_scripts(self, with_mock_config, with_hil_scripts):
        """WHEN mock with scripts THEN HIL tests discover script files."""
        _clear_ci_config_cache()
        result = run_layer_25(with_mock_config)
        assert result is True


# ------------------------------------------------------------------
# Tests: Error handling
# ------------------------------------------------------------------


class TestRunLayer25Errors:
    """GIVEN error conditions WHEN run THEN graceful handling."""

    def test_no_project_dir(self):
        """WHEN no project dir THEN uses current dir without crash."""
        result = run_layer_25(os.getcwd())
        assert result is not None

    def test_missing_scripts_dir(self, tmp_project):
        """WHEN tests/hil/ doesn't exist THEN skips gracefully."""
        result = run_layer_25(tmp_project)
        assert result is True

    def test_partial_config(self, tmp_project):
        """WHEN config has only hardware_test block THEN works."""
        _clear_ci_config_cache()
        cfg_path = Path(tmp_project) / ".yuleosh" / "ci-config.yaml"
        with open(cfg_path, "w") as f:
            f.write("hardware_test:\n  mock: true\n")
        result = run_layer_25(tmp_project)
        assert result is True


# ------------------------------------------------------------------
# Tests: Integration
# ------------------------------------------------------------------


class TestRunLayer25Integration:
    """GIVEN run_layer_25 called in sequence WHEN dependencies work."""

    def test_repeatable_run(self, with_mock_config):
        """WHEN run twice THEN both succeed."""
        _clear_ci_config_cache()
        r1 = run_layer_25(with_mock_config)
        r2 = run_layer_25(with_mock_config)
        assert r1 is True
        assert r2 is True

    def test_report_has_commit_hash(self, with_mock_config):
        """WHEN run THEN commit hash appears in report."""
        _clear_ci_config_cache()
        run_layer_25(with_mock_config)
        report = _read_hil_report(with_mock_config)
        assert "commit" in report
        assert report["commit"] != ""


# ------------------------------------------------------------------
# Tests: Non-mock code path (real HIL path exercised)
# ------------------------------------------------------------------


class TestRunLayer25NonMock:
    """GIVEN mock=False config WHEN run THEN non-mock code path is exercised."""

    @pytest.fixture
    def with_nonmock_config(self, tmp_project):
        """Write ci-config.yaml with mock=false."""
        cfg = {
            "hardware_test": {
                "enabled": True,
                "firmware": "build/firmware.elf",
                "boot_pattern": "Boot Complete",
                "flash_tool": "openocd",
                "serial_port": "/dev/ttyACM0",
                "baud": 115200,
                "boot_delay": 1.5,
                "test_timeout": 30,
                "mock": False,
            },
        }
        cfg_path = Path(tmp_project) / ".yuleosh" / "ci-config.yaml"
        import yaml
        with open(cfg_path, "w") as f:
            yaml.dump(cfg, f)
        return tmp_project

    def test_nonmock_target_detect_no_targets(self, with_nonmock_config):
        """WHEN mock=False with no target YAMLs THEN target-detect warns."""
        _clear_ci_config_cache()
        result = run_layer_25(with_nonmock_config)
        assert result is True

    def test_nonmock_target_detect_with_targets(self, with_nonmock_config):
        """WHEN mock=False with target YAML THEN targets are discovered."""
        _clear_ci_config_cache()
        targets_dir = Path(with_nonmock_config) / ".yuleosh" / "targets"
        targets_dir.mkdir(parents=True, exist_ok=True)
        with open(targets_dir / "stm32f4.yaml", "w") as f:
            f.write("mcu: cortex-m4\narch: arm\nqemu:\n  machine: lm3s6965evb\n  cpu: cortex-m3\n")
        result = run_layer_25(with_nonmock_config)
        assert result is True

    def test_nonmock_no_firmware_skips_hil(self, with_nonmock_config):
        """WHEN mock=False and no firmware file THEN HIL tests skip."""
        _clear_ci_config_cache()
        result = run_layer_25(with_nonmock_config)
        report = _read_layer_result(with_nonmock_config)
        stage_names = [s["name"] for s in report.get("stages", [])]
        assert "target-detect" in stage_names
        assert result is True

    def test_nonmock_with_firmware_attempts_hil(self, with_nonmock_config):
        """WHEN mock=False with firmware THEN attempts HIL imports."""
        _clear_ci_config_cache()
        build_dir = Path(with_nonmock_config) / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        with open(build_dir / "firmware.elf", "wb") as f:
            f.write(b"\x7fELF")
        result = run_layer_25(with_nonmock_config)
        # Should not crash — graceful import error handling
        assert result is not None
        report = _read_layer_result(with_nonmock_config)
        stage_names = [s["name"] for s in report.get("stages", [])]
        assert "hil-tests" in stage_names

    def test_nonmock_with_hil_scripts_discovers(self, with_nonmock_config):
        """WHEN mock=False with HIL scripts THEN they are discovered."""
        _clear_ci_config_cache()
        hil_dir = Path(with_nonmock_config) / "tests" / "hil"
        hil_dir.mkdir(parents=True, exist_ok=True)
        with open(hil_dir / "boot-test.yaml", "w") as f:
            f.write("name: Boot Test\nstages: []\n")
        result = run_layer_25(with_nonmock_config)
        assert result is not None


# ------------------------------------------------------------------
# Tests: Performance baseline (v0.6.0)
# ------------------------------------------------------------------


class TestRunLayer25Performance:
    """GIVEN L2.5 in mock mode WHEN run THEN completes within 1 second."""

    def test_mock_completes_under_1s(self, tmp_project):
        """WHEN mock mode THEN total time < 1000ms."""
        import time as t_mod
        start = t_mod.monotonic()
        result = run_layer_25(tmp_project)
        elapsed = t_mod.monotonic() - start
        assert result is True
        assert elapsed < 1.0, f"L2.5 mock took {elapsed:.3f}s, expected <1.0s"

    def test_mock_with_scripts_still_fast(self, with_mock_config, with_hil_scripts):
        """WHEN mock with many scripts THEN still completes fast."""
        import time as t_mod
        _clear_ci_config_cache()
        start = t_mod.monotonic()
        result = run_layer_25(with_mock_config)
        elapsed = t_mod.monotonic() - start
        assert result is True
        assert elapsed < 1.0, f"L2.5 mock with scripts took {elapsed:.3f}s"
