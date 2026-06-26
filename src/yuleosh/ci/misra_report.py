#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
MISRA C:2023 Report Formatter

Parses cppcheck MISRA output (text format) and produces structured
JSON and Markdown reports grouped by rule number and severity.

Usage:
    python3 ci/misra_report.py --input misra_output.txt --output-dir reports/
    python3 ci/misra_report.py --format json    # parse from stdin or file
    python3 ci/misra_report.py --format markdown

Integration:
    Called by ci/stages.py -> run_misra_check()
    Rule definitions loaded from misra-rules.yaml
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
    yaml = None  # type: ignore[assignment]

log = logging.getLogger("ci.misra_report")


# ------------------------------------------------------------------
# Report schema version (R3-P0-6)
# ------------------------------------------------------------------

_MISRA_SCHEMA_VERSION = "misra-report-v2"
_SELFTEST_SCHEMA_VERSION = "selftest-review-v2"


# Default report directory for loading previous builds



# ------------------------------------------------------------------
# Multi-tool result types (G-15)
# ------------------------------------------------------------------


@dataclass
class ToolResult:
    """Result from a single MISRA analysis tool.

    Attributes
    ----------
    tool_name : str
        Tool identifier: "cppcheck" | "clang-tidy" | "ai-review" | etc.
    violations : list[dict]
        Parsed violation dicts (same format as parse_cppcheck_output returns).
    status : str
        Execution status: "passed" | "failed" | "skipped".
    """
    tool_name: str = ""
    violations: list[dict] = field(default_factory=list)
    status: str = "skipped"


def merge_tool_results(results: list[ToolResult]) -> dict:
    """Merge multiple tool results into a unified report.

    Deduplicates same rule/file/line/col combinations across tools,
    tags each violation with its source tool(s), and computes combined
    statistics.

    Parameters
    ----------
    results : list[ToolResult]
        Tool results from cppcheck, clang-tidy, AI-review, etc.

    Returns
    -------
    dict with keys:
        - merged_violations: list of unified violation dicts
        - combined_stats: combined summary statistics
        - tool_contributions: per-tool violation counts
    """
    seen: dict[tuple, dict] = {}
    tool_contributions: dict[str, int] = {}

    for tr in results:
        tool_contributions[tr.tool_name] = tool_contributions.get(tr.tool_name, 0) + len(tr.violations)
        for v in tr.violations:
            # Dedup key: (rule_id, file, line, col)
            key = (v.get("rule_id", ""), v.get("file", ""), v.get("line", 0), v.get("col", 0))
            if key in seen:
                # Merge tags — append tool if not already listed
                existing = seen[key]
                tools_set = set(existing.get("_tools", [tr.tool_name]))
                tools_set.add(tr.tool_name)
                existing["_tools"] = sorted(tools_set)
            else:
                v["_tools"] = [tr.tool_name]
                seen[key] = v

    merged = list(seen.values())

    # Combined stats
    total_violations = len(merged)
    severity_counts: dict[str, int] = defaultdict(int)
    unique_files: set[str] = set()

    for v in merged:
        sev = v.get("severity", "unknown")
        severity_counts[sev] += 1
        fname = v.get("file", "")
        if fname:
            unique_files.add(fname)

    return {
        "merged_violations": merged,
        "combined_stats": {
            "total_violations": total_violations,
            "total_tools": len(results),
            "severity_counts": dict(severity_counts),
            "unique_files": sorted(unique_files),
        },
        "tool_contributions": tool_contributions,
        "tool_statuses": {tr.tool_name: tr.status for tr in results},
    }

# Default paths
# misra-rules.yaml lives at the workspace root (4 levels up: ci/ → yuleosh/ → src/ → workspace)
_DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent / "misra-rules.yaml"
_DEFAULT_OUTPUT_DIR = Path(".yuleosh") / "reports"
_DEFAULT_REPORT_DIR = _DEFAULT_OUTPUT_DIR

# Path to ci-config.yaml (project root > .yuleosh/ci-config.yaml)
_DEFAULT_CI_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".yuleosh" / "ci-config.yaml"

# Regex patterns for cppcheck MISRA output
# Typical cppcheck MISRA line (--addon=misra):
#   src/main.c:42:5: style: misra-c2023-10.1: [misra-c2012-10.1] Operands shall not be of inappropriate type
#   src/main.c:42:5: style: (information) MISRA rule 17.7
_PATTERN_CPPCHECK = re.compile(
    r"^(?P<file>[^\n:]+):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<severity>error|warning|style|performance|portability|information):\s*"
    r"(?P<message>.+)$", re.MULTILINE
)

# Pattern for MISRA addon rule extraction
_PATTERN_MISRA_RULE = re.compile(
    r"misra-c(?P<year>\d{4})-(?P<rule>\d+\.\d+)", re.IGNORECASE
)


# MISRA year normalization: cppcheck 2.17 outputs misra-c2012-*, but our
# rule definitions use misra-c2023-*.  Normalize all to misra-c2023-*.
_MISRA_YEAR_MAP = {"2012": "2023"}


def _normalize_misra_year(rule_id: str) -> str:
    """Normalize MISRA year, e.g. misra-c2012-17.7 -> misra-c2023-17.7.

    Keeps IDs that already use the canonical year (2023) unchanged.
    Unknown years are passed through as-is.
    """
    m = re.match(r"misra-c(\d{4})-(.+)$", rule_id)
    if not m:
        return rule_id
    year = m.group(1)
    canonical = _MISRA_YEAR_MAP.get(year)
    if canonical is not None:
        return f"misra-c{canonical}-{m.group(2)}"
    return rule_id

# Fallback: cppcheck text-format addon
_PATTERN_TEXT_RULE = re.compile(
    r"misra rule[:\s]+(?P<rule>\d+\.\d+)", re.IGNORECASE
)


def _load_ci_config() -> dict:
    """Load ci-config.yaml and return the raw parsed dict.

    R5-P1-1: Reads excluded_rules, excluded_files, and deviation alm_ticket
    fields from the MISRA section of ci-config.yaml.

    Returns empty dict if the file is missing or fails to parse.
    """
    path = _DEFAULT_CI_CONFIG_PATH
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _extract_excluded_rules(config: dict | None = None) -> list[str]:
    """Extract excluded MISRA rules from ci-config.yaml.

    Reads from:
    - ``misra.suppress_rules`` (explicit suppression list)
    - ``misra.rules`` where ``enabled: false``
    - ``misra.profiles.*.rule_overrides`` where ``enabled: false``

    Parameters
    ----------
    config : dict | None
        Pre-loaded ci-config dict. If None, loads it automatically.

    Returns
    -------
    list[str]
        Sorted list of excluded rule IDs.
    """
    if config is None:
        config = _load_ci_config()

    excluded: set[str] = set()

    misra_block = config.get("misra", {})
    if not isinstance(misra_block, dict):
        return []

    # 1. suppress_rules
    suppress = misra_block.get("suppress_rules", [])
    if isinstance(suppress, list):
        for s in suppress:
            excluded.add(str(s))

    # 2. rules with enabled: false
    rules_block = misra_block.get("rules", {})
    if isinstance(rules_block, dict):
        for rule_id, rule_cfg in rules_block.items():
            if isinstance(rule_cfg, dict) and not rule_cfg.get("enabled", True):
                excluded.add(str(rule_id))

    # 3. profile rule_overrides with enabled: false
    profiles_block = misra_block.get("profiles", {})
    if isinstance(profiles_block, dict):
        for prof_name, prof_cfg in profiles_block.items():
            if not isinstance(prof_cfg, dict):
                continue
            for ovr in prof_cfg.get("rule_overrides", []):
                if isinstance(ovr, dict) and not ovr.get("enabled", True):
                    excluded.add(str(ovr.get("rule", "")))

    return sorted(r for r in excluded if r)


def _extract_excluded_files(config: dict | None = None) -> list[str]:
    """Extract excluded file patterns from ci-config.yaml.

    Reads file patterns from misra.deviations entries where status
    is "rejected" or "closed" (effectively excluding those files
    from violation tracking).

    Parameters
    ----------
    config : dict | None
        Pre-loaded ci-config dict. If None, loads it automatically.

    Returns
    -------
    list[str]
        Sorted list of excluded file patterns.
    """
    if config is None:
        config = _load_ci_config()

    excluded: set[str] = set()

    misra_block = config.get("misra", {})
    if not isinstance(misra_block, dict):
        return []

    # Deviations with non-standard status that effectively exclude files
    deviations = misra_block.get("deviations", [])
    if isinstance(deviations, list):
        for d in deviations:
            if isinstance(d, dict):
                status = str(d.get("status", "")).lower()
                if status in ("rejected", "closed"):
                    fp = d.get("file", "")
                    if fp:
                        excluded.add(str(fp))

    return sorted(r for r in excluded if r)


def load_rule_definitions(rules_path: Optional[Path] = None) -> dict:
    """Load MISRA rule definitions from YAML file.

    Returns a dict keyed by rule ID (e.g. 'misra-c2023-17.7').
    Returns empty dict if the YAML file is missing or fails to parse.
    """
    path = rules_path or _DEFAULT_RULES_PATH
    if not path.exists():
        log.warning("MISRA rules file not found: %s", path)
        return {}

    if yaml is None:
        log.warning("PyYAML not installed — cannot load rule definitions")
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or "meta" not in data:
            log.warning("Invalid MISRA rules file format: %s", path)
            return {}
        # Return all entries including 'meta' for version metadata
        # Callers iterate by key; 'meta' is a reserved key used for report metadata
        return data
    except (yaml.YAMLError, OSError, Exception) as e:
        log.warning("Failed to load MISRA rules from %s: %s", path, e)
        return {}


_SOURCE_EXTENSIONS = (".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx")


def _extract_file_path(raw: str) -> str | None:
    """Extract the actual source file path from a cppcheck output "file" field.

    The cppcheck regex `[^:]+` greedily captures across newlines, producing
    multi-line strings like::

        "    if (x) return;\n    ^\nsrc/file.c"

    This function finds the last meaningful path-like segment (containing /
    and a known C/C++ extension) from such strings.  Returns None if no
    valid path can be extracted.
    """
    if not raw:
        return None

    # Fast path: clean single-line path
    if "\n" not in raw and "\r" not in raw:
        if not raw.startswith((" ", "\t")):
            if any(sep in raw for sep in ("/", "\\")):
                if any(raw.endswith(ext) for ext in _SOURCE_EXTENSIONS):
                    return raw

    # Multi-line context: extract the last path-like token with a
    # directory separator and C/C++ extension
    tokens = re.split(r"[\s\r\n^\|]+", raw)
    best: str | None = None
    for token in tokens:
        t = token.strip()
        if any(sep in t for sep in ("/", "\\")):
            if any(t.endswith(ext) for ext in _SOURCE_EXTENSIONS):
                best = t
    return best


def _is_valid_source_path(path: str) -> bool:
    """Check if a path looks like a valid source file path (extracted from
    potential multi-line context)."""
    return _extract_file_path(path) is not None


def parse_cppcheck_output(text: str) -> list[dict]:
    """Parse cppcheck MISRA output text into structured violation records.

    Returns a list of dicts with keys:
      - file, line, col, severity, message, rule_id (str or None)

    Post-processing:
      - Normalizes misra-c2012-* rule IDs to misra-c2023-* (R2-P0-1)
      - Filters out non-source-path "file" values from multi-line context (R2-P0-3)
    """
    violations = []
    for match in _PATTERN_CPPCHECK.finditer(text):
        violation = match.groupdict()
        message = violation["message"]

        # R2-P0-3: The cppcheck regex [^:]+ greedily captures across
        # newlines, so the "file" may include code context lines. Extract
        # the actual source path from the raw value.
        raw_file = violation["file"]
        clean_file = _extract_file_path(raw_file)
        if clean_file is None:
            continue
        violation["file"] = clean_file

        # Try to extract MISRA rule ID from message
        rule_match = _PATTERN_MISRA_RULE.search(message)
        if rule_match:
            rule_id = f"misra-c{rule_match.group('year')}-{rule_match.group('rule')}"
        else:
            text_match = _PATTERN_TEXT_RULE.search(message)
            if text_match:
                # Infer year from context (current year = 2023)
                rule_id = f"misra-c2023-{text_match.group('rule')}"
            else:
                rule_id = None

        # R2-P0-1: Normalize MISRA year to 2023 (backward-compatible)
        if rule_id is not None:
            rule_id = _normalize_misra_year(rule_id)

        violation["rule_id"] = rule_id
        violation["line"] = int(violation["line"])
        violation["col"] = int(violation["col"])
        violations.append(violation)

    return violations


def group_by_rule(violations: list[dict]) -> dict:
    """Group violations by rule ID and severity.

    Returns {rule_id: {title, severity, category, description, violations: [...]}}
    """
    groups: dict = {}
    for v in violations:
        rid = v.get("rule_id", "unknown")
        if rid not in groups:
            groups[rid] = {
                "rule_id": rid,
                "violations": [],
                "count": 0,
                "files": set(),
            }
        groups[rid]["violations"].append(v)
        groups[rid]["count"] += 1
        groups[rid]["files"].add(v.get("file", ""))

    # Convert sets to lists for JSON serialization
    for g in groups.values():
        g["files"] = sorted(g["files"])

    return groups


def _classify_rule_type(rule_id: str | None) -> str:
    """Classify a rule ID as "directive" or "rule".

    R5-P1-4:
    - Rule IDs starting with "dir-" or "Dir" → directive
    - Rule IDs starting with a digit → rule
    - Falling back: check rule_defs if known directive, else "rule"
    - None or empty → "rule" (default for non-MISRA violations)
    """
    if not rule_id:
        return "rule"
    rid_lower = rule_id.lower()
    if rid_lower.startswith("dir") or rid_lower.startswith("misra-c2023-dir"):
        return "directive"
    # Check if the last segment starts with "Dir" (e.g. "misra-c2023-Dir-4.12")
    last_segment = rule_id.split("-")[-1] if "-" in rule_id else rule_id
    if last_segment.startswith("Dir") or last_segment.startswith("dir"):
        return "directive"
    return "rule"


def enrich_with_definitions(
    groups: dict,
    rule_defs: dict,
) -> dict:
    """Merge rule definitions into the grouped violations.

    R5-P1-4: Adds ``type`` field ("directive" or "rule") based on
    rule_id prefix classification.

    For each rule_id in groups, if a definition exists in rule_defs,
    add title, severity, category, and description fields.
    """
    for rule_id, group in groups.items():
        if rule_id == "meta":
            continue
        if rule_id in rule_defs:
            defn = rule_defs[rule_id]
            group["title"] = defn.get("title", "")
            group["severity_category"] = defn.get("severity", "")
            group["category"] = defn.get("category", "")
            group["description"] = defn.get("description", "")
        else:
            group["title"] = ""
            group["severity_category"] = "unknown"
            group["category"] = "unrecognized"
            group["description"] = ""
        # R5-P1-4: Classify rule type
        group["type"] = _classify_rule_type(rule_id)
    return groups


def _count_source_lines(file_paths: list[str]) -> int:
    """Count non-empty, non-comment lines across a list of source files.

    Returns total effective lines (rough LOC).  Files that cannot be read
    are silently skipped.
    """
    total = 0
    for fp in file_paths:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    # Skip C-style single-line comments and block-comment markers
                    if stripped.startswith(("//", "/*", "*")):
                        continue
                    total += 1
        except (OSError, FileNotFoundError, PermissionError):
            pass
    return total


def compute_summary_stats(violations: list[dict], groups: dict, rule_defs: dict | None = None) -> dict:
    """Compute summary statistics from violations and groups.

    Returns dict with:
      - total_violations: int
      - total_rules_violated: int
      - severity_counts: dict[severity] -> count
      - misra_classification: dict[str, int] (required/advisory/directive/project_specific)
      - unique_files: list[str]
      - per_file_counts: dict[file] -> count
      - total_kloc: float (thousands of lines of effective source code)
      - violations_per_kloc: float (violation density per KLOC)
    """
    rule_defs = rule_defs or {}
    severity_counts: dict[str, int] = defaultdict(int)
    misra_classification: dict[str, int] = defaultdict(int)
    per_file_counts: dict[str, int] = defaultdict(int)
    unique_files: set[str] = set()

    for v in violations:
        sev = v.get("severity", "unknown")
        severity_counts[sev] += 1
        fname = v.get("file", "")
        if fname:
            unique_files.add(fname)
            per_file_counts[fname] += 1

        # Classify by MISRA category (required/advisory/directive)
        rid = v.get("rule_id", "")
        if rid == "meta":
            misra_sev = "project_specific"
        elif rid in rule_defs:
            misra_sev = rule_defs[rid].get("severity", "project_specific").lower()
        elif rid and not rid.startswith("unknown"):
            misra_sev = "project_specific"
        else:
            misra_sev = "project_specific"
        if misra_sev not in ("required", "advisory", "directive"):
            misra_sev = "project_specific"
        misra_classification[misra_sev] += 1

    # R2-P0-2: Count effective source lines across all unique files
    sorted_uf = sorted(unique_files)
    total_loc = _count_source_lines(sorted_uf)
    total_kloc = round(total_loc / 1000.0, 2)
    total_violations = len(violations)
    violations_per_kloc = round(total_violations / total_kloc, 2) if total_kloc > 0 else 0.0

    # R5-P1-4: Count directive vs rule violations
    directive_count = 0
    rule_count = 0
    for v in violations:
        rid = v.get("rule_id", "") or ""
        rtype = _classify_rule_type(rid)
        if rtype == "directive":
            directive_count += 1
        else:
            rule_count += 1

    return {
        "total_violations": total_violations,
        "total_rules_violated": len(groups),
        "severity_counts": dict(severity_counts),
        "misra_classification": dict(misra_classification),
        "unique_files": sorted_uf,
        "per_file_counts": dict(per_file_counts),
        "total_kloc": total_kloc,
        "violations_per_kloc": violations_per_kloc,
        # R5-P1-4: Directive vs Rule counts
        "directive_count": directive_count,
        "rule_count": rule_count,
    }


def get_tool_version() -> str:
    """Get cppcheck version string from --version."""
    try:
        result = subprocess.run(
            ["cppcheck", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() or result.stderr.strip() or "unknown"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "unknown"


def get_ruleset_version(rule_defs: dict) -> str:
    """Extract ruleset version from rule_defs meta.

    Prefers 'ruleset_version' over plain 'version' for specificity.
    """
    if "meta" in rule_defs:
        meta = rule_defs["meta"]
        return str(meta.get("ruleset_version", meta.get("version", "unknown")))
    return "unknown"


def get_ci_environ() -> dict:
    """Extract CI environment variables for build_id, commit_sha, branch."""
    return {
        "build_id": os.environ.get("BUILD_ID", ""),
        "commit_sha": os.environ.get("GIT_COMMIT", ""),
        "branch": os.environ.get("GIT_BRANCH", ""),
    }


ASPICE_MAP = {
    "SWE.4": {
        "description": "Software Unit Verification",
        "bp1": {
            "id": "SWE.4.BP1",
            "title": "Develop unit verification specification including regression strategy",
            "report_section": "Violations by Rule / Traceability Matrix",
        },
        "bp2": {
            "id": "SWE.4.BP2",
            "title": "Verify software units",
            "report_section": "Summary / Severity Breakdown",
        },
    },
}


def _load_prev_report(output_dir: str | Path) -> dict | None:
    """Load the previous MISRA report for trend comparison (R3-P0-4).

    Reads the last misra-report.json from the output directory.
    Returns None if no previous report exists or on parse failure.
    """
    prev_path = Path(output_dir) / "misra-report.json"
    if not prev_path.exists():
        return None
    try:
        with open(prev_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, Exception) as e:
        log.warning("Failed to load previous report %s: %s", prev_path, e)
        return None


def _compute_prev_build_diff(
    current_summary: dict,
    current_violations: list[dict],
    prev_report: dict | None,
) -> dict:
    """Compute difference between current and previous build (R3-P0-4).

    Returns dict with:
      - total_violations_delta: int (current - prev)
      - severity_deltas: dict[severity, int]
      - files_added: list[str] (files in current but not prev)
      - files_removed: list[str] (files in prev but not current)
    """
    if prev_report is None:
        return {}

    prev_summary = prev_report.get("summary", {})
    prev_violations = prev_report.get("violations_raw", [])

    # Violation count delta
    prev_total = prev_summary.get("total_violations", 0)
    curr_total = current_summary.get("total_violations", 0)
    total_violations_delta = curr_total - prev_total

    # Severity deltas
    prev_sev = prev_summary.get("severity_counts", {})
    curr_sev = current_summary.get("severity_counts", {})
    severity_deltas: dict[str, int] = {}
    all_sevs = set(list(prev_sev.keys()) + list(curr_sev.keys()))
    for sev in sorted(all_sevs):
        delta = curr_sev.get(sev, 0) - prev_sev.get(sev, 0)
        if delta != 0:
            severity_deltas[sev] = delta

    # File sets
    prev_files = set(v.get("file", "") for v in prev_violations if v.get("file"))
    curr_files = set(v.get("file", "") for v in current_violations if v.get("file"))
    files_added = sorted(curr_files - prev_files)
    files_removed = sorted(prev_files - curr_files)

    return {
        "total_violations_delta": total_violations_delta,
        "severity_deltas": severity_deltas,
        "files_added": files_added,
        "files_removed": files_removed,
    }


def generate_json_report(
    violations: list[dict],
    groups: dict,
    summary: dict,
    rule_defs: dict | None = None,
    output_dir: str | Path | None = None,
    deviations: list | None = None,
) -> str:
    """Generate a JSON formatted report.

    R3-P0-6: Adds schema_version to JSON root.
    R3-P0-4: Adds prev_build_diff if previous report exists.
    """
    rule_defs = rule_defs or {}
    deviations = deviations or []
    ci_env = get_ci_environ()

    # R3-P0-4: Load previous report for trend comparison
    prev_build_diff = {}
    if output_dir is not None:
        prev_report = _load_prev_report(output_dir)
        prev_build_diff = _compute_prev_build_diff(summary, violations, prev_report)

    # R3-P0-2: Count deviations by risk level
    # R4-P0-2: Build formatted deviations list for root-level field
    deviation_risk_counts: dict[str, int] = defaultdict(int)
    deviation_entries: list[dict] = []
    for dev in deviations:
        dev_dict = _deviation_to_dict(dev)
        rl = dev_dict.get("risk_level", "mid")
        deviation_risk_counts[rl] += 1
        deviation_entries.append(dev_dict)

    # R5-P1-1: Extract excluded rules and files from ci-config.yaml
    ci_config = _load_ci_config()
    excluded = {
        "rules": _extract_excluded_rules(ci_config),
        "files": _extract_excluded_files(ci_config),
    }

    # R5-P1-4: Add directive/rule type info to each group
    serialized_groups: dict[str, dict] = {}
    directive_group_count = 0
    rule_group_count = 0
    for k, v in groups.items():
        sg = _serialize_group(v)
        sg["type"] = _classify_rule_type(k)
        if sg["type"] == "directive":
            directive_group_count += 1
        else:
            rule_group_count += 1
        serialized_groups[k] = sg

    report = {
        "schema_version": _MISRA_SCHEMA_VERSION,  # R3-P0-6
        "generated_at": datetime.now().isoformat(),
        "tool": "cppcheck --addon=misra",
        "tool_version": get_tool_version(),
        "ruleset_version": get_ruleset_version(rule_defs),
        "standard": "MISRA C:2023",
        "build_id": ci_env["build_id"],
        "commit_sha": ci_env["commit_sha"],
        "branch": ci_env["branch"],
        # R5-P1-1: Excluded rules and files from config
        "excluded": excluded,
        "deviations": deviation_entries,  # R4-P0-2
        "aspice_map": ASPICE_MAP,
        "summary": summary,
        "violations_raw": violations,
        "groups": serialized_groups,
        # R5-P1-4: Directive vs Rule summary
        "type_classification": {
            "directive_count": directive_group_count + summary.get("directive_count", 0),
            "rule_count": rule_group_count + summary.get("rule_count", 0),
        },
        # 三级分类: code_category breakdown
        "code_category_breakdown": _compute_category_breakdown(violations),
    }

    # R3-P0-4: Add prev_build_diff if non-empty
    if prev_build_diff:
        report["prev_build_diff"] = prev_build_diff

    return json.dumps(report, indent=2, ensure_ascii=False, default=str)


def _compute_category_breakdown(violations: list[dict]) -> dict:
    """Compute breakdown of violations by code_category (三级分类).

    Categories: business, third_party, template, unknown.
    """
    counts: dict[str, int] = {}
    for v in violations:
        cat = v.get("code_category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def _serialize_group(group: dict) -> dict:
    """Serialize a group dict, converting any non-serializable types."""
    result = {}
    for k, v in group.items():
        if isinstance(v, set):
            result[k] = sorted(v)
        else:
            result[k] = v
    return result


def _format_delta(delta: int) -> str:
    """Format a numeric delta with +/- sign for markdown display."""
    if delta > 0:
        return f"+{delta}"
    return str(delta)


def generate_markdown_report(
    violations: list[dict],
    groups: dict,
    summary: dict,
    rule_defs: dict,
    deviations: list | None = None,
) -> str:
    """Generate a Markdown formatted MISRA report.

    R3-P0-3: Includes "Deviation Overview" section.
    R3-P0-1: Includes "3-Way Traceability" table.
    R3-P0-4: Includes "📈 vs Previous Build" trend section.
    """
    deviations = deviations or []
    lines = [
        "# MISRA C:2023 Compliance Report",
        "",
        f"> Generated: {datetime.now().isoformat()}",
        f"> Tool: cppcheck --addon=misra",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|:-------|------:|",
        f"| Total Violations | {summary['total_violations']} |",
        f"| Rules Violated | {summary['total_rules_violated']} |",
        f"| Files Affected | {len(summary['unique_files'])} |",
        f"| Total KLOC | {summary.get('total_kloc', 0)} |",
        f"| Violations / KLOC | {summary.get('violations_per_kloc', 0)} |",
        f"",
        "### MISRA Classification Breakdown",
        f"",
    ]

    mc = summary.get("misra_classification", {})
    if mc:
        lines.append("| Category | Count |")
        lines.append("|:---------|------:|")
        for cat in ["required", "advisory", "directive", "project_specific"]:
            count = mc.get(cat, 0)
            if count > 0:
                icon = {"required": "🔴", "advisory": "🟡", "directive": "🔵", "project_specific": "⚪"}.get(cat, "•")
                lines.append(f"| {icon} {cat.capitalize()} | {count} |")
        lines.append("")

    # R5-P1-4: Directive vs Rule breakdown
    dir_count = summary.get("directive_count", 0)
    rule_count_val = summary.get("rule_count", 0)
    if dir_count > 0 or rule_count_val > 0:
        lines.append("### Classification: Directive vs Rule")
        lines.append("")
        lines.append("| Type | Count |")
        lines.append("|:-----|------:|")
        if dir_count > 0:
            lines.append(f"| 📘 Directive | {dir_count} |")
        if rule_count_val > 0:
            lines.append(f"| 📗 Rule | {rule_count_val} |")
        lines.append("")

    # R5-P1-1: Excluded rules and files section
    ci_config_report = _load_ci_config()
    excluded_rules_report = _extract_excluded_rules(ci_config_report)
    excluded_files_report = _extract_excluded_files(ci_config_report)
    if excluded_rules_report or excluded_files_report:
        lines.append("## Excluded Items (from ci-config.yaml)")
        lines.append("")
        if excluded_rules_report:
            lines.append("### Excluded Rules")
            lines.append("")
            lines.append("| Rule |")
            lines.append("|:-----|")
            for r in excluded_rules_report:
                lines.append(f"| `{r}` |")
            lines.append("")
        if excluded_files_report:
            lines.append("### Excluded Files")
            lines.append("")
            lines.append("| File Pattern |")
            lines.append("|:-------------|")
            for f in excluded_files_report:
                lines.append(f"| `{f}` |")
            lines.append("")

    lines.append("### Severity Breakdown")

    for sev in ["error", "warning", "style", "performance", "portability", "information"]:
        count = summary["severity_counts"].get(sev, 0)
        if count > 0:
            icon = {"error": "❌", "warning": "⚠️", "style": "🎨", "performance": "⚡",
                    "portability": "🔗", "information": "ℹ️"}.get(sev, "•")
            lines.append(f"| {icon} {sev.capitalize()} | {count} |")

    lines.append("")
    lines.append("### Code Category Breakdown")
    lines.append("")
    category_counts = _compute_category_breakdown(violations)
    for cat in ["business", "third_party", "template", "unknown"]:
        count = category_counts.get(cat, 0)
        if count > 0:
            icon = {"business": "🔴", "third_party": "🟡", "template": "🟢", "unknown": "⚪"}.get(cat, "•")
            lines.append(f"| {icon} {cat.capitalize()} | {count} |")
    lines.append("")
    lines.append("### Files with Violations")
    lines.append("")
    for fname, count in sorted(summary["per_file_counts"].items()):
        lines.append(f"- `{fname}`: {count} violation(s)")
    lines.append("")

    # Violations by Rule Group
    sorted_rules = sorted(groups.items(), key=lambda x: -x[1]["count"])
    if sorted_rules:
        lines.append("## Violations by Rule")
        lines.append("")

        for rule_id, group in sorted_rules:
            title = group.get("title", rule_defs.get(rule_id, {}).get("title", ""))
            sev = group.get("severity_category", rule_defs.get(rule_id, {}).get("severity", "unknown"))
            sev_icon = {"required": "🔴", "advisory": "🟡", "unknown": "⚪"}.get(sev, "⚪")
            # R5-P1-4: Show rule type
            rtype = group.get("type", _classify_rule_type(rule_id))
            type_icon = "📘" if rtype == "directive" else "📗"
            lines.append(f"### {type_icon} [{rtype.capitalize()}] {rule_id}: {title}")
            lines.append(f"")
            lines.append(f"- **Type**: {type_icon} {rtype.capitalize()}")
            lines.append(f"- **Severity**: {sev_icon} {sev}")
            lines.append(f"- **Count**: {group['count']}")
            lines.append(f"- **Files**: {', '.join(group['files'][:5])}")
            if len(group['files']) > 5:
                lines.append(f"  *...and {len(group['files']) - 5} more file(s)*")
            lines.append("")
            lines.append("| File | Line | Column | Severity | Message |")
            lines.append("|:-----|:----|:------|:---------|:--------|")

            for v in group["violations"][:20]:
                msg = v["message"][:80]
                lines.append(f"| `{v['file']}` | {v['line']} | {v['col']} | {v['severity']} | {msg} |")

            if len(group["violations"]) > 20:
                lines.append(f"| ... | ... | ... | ... | *{len(group['violations']) - 20} more* |")
            lines.append("")

    # R3-P0-3: Deviation Overview section
    if deviations:
        lines.append("## Deviation Overview")
        lines.append("")
        # R5-P2-1: Include ALM ticket column
        lines.append("| Rule ID | File Pattern | Reason | Status | Risk Level | Expires | Approved By | ALM Ticket |")
        lines.append("|:--------|:-------------|:-------|:-------|:-----------|:--------|:------------|:-----------|")
        for dev in deviations:
            dd = _deviation_to_dict(dev)
            risk_icon = {"low": "🟢", "mid": "🟡", "high": "🔴"}.get(dd.get("risk_level", "mid"), "⚪")
            expiry = dd.get("expires", "—")
            if expiry != "—" and _is_deviation_expired(expiry):
                expiry += " ⚠️ EXPIRED"
            alm_ticket = dd.get("alm_ticket", "")
            alm_str = f"`{alm_ticket}`" if alm_ticket else "—"
            lines.append(
                f"| {dd.get('deviation_rule', '')} "
                f"| `{dd.get('file_pattern', '')}` "
                f"| {dd.get('reason', '')[:60]} "
                f"| {dd.get('status', 'pending')} "
                f"| {risk_icon} {dd.get('risk_level', 'mid')} "
                f"| {expiry} "
                f"| {dd.get('approved_by', '—')} "
                f"| {alm_str} |"
            )
        lines.append("")
    else:
        lines.append("## Deviation Overview")
        lines.append("")
        lines.append("No deviations recorded. All violations are in unresolved state.")
        lines.append("")

    # R3-P0-4: vs Previous Build trend
    # Try to compute prev_build_diff from the existing report
    prev_report = _load_prev_report("./.yuleosh/reports")
    if prev_report:
        pbd = _compute_prev_build_diff(summary, violations, prev_report)
        if pbd:
            lines.append("## 📈 vs Previous Build")
            lines.append("")
            total_delta = pbd.get("total_violations_delta", 0)
            delta_str = _format_delta(total_delta)
            if total_delta > 0:
                emoji = "🔴"
            elif total_delta < 0:
                emoji = "🟢"
            else:
                emoji = "⚪"
            lines.append(f"| Metric | Delta |")
            lines.append(f"|:-------|------:|")
            lines.append(f"| {emoji} Total Violations | {delta_str} |")

            for sev, delta in sorted(pbd.get("severity_deltas", {}).items()):
                sev_emoji = {"error": "❌", "warning": "⚠️", "style": "🎨",
                             "performance": "⚡", "portability": "🔗",
                             "information": "ℹ️"}.get(sev, "•")
                lines.append(f"| {sev_emoji} {sev.capitalize()} | {_format_delta(delta)} |")

            added = pbd.get("files_added", [])
            removed = pbd.get("files_removed", [])
            if added:
                for f in added[:5]:
                    lines.append(f"| 🆕 New file `{f}` | — |")
                if len(added) > 5:
                    lines.append(f"| ... and {len(added) - 5} more new files | — |")
            if removed:
                for f in removed[:5]:
                    lines.append(f"| 🗑️ Removed file `{f}` | — |")
                if len(removed) > 5:
                    lines.append(f"| ... and {len(removed) - 5} more removed files | — |")
            lines.append("")

    # R3-P0-1: 3-Way Traceability table
    lines.append("## 3-Way Traceability (Rule→Spec→Test)")
    lines.append("")
    lines.append("| Rule ID | Spec Ref | Implementation | Test Ref |")
    lines.append("|:--------|:---------|:---------------|:---------|")

    # Collect the top-N violated rules
    for rule_id, _ in sorted_rules[:10]:
        defn = rule_defs.get(rule_id, {})
        spec_ref = defn.get("spec_ref", "—")
        impl_ref = defn.get("impl_ref", defn.get("check_method", "—"))
        test_ref = defn.get("test_ref", "—")
        lines.append(f"| {rule_id} | {spec_ref} | {impl_ref} | {test_ref} |")
    if len(sorted_rules) > 10:
        lines.append(f"| ... and {len(sorted_rules) - 10} more rules | ... | ... | ... |")
    lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    critical_rules = [r for r, g in sorted_rules if g.get("severity_category") == "required" and g["count"] > 0]
    if critical_rules:
        lines.append("### Required Rules to Fix (Priority)")
        lines.append("")
        for rule_id in critical_rules[:10]:
            defn = rule_defs.get(rule_id, {})
            title = defn.get("title", groups[rule_id].get("title", ""))
            desc = defn.get("description", "")
            lines.append(f"- **{rule_id}**: {title}")
            if desc:
                lines.append(f"  - {desc}")
        lines.append("")

    lines.append("---")
    lines.append("*Report generated by yuleOSH MISRA Report Formatter*")
    return "\n".join(lines)


def save_report(
    violations: list[dict],
    groups: dict,
    summary: dict,
    rule_defs: dict,
    output_dir: str | Path,
    deviations: list | None = None,
) -> tuple[Path, Path, Path, Path]:
    """Save JSON, Markdown, traceability matrix, and Excel reports to disk.

    Parameters
    ----------
    deviations : list[tuple[str, str]] | None
        List of deviation records. Accepts both tuple and dict formats.
        Matched violations get fix_status="acknowledged" in traceability.

    Returns tuple of (json_path, md_path, trace_path, excel_path).
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # R3-P0-4: Pass output_dir to generate_json_report for prev_build_diff
    # R3-P0-6: schema_version handled inside generate_json_report
    json_path = out_dir / "misra-report.json"
    json_content = generate_json_report(
        violations, groups, summary, rule_defs,
        output_dir=out_dir, deviations=deviations,
    )
    json_path.write_text(json_content, encoding="utf-8")

    # R3-P0-1: Pass test_dir for 3-way traceability enrichment
    test_dir = str(out_dir.parent / "tests") if (out_dir.parent / "tests").is_dir() else None

    # Markdown (with enriched deviation details)
    md_path = out_dir / "misra-report.md"
    md_content = generate_markdown_report(
        violations, groups, summary, rule_defs,
        deviations=deviations,
    )
    md_path.write_text(md_content, encoding="utf-8")

    # Traceability matrix (JSON) with 3-way traceability + deviation risk info
    trace_path = out_dir / "misra-traceability.json"
    trace_data = generate_traceability_matrix(
        violations, rule_defs,
        deviations=deviations,
        test_dir=test_dir,  # R3-P0-1
    )
    trace_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "total_entries": len(trace_data),
                "traceability": trace_data,
            },
            indent=2, ensure_ascii=False, default=str,
        ),
        encoding="utf-8",
    )

    # Excel report
    from yuleosh.evidence.excel_writer import ExcelReportWriter
    excel_path = out_dir / "misra-report.xlsx"
    try:
        writer = ExcelReportWriter(out_dir)
        writer.write_misra_report(
            violations=violations,
            groups=groups,
            summary=summary,
            rule_defs=rule_defs,
            deviations=deviations,
            output_path=excel_path,
        )
        log.info("MISRA Excel report saved: %s", excel_path)
    except Exception as e:
        log.warning("Failed to generate MISRA Excel report: %s", e)

    log.info("MISRA report saved: %s, %s, %s, %s", json_path, md_path, trace_path, excel_path)
    return json_path, md_path, trace_path, excel_path


def save_merged_report(
    merge_result: dict,
    rule_defs: dict,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Save a multi-tool merged report to disk.

    Parameters
    ----------
    merge_result : dict
        Output from merge_tool_results().
    rule_defs : dict
        Rule definitions from load_rule_definitions().
    output_dir : str | Path
        Output directory.

    Returns tuple of (json_path, md_path).
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_at": datetime.now().isoformat(),
        "standard": "MISRA C:2023",
        "multi_tool": True,
        "tool_statuses": merge_result.get("tool_statuses", {}),
        "tool_contributions": merge_result.get("tool_contributions", {}),
        "combined_stats": merge_result.get("combined_stats", {}),
        "merged_violations": merge_result.get("merged_violations", []),
    }

    json_path = out_dir / "misra-report-merged.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md_lines = [
        "# MISRA C:2023 Multi-Tool Compliance Report",
        "",
        f"> Generated: {datetime.now().isoformat()}",
        "",
        "## Tool Summary",
        "",
        "| Tool | Status | Violations |",
        "|:----|:------|:----------|",
    ]
    for tool_name, status in sorted(merge_result.get("tool_statuses", {}).items()):
        count = merge_result.get("tool_contributions", {}).get(tool_name, 0)
        md_lines.append(f"| {tool_name} | {status} | {count} |")

    stats = merge_result.get("combined_stats", {})
    md_lines.extend([
        "",
        "## Combined Summary",
        "",
        f"| Metric | Value |",
        f"|:-------|------:|",
        f"| Total Unique Violations | {stats.get('total_violations', 0)} |",
        f"| Files Affected | {len(stats.get('unique_files', []))} |",
        f"| Tools Used | {stats.get('total_tools', 0)} |",
        "",
    ])

    md_path = out_dir / "misra-report-merged.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    log.info("Merged MISRA report saved: %s, %s", json_path, md_path)
    return json_path, md_path


def print_summary(summary: dict) -> None:
    """Print a human-readable summary to stdout."""
    print(f"\n  📊 MISRA C:2023 Summary:")
    print(f"     Total violations: {summary['total_violations']}")
    print(f"     Rules violated:   {summary['total_rules_violated']}")
    print(f"     Files affected:   {len(summary['unique_files'])}")
    print(f"     Total KLOC:       {summary.get('total_kloc', 0)}")
    print(f"     Violations/KLOC:  {summary.get('violations_per_kloc', 0)}")
    for sev in ["error", "warning", "style", "performance", "portability", "information"]:
        count = summary["severity_counts"].get(sev, 0)
        if count > 0:
            icon = {"error": "❌", "warning": "⚠️", "style": "🎨", "performance": "⚡",
                    "portability": "🔗", "information": "ℹ️"}.get(sev, "•")
            print(f"       {icon} {sev}: {count}")
    print()


def _deviation_to_dict(dev: tuple | dict | object) -> dict:
    """Normalize a deviation entry to a dict with common fields.

    Accepts:
    - tuple[str, str] (backward compat: rule_id, file_pattern)
    - dict (rich format with rule_id, file_pattern, reason, approved_by,
      risk_level, expires, status, alm_ticket)
    - MisraDeviation dataclass object

    R5-P2-1: Also propagates ``alm_ticket`` field if present.
    """
    if isinstance(dev, dict):
        return {
            "deviation_rule": dev.get("rule_id", ""),
            "file_pattern": dev.get("file_pattern", ""),
            "reason": dev.get("reason", ""),
            "approved_by": dev.get("approved_by", ""),
            "risk_level": dev.get("risk_level", "mid"),
            "expires": dev.get("expires", ""),
            "status": dev.get("status", "pending"),
            # R5-P2-1: ALM ticket reference
            "alm_ticket": dev.get("alm_ticket", ""),
        }
    if isinstance(dev, tuple):
        # Tuple format: (rule_id, file_pattern) or (rule_id, file_pattern, reason, ...)
        fields = tuple(dev)
        return {
            "deviation_rule": fields[0] if len(fields) > 0 else "",
            "file_pattern": fields[1] if len(fields) > 1 else "",
            "reason": fields[2] if len(fields) > 2 else "",
            "approved_by": fields[3] if len(fields) > 3 else "",
            "risk_level": fields[4] if len(fields) > 4 else "mid",
            "expires": fields[5] if len(fields) > 5 else "",
            "status": fields[6] if len(fields) > 6 else "pending",
            "alm_ticket": fields[7] if len(fields) > 7 else "",
        }
    # Object with attribute access (MisraDeviation)
    return {
        "deviation_rule": getattr(dev, "rule_id", ""),
        "file_pattern": getattr(dev, "file_pattern", ""),
        "reason": getattr(dev, "reason", ""),
        "approved_by": getattr(dev, "approved_by", ""),
        "risk_level": getattr(dev, "risk_level", "mid"),
        "expires": getattr(dev, "expires", ""),
        "status": getattr(dev, "status", "pending"),
        # R5-P2-1: ALM ticket reference
        "alm_ticket": getattr(dev, "alm_ticket", ""),
    }


def _is_deviation_expired(expires_str: str) -> bool:
    """Check if a deviation has expired based on its expires date.

    Returns True if expires is a valid ISO date and is in the past.
    Returns False if expires is empty or unparseable (assumes no expiry).
    """
    if not expires_str:
        return False
    try:
        from datetime import datetime
        expiry = datetime.fromisoformat(expires_str)
        return expiry < datetime.now()
    except (ValueError, TypeError):
        return False


def _match_deviation(
    rule_id: str,
    file_path: str,
    deviations: list,  # list[tuple | dict] — normalized internally
) -> tuple[bool, dict | None]:
    """Check if a violation matches any deviation record.

    Supports both simple tuple format (rule_id, file_pattern) and rich
    dict format with risk_level, expires, reason, approved_by, status.

    Returns (matched, deviation_info) where deviation_info contains
    the matched deviation details if found, including:
      - deviation_rule, file_pattern
      - reason, approved_by, risk_level, expires, status
      - risk_level_info: str description of risk level
      - expiration_status: dict with is_expired / expires fields
    """
    import fnmatch
    for dev in deviations:
        dev_dict = _deviation_to_dict(dev)
        dev_rule = dev_dict["deviation_rule"]
        dev_pattern = dev_dict["file_pattern"]

        # Match rule
        rule_match = (dev_rule == rule_id)
        if not rule_match and dev_rule:
            # Try suffix matching (e.g. rule_id="misra-c2023-17.7", dev="17.7")
            suffix = dev_rule.split("-")[-1] if "-" in dev_rule else dev_rule
            rule_match = rule_id.endswith(suffix)

        if rule_match and fnmatch.fnmatch(file_path, dev_pattern):
            # R3-P0-2: Enrich with risk_level info + expiration check
            risk_level = dev_dict.get("risk_level", "mid")
            expires = dev_dict.get("expires", "")
            is_expired = _is_deviation_expired(expires)

            info = dict(dev_dict)
            info["risk_level_info"] = {
                "low": "Low risk — accepted with documentation",
                "mid": "Medium risk — accepted with review",
                "high": "High risk — requires urgent resolution",
            }.get(risk_level, "Unknown risk level")
            info["expiration_status"] = {
                "is_expired": is_expired,
                "expires": expires,
            }
            return True, info
    return False, None


def _enrich_traceability_with_tests(
    rule_defs: dict,
    test_dir: str | None = None,
) -> dict[str, dict]:
    """Map rules to their implementation and test IDs (R3-P0-1).

    Attempts to discover test files from the test directory that
    correspond to each rule. Returns a dict keyed by rule_id with:
      - spec_id: str (from rule_defs spec_ref)
      - impl_id: str (from rule_defs impl_ref or auto-generated)
      - test_id: str (discovered test file or ID)
    """
    result: dict[str, dict] = {}

    for rid, defn in rule_defs.items():
        if rid == "meta":
            continue
        spec_id = defn.get("spec_ref", "")
        impl_id = defn.get("impl_ref", defn.get("check_method", ""))
        test_id = ""

        # Try to discover test files from test directory
        if test_dir and impl_id:
            test_dir_path = Path(test_dir)
            if test_dir_path.is_dir():
                # Look for test files matching the rule or implementation
                rule_num = rid.split("-")[-1] if "-" in rid else rid
                for tf in test_dir_path.rglob("*.py"):
                    if rule_num.replace(".", "_") in tf.stem:
                        test_id = str(tf.relative_to(test_dir_path.parent) if test_dir_path.parent else tf)
                        break

        result[rid] = {
            "spec_id": spec_id,
            "impl_id": impl_id,
            "test_id": test_id,
        }
    return result


def generate_traceability_matrix(
    violations: list[dict],
    rule_defs: dict,
    deviations: list | None = None,
    test_dir: str | None = None,
) -> list[dict]:
    """Build traceability: Rule ID → File:Line → Spec Ref → Fix Status.

    R3-P0-1: Adds impl_id, test_ref for 3-way traceability (rule→spec→test).
    R3-P0-2: Adds risk_level_info, expiration_status for deviations.

    Returns a list of dicts, one per violation, with:
      - rule_id: str
      - file: str
      - line: int
      - col: int
      - severity: str
      - message: str
      - spec_ref: str (from rule_defs, or "" if unknown)
      - impl_id: str (R3-P0-1, from rule_defs impl_ref or check_method)
      - test_ref: str (R3-P0-1, discovered test file if any)
      - check_method: str (from rule_defs, or "" if unknown)
      - auto_checkable: bool (from rule_defs, default True)
      - fix_status: str ("unresolved" | "acknowledged" | "suppressed")
      - deviation_ref: dict | None (matched deviation details, if any)
      - risk_level_info: str | None (R3-P0-2, if deviation matched)
      - expiration_status: dict | None (R3-P0-2, if deviation matched)

    Backward compatible: deviations parameter accepts both list[tuple]
    and list[dict] formats.
    """
    deviations = deviations or []

    # R3-P0-1: Enrich with test discovery
    trace_tests = _enrich_traceability_with_tests(rule_defs, test_dir=test_dir)

    traceability = []
    for v in violations:
        rid = v.get("rule_id", "unknown")
        defn = rule_defs.get(rid, {})
        file_path = v.get("file", "")

        matched, dev_info = _match_deviation(rid, file_path, deviations)
        fix_status = "acknowledged" if matched else "unresolved"

        # R3-P0-1: 3-way traceability fields
        three_way = trace_tests.get(rid, {})
        spec_id = three_way.get("spec_id", defn.get("spec_ref", ""))
        impl_id = three_way.get("impl_id", defn.get("impl_ref", defn.get("check_method", "")))
        test_id = three_way.get("test_id", "")

        entry = {
            "rule_id": rid,
            "file": file_path,
            "line": v.get("line", 0),
            "col": v.get("col", 0),
            "severity": v.get("severity", ""),
            "message": v.get("message", ""),
            "spec_ref": spec_id,
            "impl_id": impl_id,
            "test_ref": test_id,
            "check_method": defn.get("check_method", ""),
            "auto_checkable": bool(defn.get("auto_checkable", True)),
            "fix_status": fix_status,
        }
        # R3-P0-2: Enrich with risk_level info + expiration if deviation matched
        if matched and dev_info:
            entry["deviation_ref"] = dev_info
            entry["risk_level_info"] = dev_info.get("risk_level_info", "")
            entry["expiration_status"] = dev_info.get("expiration_status", {})

        traceability.append(entry)
    return traceability


def generate_fix_tasks(
    project_dir: str,
    violations: list[dict],
    rule_defs: dict,
    deviations: list | None = None,
) -> list[str]:
    """Generate fix task .md files for each unresolved violation.

    Creates one .md file per violated rule under
    ``.yuleosh/fix-tasks/misra-{rule_id}.md``.

    Violations matching deviation records are excluded from fix tasks
    since they are already "acknowledged".

    Accepts both old tuple format and new dict format for deviations.

    Returns list of file paths created.
    """
    from datetime import datetime

    deviations = deviations or []
    fix_dir = Path(project_dir) / ".yuleosh" / "fix-tasks"
    fix_dir.mkdir(parents=True, exist_ok=True)

    # Group violations by rule_id, skipping acknowledged ones
    rule_groups: dict[str, list[dict]] = {}
    for v in violations:
        rid = v.get("rule_id", "unknown")
        file_path = v.get("file", "")
        # Skip deviations-acknowledged violations
        matched, _ = _match_deviation(rid, file_path, deviations)
        if matched:
            continue
        rule_groups.setdefault(rid, []).append(v)

    created_files: list[str] = []
    for rule_id, vs in sorted(rule_groups.items()):
        defn = rule_defs.get(rule_id, {})
        title = defn.get("title", rule_id)
        spec_ref = defn.get("spec_ref", "")
        severity = defn.get("severity", "unknown")

        lines = [
            f"# MISRA Fix Task: {rule_id}",
            "",
            f"> Generated: {datetime.now().isoformat()}",
            f"> Severity: {severity}",
            f"> Spec Ref: {spec_ref}",
            "",
            f"## Rule: {title}",
            "",
            f"{defn.get('description', '')}",
            "",
            "## Violations",
            "",
            "| # | File | Line | Col | Message |",
            "|--:|:-----|:----|:----|:--------|",
        ]
        for idx, v in enumerate(vs, 1):
            msg = v.get("message", "")[:80]
            lines.append(f"| {idx} | `{v.get('file', '')}` | {v.get('line', 0)} | {v.get('col', 0)} | {msg} |")

        lines.extend([
            "",
            "## Fix Checklist",
            "",
            "- [ ] Understand the violation context",
            "- [ ] Apply fix to source code",
            "- [ ] Re-run MISRA check to verify fix",
            "- [ ] Update traceability matrix",
            "- [ ] Document deviation if fix is not feasible",
            "",
            "---",
            "*Generated by yuleOSH MISRA fix-task generator*",
        ])

        file_path = fix_dir / f"misra-{rule_id}.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")
        created_files.append(str(file_path))
        log.info("MISRA fix task created: %s", file_path)

    return created_files


# ------------------------------------------------------------------
# CLI Entry Point
# ------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MISRA C:2023 Report Formatter — parse cppcheck MISRA output",
    )
    parser.add_argument(
        "--input", "-i",
        help="Path to cppcheck MISRA output file (reads from stdin if omitted)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=str(_DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {_DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--rules", "-r",
        default=str(_DEFAULT_RULES_PATH),
        help=f"Path to misra-rules.yaml (default: {_DEFAULT_RULES_PATH})",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "markdown", "summary", "excel"],
        default="summary",
        help="Output format (default: summary to stdout)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress summary output",
    )

    args = parser.parse_args()

    # Read input
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("No MISRA output provided — nothing to report.")
        return

    # Load rule definitions
    rule_defs = load_rule_definitions(Path(args.rules))

    # Parse
    violations = parse_cppcheck_output(text)
    if not violations:
        print("No MISRA violations found in input.")
        return

    # Group and enrich
    groups = group_by_rule(violations)
    groups = enrich_with_definitions(groups, rule_defs)
    summary = compute_summary_stats(violations, groups, rule_defs)

    # Output
    if args.format == "json":
        print(generate_json_report(violations, groups, summary, rule_defs))
    elif args.format == "markdown":
        print(generate_markdown_report(violations, groups, summary, rule_defs))
    elif args.format == "excel":
        # Generate Excel only and save to output_dir
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        writer = ExcelReportWriter(out_dir)
        excel_path = writer.write_misra_report(
            violations=violations,
            groups=groups,
            summary=summary,
            rule_defs=rule_defs,
            deviations=None,
            output_path=out_dir / "misra-report.xlsx",
        )
        if not args.quiet:
            print_summary(summary)
            print(f"  Excel: {excel_path}")
    else:
        # Save reports and print summary
        json_path, md_path, trace_path, excel_path = save_report(
            violations, groups, summary, rule_defs, args.output_dir
        )
        if not args.quiet:
            print_summary(summary)
            print(f"  Reports saved:")
            print(f"    JSON: {json_path}")
            print(f"    MD:   {md_path}")
            print(f"    Trace: {trace_path}")
            print(f"    Excel: {excel_path}")


if __name__ == "__main__":
    main()
