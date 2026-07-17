#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI KPI — backward-compatible re-export package.

This package replaces the monolithic kpi.py (Phase 2.2 refactor).
"""

import logging
log = logging.getLogger("ci.kpi")

from yuleosh.ci.kpi.utils import (_ensure_dir, _load_latest_misra_entry, _load_latest_coverage_entry, _parse_ts, _load_baseline, DEFAULT_THRESHOLDS)
from yuleosh.ci.kpi.trend import (_get_misra_trend_avg, _get_coverage_trend_avg)
from yuleosh.ci.kpi.stability import (_ensure_process_kpi_dir, record_process_stability, _load_process_kpi_entries, get_process_stability_summary, generate_process_baseline_report)
from yuleosh.ci.kpi.defects import (_ensure_defect_escape_dir, record_defect_escape, _load_defect_escape_entries, get_defect_escape_summary)
from yuleosh.ci.kpi.report import (kpi_status, kpi_baseline_save, kpi_baseline_compare)
from yuleosh.ci.kpi.kg_source import (get_kg_coverage_metrics, get_kg_health_metrics, get_kg_confidence_metrics, get_kg_metrics_summary)
