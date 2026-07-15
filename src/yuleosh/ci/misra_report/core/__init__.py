"""
misra_report.core — Top-level backward-compatible re-exports.

Sourced from: core/config.py, core/parser.py, core/analysis.py, core/reporting.py
"""

# Config/constants
from yuleosh.ci.misra_report.core.config import (
    _MISRA_SCHEMA_VERSION,
    _SELFTEST_SCHEMA_VERSION,
    _PATTERN_CPPCHECK,
    _PATTERN_MISRA_RULE,
    _PATTERN_TEXT_RULE,
    _normalize_misra_year,
    _load_ci_config,
    _extract_excluded_rules,
    _extract_excluded_files,
    load_rule_definitions,
    get_tool_version,
    get_ruleset_version,
    get_ci_environ,
    _count_source_lines,
)

# Parsing
from yuleosh.ci.misra_report.core.parser import (
    _extract_file_path,
    _is_valid_source_path,
    parse_cppcheck_output,
)

# Analysis
from yuleosh.ci.misra_report.core.analysis import (
    group_by_rule,
    _classify_rule_type,
    enrich_with_definitions,
    compute_summary_stats,
    _load_prev_report,
    _compute_prev_build_diff,
    _compute_category_breakdown,
)

# Reporting
from yuleosh.ci.misra_report.core.reporting import (
    generate_json_report,
    _serialize_group,
    _format_delta,
    generate_markdown_report,
    save_report,
    save_merged_report,
    print_summary,
)
