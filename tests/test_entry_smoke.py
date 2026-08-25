"""Smoke tests for yuleosh._entry — CLI entry point.
Tests import and basic main() delegation.
All external calls mocked.
"""

# @tests src/yuleosh/_entry.py

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


class TestEntry:
    def test_import(self):
        from yuleosh._entry import main
        assert callable(main)

    def test_main_calls_cli(self):
        from yuleosh._entry import main
        # v3.4.0: entry delegates via the module-level ``cli_main`` binding
        with patch("yuleosh._entry.cli_main") as mock_cli_main:
            with patch("sys.exit") as mock_exit:
                main()
                mock_cli_main.assert_called_once()
                mock_exit.assert_called_once_with(mock_cli_main.return_value)
