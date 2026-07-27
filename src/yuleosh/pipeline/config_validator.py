# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Config Validator — Validate ARXML + JSON config for pipeline readiness.

Checks:
  - ARXML syntax correctness
  - Configuration completeness (missing modules)
  - Module interdependency satisfaction

Usage:
    yuleosh validate-config --arxml path/to/config.arxml
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("pipeline.config_validator")

# ── Well-known AUTOSAR BSW modules and their dependencies ─────────────────

BSW_MODULE_DEPENDENCIES = {
    "Can":        {"required": ["Mcu"], "optional": ["Port", "Dio"]},
    "CanIf":      {"required": ["Can"], "optional": []},
    "CanTp":      {"required": ["CanIf"], "optional": []},
    "CanSm":      {"required": ["CanIf"], "optional": []},
    "Lin":        {"required": ["Mcu"], "optional": ["Port", "Dio"]},
    "LinIf":      {"required": ["Lin"], "optional": []},
    "LinTp":      {"required": ["LinIf"], "optional": []},
    "Eth":        {"required": ["Mcu"], "optional": ["Port", "Dio"]},
    "EthIf":      {"required": ["Eth"], "optional": []},
    "Fr":         {"required": ["Mcu"], "optional": ["Port", "Dio"]},
    "FrIf":       {"required": ["Fr"], "optional": []},
    "Mcu":        {"required": [], "optional": []},
    "Port":       {"required": ["Mcu"], "optional": []},
    "Dio":        {"required": ["Mcu"], "optional": []},
    "Adc":        {"required": ["Mcu"], "optional": []},
    "Icu":        {"required": ["Mcu"], "optional": []},
    "Pwm":        {"required": ["Mcu", "Gpt"], "optional": ["Port"]},
    "Gpt":        {"required": ["Mcu"], "optional": []},
    "Wdg":        {"required": ["Mcu"], "optional": []},
    "WdgIf":      {"required": ["Wdg"], "optional": []},
    "Spi":        {"required": ["Mcu"], "optional": ["Port"]},
    "Dem":        {"required": ["Mcu"], "optional": []},
    "Det":        {"required": [], "optional": []},
    "Dcm":        {"required": ["CanTp", "LinTp", "FrIf"], "optional": ["Dem"]},
    "FiM":        {"required": ["Dem"], "optional": []},
    "EcuM":       {"required": ["Mcu"], "optional": ["Wdg", "Det"]},
    "BswM":       {"required": ["EcuM"], "optional": ["Dem", "FiM"]},
    "Os":         {"required": ["Mcu"], "optional": []},
    "Com":        {"required": ["CanIf", "LinIf", "FrIf", "EthIf"], "optional": []},
    "PduR":       {"required": ["CanIf", "LinIf", "FrIf", "EthIf"], "optional": []},
    "SchM":       {"required": ["Os"], "optional": []},
}

# Minimum required modules for a functional AUTOSAR stack
REQUIRED_MODULES = ["Mcu", "Port", "Dio", "Os"]


def validate_pipeline_config(
    project_dir: str = "",
    config_json: Optional[str] = None,
    arxml_content: Optional[str] = None,
) -> dict:
    """Validate configuration for pipeline readiness.

    Returns:
        {"valid": bool, "issues": list[str], "modules_found": list[str]}
    """
    issues = []
    modules_found = set()

    # 1. Parse config_json if provided
    if config_json:
        try:
            cfg = json.loads(config_json)
            # Extract module names from various formats
            if isinstance(cfg, dict):
                if "modules" in cfg:
                    for m in cfg["modules"]:
                        if isinstance(m, dict):
                            name = m.get("name") or m.get("module", "")
                            if name:
                                modules_found.add(name)
                    modules_found.update(cfg.get("enabled_modules", []))
                else:
                    for key in cfg:
                        if isinstance(cfg[key], dict) and "enabled" in cfg[key]:
                            modules_found.add(key)
        except json.JSONDecodeError as e:
            issues.append(f"Config JSON parse error: {e}")

    # 2. Parse ARXML if provided
    if arxml_content:
        arxml_modules = _extract_arxml_modules(arxml_content)
        modules_found.update(arxml_modules)
        # Check ARXML structure
        arxml_issues = _validate_arxml_syntax(arxml_content)
        issues.extend(arxml_issues)

    # 3. Check project files if no config provided
    if not config_json and not arxml_content and project_dir:
        project_path = Path(project_dir)
        # Scan .yuleosh directory for configs
        yuleosh_dir = project_path / ".yuleosh"
        if yuleosh_dir.exists():
            for cfg_file in yuleosh_dir.rglob("*.json"):
                try:
                    data = json.loads(cfg_file.read_text())
                    if isinstance(data, dict):
                        modules_found.update(data.get("modules", []))
                        for key in data:
                            if isinstance(data[key], dict) and "module" in data[key]:
                                modules_found.add(data[key]["module"])
                except (json.JSONDecodeError, OSError):
                    pass
            for arxml_file in yuleosh_dir.rglob("*.arxml"):
                arxml_modules = _extract_arxml_modules(arxml_file.read_text())
                modules_found.update(arxml_modules)

    # 4. Check minimum required modules
    for req in REQUIRED_MODULES:
        if req not in modules_found:
            issues.append(f"Missing required module: {req}")

    # 5. Check dependencies
    for mod in modules_found:
        if mod in BSW_MODULE_DEPENDENCIES:
            for dep in BSW_MODULE_DEPENDENCIES[mod]["required"]:
                if dep not in modules_found:
                    issues.append(f"Module '{mod}' requires '{dep}' but it is not configured")

    valid = len(issues) == 0
    return {
        "valid": valid,
        "issues": issues,
        "modules_found": sorted(modules_found),
        "project_dir": project_dir,
    }


def _validate_arxml_syntax(arxml_content: str) -> list[str]:
    """Validate basic ARXML syntax."""
    issues = []

    if not arxml_content or not arxml_content.strip():
        issues.append("ARXML content is empty")
        return issues

    # Check XML prolog
    if not arxml_content.lstrip().startswith("<?xml"):
        issues.append("ARXML: Missing XML prolog (<?xml ... ?>)")

    # Check root element
    if "<AUTOSAR" not in arxml_content:
        issues.append("ARXML: Missing root <AUTOSAR> element")

    # Check closing tag
    if "</AUTOSAR>" not in arxml_content:
        issues.append("ARXML: Missing closing </AUTOSAR> tag")

    # Check for unbalanced tags (basic)
    opens = arxml_content.count("<ECUC-MODULE-CONFIGURATION")
    closes = arxml_content.count("</ECUC-MODULE-CONFIGURATION")
    if opens != closes:
        issues.append(f"ARXML: Unbalanced ECUC-MODULE-CONFIGURATION tags ({opens} open, {closes} close)")

    return issues


def _extract_arxml_modules(arxml_content: str) -> list[str]:
    """Extract module names from ARXML content."""
    modules = []

    # Match ECUC-MODULE-CONFIGURATION module definitions
    pattern = r'<ECUC-MODULE-CONFIGURATION[^>]*>\s*<SHORT-NAME>\s*(\w+)\s*</SHORT-NAME>'
    for match in re.finditer(pattern, arxml_content, re.DOTALL):
        modules.append(match.group(1))

    # Also match simple module refs
    pattern2 = r'<MODULE-REF[^>]*>([^<]+)</MODULE-REF>'
    for match in re.finditer(pattern2, arxml_content):
        mod = match.group(1).strip()
        if "/" in mod:
            mod = mod.rsplit("/", 1)[-1]
        if mod and mod not in modules:
            modules.append(mod)

    return list(set(modules))


def cli_validate(args: list[str]) -> int:
    """CLI entry point for 'yuleosh validate-config'.

    Usage: yuleosh validate-config --arxml <path> [--json <path>]
    """
    import argparse
    parser = argparse.ArgumentParser(prog="yuleosh validate-config")
    parser.add_argument("--arxml", type=str, help="Path to ARXML config file")
    parser.add_argument("--json", type=str, help="Path to JSON config file")
    parser.add_argument("--project-dir", type=str, default=".", help="Project directory")
    parsed = parser.parse_args(args)

    config_json = None
    arxml_content = None

    if parsed.json:
        try:
            with open(parsed.json) as f:
                config_json = f.read()
        except FileNotFoundError:
            print(f"Error: JSON file not found: {parsed.json}", file=sys.stderr)
            return 1
        except OSError as e:
            print(f"Error reading JSON: {e}", file=sys.stderr)
            return 1

    if parsed.arxml:
        try:
            with open(parsed.arxml) as f:
                arxml_content = f.read()
        except FileNotFoundError:
            print(f"Error: ARXML file not found: {parsed.arxml}", file=sys.stderr)
            return 1
        except OSError as e:
            print(f"Error reading ARXML: {e}", file=sys.stderr)
            return 1

    result = validate_pipeline_config(
        project_dir=parsed.project_dir,
        config_json=config_json,
        arxml_content=arxml_content,
    )

    print(f"\n{'='*50}")
    print(f"  yuleOSH Config Validation Report")
    print(f"{'='*50}")
    print(f"  Status:      {'✅ VALID' if result['valid'] else '❌ INVALID'}")
    print(f"  Modules:     {len(result['modules_found'])} found")
    print(f"  Issues:      {len(result['issues'])}")
    print(f"{'='*50}")

    if result["modules_found"]:
        print(f"\n  Modules found:")
        for m in result["modules_found"]:
            print(f"    - {m}")

    if result["issues"]:
        print(f"\n  Issues:")
        for issue in result["issues"]:
            print(f"    ⚠ {issue}")

    print(f"\n{'='*50}\n")
    return 0 if result["valid"] else 1
