#!/usr/bin/env python3
"""
yuleOSH CLI entry point — imported via pip entry point 'yuleosh'.

This module is the canonical entry point. It imports the CLI main function
directly from the yuleosh package (yuleosh.cli.main), which works in both
dev (pip install -e .) and production (pip install .) environments.

Kept as explicit delegation layer (P2-8 evaluated): test suite imports
``yuleosh._entry`` directly (test_entry_smoke, test_cli, test_max_import,
test_methodology_hosting), and ``sys.exit(cli_main())`` provides consistent
exit-code semantics for the pip-generated console_scripts wrapper.
"""

import sys

from yuleosh.cli.main import main as cli_main


def main():
    """Delegate to the CLI main function."""
    sys.exit(cli_main())


if __name__ == '__main__':
    main()
