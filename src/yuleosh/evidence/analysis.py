"""
yuleOSH Evidence Engine — Traceability analysis and requirement-to-test mapping.

Provides the internal parsing and matching methods that the ``EvidenceCollector``
uses to analyze test coverage and build traceability matrices.
"""

import ast
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger("evidence.collector")


# ==================================================================
# Scenario-Ref parsing (Priority 1 exact matching)
# ==================================================================


def parse_scenario_refs(text: str) -> list[str]:
    """Parse Scenario-Ref: markers from docstring or comment text.

    Supports two formats:
      1. Inline on a Covers: line: Covers: ..., Scenario-Ref: XXX
      2. Standalone line: Scenario-Ref: XXX

    Returns deduplicated list of scenario reference names.
    """
    refs: list[str] = []
    seen: set[str] = set()
    for line in text.split("\n"):
        m = re.search(r"Scenario-Ref:\s*(.+)$", line, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            raw = re.split(r",\s*Scenario-Ref:", raw, flags=re.IGNORECASE)[0]
            raw = raw.rstrip('",; \t\n\r')
            raw = re.sub(r'"{2,}$', '', raw)
            if raw and raw not in seen:
                seen.add(raw)
                refs.append(raw)
    return refs


def parse_module_covers(tree: ast.AST) -> list[str]:
    """Parse module-level docstring Covers: marker.

    Strips Scenario-Ref: portions to keep keywords clean.
    """
    keywords = []
    docstring = ast.get_docstring(tree)
    if docstring:
        for line in docstring.split("\n"):
            m = re.search(r"^\s*Covers:\s*(.+)$", line, re.IGNORECASE)
            if m:
                raw = m.group(1)
                raw = _strip_scenario_ref(raw)
                keywords.extend(k.strip() for k in raw.split(",") if k.strip())
    return keywords


def parse_comment_covers(content: str) -> list[str]:
    """Parse # Covers: line comments (fallback when no module docstring).

    Strips Scenario-Ref: portions to keep keywords clean.
    """
    keywords = []
    for line in content.split("\n"):
        m = re.search(r"^\s*#\s*Covers:\s*(.+)$", line, re.IGNORECASE)
        if m:
            raw = m.group(1)
            raw = _strip_scenario_ref(raw)
            keywords.extend(k.strip() for k in raw.split(",") if k.strip())
    return keywords


def _strip_scenario_ref(text: str) -> str:
    """Remove Scenario-Ref segments from a Covers: line."""
    return re.sub(r"Scenario-Ref:\s*[^,]+(?:,\s*)?", "", text, flags=re.IGNORECASE)


def parse_function_covers(tree: ast.AST) -> list[str]:
    """Parse Covers: from each test function's docstring."""
    keywords = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                docstring = ast.get_docstring(node)
                if docstring:
                    for line in docstring.split("\n"):
                        m = re.search(r"^\s*Covers:\s*(.+)$", line, re.IGNORECASE)
                        if m:
                            raw = m.group(1)
                            keywords.extend(
                                k.strip() for k in raw.split(",") if k.strip()
                            )
    return keywords


def infer_covers_from_function_names(tree: ast.AST, stop_words: set[str] | None = None) -> list[str]:
    """Infer Covers keywords from test function names.

    e.g. test_pipeline_processing -> ['pipeline', 'processing']
    """
    if stop_words is None:
        stop_words = {"test", "the", "and", "for", "with", "each", "from",
                      "that", "this", "all", "support", "system", "shall",
                      "should", "basic", "dummy", "can", "be", "is", "a",
                      "an", "in", "to", "of", "it", "as", "at", "by", "on"}
    inferred: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_name = node.name
            if fn_name.startswith("test_"):
                rest = fn_name[len("test_"):]
                parts = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", rest)
                for part in parts:
                    for word in re.split(r"[_]+|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", part):
                        w = word.lower().strip("_")
                        if w and len(w) > 2 and w not in stop_words:
                            inferred.add(w)
    return list(inferred)


def parse_covers_from_file(test_path: str, stop_words: set[str] | None = None) -> list[str]:
    """Multi-layer Covers marker parser.

    Priority (all merged):
      1. Module-level docstring Covers:
      2. Module-level # Covers: line comments (fallback)
      3. Per-test-function docstring Covers:
      4. Inference from test function names

    Note: Scenario-Ref markers on Covers lines are stripped from keywords;
    they are parsed separately via parse_scenario_refs().
    """
    keywords = []
    try:
        with open(test_path, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return keywords

    try:
        tree = ast.parse(content)
        mod_kw = parse_module_covers(tree)
        if not mod_kw:
            mod_kw = parse_comment_covers(content)
        keywords.extend(mod_kw)
        fn_kw = parse_function_covers(tree)
        keywords.extend(fn_kw)
        inf_kw = infer_covers_from_function_names(tree, stop_words)
        keywords.extend(inf_kw)
    except SyntaxError:
        keywords.extend(parse_comment_covers(content))

    return keywords


def categorize_uncovered(uncovered: list[dict]) -> tuple[list[dict], list[dict]]:
    """Categorize uncovered SHALLs into critical (core logic) and warn (non-functional)."""
    critical: list[dict] = []
    warn: list[dict] = []

    _non_functional_keywords = {
        "multi", "multitenant", "multi-tenant", "saas",
        "web", "ui", "mobile", "desktop", "interface",
        "architecture", "deployment", "deploy",
        "performance", "parallel", "concurrent", "retry",
        "single-tenant", "organization", "project", "team hierarchy",
    }

    for u in uncovered:
        shall_text = u.get("shall", "").lower()
        req_name = u.get("req_name", "").lower()
        combined = shall_text + " " + req_name
        is_non_functional = any(kw in combined for kw in _non_functional_keywords)
        if is_non_functional:
            warn.append(u)
        else:
            critical.append(u)

    return critical, warn
