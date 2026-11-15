# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""AUTOSAR Classic pipeline rules shared by prompting and output validation."""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT_AUTOSAR_RULES: dict = {
    "enabled": True,
    "source_root": "src",
    "required_dirs": [
        "src/application",
        "src/rte",
        "src/bsw/services",
        "src/bsw/ecu_abstraction",
        "src/bsw/mcal",
    ],
    "common_dirs": ["src/common"],
    "entry_files": ["src/main.c"],
}

# A layer may use its own headers and the layers listed here. The pipeline
# validator resolves quoted includes against generated headers, so custom MCAL
# names (Can.h, Dio.h, Adc.h, ...) are covered without a hardcoded driver list.
_DEPENDENCIES = {
    "src/application": {"src/application", "src/rte", "src/common"},
    "src/rte": {"src/rte", "src/common", "src/bsw/services", "src/bsw/ecu_abstraction"},
    "src/bsw/services": {"src/bsw/services", "src/bsw/ecu_abstraction", "src/common"},
    "src/bsw/ecu_abstraction": {"src/bsw/ecu_abstraction", "src/bsw/mcal", "src/common"},
    "src/bsw/mcal": {"src/bsw/mcal", "src/common"},
    "src/common": {"src/common"},
}
_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.MULTILINE)


def normalize_autosar_rules(value=None) -> dict | None:
    """Normalize ``codegen.autosar_classic`` from pipeline YAML."""
    if value is None or value is False:
        return None
    if isinstance(value, dict):
        if value.get("enabled", True) is False:
            return None
        rules = {**DEFAULT_AUTOSAR_RULES, **value}
    else:
        rules = dict(DEFAULT_AUTOSAR_RULES)
    rules["required_dirs"] = list(rules.get("required_dirs") or [])
    rules["common_dirs"] = list(rules.get("common_dirs") or [])
    rules["entry_files"] = list(rules.get("entry_files") or [])
    return rules


def build_autosar_prompt(rules: dict) -> str:
    """Render the pipeline-owned rules into the LLM system prompt."""
    required = "\n".join(f"     - `{d}/`" for d in rules["required_dirs"])
    common = ", ".join(f"`{d}/`" for d in rules.get("common_dirs", [])) or "`src/common/`"
    return f"""
8. AUTOSAR CLASSIC LAYERING HARD RULE (pipeline-enforced):
   - Generate C/H sources under these required pipeline directories:
{required}
     Shared AUTOSAR standard types belong in {common}.
   - Dependency direction is Application SWC -> RTE -> BSW Services /
     ECU Abstraction -> MCAL. Application files may include only their own,
     RTE and common headers. RTE must not include MCAL directly. MCAL must
     not include any upper-layer header.
   - Application SWCs contain requirement logic and call only `Rte_*` ports.
     RTE contains interface mapping/glue, not business state machines.
     ECU Abstraction hides channels/board routing. MCAL is the only layer
     allowed to contain target register or peripheral access.
   - Give every module a paired header with its public API. Keep `main.c`
     (when needed) as a composition root for init/runnable dispatch only.
     NEVER place all requirements in `main.c` or one monolithic source file.
   - The pipeline validates these directories and include dependencies after
     every generation round. Violations are returned for repair; they are not
     warnings and must be fixed by reorganizing/regenerating the files.
"""


def _layer_of(rel_path: str) -> str | None:
    for layer in sorted(_DEPENDENCIES, key=len, reverse=True):
        if rel_path.startswith(layer + "/"):
            return layer
    return None


def validate_autosar_output(out_dir: str | Path, rules: dict) -> str:
    """Return pipeline violations for the final/generated C source tree."""
    root = Path(out_dir)
    source_root = rules.get("source_root", "src")
    sources = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".c", ".h"}
    ]
    rel_paths = {p.relative_to(root).as_posix(): p for p in sources}
    errors: list[str] = []

    for required in rules["required_dirs"]:
        if not any(rel.startswith(required.rstrip("/") + "/") for rel in rel_paths):
            errors.append(f"AUTOSAR: missing required layer `{required}/` — generate C/H module(s) there.")

    allowed_dirs = set(rules["required_dirs"]) | set(rules.get("common_dirs", []))
    entry_files = set(rules.get("entry_files", []))
    for rel in sorted(rel_paths):
        if rel in entry_files or not rel.startswith(source_root.rstrip("/") + "/"):
            continue
        if not any(rel.startswith(d.rstrip("/") + "/") for d in allowed_dirs):
            errors.append(f"AUTOSAR: `{rel}` is outside the configured layer directories; move it to the correct layer.")

    headers = {p.name: rel for rel, p in rel_paths.items() if p.suffix.lower() == ".h"}
    for rel, path in sorted(rel_paths.items()):
        source_layer = _layer_of(rel)
        if source_layer is None:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for include in _INCLUDE_RE.findall(content):
            target_rel = headers.get(Path(include).name)
            if not target_rel:
                continue  # system/external header — compiler owns resolution
            target_layer = _layer_of(target_rel)
            if target_layer and target_layer not in _DEPENDENCIES[source_layer]:
                errors.append(
                    f"AUTOSAR: `{rel}` illegally includes `{include}` from `{target_layer}/`; "
                    f"allowed dependencies for `{source_layer}/` are {sorted(_DEPENDENCIES[source_layer])}."
                )

    return "\n".join(errors)
