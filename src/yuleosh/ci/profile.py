#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

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
#
# 方向1 (2026-08-11): 反转为增量装配
#   - minimal: 白名单基线（include_steps 显式列出）——新用户首跑最小闭环
#   - safety : 恒等于 PIPELINE_STEPS 全集（不变量1）
#   - ci/performance/testing: 保持黑名单模式（不变量3：差集等价，零迁移风险）
#   - ALWAYS_INCLUDE: P0 保护集 —— 所有档强制包含，防止白名单档新 P0 门禁
#     静默消失（不变量2 的 fail-safe 兜底）
BUILTIN_PROFILES = {
    "safety": {
        "description": "Full safety-critical pipeline — all steps enabled",
        "include_steps": None,  # All steps
        "exclude_steps": [],    # None excluded
    },
    "minimal": {
        "description": "Minimal bootstrap — core quality gates only, add steps on demand",
        "include_steps": [
            "spec-check", "c-unit-test", "integration-test",
            "qemu-verify", "review-critical-safety", "merge-gate",
        ],
        "exclude_steps": [],
    },
    "ci": {
        "description": "CI pipeline — excludes LLM-heavy review steps for speed",
        "include_steps": None,
        "exclude_steps": [
            "super-analysis", "prd", "prd-review",
            "architecture", "arch-review",
            "development", "development-review",
            "internal-code-review", "claude-review", "test-planning",
            "verify-loop",
            "code-review", "final-report",
        ],
    },
    "performance": {
        "description": "Performance-optimized pipeline — fewer steps, faster",
        "include_steps": None,
        "exclude_steps": [
            "super-analysis", "architecture", "arch-review",
            "verify-loop", "final-report",
        ],
    },
    "testing": {
        "description": "Testing-focused pipeline — only quality gates",
        "include_steps": None,
        "exclude_steps": [
            "super-analysis", "prd", "prd-review",
            "architecture", "arch-review",
            "development", "development-review",
            "internal-code-review", "claude-review", "test-planning",
            "verify-loop",
            "code-review", "misra-review", "coverage-review",
            "test-qualification", "final-report",
        ],
    },
}

# P0 保护集（方向1）: 语义上不可绕过的门禁，任何档（含 minimal 白名单）
# 都必须保留。新步骤若加入此集，自动进入所有档 —— 防白名单模式漏步骤。
ALWAYS_INCLUDE = [
    "review-critical-safety",
    "merge-gate",
]


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

    方向1 (2026-08-11) 增量装配语义:
      - include_steps 非 None（白名单模式）: 只保留 include 列表 + ALWAYS_INCLUDE
        保护集（P0 门禁永不裁剪）中的步骤；未显式声明的新步骤默认保留
        （不变量2 fail-safe: unlisted = run，除非被 exclude 显式剔除）。
      - include_steps 为 None（黑名单模式）: 保留全部 − exclude_steps
        （现状行为，差集等价不变量3）。
      - safety: include_steps=None + exclude_steps=[] → 恒等于全集（不变量1）。
      - 自定义 profile 支持 extends 继承 + include_steps/exclude_steps 叠加
        （修复此前 hasattr exclude_steps 死代码 bug）。

    Parameters
    ----------
    steps : list[tuple]
        Full PIPELINE_STEPS list.
    profile_name : str
        Active profile name (e.g. "safety", "ci", "minimal").
    project_dir : str
        Project root, to check ci-config.yaml custom profile overrides.

    Returns
    -------
    list[tuple]
        Filtered step list.
    """
    # Get base profile config
    profile_cfg = BUILTIN_PROFILES.get(profile_name, BUILTIN_PROFILES["safety"])

    # Custom profile overrides in ci-config.yaml (方向1: extends + include/exclude 叠加)
    try:
        cfg = _get_ci_config(project_dir)
        config_profiles = cfg.misra.profiles or {}
        custom_profile = config_profiles.get(profile_name)
        if custom_profile:
            # extends: 继承另一内置/自定义 profile 的步骤语义
            ext = getattr(custom_profile, "extends", "") or ""
            if ext:
                base = dict(BUILTIN_PROFILES.get(ext, profile_cfg))
            else:
                base = dict(BUILTIN_PROFILES.get(profile_name, profile_cfg))
            inc = list(getattr(custom_profile, "include_steps", []) or [])
            exc = list(getattr(custom_profile, "exclude_steps", []) or [])
            if inc:
                # 白名单模式: 自定义 include 覆盖（+ 保护集）
                profile_cfg = {**base, "include_steps": inc, "exclude_steps": exc}
            elif exc:
                # 黑名单模式: 在 base 上追加排除
                merged_exc = list(base.get("exclude_steps", [])) + exc
                profile_cfg = {**base, "exclude_steps": merged_exc}
    except Exception:
        pass  # Fall back to builtin profile config

    include = profile_cfg.get("include_steps")
    exclude = set(profile_cfg.get("exclude_steps", []))
    # P0 保护集: 任何档都不能被排除
    always_include = set(ALWAYS_INCLUDE)

    if include is not None:
        # Whitelist mode: include 列表 + 保护集，减显式 exclude
        include_set = set(include) | always_include
        filtered = [s for s in steps if s[0] in include_set and s[0] not in exclude]
    else:
        # Blacklist mode: 全部 − exclude（但保护集强制保留）
        filtered = [s for s in steps if s[0] not in exclude or s[0] in always_include]

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
