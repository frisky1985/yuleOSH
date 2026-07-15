#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985

"""
MISRA Report — Config / Constants / Version helpers.

Split from core.py (Phase 2.2 → Phase 3).
"""

import json
import logging
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None

log = logging.getLogger("ci.misra_report")

# Report schema version (R3-P0-6)
_MISRA_SCHEMA_VERSION = "misra-report-v2"
_SELFTEST_SCHEMA_VERSION = "selftest-review-v2"

# Default report directory for loading previous builds
_DEFAULT_REPORT_DIR = os.environ.get("OSH_HOME", os.path.expanduser("~/.yuleosh"))

# ------------------------------------------------------------------
# Multi-tool result types (G-15)
# ------------------------------------------------------------------
# Regex patterns for parsing cppcheck output
_PATTERN_CPPCHECK = re.compile(
    r"^"
    r"(?:"
    r"  \[(?P<file>[^:\n]+):(?P<line>\d+)(?::(?P<col>\d+))?\]\s*\((?P<severity>[^)]+)\)\s+"
    r"|"
    r"  (?P<file2>[^:\n]+):(?P<line2>\d+):(?P<col2>\d+):\s*(?P<severity2>[^:]+):\s+"
    r")"
    r"(?P<message>.+)$",
    re.MULTILINE | re.VERBOSE,
)
_PATTERN_MISRA_RULE = re.compile(
    r"(?:MISRA[- ]?(?:C\d{4})?[-.]?)(?P<rule_id>\d+\.\d+)",
    re.IGNORECASE,
)
_PATTERN_TEXT_RULE = re.compile(
    r"(?:MISRA|Rule|Dir)[- :]+(?P<rule_id>\d+(?:\.\d+)?(?:[-.][A-Z0-9]+)*)",
    re.IGNORECASE,
)


def _normalize_misra_year(rule_id: str) -> str:
    """Normalize MISRA rule ID to canonical year format."""
    rule_id = rule_id.strip()
    if rule_id.startswith("MISRA") or rule_id.startswith("Rule"):
        parts = rule_id.replace("MISRA", "").replace("Rule", "").strip().split()
        if parts:
            rule_id = parts[0]
    return rule_id


def _load_ci_config() -> dict:
    """Load CI configuration (ci_config.yaml / ci_config.json)."""
    config_dir = Path(os.environ.get("OSH_HOME", ".")) / ".osh"
    for name in ("ci_config.yaml", "ci_config.yml", "ci_config.json"):
        path = config_dir / name
        if path.exists():
            try:
                if name.endswith(".json"):
                    return json.loads(path.read_text())
                if yaml:
                    return yaml.safe_load(path.read_text())
                log.warning("PyYAML not installed; cannot load %s", name)
            except Exception as e:
                log.warning("Failed to load %s: %s", name, e)
    return {}


def _extract_excluded_rules(config: dict | None = None) -> list[str]:
    """Extract excluded MISRA rule IDs from CI config."""
    config = config or _load_ci_config()
    misra_cfg = config.get("misra", {})
    excluded = misra_cfg.get("exclude_rules", []) or []
    if isinstance(excluded, str):
        excluded = [excluded]
    return excluded


def _extract_excluded_files(config: dict | None = None) -> list[str]:
    """Extract excluded file patterns from CI config."""
    config = config or _load_ci_config()
    misra_cfg = config.get("misra", {})
    excluded = misra_cfg.get("exclude_files", []) or []
    if isinstance(excluded, str):
        excluded = [excluded]
    return excluded


def load_rule_definitions(rules_path: Optional[Path] = None) -> dict:
    """Load MISRA rule definitions from YAML."""
    if rules_path is None:
        # Reach project root from src/yuleosh/ci/misra_report/core/config.py
        # Path: .../src/yuleosh/ci/misra_report/core/config.py → go up 6 levels
        base = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
        rules_path = base / "misra-rules.yaml"
    if not rules_path.exists():
        log.warning("MISRA rules file not found: %s", rules_path)
        return {}
    try:
        if yaml:
            return yaml.safe_load(rules_path.read_text()) or {}
        log.warning("PyYAML not installed; cannot load rules")
        return {}
    except Exception as e:
        log.error("Failed to load rules from %s: %s", rules_path, e)
        return {}


def _count_source_lines(file_paths: list[str]) -> int:
    """Count total source lines across a list of file paths."""
    total = 0
    for fp in file_paths:
        try:
            with open(fp) as f:
                total += sum(1 for _ in f)
        except Exception:
            pass
    return total


def get_tool_version() -> str:
    """Get MISRA checking tool version."""
    try:
        result = subprocess.run(
            ["cppcheck", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def get_ruleset_version(rule_defs: dict) -> str:
    """Get ruleset version from rule definitions."""
    if rule_defs and "meta" in rule_defs:
        return rule_defs["meta"].get("version", "unknown")
    return "unknown"


def get_ci_environ() -> dict:
    """Extract CI environment metadata."""
    return {
        "build_id": os.environ.get("BUILD_ID", ""),
        "commit_sha": os.environ.get("GIT_COMMIT", ""),
        "branch": os.environ.get("BRANCH_NAME", ""),
        "job_name": os.environ.get("JOB_NAME", ""),
        "workspace": os.environ.get("WORKSPACE", ""),
    }
