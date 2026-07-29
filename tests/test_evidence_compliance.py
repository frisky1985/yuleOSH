#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for evidence/compliance.py — compliance pack, SHA256, manifest, pipeline check.
"""

import json
import os
import tempfile
import time
from pathlib import Path

from yuleosh.evidence.compliance import (
    _compute_sha256,
    _build_manifest_entry,
    _check_pipeline_not_running,
)


class TestEvidenceCompliance:
    """Coverage-boosting tests for evidence/compliance."""

    def test_compute_sha256(self):
        """SHA256 of a known string."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("hello world")
            f.flush()
            path = f.name
        try:
            digest = _compute_sha256(path)
            # SHA256("hello world") = b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9
            assert digest == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        finally:
            os.unlink(path)

    def test_compute_sha256_empty(self):
        """SHA256 of empty file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("")
            f.flush()
            path = f.name
        try:
            digest = _compute_sha256(path)
            assert digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        finally:
            os.unlink(path)

    def test_build_manifest_entry(self):
        """_build_manifest_entry returns correct structure."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            f.flush()
            path = Path(f.name)
        try:
            entry = _build_manifest_entry(path, "test.txt")
            assert entry["path"] == "test.txt"
            assert entry["size_bytes"] > 0
            assert entry["sha256"] == _compute_sha256(str(path))
            assert "mtime" in entry
            assert "mtime_iso" in entry
        finally:
            os.unlink(str(path))

    def test_check_pipeline_not_running_no_session(self):
        """No session directory → pipeline is not running."""
        with tempfile.TemporaryDirectory() as tmp:
            assert _check_pipeline_not_running(tmp) is True

    def test_check_pipeline_not_running_completed(self):
        """Completed session → pipeline is not running."""
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp) / ".osh" / "sessions" / "test-run"
            sessions_dir.mkdir(parents=True)
            session_file = sessions_dir / "session.json"
            session_file.write_text(json.dumps({"status": "completed"}))
            assert _check_pipeline_not_running(tmp) is True

    def test_check_pipeline_not_running_active(self):
        """Running session → pipeline is running."""
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp) / ".osh" / "sessions" / "test-run"
            sessions_dir.mkdir(parents=True)
            session_file = sessions_dir / "session.json"
            session_file.write_text(json.dumps({"status": "running"}))
            assert _check_pipeline_not_running(tmp) is False

    def test_check_pipeline_recent_writes(self):
        """Recent writes in reviews/ are flagged."""
        with tempfile.TemporaryDirectory() as tmp:
            reviews_dir = Path(tmp) / ".osh" / "reviews"
            reviews_dir.mkdir(parents=True)
            recent_file = reviews_dir / "review.json"
            recent_file.write_text("{}")
            # File was just written, pipeline should be considered active
            assert _check_pipeline_not_running(tmp) is False
