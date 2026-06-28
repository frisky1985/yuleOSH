#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI MISRA Report — Core.

Part of the misra_report/ package split from misra_report.py (Phase 2.2).
"""

#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


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

from yuleosh.ci.misra_report.deviation import _deviation_to_dict, _is_deviation_expired
from yuleosh.ci.misra_report.traceability import generate_traceability_matrix


# ------------------------------------------------------------------
# Report schema version (R3-P0-6)
# ------------------------------------------------------------------

_MISRA_SCHEMA_VERSION = "misra-report-v2"
_SELFTEST_SCHEMA_VERSION = "selftest-review-v2"


# Default report directory for loading previous builds



# ------------------------------------------------------------------
# Multi-tool result types (G-15)
# ------------------------------------------------------------------




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
