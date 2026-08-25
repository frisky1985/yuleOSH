#!/usr/bin/env python3

# @req RS-005
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Traceability configuration loader (Q5).

Reads project-level `.yuleosh/traceability.yaml` to allow per-project
customization of:
  - component_map: req_id prefix → source path keywords
  - scenario_terms: domain-specific GIVEN/WHEN/THEN keywords to preserve
  - test_id_prefixes: patterns that identify test IDs in source/reports
  - stop_words: additional words to exclude from keyword extraction

Falls back to built-in defaults when the file is absent or malformed —
always logs a warning so projects know they should create one.

Example .yuleosh/traceability.yaml:
  component_map:
    RS-001: [init, startup, boot]
    RS-002: [communication, uart, can]
  scenario_terms:
    - heartbeat
    - watchdog
  test_id_prefixes:
    - TC-
    - SWR-
  stop_words:
    - firmware
    - embedded
"""

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("yuleosh.alm.traceability_config")

# ── Built-in defaults ────────────────────────────────────────────────────────

_DEFAULT_COMPONENT_MAP: dict[str, list[str]] = {}

_DEFAULT_SCENARIO_TERMS: list[str] = [
    "given", "when", "then", "shall", "should", "must",
    "initialize", "startup", "shutdown", "error", "timeout",
    "receive", "transmit", "state", "mode", "event", "signal",
]

_DEFAULT_TEST_ID_PREFIXES: list[str] = [
    "TC-", "RS-", "SWR-", "SRS-", "REQ-", "TS-", "test_",
]

_DEFAULT_STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "as", "is", "was", "be",
    "are", "been", "being", "have", "has", "had", "do", "does",
    "did", "will", "would", "could", "should", "may", "might",
    "shall", "must", "not", "no", "its", "their", "them",
    "they", "this", "that", "these", "those",
})

# Chinese stop words — common function words and generic nouns that add
# little traceability signal when extracted as CJK bigrams.
_DEFAULT_ZH_STOP_WORDS: frozenset[str] = frozenset({
    "的", "了", "在", "是", "将", "应", "应当", "须", "需", "其", "该",
    "以", "并", "且", "或", "及", "等", "对", "为", "到", "从", "与",
    "内", "中", "下", "上", "后", "前", "系统", "功能", "模块",
})

_CONFIG_FILENAME = ".yuleosh/traceability.yaml"


# ── Loader ────────────────────────────────────────────────────────────────────

def load_traceability_config(project_dir: str | Path) -> dict[str, Any]:
    """Load traceability config from <project_dir>/.yuleosh/traceability.yaml.

    Returns a dict with keys:
      - component_map: dict[str, list[str]]
      - scenario_terms: list[str]
      - test_id_prefixes: list[str]
      - stop_words: frozenset[str]

    Falls back to built-in defaults when the file is absent, unreadable,
    or malformed (logs a warning in each case).
    """
    config_path = Path(project_dir) / _CONFIG_FILENAME

    if not config_path.exists():
        log.warning(
            "traceability config not found: %s — using built-in defaults. "
            "Create the file to customize keyword mapping for this project.",
            config_path,
        )
        return _default_config()

    try:
        import yaml as _yaml  # optional dependency
    except ImportError:
        log.warning(
            "PyYAML not installed — cannot load %s; using built-in defaults.",
            config_path,
        )
        return _default_config()

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = _yaml.safe_load(raw) or {}
    except Exception as exc:
        log.warning(
            "Failed to parse %s: %s — using built-in defaults.",
            config_path, exc,
        )
        return _default_config()

    if not isinstance(data, dict):
        log.warning(
            "traceability config %s is not a YAML mapping — using built-in defaults.",
            config_path,
        )
        return _default_config()

    component_map = data.get("component_map", {})
    if not isinstance(component_map, dict):
        log.warning("component_map in %s is not a dict — using empty map.", config_path)
        component_map = {}
    # Ensure all values are lists of strings
    cleaned_map: dict[str, list[str]] = {}
    for k, v in component_map.items():
        if isinstance(v, list):
            cleaned_map[str(k)] = [str(x) for x in v]
        else:
            cleaned_map[str(k)] = [str(v)]

    scenario_terms = data.get("scenario_terms", list(_DEFAULT_SCENARIO_TERMS))
    if not isinstance(scenario_terms, list):
        scenario_terms = list(_DEFAULT_SCENARIO_TERMS)

    test_id_prefixes = data.get("test_id_prefixes", list(_DEFAULT_TEST_ID_PREFIXES))
    if not isinstance(test_id_prefixes, list):
        test_id_prefixes = list(_DEFAULT_TEST_ID_PREFIXES)

    extra_stop_words = data.get("stop_words", [])
    if not isinstance(extra_stop_words, list):
        extra_stop_words = []
    extra_zh_stop_words = data.get("zh_stop_words", [])
    if not isinstance(extra_zh_stop_words, list):
        extra_zh_stop_words = []
    stop_words = (
        _DEFAULT_STOP_WORDS
        | _DEFAULT_ZH_STOP_WORDS
        | frozenset(str(w).lower() for w in extra_stop_words)
        | frozenset(str(w) for w in extra_zh_stop_words)
    )

    log.debug("Loaded traceability config from %s", config_path)
    return {
        "component_map": cleaned_map,
        "scenario_terms": scenario_terms,
        "test_id_prefixes": test_id_prefixes,
        "stop_words": stop_words,
    }


def _default_config() -> dict[str, Any]:
    return {
        "component_map": dict(_DEFAULT_COMPONENT_MAP),
        "scenario_terms": list(_DEFAULT_SCENARIO_TERMS),
        "test_id_prefixes": list(_DEFAULT_TEST_ID_PREFIXES),
        "stop_words": frozenset(_DEFAULT_STOP_WORDS | _DEFAULT_ZH_STOP_WORDS),
    }


def get_stop_words(project_dir: str | Path | None = None) -> frozenset[str]:
    """Convenience: return effective stop_words for keyword extraction."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", ".")
    return load_traceability_config(project_dir)["stop_words"]


def get_test_id_prefixes(project_dir: str | Path | None = None) -> list[str]:
    """Convenience: return effective test_id_prefixes."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", ".")
    return load_traceability_config(project_dir)["test_id_prefixes"]
