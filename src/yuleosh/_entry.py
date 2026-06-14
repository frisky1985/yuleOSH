#!/usr/bin/env python3
"""
yuleOSH CLI entry point — imported via pip entry point 'yuleosh-cli'.

This module bridges between the pip-installed entry point and the
existing yuleosh_cli.py at the project root.
"""

import sys
import os


def main():
    """Locate yuleosh_cli.py and delegate to it."""
    # Locate this file's parent directory (src/yuleosh/), then go up 2 levels to project root
    src_yuleosh_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(src_yuleosh_dir, '..', '..'))

    # Also try parent of src/ which is the project root
    src_dir = os.path.dirname(src_yuleosh_dir)  # src/
    project_root_alt = os.path.dirname(src_dir)  # project root

    # Add both possible roots to sys.path
    for p in [project_root, project_root_alt]:
        if p not in sys.path:
            sys.path.insert(0, p)

    from yuleosh_cli import main as cli_main
    sys.exit(cli_main())


if __name__ == '__main__':
    main()
