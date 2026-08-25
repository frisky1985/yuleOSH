#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Rule sink — extracts project rules from manual corrections and persists them
to .yuleosh/agents/LEARNED-RULES.md.

When a developer corrects a generated file, the diff between the LLM output
and the human-corrected version is analyzed to extract "do / don't" rules
that are appended to the project's agent rules file. On the next codegen run
the rules file is injected into the system prompt via the agent constraints
loading mechanism in pipeline/orchestrator.py.

Usage:
    sink = RuleSink(project_dir)
    rules = sink.record_correction("motor.c", original_content, corrected_content)
    # rules written to .yuleosh/agents/LEARNED-RULES.md

    # CLI convenience:
    result = cli_add_correction("motor_llm.c", "motor_human.c", project_dir)
    # {"rules_added": 2, "rules": ["Required: (void)timeMs;", "Forbidden: int64_t"]}
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

CATEGORY_TYPES = ("style", "safety", "api", "forbidden", "required")

_FORBIDDEN_PATTERNS = [
    (r"\bint64_t\b",  "int64_t causes ARM __aeabi_ldivmod linker errors — use uint32_t"),
    (r"\bdouble\b",   "double is 64-bit FP — use float on Cortex-M without FPU"),
    (r"\bmalloc\s*\(", "malloc() is forbidden in safety-critical code — use static allocation"),
    (r"\bfree\s*\(",  "free() is forbidden in safety-critical code"),
    (r"\bprintf\s*\(", "printf() pulls in large libc — use custom log functions"),
]

_REQUIRED_PATTERNS = [
    (r"\(void\)\s*\w+\s*;", "Use (void)param; to suppress -Wunused-parameter"),
    (r"#ifndef\s+\w+_H\b", "Header guard required: #ifndef HEADER_H / #define / #endif"),
    (r"#pragma once",       "Use #pragma once or header guard"),
    (r"\bstatic_assert\b",  "Use static_assert for compile-time contract checks"),
    (r"\bvolatile\b",       "Use volatile for hardware registers and ISR-shared variables"),
]

_RULE_OPEN = "<!-- RULE:"
_RULE_CLOSE = "<!-- /RULE -->"
_RULE_BLOCK_RE = re.compile(
    r"<!-- RULE: id=([\w-]+) category=(\w+) -->\s*\n"
    r"## (.+?)\n\n"
    r"(.+?)\n\n"
    r"\*\*DO:\*\* `(.+?)`\n\n"
    r"\*\*DON'T:\*\* `(.+?)`\n\n"
    r"\*Source: (.+?) — (.+?)\*\n\n",
    re.DOTALL,
)


@dataclass
class ExtractedRule:
    id: str
    category: str
    title: str
    description: str
    do_example: str
    dont_example: str
    source_file: str
    created_at: str


def _rule_id(title: str, source_file: str) -> str:
    return hashlib.sha256(f"{title}|{source_file}".encode("utf-8")).hexdigest()[:8]


def extract_rules_from_diff(
    original: str,
    corrected: str,
    file_path: str,
    context: str = "",
) -> list[ExtractedRule]:
    """Analyze diff between *original* (LLM output) and *corrected* (human fix).

    Returns up to 3 high-signal rules inferred from the changes.
    """
    rules: list[ExtractedRule] = []
    diff = list(difflib.unified_diff(
        original.splitlines(),
        corrected.splitlines(),
        lineterm="",
    ))

    added_lines = [ln[1:] for ln in diff if ln.startswith("+") and not ln.startswith("+++")]
    removed_lines = [ln[1:] for ln in diff if ln.startswith("-") and not ln.startswith("---")]

    # 1. Required patterns — lines added that match known must-haves
    for added in added_lines:
        for pat, reason in _REQUIRED_PATTERNS:
            if re.search(pat, added):
                title = f"Required: {added.strip()[:60]}"
                rule = ExtractedRule(
                    id=_rule_id(title, file_path),
                    category="required",
                    title=title,
                    description=reason,
                    do_example=added.strip()[:120],
                    dont_example="(omitted — caused the correction)",
                    source_file=file_path,
                    created_at=datetime.now().isoformat(),
                )
                if not any(r.id == rule.id for r in rules):
                    rules.append(rule)
                break
        if len(rules) >= 3:
            return rules[:3]

    # 2. Forbidden patterns — lines removed that match bad patterns
    for removed in removed_lines:
        for pat, reason in _FORBIDDEN_PATTERNS:
            if re.search(pat, removed):
                title = f"Forbidden: {removed.strip()[:60]}"
                rule = ExtractedRule(
                    id=_rule_id(title, file_path),
                    category="forbidden",
                    title=title,
                    description=reason,
                    do_example="(use alternative — see description)",
                    dont_example=removed.strip()[:120],
                    source_file=file_path,
                    created_at=datetime.now().isoformat(),
                )
                if not any(r.id == rule.id for r in rules):
                    rules.append(rule)
                break
        if len(rules) >= 3:
            return rules[:3]

    # 3. Naming convention changes — camelCase → snake_case
    if len(rules) < 3:
        for removed, added in zip(removed_lines[:10], added_lines[:10]):
            r_camel = re.findall(r"\b([a-z][A-Z][A-Za-z]+)\b", removed)
            a_snake = re.findall(r"\b([a-z]+_[a-z_]+)\b", added)
            if r_camel and a_snake:
                title = f"Style: use snake_case ({r_camel[0]} → {a_snake[0]})"
                rule = ExtractedRule(
                    id=_rule_id(title, file_path),
                    category="style",
                    title=title,
                    description=f"Naming convention correction in {file_path}.",
                    do_example=added.strip()[:80],
                    dont_example=removed.strip()[:80],
                    source_file=file_path,
                    created_at=datetime.now().isoformat(),
                )
                if not any(r.id == rule.id for r in rules):
                    rules.append(rule)
                break

    return rules[:3]


class RuleSink:
    """Writes extracted rules to .yuleosh/agents/LEARNED-RULES.md."""

    def __init__(self, project_dir: str) -> None:
        self.project_dir = Path(project_dir)
        self.rules_file = self.project_dir / ".yuleosh" / "agents" / "LEARNED-RULES.md"
        self.rules_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.rules_file.exists():
            self.rules_file.write_text(
                "# LEARNED-RULES.md — Auto-generated project rules\n\n"
                "> Rules extracted from human corrections to LLM-generated code.\n"
                "> Automatically included in codegen system prompts.\n\n",
                encoding="utf-8",
            )

    def add_rules(self, rules: list[ExtractedRule]) -> int:
        """Append new rules (deduplicated by id). Returns count added."""
        existing_ids = {r.id for r in self.load_rules()}
        added = 0
        with self.rules_file.open("a", encoding="utf-8") as f:
            for rule in rules:
                if rule.id in existing_ids:
                    continue
                f.write(
                    f"\n{_RULE_OPEN} id={rule.id} category={rule.category} -->\n"
                    f"## {rule.title}\n\n"
                    f"{rule.description}\n\n"
                    f"**DO:** `{rule.do_example}`\n\n"
                    f"**DON'T:** `{rule.dont_example}`\n\n"
                    f"*Source: {rule.source_file} — {rule.created_at[:10]}*\n\n"
                    f"{_RULE_CLOSE}\n"
                )
                existing_ids.add(rule.id)
                added += 1
        return added

    def load_rules(self) -> list[ExtractedRule]:
        """Parse LEARNED-RULES.md back to ExtractedRule structs."""
        if not self.rules_file.exists():
            return []
        text = self.rules_file.read_text(encoding="utf-8")
        rules: list[ExtractedRule] = []
        for m in _RULE_BLOCK_RE.finditer(text):
            rules.append(ExtractedRule(
                id=m.group(1),
                category=m.group(2),
                title=m.group(3).strip(),
                description=m.group(4).strip(),
                do_example=m.group(5).strip(),
                dont_example=m.group(6).strip(),
                source_file=m.group(7).strip(),
                created_at=m.group(8).strip(),
            ))
        return rules

    def format_for_prompt(
        self, rules: list[ExtractedRule], max_chars: int = 1500
    ) -> str:
        """Format rules as a DO/DON'T block for LLM system prompts."""
        if not rules:
            return ""
        do_rules = [r for r in rules if r.category in ("required", "api", "style")]
        dont_rules = [r for r in rules if r.category in ("forbidden", "safety")]
        lines = ["## Project-Learned Rules\n"]
        if do_rules:
            lines.append("### DO\n")
            for r in do_rules:
                lines.append(f"- {r.title}: `{r.do_example}`")
        if dont_rules:
            lines.append("\n### DON'T\n")
            for r in dont_rules:
                lines.append(f"- {r.title}: `{r.dont_example}`")
        return "\n".join(lines)[:max_chars]

    def record_correction(
        self,
        original_file: str,
        original_content: str,
        corrected_content: str,
        context: str = "",
    ) -> list[ExtractedRule]:
        """Diff two versions, extract rules, sink them, return extracted list."""
        rules = extract_rules_from_diff(
            original_content, corrected_content, original_file, context
        )
        self.add_rules(rules)
        return rules


def cli_add_correction(
    original_path: str, corrected_path: str, project_dir: str
) -> dict:
    """CLI convenience: diff two files, extract rules, sink to LEARNED-RULES.md."""
    orig = Path(original_path).read_text(encoding="utf-8")
    corr = Path(corrected_path).read_text(encoding="utf-8")
    sink = RuleSink(project_dir)
    rules = sink.record_correction(original_path, orig, corr)
    return {"rules_added": len(rules), "rules": [r.title for r in rules]}
