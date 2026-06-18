"""Tests for KPI baseline management."""
import os, sys, json, tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

@pytest.mark.skip(reason="Requires project context with CI history")
def test_misra_trend_append():
    """Test MISRA trend append_entry works."""
    from yuleosh.ci.misra_trend import append_entry, show_trend
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        Path(".yuleosh/reports").mkdir(parents=True)
        entry = append_entry(project_dir=tmp, total_violations=5, required=2, advisory=3)
        assert entry is not None
        result = show_trend(project_dir=tmp, lines=5)
        assert "5" in result


@pytest.mark.skip(reason="Requires coverage history data")
def test_coverage_trend_show():
    """Test coverage trend show_coverage_trend exists."""
    from yuleosh.ci.coverage_trend import show_coverage_trend
    result = show_coverage_trend(lines=3)
    assert result is not None


def test_kpi_cli_functions_exist():
    """Test KPI CLI functions are importable."""
    from yuleosh_cli import cmd_kpi_status, cmd_kpi_baseline_save, cmd_kpi_baseline_compare
    assert callable(cmd_kpi_status)
    assert callable(cmd_kpi_baseline_save)
    assert callable(cmd_kpi_baseline_compare)


def test_kpi_baseline_save_and_compare():
    """Test baseline save creates file and compare reads it."""
    from yuleosh_cli import cmd_kpi_baseline_save, cmd_kpi_baseline_compare
    import io
    from contextlib import redirect_stdout
    
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        Path(".yuleosh/reports").mkdir(parents=True)
        
        # Save
        f = io.StringIO()
        with redirect_stdout(f):
            cmd_kpi_baseline_save()
        output = f.getvalue()
        assert "baseline saved" in output.lower()
        
        # Verify file exists
        baselines = list(Path(tmp).glob(".yuleosh/reports/kpi-baseline-*.json"))
        assert len(baselines) > 0
        
        # Compare
        f2 = io.StringIO()
        with redirect_stdout(f2):
            cmd_kpi_baseline_compare()
        output2 = f2.getvalue()
        assert "baseline" in output2.lower()
