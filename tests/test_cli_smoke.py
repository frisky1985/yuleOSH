"""Smoke tests for yuleosh.cli — stats and template."""
import os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestCli:
    def test_cli_init(self):
        import yuleosh.cli
        assert yuleosh.cli is not None

    def test_stats_functions(self):
        from yuleosh.cli.stats import (
            cmd_stats, compute_spec_coverage,
            count_ci_runs, count_pipeline_runs,
            count_source_lines, count_tests
        )
        assert callable(cmd_stats)
        assert callable(compute_spec_coverage)

    def test_template_functions(self):
        from yuleosh.cli.template import cmd_template_init
        assert callable(cmd_template_init)
