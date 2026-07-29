#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Project Auto-Detection — discover project type from `.yuleosh.yaml`.

Scans project root for `.yuleosh.yaml` and returns structured project info.

Usage::

    from yuleosh.project_detection import detect_project

    info = detect_project(project_dir)
    # info == {
    #     "name": "yuleASR-BSW",
    #     "type": "autosar",
    #     "language": "c",
    #     "target": "s32k312",
    #     "pipeline_template": "autosar",
    #     "ci_layers": {...},
    #     "cross_compile": {...},
    #     "misra": {...},
    #     "coverage": {...},
    # }
"""

import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("project_detection")

# Map project type → template name
TYPE_TO_TEMPLATE = {
    "autosar": "autosar-classic",
    "yuleasr": "yuleasr",
    "baremetal": "baremetal-safety",
    "freertos": "freertos-misra",
    "arm-cmsis": "arm-cmsis",
    "stm32-hal": "stm32-hal",
    "esp32": "esp32-idf",
    "zephyr": "zephyr-rtos",
    "generic-embedded-c": "generic-embedded-c",
    "generic-python": "generic-python",
    "unit-test-harness": "unit-test-harness",
}


def detect_project(project_dir: str) -> Optional[dict]:
    """Detect project configuration from ``.yuleosh.yaml`` in project root.

    Returns a dict with project metadata and resolved pipeline configuration,
    or ``None`` if no ``.yuleosh.yaml`` is found.
    """
    yaml_path = Path(project_dir) / ".yuleosh.yaml"
    if not yaml_path.exists():
        return None

    try:
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except Exception as e:
        log.warning("Failed to parse %s: %s", yaml_path, e)
        return None

    if not raw:
        return None

    project = raw.get("project", {})
    project_type = project.get("type", "")
    pipeline = raw.get("pipeline", {})

    # Resolve template name
    template_name = pipeline.get("template", "") or TYPE_TO_TEMPLATE.get(project_type, "")

    # Resolve the actual template path
    template_dir = _resolve_template_dir(template_name, project_dir)

    result = {
        "name": project.get("name", ""),
        "type": project_type,
        "language": project.get("language", ""),
        "target": project.get("target", ""),
        "pipeline_template": template_name,
        "pipeline_config": raw.get("pipeline", {}),
        "ci_layers": pipeline.get("ci_layers", {}),
        "cross_compile": raw.get("cross_compile", {}),
        "misra": raw.get("misra", {}),
        "coverage": raw.get("coverage", {}),
        "template_dir": str(template_dir) if template_dir else None,
        "_raw": raw,
    }

    return result


def resolve_pipeline_config(project_dir: str) -> Optional[dict]:
    """Resolve the full pipeline config for a project.

    Merges project-level overrides from ``.yuleosh.yaml`` with the
    template's default ``pipeline/config.yaml``.

    Returns a dict with ``steps`` and ``ci_layers`` keys, or None
    if no config can be resolved.
    """
    info = detect_project(project_dir)
    if not info:
        return None

    template_dir = info.get("template_dir")
    if not template_dir:
        return None

    # Load template pipeline config
    template_config_path = Path(template_dir) / "pipeline" / "config.yaml"
    if not template_config_path.exists():
        return None

    try:
        import yaml
        with open(template_config_path, "r") as f:
            template_cfg = yaml.safe_load(f)
    except Exception as e:
        log.warning("Failed to load template config %s: %s", template_config_path, e)
        return None

    if not template_cfg:
        return None

    return {
        "steps": template_cfg.get("steps", []),
        "ci_layers": template_cfg.get("ci_layers", {}),
        "review_gates": template_cfg.get("review_gates", []),
        "tools": template_cfg.get("tools", {}),
    }


def _resolve_template_dir(template_name: str, project_dir: str) -> Optional[Path]:
    """Resolve template directory matching yuleOSH template search order."""
    from yuleosh.templates import resolve_template
    tpl = resolve_template(template_name, project_root=project_dir)
    if tpl:
        dir_str = tpl.get("_dir")
        if dir_str:
            return Path(dir_str)
    return None
