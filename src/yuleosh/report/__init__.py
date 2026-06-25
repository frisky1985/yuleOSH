#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Report generation module for yuleOSH CI.

Provides:
  - report_exporter: Generate JSON + Markdown + Excel CI reports
  - card_generator: Generate quality summary cards (Feishu-ready)

Reports are output to .yuleosh/reports/ after each CI layer run.
"""

from yuleosh.report.exporter import generate_layer_report, generate_final_report
from yuleosh.report.card_generator import generate_quality_card
from yuleosh.report.feishu_notifier import post_quality_card_to_feishu

__all__ = [
    "generate_layer_report",
    "generate_final_report",
    "generate_quality_card",
    "post_quality_card_to_feishu",
]
