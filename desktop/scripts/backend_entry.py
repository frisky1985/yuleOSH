#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""PyInstaller entry point for the bundled yuleOSH backend.

This script is packaged into a standalone executable by
``desktop/scripts/build-backend.js``.  It starts the same HTTP server as
``python -m yuleosh.ui.server`` / ``yuleosh ui``, reading ``OSH_PORT`` and
``OSH_HOME`` from the environment (injected by ServerManager).

@req SHALL-253
"""

import sys


def main() -> int:
    from yuleosh.ui.server import main as server_main

    server_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
