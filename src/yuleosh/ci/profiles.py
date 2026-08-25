#!/usr/bin/env python3

# @req RS-004
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
CI Environment Profiles — development / ci / production (QG-007).

Defines environment-specific CI profile settings for coverage thresholds,
MISRA profiles, and strict mode.  Each profile represents a different
phase in the development lifecycle:

  - ``development``  — local dev, fast iteration (low gate)
  - ``ci``           — PR check, standard gate (default)
  - ``production``   — release, highest gate

Usage:
    yuleosh ci run 2 --profile development
    yuleosh ci run 2 --profile ci
    yuleosh ci run 2 --profile production
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("ci.profiles")


# ------------------------------------------------------------------
# CI Profile Dataclass
# ------------------------------------------------------------------


@dataclass
class CIProfile:
    """Configuration for a single CI environment profile.

    Attributes
    ----------
    name : str
        Profile name (development, ci, production).
    threshold_line : float
        Line coverage threshold percentage.
    threshold_condition : float
        Condition/branch coverage threshold percentage.
    strict : bool
        If True, coverage failures block the pipeline.
    misra_profile : str
        MISRA profile to use (safety, motor, benchmark).
    module_thresholds : dict[str, float]
        Per-module coverage threshold overrides.
    description : str
        Human-readable description of this profile.
    """

    name: str = ""
    threshold_line: float = 50.0
    threshold_condition: float = 50.0
    strict: bool = True
    misra_profile: str = "safety"
    module_thresholds: dict[str, float] = field(default_factory=dict)
    description: str = ""


# ------------------------------------------------------------------
# Built-in CI Profiles
# ------------------------------------------------------------------

BUILTIN_CI_PROFILES: dict[str, CIProfile] = {
    "development": CIProfile(
        name="development",
        threshold_line=5.0,
        threshold_condition=5.0,
        strict=False,
        misra_profile="motor",
        module_thresholds={},
        description="Local development — fast iteration, low gate, advisory-only MISRA",
    ),
    "ci": CIProfile(
        name="ci",
        threshold_line=50.0,
        threshold_condition=50.0,
        strict=True,
        misra_profile="safety",
        module_thresholds={},
        description="PR/CI check — standard gate, strict coverage, safety MISRA (default)",
    ),
    "production": CIProfile(
        name="production",
        threshold_line=80.0,
        threshold_condition=60.0,
        strict=True,
        misra_profile="safety",
        module_thresholds={
            "src/core": 90.0,
            "src/mcal": 85.0,
            "src/ecual": 80.0,
            "src/services": 75.0,
        },
        description="Release — highest gate, per-module thresholds, full safety MISRA",
    ),
}


# ------------------------------------------------------------------
# Lookup and Merge Logic
# ------------------------------------------------------------------


def get_ci_profile(name: str) -> Optional[CIProfile]:
    """Retrieve a built-in CI profile by name.

    Returns None if the profile is not found.
    """
    return BUILTIN_CI_PROFILES.get(name)


def list_ci_profiles() -> dict[str, dict]:
    """List all available CI profiles with summary info."""
    return {
        name: {
            "name": p.name,
            "threshold_line": p.threshold_line,
            "threshold_condition": p.threshold_condition,
            "strict": p.strict,
            "misra_profile": p.misra_profile,
            "has_module_thresholds": bool(p.module_thresholds),
            "description": p.description,
        }
        for name, p in BUILTIN_CI_PROFILES.items()
    }


def resolve_ci_profile(
    profile_name: Optional[str],
    ci_config_coverage_threshold_line: float,
    ci_config_coverage_threshold_condition: float,
    ci_config_strict: bool,
    ci_config_misra_profile: str,
    ci_config_module_thresholds: dict[str, float] | None = None,
) -> dict:
    """Merge a named CI profile over the ci-config.yaml base values.

    The workflow:
    1. Start with the named profile's values as the base.
    2. Override with ci-config.yaml values where the profile has
       lower strictness — ci-config.yaml always wins for security.
    3. Return the merged settings dict.

    If ``profile_name`` is None or not found, ci-config.yaml values
    are returned as-is (default: ci profile behavior).

    Parameters
    ----------
    profile_name : str or None
        The named CI profile to use (development / ci / production).
    ci_config_coverage_threshold_line : float
        Line coverage threshold from ci-config.yaml.
    ci_config_coverage_threshold_condition : float
        Branch coverage threshold from ci-config.yaml.
    ci_config_strict : bool
        Strict mode from ci-config.yaml.
    ci_config_misra_profile : str
        Active MISRA profile from ci-config.yaml.
    ci_config_module_thresholds : dict or None
        Per-module thresholds from ci-config.yaml.

    Returns
    -------
    dict
        Merged settings dict with keys:
        - threshold_line
        - threshold_condition
        - strict
        - misra_profile
        - module_thresholds
        - profile_name (the resolved profile name)
    """
    if profile_name:
        profile = get_ci_profile(profile_name)
        if profile:
            # Start with profile values
            merged = {
                "threshold_line": profile.threshold_line,
                "threshold_condition": profile.threshold_condition,
                "strict": profile.strict,
                "misra_profile": profile.misra_profile,
                "module_thresholds": dict(profile.module_thresholds),
                "profile_name": profile_name,
            }

            # ci-config.yaml overrides take precedence (security: file beats profile default)
            # If ci-config sets a HIGHER threshold, use it (safety wins)
            # If ci-config sets LOWER threshold, profile threshold wins unless explicitly overridden
            merged["threshold_line"] = max(
                merged["threshold_line"], ci_config_coverage_threshold_line
            )
            merged["threshold_condition"] = max(
                merged["threshold_condition"], ci_config_coverage_threshold_condition
            )

            # Strict mode: ci-config strict takes precedence
            if ci_config_strict is not None:
                merged["strict"] = ci_config_strict

            # Module thresholds: merge both (config overrides profile)
            if ci_config_module_thresholds:
                for k, v in ci_config_module_thresholds.items():
                    merged["module_thresholds"][k] = v
                # Drop profile module thresholds where config sets lower
                for k in list(merged["module_thresholds"].keys()):
                    if k in ci_config_module_thresholds and ci_config_module_thresholds[k] < merged["module_thresholds"].get(k, 0):
                        merged["module_thresholds"][k] = ci_config_module_thresholds[k]

            log.info(
                "Resolved CI profile '%s': line=%.1f%%, strict=%s, misra=%s",
                profile_name,
                merged["threshold_line"],
                merged["strict"],
                merged["misra_profile"],
            )
            return merged

        log.warning(
            "CI profile '%s' not found, falling back to ci-config.yaml values",
            profile_name,
        )

    # Fallback: return as-is from ci-config.yaml
    return {
        "threshold_line": ci_config_coverage_threshold_line,
        "threshold_condition": ci_config_coverage_threshold_condition,
        "strict": ci_config_strict,
        "misra_profile": ci_config_misra_profile,
        "module_thresholds": ci_config_module_thresholds or {},
        "profile_name": profile_name or "ci",
    }


# ------------------------------------------------------------------
# Convenience: print profile info
# ------------------------------------------------------------------


def print_profile_summary() -> None:
    """Print a formatted summary of all available CI profiles."""
    print()
    print("  " + "=" * 65)
    print("  CI Environment Profiles")
    print("  " + "=" * 65)
    print()

    for name in ["development", "ci", "production"]:
        p = get_ci_profile(name)
        if not p:
            continue

        print(f"  🔹 {name}")
        print(f"     {p.description}")
        print(f"     Line threshold:    {p.threshold_line:.0f}%")
        print(f"     Condition thresh:  {p.threshold_condition:.0f}%")
        print(f"     Strict:            {'true' if p.strict else 'false'}")
        print(f"     MISRA profile:     {p.misra_profile}")
        if p.module_thresholds:
            print(f"     Module thresholds: {p.module_thresholds!r}")
        print()
