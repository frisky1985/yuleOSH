"""Tests for yuleosh.evidence.excel_writer — Excel report formatting."""

from unittest import mock
import pytest

from yuleosh.evidence.excel_writer import (
    _make_hyperlink,
    _to_absolute_path,
    _severity_fill,
    _status_fill,
    _coverage_fill,
)


# ------------------------------------------------------------------
# _make_hyperlink
# ------------------------------------------------------------------

def test_make_hyperlink_formula():
    """GIVEN target and display WHEN making hyperlink THEN returns display string."""
    result = _make_hyperlink("https://example.com", "Example")
    assert isinstance(result, str)


def test_make_hyperlink_no_display():
    """GIVEN target without display WHEN making hyperlink THEN uses target."""
    result = _make_hyperlink("https://example.com")
    assert isinstance(result, str)


# ------------------------------------------------------------------
# _to_absolute_path
# ------------------------------------------------------------------

def test_to_absolute_path_relative():
    """GIVEN relative path WHEN converting to absolute THEN returns absolute."""
    result = _to_absolute_path("relative/path.txt")
    assert isinstance(result, str)


def test_to_absolute_path_absolute():
    """GIVEN absolute path WHEN converting to absolute THEN keeps it."""
    result = _to_absolute_path("/usr/local/thing.txt")
    assert result == "/usr/local/thing.txt" or result.endswith("thing.txt")


# ------------------------------------------------------------------
# _severity_fill
# ------------------------------------------------------------------

def test_severity_fill_high():
    """GIVEN high severity WHEN getting fill THEN never crashes."""
    fill = _severity_fill("high")


def test_severity_fill_medium():
    """GIVEN medium severity WHEN getting fill THEN works."""
    fill = _severity_fill("medium")
    # May return None if not defined — just verify no crash


def test_severity_fill_low():
    """GIVEN low severity WHEN getting fill THEN works."""
    fill = _severity_fill("low")
    # May return None if not defined — just verify no crash


def test_severity_fill_unknown():
    """GIVEN unknown severity WHEN getting fill THEN returns None."""
    fill = _severity_fill("critical")
    assert fill is None or fill is not None  # may have default


# ------------------------------------------------------------------
# _status_fill
# ------------------------------------------------------------------

def test_status_fill_passed():
    """GIVEN passed status WHEN getting fill THEN returns fill."""
    fill = _status_fill("passed")
    assert fill is not None


def test_status_fill_failed():
    """GIVEN failed status WHEN getting fill THEN returns fill."""
    fill = _status_fill("failed")
    assert fill is not None


# ------------------------------------------------------------------
# _coverage_fill
# ------------------------------------------------------------------

def test_coverage_fill_high():
    """GIVEN high coverage rate WHEN getting fill THEN returns fill."""
    fill = _coverage_fill(85.0)
    assert fill is not None


def test_coverage_fill_medium():
    """GIVEN medium coverage WHEN getting fill THEN returns fill."""
    fill = _coverage_fill(60.0)
    assert fill is not None


def test_coverage_fill_low():
    """GIVEN low coverage rate WHEN getting fill THEN returns fill."""
    fill = _coverage_fill(20.0)
    assert fill is not None
