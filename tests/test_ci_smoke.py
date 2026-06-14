"""Smoke tests for yuleosh.ci — CI config and runner."""
import os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestCiConfig:
    def test_import(self):
        from yuleosh.ci.config import CiConfig, load_ci_config
        assert CiConfig is not None

    def test_ci_config_defaults(self):
        from yuleosh.ci.config import CiConfig
        cfg = CiConfig()
        assert cfg is not None

    def test_load_ci_config_not_found(self):
        from yuleosh.ci.config import load_ci_config
        with patch("pathlib.Path.exists", return_value=False):
            cfg = load_ci_config("/nonexistent")
            assert cfg is not None

    def test_coverage_config(self):
        from yuleosh.ci.config import CoverageConfig
        cfg = CoverageConfig()
        assert cfg is not None

    def test_hardware_test_config(self):
        from yuleosh.ci.config import HardwareTestConfig
        cfg = HardwareTestConfig()
        assert cfg is not None


class TestCiInit:
    def test_import(self):
        import yuleosh.ci
        assert hasattr(yuleosh.ci, "__init__")
