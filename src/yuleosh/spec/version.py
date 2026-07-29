#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Spec Version Management — read, write, and increment spec version.

Maintains a version lock file at ``.yuleosh/spec-version.json``.
Supports semantic versioning (MAJOR.MINOR.PATCH).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("spec.version")

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

DEFAULT_VERSION_FILE = ".yuleosh/spec-version.json"
DEFAULT_VERSION = "1.0.0"

# ------------------------------------------------------------------
# Dataclass
# ------------------------------------------------------------------


@dataclass
class SpecVersion:
    """Spec version information.

    Attributes
    ----------
    version : str
        Semantic version string (MAJOR.MINOR.PATCH).
    spec_path : str
        Path to the main spec file (typically docs/spec.md).
    updated_at : str
        ISO timestamp of last update.
    updated_by : str
        Who performed the update (e.g., command name or user).
    history : list[dict]
        List of version change records.
    """

    version: str = DEFAULT_VERSION
    spec_path: str = "docs/spec.md"
    updated_at: str = ""
    updated_by: str = ""
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "spec_path": self.spec_path,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpecVersion":
        return cls(
            version=str(data.get("version", DEFAULT_VERSION)),
            spec_path=str(data.get("spec_path", "docs/spec.md")),
            updated_at=str(data.get("updated_at", "")),
            updated_by=str(data.get("updated_by", "")),
            history=list(data.get("history", [])),
        )


# ------------------------------------------------------------------
# Version parsing helpers
# ------------------------------------------------------------------


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse a semver string into (major, minor, patch).

    Returns (0, 0, 0) on format error.
    """
    try:
        parts = version_str.strip().split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except (ValueError, IndexError, AttributeError):
        return (0, 0, 0)


def compare_versions(a: str, b: str) -> int:
    """Compare two version strings.

    Returns:
        -1 if a < b
         0 if a == b
         1 if a > b
    """
    va = parse_version(a)
    vb = parse_version(b)
    if va < vb:
        return -1
    if va > vb:
        return 1
    return 0


def increment_version(
    current: str,
    part: str = "minor",
    delta_version: Optional[str] = None,
) -> str:
    """Increment a semantic version.

    Parameters
    ----------
    current : str
        Current version string (MAJOR.MINOR.PATCH).
    part : str
        Which part to increment: "major", "minor", or "patch".
        Ignored if *delta_version* is provided.
    delta_version : str, optional
        If provided, compute the next version as max(current, delta_version).
        Used when a spec-delta declares its own target version.

    Returns
    -------
    str
        Incremented version string.
    """
    if delta_version:
        # Use the delta's declared version, but ensure it's >= current
        cmp = compare_versions(delta_version, current)
        if cmp > 0:
            return delta_version
        # Delta version is <= current — bump current anyway
        return _auto_bump(current)

    return _auto_bump(current, part)


def _auto_bump(current: str, part: str = "minor") -> str:
    """Auto-bump the version by incrementing the specified part."""
    major, minor, patch = parse_version(current)

    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "patch":
        patch += 1
    else:  # minor (default)
        minor += 1
        patch = 0

    return f"{major}.{minor}.{patch}"


# ------------------------------------------------------------------
# Read/Write
# ------------------------------------------------------------------


def read_spec_version(
    project_dir: Optional[str] = None,
    version_file: Optional[str] = None,
) -> SpecVersion:
    """Read spec version from ``.yuleosh/spec-version.json``.

    If the file does not exist, returns a default SpecVersion
    with version from ``docs/spec.md`` header if found.

    Parameters
    ----------
    project_dir : str, optional
        Project root directory. Defaults to ``OSH_HOME`` or current dir.
    version_file : str, optional
        Path to version file (relative to project_dir).

    Returns
    -------
    SpecVersion
        Parsed version information.
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    path = version_file or DEFAULT_VERSION_FILE
    full_path = os.path.join(project_dir, path)

    if os.path.exists(full_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SpecVersion.from_dict(data)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Cannot read spec version from %s: %s", full_path, e)

    # Fallback: parse version from docs/spec.md header
    spec_path = os.path.join(project_dir, "docs", "spec.md")
    if os.path.exists(spec_path):
        version = _parse_version_from_spec_header(spec_path)
        if version:
            return SpecVersion(version=version, spec_path="docs/spec.md")

    return SpecVersion()


def _parse_version_from_spec_header(spec_path: str) -> Optional[str]:
    """Extract version from the spec.md header line.

    Looks for ``**Version**: X.Y.Z`` pattern.
    """
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            for line in f:
                if "**Version**" in line or "Version:" in line:
                    import re
                    m = re.search(r'(\d+\.\d+\.\d+)', line)
                    if m:
                        return m.group(1)
    except OSError:
        pass
    return None


def write_spec_version(
    sv: SpecVersion,
    project_dir: Optional[str] = None,
    version_file: Optional[str] = None,
) -> bool:
    """Write spec version to ``.yuleosh/spec-version.json``.

    Returns True on success.
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    path = version_file or DEFAULT_VERSION_FILE
    full_path = os.path.join(project_dir, path)

    try:
        Path(full_path).parent.mkdir(parents=True, exist_ok=True)
        sv.updated_at = datetime.now().isoformat()
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(sv.to_dict(), f, indent=2, ensure_ascii=False)
        log.info("Spec version written: %s → %s", full_path, sv.version)
        return True
    except OSError as e:
        log.error("Cannot write spec version: %s", e)
        return False


# ------------------------------------------------------------------
# Compatibility helpers
# ------------------------------------------------------------------


def detect_spec_path(project_dir: str) -> str:
    """Detect the main spec file path."""
    candidates = [
        "docs/spec.md",
        "specs/spec.md",
        "SPEC.md",
        "spec.md",
    ]
    for c in candidates:
        if os.path.exists(os.path.join(project_dir, c)):
            return c
    return "docs/spec.md"
