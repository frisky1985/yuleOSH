"""Smoke tests for yuleosh._entry — CLI entry point.
Tests import and basic main() delegation.
All external calls mocked.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestEntry:
    def test_import(self):
        from yuleosh._entry import main
        assert callable(main)

    def test_main_calls_cli(self):
        from yuleosh._entry import main
        # yuleosh_cli is imported inside main(), so we patch at the module level
        with patch("yuleosh_cli.main") as mock_cli_main:
            try:
                main()
            except SystemExit:
                pass
            mock_cli_main.assert_called_once()
