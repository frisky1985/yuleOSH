"""Tests for yuleosh.pipeline.prompts — prompt builders."""

import pytest

from yuleosh.pipeline.prompts import (
    get_prompt_versions,
    get_prompt_version,
    build_super_analysis_prompt,
    build_prd_prompt,
    build_architecture_prompt,
    build_development_prompt,
    build_test_planning_prompt,
)


# ------------------------------------------------------------------
# Version helpers
# ------------------------------------------------------------------

def test_get_prompt_versions():
    """GIVEN all prompts WHEN getting versions THEN returns non-empty dict."""
    versions = get_prompt_versions()
    assert isinstance(versions, dict)
    assert len(versions) > 0


def test_get_prompt_version_valid():
    """GIVEN valid step key WHEN getting version THEN returns string."""
    versions = get_prompt_versions()
    if versions:
        key = list(versions.keys())[0]
        version = get_prompt_version(key)
        assert isinstance(version, str)
        assert len(version) > 0


def test_get_prompt_version_invalid():
    """GIVEN invalid step key WHEN getting version THEN returns fallback version."""
    version = get_prompt_version("nonexistent")
    assert isinstance(version, str)


# ------------------------------------------------------------------
# Prompt builders — all return (system, user) tuples
# ------------------------------------------------------------------

def test_build_super_analysis_prompt():
    """GIVEN spec WHEN building super analysis prompt THEN returns tuple."""
    result = build_super_analysis_prompt("# Spec", "spec.md", [{"id": "R1"}], ["scenario 1"])
    assert isinstance(result, tuple) and len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], str)


def test_build_prd_prompt():
    """GIVEN spec WHEN building PRD prompt THEN returns tuple."""
    result = build_prd_prompt("# Spec", "spec.md", [{"id": "R1", "text": "Do X"}], ["scenario 1"])
    assert isinstance(result, tuple) and len(result) == 2


def test_build_architecture_prompt():
    """GIVEN spec WHEN building architecture prompt THEN returns tuple."""
    result = build_architecture_prompt(
        "# Spec", "spec.md", "session-1",
        ["src/"], ["main.py"],
        ["Python"], "src/main.py\nsrc/utils.py",
        ["main.py", "utils.py"],
    )
    assert isinstance(result, tuple) and len(result) == 2


def test_build_development_prompt():
    """GIVEN spec WHEN building development prompt THEN returns tuple."""
    result = build_development_prompt("# Spec", "spec.md")
    assert isinstance(result, tuple) and len(result) == 2


def test_build_test_planning_prompt():
    """GIVEN spec WHEN building test planning prompt THEN returns tuple."""
    result = build_test_planning_prompt("# Spec", [{"id": "REQ-1", "text": "Do X"}])
    assert isinstance(result, tuple) and len(result) == 2


# ------------------------------------------------------------------
# All prompts produce meaningful content
# ------------------------------------------------------------------

def test_all_prompts_different():
    """GIVEN multiple prompt builders WHEN called THEN each produces different output."""
    r1 = build_super_analysis_prompt("# S", "s.md", [{"id": "R1"}], ["sc1"])
    r2 = build_prd_prompt("# S", "s.md", [{"id": "R1", "text": "Do X"}], ["sc1"])
    # Both should be different
    assert r1 != r2
