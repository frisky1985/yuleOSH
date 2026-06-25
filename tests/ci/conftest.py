#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
pytest configuration for CI tests.
"""


def pytest_configure(config):
    """Register custom markers to suppress pytest warnings."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )
    config.addinivalue_line(
        "markers",
        "e2e: marks tests as end-to-end integration tests",
    )
