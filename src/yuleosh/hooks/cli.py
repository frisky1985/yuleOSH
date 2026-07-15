# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""CLI integration for installing yuleOSH Git hooks.

Usage:
    yuleosh hook install    — Install pre-commit and post-merge hooks into .git/hooks/
    yuleosh hook run pre-commit  — Run the pre-commit hook directly
    yuleosh hook run post-merge  — Run the post-merge hook directly
"""

import argparse
import os
import stat
import sys
from pathlib import Path

# ── Hook templates ──────────────────────────────────────────────────────
# These are small shell scripts that delegate to the Python implementation.

PRE_COMMIT_TEMPLATE = """#!/bin/sh
# yuleOSH pre-commit hook — auto-generated, do not edit manually
# Installed by `yuleosh hook install`

set -e

# Find yuleosh CLI
if command -v yuleosh >/dev/null 2>&1; then
    exec yuleosh hook run pre-commit
elif [ -f "$(dirname "$0")/../../.yuleosh/venv/bin/yuleosh" ]; then
    exec "$(dirname "$0")/../../.yuleosh/venv/bin/yuleosh" hook run pre-commit
else
    echo "yuleOSH: yuleosh CLI not found — skipping pre-commit hook"
    exit 0
fi
"""

POST_MERGE_TEMPLATE = """#!/bin/sh
# yuleOSH post-merge hook — auto-generated, do not edit manually
# Installed by `yuleosh hook install`

set -e

if command -v yuleosh >/dev/null 2>&1; then
    exec yuleosh hook run post-merge
elif [ -f "$(dirname "$0")/../../.yuleosh/venv/bin/yuleosh" ]; then
    exec "$(dirname "$0")/../../.yuleosh/venv/bin/yuleosh" hook run post-merge
else
    echo "yuleOSH: yuleosh CLI not found — skipping post-merge hook"
    exit 0
fi
"""


def _find_git_hooks_dir(cwd: str | None = None) -> Path | None:
    """Locate .git/hooks/ by walking up from *cwd*."""
    if cwd is None:
        cwd = os.getcwd()
    root = Path(cwd).resolve()
    for ancestor in [root] + list(root.parents):
        git_dir = ancestor / ".git"
        if git_dir.is_dir():
            hooks_dir = git_dir / "hooks"
            if not hooks_dir.exists():
                hooks_dir.mkdir(parents=True, exist_ok=True)
            return hooks_dir
    return None


def _install_hook(hooks_dir: Path, name: str, template: str) -> bool:
    """Write *template* to hooks_dir/name and make executable. Returns True if written."""
    hook_path = hooks_dir / name
    if hook_path.exists():
        try:
            content = hook_path.read_text(encoding="utf-8", errors="replace")
            if "yuleOSH" in content:
                return False  # Already installed
        except OSError:
            pass

    hook_path.write_text(template)
    mode = hook_path.stat().st_mode if hook_path.exists() else 0o644
    hook_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return True


def cmd_hook_install(cwd: str | None = None) -> int:
    """Install yuleOSH hooks into .git/hooks/."""
    if cwd is None:
        cwd = os.getcwd()

    hooks_dir = _find_git_hooks_dir(cwd)
    if hooks_dir is None:
        print("❌ No .git/ directory found. Are you in a Git repository?", file=sys.stderr)
        return 1

    changed = 0
    if _install_hook(hooks_dir, "pre-commit", PRE_COMMIT_TEMPLATE):
        print(f"✅ Installed pre-commit hook: {hooks_dir / 'pre-commit'}")
        changed += 1
    else:
        print("ℹ️  pre-commit hook already installed (yuleOSH).")

    if _install_hook(hooks_dir, "post-merge", POST_MERGE_TEMPLATE):
        print(f"✅ Installed post-merge hook: {hooks_dir / 'post-merge'}")
        changed += 1
    else:
        print("ℹ️  post-merge hook already installed (yuleOSH).")

    if changed:
        print(f"\n✨ {changed} hook(s) installed. They will run automatically on commit/merge.")
    return 0


def cmd_hook_run(hook_name: str) -> int:
    """Run a hook by name."""
    hook_name = hook_name.lower()

    if hook_name == "pre-commit" or hook_name == "pre_commit":
        from yuleosh.hooks.pre_commit import run_pre_commit
        return run_pre_commit()
    elif hook_name == "post-merge" or hook_name == "post_merge":
        from yuleosh.hooks.post_merge import run_post_merge
        return run_post_merge()
    else:
        print(f"❌ Unknown hook: {hook_name}", file=sys.stderr)
        print("  Available: pre-commit, post-merge", file=sys.stderr)
        return 1


def build_hook_subparser(subparsers):
    """Add the 'hook' subcommand parser."""
    hook_parser = subparsers.add_parser("hook", help="Git hook management (install, run)")
    hook_sub = hook_parser.add_subparsers(dest="hook_sub", required=True)

    # hook install
    hook_sub.add_parser("install", help="Install pre-commit and post-merge hooks")

    # hook run
    run_p = hook_sub.add_parser("run", help="Run a hook directly")
    run_p.add_argument("hook_name", help="Hook to run (pre-commit, post-merge)")

    return hook_parser


def handle_hook_command(args) -> int:
    """Dispatch hook subcommand."""
    if args.hook_sub == "install":
        return cmd_hook_install()
    elif args.hook_sub == "run":
        return cmd_hook_run(args.hook_name)
    return 1
