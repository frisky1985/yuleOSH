#!/usr/bin/env python3
"""
yuleOSH CLI entry point — imported via pip entry point 'yuleosh'.

This module is the canonical entry point. It imports the CLI main function
directly from the yuleosh package (yuleosh.cli.main), which works in both
dev (pip install -e .) and production (pip install .) environments.
"""

import sys

from yuleosh.cli.main import main as cli_main


def main():
    """Delegate to the CLI main function."""
    sys.exit(cli_main())


if __name__ == '__main__':
    main()
