#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985

"""
MISRA Report — cppcheck output parser.

Split from core.py (Phase 2.2 → Phase 3).
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.misra_report")

# Also import patterns from config (avoid circular dependency)
from yuleosh.ci.misra_report.core.config import (
    _PATTERN_CPPCHECK,
    _PATTERN_MISRA_RULE,
    _PATTERN_TEXT_RULE,
)

# Pre-built lookup for short rule IDs / C:2012-style IDs → canonical C:2023 YAML keys.
# cppcheck outputs "1.1", "10.1" etc., but misra-rules.yaml uses "misra-c2023-1.1".
# We build this mapping once at import time by scanning the YAML file.
_CANONICAL_RULE_LOOKUP: dict[str, str] = {}


def _build_rule_lookup():
    """Build a lookup from short rule ID to canonical YAML key.

    Supports:
    - Short numeric IDs: "1.1" → "misra-c2023-1.1"
    - C:2012-style IDs: "Rule 10.1" → "misra-c2023-10.1"
    - Directive IDs: "Dir 4.1" → "misra-c2023-dir-4.1"
    - Canonical IDs: already handled elsewhere
    """
    global _CANONICAL_RULE_LOOKUP
    _CANONICAL_RULE_LOOKUP.clear()
    try:
        from yuleosh.ci.misra_report.core.config import load_rule_definitions
        rule_defs = load_rule_definitions()
        rules = rule_defs.get("rules", rule_defs)

        # Phase 1: Build lookup from rule keys directly
        for key in rules:
            if key == "meta":
                continue
            # Extract short form: "misra-c2023-1.1" → "1.1"
            m = re.match(r'^misra-c\d{4}-(.+)$', key, re.IGNORECASE)
            if m:
                short = m.group(1).lower()
                _CANONICAL_RULE_LOOKUP[short] = key
                # Also store just the numeric part for "X.Y" matches
                num_m = re.match(r'^(\d+\.\d+)$', short)
                if num_m:
                    _CANONICAL_RULE_LOOKUP[num_m.group(1)] = key
                # Handle directive forms
                dir_m = re.match(r'^dir[- ]?(\d+\.\d+)$', short, re.IGNORECASE)
                if dir_m:
                    _CANONICAL_RULE_LOOKUP[dir_m.group(1)] = key
                    _CANONICAL_RULE_LOOKUP[f"dir {dir_m.group(1)}".lower()] = key

        # Phase 2: Load backward_compat mapping from meta section
        # Maps C:2012 rule IDs like "Rule 1.1" → C:2023 key "misra-c2023-1.1"
        meta = rule_defs.get("meta", {})
        backward_compat = meta.get("backward_compat", {})
        c2012_mapping = backward_compat.get("mapping", {})
        for c2012_id, info in c2012_mapping.items():
            c2023_id = info.get("c2023_id", "")
            if c2023_id:
                # Store the C:2012-style ID as a lookup key
                _CANONICAL_RULE_LOOKUP[c2012_id.lower()] = c2023_id
                # Also store just the rule number as lowercased "rule x.y"
                num_part = re.sub(r'^(?:rule|dir)\s+', '', c2012_id, flags=re.IGNORECASE)
                _CANONICAL_RULE_LOOKUP[f"rule {num_part.lower()}"] = c2023_id

        log.debug("Rule lookup built: %d entries", len(_CANONICAL_RULE_LOOKUP))
    except Exception as e:
        log.debug("Failed to build rule lookup: %s", e)


# Build the lookup on import
_build_rule_lookup()


def _extract_file_path(raw: str) -> str | None:
    """Extract a normalized file path from cppcheck output."""
    if not raw or raw == "<stdin>":
        return None
    raw = raw.strip().strip('"')
    try:
        p = Path(raw)
        if p.exists():
            return str(p.resolve())
        return raw
    except Exception:
        return raw


def _is_valid_source_path(path: str) -> bool:
    """Check if a path is a valid source file."""
    if not path:
        return False
    valid_extensions = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hxx", ".s", ".S", ".asm"}
    p = Path(path)
    return p.suffix.lower() in valid_extensions


def parse_cppcheck_output(text: str) -> list[dict]:
    """Parse cppcheck plain-text output into structured violations.

    Supports both bracketed format:
        [file:line:col] (severity) message [rule]
    And legacy format:
        file:line:col: severity: message [rule]
    """
    violations = []
    for match in _PATTERN_CPPCHECK.finditer(text):
        # Determine which format matched (bracketed vs legacy)
        raw_file = match.group("file") or match.group("file2")
        file_path = _extract_file_path(raw_file)
        line = int(match.group("line") or match.group("line2"))
        col_str = match.group("col") or match.group("col2")
        column = int(col_str) if col_str else 0
        severity = (match.group("severity") or match.group("severity2")).lower()
        message = match.group("message").strip()

        # Extract rule ID from message
        rule_match = _PATTERN_MISRA_RULE.search(message) or _PATTERN_TEXT_RULE.search(message)
        rule_id = _normalize_rule_id(rule_match.group("rule_id")) if rule_match else None

        violations.append({
            "file": file_path or raw_file,
            "line": line,
            "column": column,
            "severity": severity,
            "message": message,
            "rule_id": rule_id,
            "rule_year": "2012",  # default
        })
    return violations


def _normalize_rule_id(rule_id: str) -> str:
    """Normalize MISRA rule ID to canonical format.

    cppcheck outputs short rule IDs like "1.1", "10.1" or
    "Dir 4.1", while misra-rules.yaml uses canonical keys like
    "misra-c2023-1.1", "misra-c2023-dir-4.1".

    This function normalizes cppcheck output to match the YAML keys.
    """
    rule_id = rule_id.strip()

    # Already canonical (starts with misra-cXXXX-)
    if re.match(r'^misra-c\d{4}-', rule_id, re.IGNORECASE):
        return rule_id.lower()

    # Normalize by stripping MISRA/Rule/Dir prefixes
    normalized = rule_id
    if normalized.startswith("MISRA") or normalized.startswith("Rule"):
        normalized = re.sub(r'^(?:MISRA|Rule)\s*', '', normalized).strip()
    elif normalized.startswith("Dir"):
        normalized = re.sub(r'^Dir\s*', '', normalized, flags=re.IGNORECASE).strip()
        # Also add "dir-" prefix for lookup
        dir_lookup = f"dir-{normalized}".lower()
        if dir_lookup in _CANONICAL_RULE_LOOKUP:
            return _CANONICAL_RULE_LOOKUP[dir_lookup]

    # Check against pre-built lookup
    lookup_key = normalized.lower()
    if lookup_key in _CANONICAL_RULE_LOOKUP:
        return _CANONICAL_RULE_LOOKUP[lookup_key]

    # Try just the numeric part (e.g. "10.1" from "MISRA Rule 10.1 [required]")
    num_match = re.match(r'^(\d+\.\d+)', normalized)
    if num_match and num_match.group(1) in _CANONICAL_RULE_LOOKUP:
        return _CANONICAL_RULE_LOOKUP[num_match.group(1)]

    # Try directive format: "Dir 4.1" → "4.1" or "dir-4.1"
    dir_match = re.match(r'^[Dd]ir\s*(\d+\.\d+)', normalized)
    if dir_match and dir_match.group(1) in _CANONICAL_RULE_LOOKUP:
        return _CANONICAL_RULE_LOOKUP[dir_match.group(1)]

    # Fallback: use the extracted numeric part as-is (may still be "unknown")
    return normalized
