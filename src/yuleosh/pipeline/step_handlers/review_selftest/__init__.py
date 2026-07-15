"""
review_selftest — 自测结果审查 (package split from review_selftest.py).

Maintains backward compatibility by re-exporting everything from core.py.
"""

from yuleosh.pipeline.step_handlers.review_selftest.core import (
    # Constants
    _SELFTEST_SCHEMA_VERSION,
    ASPICE_MAP,
    # Regression
    _load_prev_selftest_review,
    _compute_selftest_regression,
    # Environment
    _get_ci_environ,
    _get_tool_version,
    _collect_environment_info,
    # Formatting
    _generate_xunit_compatible,
    _generate_selftest_markdown,
    # History
    _get_run_history_path,
    _load_run_history,
    _save_run_history,
    # Discovery
    _discover_junit_xml,
    _discover_coverage_files,
    # Coverage
    _parse_lcov_coverage,
    # Spec analysis
    _extract_shall_statements,
    # Prompt building
    _build_selftest_review_prompt,
    # Main entry
    step_review_selftest,
    # Backward-compat thin wrappers (delegating to ci/review_helpers)
    _parse_junit_xml,
    _auto_map_shall_coverage,
    _find_test_source_files,
)
