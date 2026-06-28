#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""CI MISRA Report — backward-compatible re-export package."""

import logging
log = logging.getLogger("ci.misra_report")

from yuleosh.ci.misra_report.models import (ToolResult, merge_tool_results)
from yuleosh.ci.misra_report.core import (_normalize_misra_year, _load_ci_config, _extract_excluded_rules, _extract_excluded_files, load_rule_definitions, _extract_file_path, _is_valid_source_path, parse_cppcheck_output, group_by_rule, _classify_rule_type, enrich_with_definitions, _count_source_lines, compute_summary_stats, get_tool_version, get_ruleset_version, get_ci_environ, _load_prev_report, _compute_prev_build_diff, generate_json_report, _compute_category_breakdown, _serialize_group, _format_delta, generate_markdown_report, print_summary, save_report, save_merged_report)
from yuleosh.ci.misra_report.deviation import (_deviation_to_dict, _is_deviation_expired, _match_deviation)
from yuleosh.ci.misra_report.traceability import (_enrich_traceability_with_tests, generate_traceability_matrix, generate_fix_tasks)
from yuleosh.ci.misra_report.cli import (main)
