#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Template Gallery — built-in project templates for yuleOSH.

Each template lives in its own subdirectory with:
  - template.yaml   — metadata manifest
  - specs/spec.md   — default OpenSpec specification
  - pipeline/config.yaml — pre-configured pipeline steps
  - src/            — initial code skeleton
  - .gitignore      — language-specific ignore patterns

Search priority (TG-REQ-002):
  1. Project-local: <project_root>/.yuleosh/templates/<name>/
  2. User-local:    ~/.yuleosh/templates/<name>/
  3. Built-in:      <package>/yuleosh/templates/<name>/
"""

import os
from pathlib import Path
from typing import Optional

import yaml

TEMPLATES_DIR = Path(__file__).resolve().parent


def _discover_builtin_templates() -> list[dict]:
    """Discover all built-in templates from the templates/ directory."""
    templates = []
    for d in sorted(TEMPLATES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        tpl_yaml = d / "template.yaml"
        if tpl_yaml.exists():
            try:
                meta = yaml.safe_load(tpl_yaml.read_text(encoding="utf-8"))
                if meta and meta.get("name"):
                    meta["_dir"] = str(d)
                    meta["_source"] = "builtin"
                    templates.append(meta)
            except Exception as e:
                import logging
                logging.getLogger("templates").warning(
                    "Failed to load %s: %s", tpl_yaml, e
                )
    return templates


def _discover_user_templates(base_dir: str | Path) -> list[dict]:
    """Discover templates from a user/project-local directory."""
    base = Path(base_dir)
    templates = []
    if not base.exists():
        return templates
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        tpl_yaml = d / "template.yaml"
        if tpl_yaml.exists():
            try:
                meta = yaml.safe_load(tpl_yaml.read_text(encoding="utf-8"))
                if meta and meta.get("name"):
                    meta["_dir"] = str(d)
                    meta["_source"] = "user" if ".yuleosh" in str(base) else "project"
                    templates.append(meta)
            except Exception:
                pass
    return templates


def list_templates(project_root: Optional[str | Path] = None) -> list[dict]:
    """List all discoverable templates, deduplicated by name.

    Search order (TG-REQ-002): project-local > user-local > built-in.
    User-local overrides built-in, project-local overrides both.
    """
    # Collect in order (first wins)
    seen: set[str] = set()
    result: list[dict] = []

    # 1. Project-local
    if project_root:
        proj_dir = Path(project_root) / ".yuleosh" / "templates"
        for t in _discover_user_templates(proj_dir):
            if t["name"] not in seen:
                seen.add(t["name"])
                result.append(t)

    # 2. User-local
    user_dir = Path.home() / ".yuleosh" / "templates"
    for t in _discover_user_templates(user_dir):
        if t["name"] not in seen:
            seen.add(t["name"])
            result.append(t)

    # 3. Built-in
    for t in _discover_builtin_templates():
        if t["name"] not in seen:
            seen.add(t["name"])
            result.append(t)

    return result


def resolve_template(name: str, project_root: Optional[str | Path] = None) -> Optional[dict]:
    """Resolve a template by name with search priority (TG-REQ-002)."""
    templates = list_templates(project_root)
    for t in templates:
        if t["name"] == name:
            return t
    return None


def get_template_dir(template: dict) -> Optional[Path]:
    """Get the resolved filesystem path for a template."""
    dir_str = template.get("_dir")
    if dir_str:
        return Path(dir_str)
    return None
