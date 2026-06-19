#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Pipeline Profile — profile definitions, validation, and step filtering.

Supports the G-33 requirement (Pipeline Profile 切换机制):
- ci-config.yaml profile definitions
- ≥2 profiles (safety, ci)
- Startup validation
- Step filtering based on active profile
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from yuleosh.ci.config import _get_ci_config, MisraProfile, MisraConfig

log = logging.getLogger("ci.profile")

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

# Default step inclusion/exclusion per profile
# Each profile can specify which steps to include/exclude.
# None = include all steps (no filtering)
BUILTIN_PROFILES = {
    "safety": {
        "description": "Full safety-critical pipeline — all steps enabled",
        "include_steps": None,  # All steps
        "exclude_steps": [],    # None excluded
    },
    "ci": {
        "description": "CI pipeline — excludes LLM-heavy review steps for speed",
        "include_steps": None,
        "exclude_steps": [
            "super-analysis", "prd", "prd-review",
            "architecture", "arch-review",
            "development", "devplan-review",
            "internal-code-review", "test-planning",
            "self-test", "self-test-review",
            "code-review", "final-report",
        ],
    },
    "performance": {
        "description": "Performance-optimized pipeline — fewer steps, faster",
        "include_steps": None,
        "exclude_steps": [
            "super-analysis", "architecture", "arch-review",
            "self-test", "self-test-review", "final-report",
        ],
    },
    "testing": {
        "description": "Testing-focused pipeline — only quality gates",
        "include_steps": None,
        "exclude_steps": [
            "super-analysis", "prd", "prd-review",
            "architecture", "arch-review",
            "development", "devplan-review",
            "internal-code-review", "test-planning",
            "self-test", "self-test-review",
            "code-review", "misra-review", "coverage-review",
            "review-linker", "review-startup", "review-rtos", "review-memory",
            "review-bsp", "review-build", "review-power",
            "test-qualification", "final-report",
        ],
    },
}


def get_available_profiles() -> dict:
    """Return all available profile definitions (builtin + custom)."""
    return dict(BUILTIN_PROFILES)


def get_profile_config(profile_name: str) -> Optional[dict]:
    """Get configuration for a named profile.

    Returns the profile config dict or None if not found.
    """
    return BUILTIN_PROFILES.get(profile_name)


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------


def validate_active_profile(project_dir: str) -> tuple[bool, str]:
    """Validate that the active profile from ci-config.yaml is valid.

    Returns (valid: bool, message: str).
    Checks:
      1. active_profile is a known profile name
      2. ci-config.yaml has at least 2 profiles defined
    """
    try:
        cfg = _get_ci_config(project_dir)
    except Exception as e:
        return False, f"Cannot load ci-config.yaml: {e}"

    misra_cfg: MisraConfig = cfg.misra
    profile_name = misra_cfg.active_profile or "safety"

    # Check if profile exists in builtin set
    if profile_name not in BUILTIN_PROFILES:
        return False, (
            f"Active profile '{profile_name}' not found. "
            f"Available profiles: {', '.join(sorted(BUILTIN_PROFILES.keys()))}"
        )

    # Check custom profiles from config
    config_profiles = misra_cfg.profiles or {}
    if config_profiles:
        if profile_name not in config_profiles and profile_name not in BUILTIN_PROFILES:
            return False, (
                f"Active profile '{profile_name}' not found in ci-config.yaml profiles. "
                f"Defined profiles: {', '.join(sorted(config_profiles.keys()))}"
            )

    # Verify at least 2 profiles exist (builtin or config)
    available = set(BUILTIN_PROFILES.keys())
    if config_profiles:
        available.update(config_profiles.keys())

    if len(available) < 2:
        return False, (
            f"Only {len(available)} profile(s) found ({', '.join(sorted(available))}). "
            "At least 2 profiles are required (G-33 §16.2)."
        )

    return True, f"Profile '{profile_name}' is valid. ({len(available)} profiles available)"


# ------------------------------------------------------------------
# Step filtering
# ------------------------------------------------------------------


def filter_steps_for_profile(
    steps: list[tuple],
    profile_name: str,
    project_dir: str = "",
) -> list[tuple]:
    """Filter pipeline steps based on the active profile.

    Returns a filtered list of (step_key, agent, step_name, handler) tuples.
    Steps excluded by the active profile are removed.

    Parameters
    ----------
    steps : list[tuple]
        Full PIPELINE_STEPS list.
    profile_name : str
        Active profile name (e.g. "safety", "ci").
    project_dir : str
        Project root, to check ci-config.yaml custom profile overrides.

    Returns
    -------
    list[tuple]
        Filtered step list.
    """
    # Get base profile config
    profile_cfg = BUILTIN_PROFILES.get(profile_name, BUILTIN_PROFILES["safety"])

    # Check for custom profile overrides in ci-config.yaml
    try:
        cfg = _get_ci_config(project_dir)
        config_profiles = cfg.misra.profiles or {}
        custom_profile = config_profiles.get(profile_name)
        if custom_profile:
            # Merge custom exclude steps if defined
            if hasattr(custom_profile, 'exclude_steps') and custom_profile.exclude_steps:
                profile_cfg = {**profile_cfg, "exclude_steps": custom_profile.exclude_steps}
    except Exception:
        pass  # Fall back to builtin profile config

    exclude = set(profile_cfg.get("exclude_steps", []))
    include = profile_cfg.get("include_steps")

    if include is not None:
        # Whitelist mode: only include specified steps
        include_set = set(include)
        filtered = [s for s in steps if s[0] in include_set]
    elif exclude:
        # Blacklist mode: remove excluded steps
        filtered = [s for s in steps if s[0] not in exclude]
    else:
        # Include all steps
        filtered = list(steps)

    excluded_count = len(steps) - len(filtered)
    if excluded_count > 0:
        log.info(
            "Profile '%s' filtered out %d step(s): %s",
            profile_name,
            excluded_count,
            ", ".join(s[0] for s in steps if s[0] not in {ss[0] for ss in filtered}),
        )

    return filtered


def get_current_profile(project_dir: str) -> str:
    """Get the active profile name from ci-config.yaml.

    Falls back to 'safety' if not configured.
    """
    try:
        cfg = _get_ci_config(project_dir)
        return cfg.misra.active_profile or "safety"
    except Exception:
        return "safety"


# ═══════════════════════════════════════════════════════════════════════
# Sprint E: Profile 变更审计
# ═══════════════════════════════════════════════════════════════════════

import json
import os
import subprocess as _subprocess
from datetime import datetime

PROFILE_AUDIT_FILE = Path(".yuleosh") / "reports" / "profile-audit.jsonl"


def _ensure_audit_dir(project_dir: str) -> Path:
    path = Path(project_dir) / PROFILE_AUDIT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _get_git_commit(project_dir: str) -> str:
    """Get the current git commit SHA (short)."""
    try:
        r = _subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=project_dir,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _get_git_user(project_dir: str) -> str:
    """Get the configured git user name."""
    try:
        r = _subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, timeout=5,
            cwd=project_dir,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def record_profile_change(
    project_dir: str,
    old_profile: str,
    new_profile: str,
    user: str = "",
    reason: str = "",
) -> dict:
    """Record a profile change to the audit log.

    Captures: timestamp, user, old profile, new profile,
    commit SHA at time of change, and optional reason.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    old_profile : str
        Previous profile value.
    new_profile : str
        New profile value.
    user : str
        User who made the change. Auto-detected from git if empty.
    reason : str
        Optional reason for the change.

    Returns
    -------
    dict
        The recorded audit entry.
    """
    if not user:
        user = _get_git_user(project_dir)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "old_profile": old_profile,
        "new_profile": new_profile,
        "commit": _get_git_commit(project_dir),
        "reason": reason,
    }

    path = _ensure_audit_dir(project_dir)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    log.info(
        "Profile change audited: %s -> %s (user=%s, commit=%s)",
        old_profile, new_profile, user, entry["commit"],
    )
    return entry


def get_profile_audit_log(
    project_dir: str,
    limit: int = 50,
    as_json: bool = False,
) -> str:
    """Get the profile change audit log.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    limit : int
        Max entries to show (most recent first).
    as_json : bool
        Return JSON string instead of formatted text.

    Returns
    -------
    str
        Audit log summary.
    """
    path = Path(project_dir) / PROFILE_AUDIT_FILE
    if not path.exists():
        msg = "*No profile change audit records found.*"
        return json.dumps({"error": msg}) if as_json else msg

    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue

    # Most recent first
    entries.reverse()
    recent = entries[:limit]

    if as_json:
        result = {
            "total_entries": len(entries),
            "entries": recent,
        }
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    rows = [
        "## Profile 变更审计日志",
        "",
        f"*共 {len(entries)} 条记录，显示最近 {len(recent)} 条*",
        "",
    ]

    if not recent:
        rows.append("*无记录*")
        return "\n".join(rows)

    rows.append("| # | 时间 | 用户 | 旧Profile | 新Profile | Commit | 原因 |")
    rows.append("|--:|:-----|:-----|:----------|:----------|:------|:----|")

    for idx, e in enumerate(recent, 1):
        ts = e.get("timestamp", "")[:19]
        user = e.get("user", "")
        old_p = e.get("old_profile", "")
        new_p = e.get("new_profile", "")
        commit = e.get("commit", "")[:8]
        reason = e.get("reason", "")
        rows.append(f"| {idx} | {ts} | {user} | {old_p} | {new_p} | {commit} | {reason} |")

    rows.append("")
    return "\n".join(rows)
