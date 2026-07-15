"""
Extended tests for evidence/aspice_check.py — 0% → ≥60% coverage.

Tests aspice_gap_check, _format_gap_markdown, _format_gap_json,
_add_cli_hints, and the mock-controlled ComplianceChecker interaction.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def mock_checker_report():
    """A realistic compliance report returned by ComplianceChecker.run()."""
    return {
        "generated_at": "2026-07-10T12:00:00",
        "project_dir": "/fake/project",
        "standard": "ASPICE",
        "version": "3.1",
        "summary": {
            "total_bps": 18,
            "passed": 5,
            "partial": 8,
            "failed": 5,
        },
        "swe_sections": {
            "swe.1": {
                "id": "SWE.1",
                "title": "Software Requirements Analysis",
                "description": "Establish software requirements.",
                "base_practices": [
                    {
                        "id": "SWE.1.BP1",
                        "title": "Specify software requirements",
                        "status": "✅",
                        "passed_checks": 3,
                        "failed_checks": 0,
                        "total_checks": 3,
                        "details": [
                            "  ✅ Evidence found: requirements.md",
                            "  ✅ Check: Each SHALL statement",
                            "  ✅ Check: traced to system requirements",
                        ],
                    },
                    {
                        "id": "SWE.1.BP2",
                        "title": "Structure requirements",
                        "status": "⚠️",
                        "passed_checks": 1,
                        "failed_checks": 1,
                        "total_checks": 2,
                        "details": [
                            "  ✅ Evidence found: structured directory",
                            "  ❌ Missing evidence: requirement attributes",
                        ],
                    },
                    {
                        "id": "SWE.1.BP3",
                        "title": "Analyze impact",
                        "status": "❌",
                        "passed_checks": 0,
                        "failed_checks": 2,
                        "total_checks": 2,
                        "details": [
                            "  ❌ Missing: impact-analysis.md",
                            "  ❌ Missing: change impact tracking",
                        ],
                    },
                ],
            },
            "swe.2": {
                "id": "SWE.2",
                "title": "Software Architectural Design",
                "description": "Establish architectural design.",
                "base_practices": [
                    {
                        "id": "SWE.2.BP1",
                        "title": "Design software architecture",
                        "status": "✅",
                        "passed_checks": 4,
                        "failed_checks": 0,
                        "total_checks": 4,
                        "details": [
                            "  ✅ Evidence found: architecture.md",
                            "  ✅ Check: covers all requirements",
                        ],
                    },
                ],
            },
            "swe.4": {
                "id": "SWE.4",
                "title": "Software Unit Verification",
                "description": "Verify software units.",
                "base_practices": [
                    {
                        "id": "SWE.4.BP1",
                        "title": "Develop unit verification",
                        "status": "⚠️",
                        "passed_checks": 2,
                        "failed_checks": 1,
                        "total_checks": 3,
                        "details": [
                            "  ✅ Check: unit tests present",
                            "  ❌ Missing evidence: coverage report",
                            "  ✅ Check: CI execution recorded",
                        ],
                    },
                ],
            },
        },
    }


# ======================================================================
# Tests: aspice_gap_check — markdown output (default)
# ======================================================================

@mock.patch("yuleosh.evidence.aspice_check.ComplianceChecker")
def test_aspice_gap_check_markdown_default(mock_checker_cls, mock_checker_report):
    """GIVEN mock ComplianceChecker WHEN gap check markdown THEN returns formatted report."""
    mock_checker_instance = mock_checker_cls.return_value
    mock_checker_instance.run.return_value = mock_checker_report

    from yuleosh.evidence.aspice_check import aspice_gap_check

    result = aspice_gap_check(project_dir="/fake/project")

    # Should be markdown by default
    assert isinstance(result, str)
    assert "# 🔍 yuleOSH ASPICE Compliance Gap Check" in result
    assert "/fake/project" in result
    assert "ASPICE" in result
    assert "SWE.1" in result
    assert "SWE.1.BP1" in result
    assert "SWE.1.BP2" in result
    assert "SWE.1.BP3" in result
    assert "✅" in result
    assert "⚠️" in result
    assert "❌" in result
    assert "📊 概要" in result
    assert "13" in result  # partial + failed = 13
    assert "快速启动" in result
    assert "yuleosh evidence pack" in result
    assert "yuleosh --help" in result

    # Verify ComplianceChecker was constructed with correct args
    mock_checker_cls.assert_called_once_with(
        project_dir="/fake/project",
        template_path=None,
    )


@mock.patch("yuleosh.evidence.aspice_check.ComplianceChecker")
def test_aspice_gap_check_markdown_all_passed(mock_checker_cls):
    """GIVEN all BPs passed WHEN gap check THEN shows all-ready message."""
    mock_instance = mock_checker_cls.return_value
    all_passed_report = {
        "generated_at": "2026-07-10T12:00:00",
        "project_dir": "/fake/project",
        "standard": "ASPICE",
        "version": "3.1",
        "summary": {"total_bps": 18, "passed": 18, "partial": 0, "failed": 0},
        "swe_sections": {
            "swe.1": {
                "id": "SWE.1",
                "title": "Requirements",
                "description": "",
                "base_practices": [
                    {
                        "id": "SWE.1.BP1",
                        "title": "Specify requirements",
                        "status": "✅",
                        "passed_checks": 3,
                        "failed_checks": 0,
                        "total_checks": 3,
                        "details": ["  ✅ All good"],
                    },
                ],
            },
        },
    }
    mock_instance.run.return_value = all_passed_report

    from yuleosh.evidence.aspice_check import aspice_gap_check

    result = aspice_gap_check(project_dir="/fake/project")
    assert "🎉 **所有 Base Practices 均已就绪！**" in result


@mock.patch("yuleosh.evidence.aspice_check.ComplianceChecker")
def test_aspice_gap_check_json(mock_checker_cls, mock_checker_report):
    """GIVEN output_format='json' WHEN gap check THEN returns JSON string."""
    mock_instance = mock_checker_cls.return_value
    mock_instance.run.return_value = mock_checker_report

    from yuleosh.evidence.aspice_check import aspice_gap_check

    result = aspice_gap_check(
        project_dir="/fake/project",
        output_format="json",
    )

    parsed = json.loads(result)
    assert parsed["project_dir"] == "/fake/project"
    assert parsed["standard"] == "ASPICE"
    assert "summary" in parsed
    assert parsed["summary"]["bps_not_fully_passed"] == 13
    assert "gaps" in parsed
    assert len(parsed["gaps"]) > 0
    # Check gap structure
    gap = parsed["gaps"][0]
    assert "swe_id" in gap
    assert "bp_id" in gap
    assert "status" in gap
    assert "fix_steps" in gap


@mock.patch("yuleosh.evidence.aspice_check.ComplianceChecker")
def test_aspice_gap_check_with_template_path(mock_checker_cls, mock_checker_report):
    """GIVEN template_path WHEN gap check THEN passes to ComplianceChecker."""
    mock_instance = mock_checker_cls.return_value
    mock_instance.run.return_value = mock_checker_report

    from yuleosh.evidence.aspice_check import aspice_gap_check

    result = aspice_gap_check(
        project_dir="/fake/project",
        template_path="/fake/template.yaml",
    )

    mock_checker_cls.assert_called_once_with(
        project_dir="/fake/project",
        template_path=mock.ANY,
    )
    # Verify template_path was converted to Path
    call_kwargs = mock_checker_cls.call_args[1]
    assert str(call_kwargs["template_path"]) == "/fake/template.yaml"


@mock.patch("yuleosh.evidence.aspice_check.ComplianceChecker")
def test_aspice_gap_check_default_project_dir(mock_checker_cls, mock_checker_report):
    """GIVEN no project_dir WHEN gap check THEN uses OSH_HOME or CWD."""
    mock_instance = mock_checker_cls.return_value
    mock_instance.run.return_value = mock_checker_report

    from yuleosh.evidence.aspice_check import aspice_gap_check

    # Simulate OSH_HOME set
    with mock.patch.dict(os.environ, {"OSH_HOME": "/env/osh"}):
        result = aspice_gap_check()
        mock_checker_cls.assert_called_with(
            project_dir="/env/osh",
            template_path=None,
        )

    # Without OSH_HOME — falls back to CWD
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("os.getcwd", return_value="/cwd"):
            result = aspice_gap_check()
            mock_checker_cls.assert_called_with(
                project_dir="/cwd",
                template_path=None,
            )


# ======================================================================
# Tests: _format_gap_markdown — specific sections
# ======================================================================

def test_format_gap_markdown_empty_swe():
    """GIVEN empty swe_sections WHEN format THEN handles gracefully."""
    from yuleosh.evidence.aspice_check import _format_gap_markdown

    report = {
        "project_dir": "/test",
        "standard": "ASPICE",
        "version": "3.1",
        "generated_at": "2026-07-10T12:00:00",
        "summary": {"total_bps": 0, "passed": 0, "partial": 0, "failed": 0},
        "swe_sections": {},
    }
    result = _format_gap_markdown(report, "/test")
    assert isinstance(result, str)
    assert "ASPICE" in result


# ======================================================================
# Tests: _format_gap_json — specific structures
# ======================================================================

def test_format_gap_json_empty():
    """GIVEN report with no gaps WHEN JSON format THEN empty gaps list."""
    from yuleosh.evidence.aspice_check import _format_gap_json

    report = {
        "project_dir": "/test",
        "standard": "ASPICE",
        "version": "3.1",
        "generated_at": "2026-07-10T12:00:00",
        "summary": {"total_bps": 1, "passed": 1, "partial": 0, "failed": 0},
        "swe_sections": {},
    }
    result = json.loads(_format_gap_json(report))
    assert result["summary"]["bps_not_fully_passed"] == 0


# ======================================================================
# Tests: _add_cli_hints
# ======================================================================

def test_add_cli_hints_all_bps():
    """GIVEN known BP IDs WHEN _add_cli_hints THEN adds appropriate CLI hints."""
    from yuleosh.evidence.aspice_check import _add_cli_hints

    known_bps = [
        "SWE.1.BP1", "SWE.1.BP2", "SWE.2.BP1", "SWE.2.BP2",
        "SWE.3.BP1", "SWE.3.BP2", "SWE.4.BP1", "SWE.4.BP2",
        "SWE.4.BP3", "SWE.5.BP1", "SWE.5.BP3", "SWE.6.BP1",
        "SWE.6.BP2", "SWE.6.BP3",
    ]

    for bp_id in known_bps:
        lines = []
        _add_cli_hints(lines, bp_id)
        assert len(lines) >= 1, f"No hints for {bp_id}"
        assert "yuleosh" in lines[0], f"Hint missing yuleosh for {bp_id}"

    # Unknown BP gets the fallback --help hint
    lines = []
    _add_cli_hints(lines, "SWE.99.BP99")
    assert len(lines) >= 1, "Should have default hint"
    assert "yuleosh --help" in lines[-1]


# ======================================================================
# Tests: aspice_gap_check with empty report edge case
# ======================================================================

@mock.patch("yuleosh.evidence.aspice_check.ComplianceChecker")
def test_aspice_gap_check_swe_section_no_bps(mock_checker_cls):
    """GIVEN SWE section with no base practices WHEN gap check THEN handles."""
    mock_instance = mock_checker_cls.return_value
    empty_report = {
        "generated_at": "2026-07-10T12:00:00",
        "project_dir": "/test",
        "standard": "ASPICE",
        "version": "3.1",
        "summary": {"total_bps": 0, "passed": 0, "partial": 0, "failed": 0},
        "swe_sections": {
            "swe.1": {
                "id": "SWE.1",
                "title": "Requirements",
                "description": "",
                "base_practices": [],
            },
        },
    }
    mock_instance.run.return_value = empty_report

    from yuleosh.evidence.aspice_check import aspice_gap_check

    result = aspice_gap_check(project_dir="/test")
    assert "0/0 BP" in result
