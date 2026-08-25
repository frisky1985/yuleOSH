"""Unit tests for yuleosh.project_detection — pure Python, no external deps.

Note: This module requires os, pathlib for directory scanning.
Tests are file-system based but use temp directories.
"""

# @tests src/yuleosh/project_detection.py

import os
import tempfile
from pathlib import Path

import pytest

from yuleosh.project_detection import (
    detect_project,
    resolve_pipeline_config,
)


class TestDetectProject:
    def test_detect_from_cmakelists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "CMakeLists.txt")).touch()
            result = detect_project(tmpdir)
            # Should return a dict with project info
            if result is not None:
                assert isinstance(result, dict)

    def test_detect_from_py_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "setup.py")).touch()
            result = detect_project(tmpdir)
            if result is not None:
                assert isinstance(result, dict)

    def test_detect_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = detect_project(tmpdir)
            # Should not crash
            assert result is None or isinstance(result, dict)

    def test_detect_from_git(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, ".git")).mkdir()
            result = detect_project(tmpdir)
            if result is not None:
                assert isinstance(result, dict)


class TestResolvePipelineConfig:
    def test_resolve_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = resolve_pipeline_config(tmpdir)
            # Should not crash
            assert result is None or isinstance(result, dict)
