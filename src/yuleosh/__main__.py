#!/usr/bin/env python3
"""yuleOSH `python3 -m yuleosh` entry point.

Enables `python3 -m yuleosh ...` as an alias for the installed `yuleosh`
CLI (same behaviour as the console-script entry point `yuleosh` defined in
pyproject.toml [project.scripts]).
"""

import sys

from yuleosh.cli.main import main as cli_main


if __name__ == "__main__":
    sys.exit(cli_main())
