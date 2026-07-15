# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Git Hooks — pre-commit, post-merge, and CLI installer."""

from .pre_commit import run_pre_commit
from .post_merge import run_post_merge

__all__ = ["run_pre_commit", "run_post_merge"]
