#!/usr/bin/env python3

# @req RS-001
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
pipeline/source_grounding.py — SourceGroundingChecker (H2-1a).

Abstracts the file:line / function-name / requirement-ID grounding logic
from review_guard.py into a reusable checker that can run on any LLM step
output, not just code-review findings.

Three checks are supported:
  1. file_line  — validate that file:line references point to real lines in
                  the injected source files.
  2. func_name  — validate that mentioned function names exist in the repo.
  3. req_id     — validate that requirement IDs exist in the declared
                  requirements set.

The checker is intentionally non-fatal: it annotates unverified references
in a ``grounding_report`` dict but never raises — callers decide how to
handle the report.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("pipeline.source_grounding")

# ── Patterns ──────────────────────────────────────────────────────────────────

# file:line references: "foo.c:42", "src/bar.h:100", "module/baz.py:7"
_FILE_LINE_RE = re.compile(
    r"\b([\w/.\-]+\.(?:c|h|cpp|hpp|py|sh|yaml|yml|json|md))(?::(\d+))?\b"
)

# Bare function-name calls: "hal_init(", "compute_crc(", "test_foo("
_FUNC_CALL_RE = re.compile(r"\b([a-zA-Z_]\w{2,})\s*\(")

# Requirement IDs: REQ-XXX-NNN, SWR-NNN, SRS-NNN, ASPICE-NNN, UC-NNN
_REQ_ID_RE = re.compile(
    r"\b((?:REQ|SWR|SRS|ASPICE|SW[-_]REQ|UC|HW[-_]REQ)[-_][A-Z0-9][-A-Z0-9_]{0,30})\b",
    re.I,
)


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class GroundingViolation:
    """A single unverified reference found in LLM output."""

    kind: str          # "file_line" | "func_name" | "req_id"
    reference: str     # the raw reference as it appeared in the text
    reason: str        # human-readable explanation


@dataclass
class GroundingReport:
    """Result of a grounding check on one LLM output."""

    violations: list[GroundingViolation] = field(default_factory=list)
    checked_file_lines: int = 0
    checked_func_names: int = 0
    checked_req_ids: int = 0

    @property
    def clean(self) -> bool:
        return len(self.violations) == 0

    def to_dict(self) -> dict:
        return {
            "clean": self.clean,
            "violation_count": len(self.violations),
            "violations": [
                {"kind": v.kind, "reference": v.reference, "reason": v.reason}
                for v in self.violations
            ],
            "checked_file_lines": self.checked_file_lines,
            "checked_func_names": self.checked_func_names,
            "checked_req_ids": self.checked_req_ids,
        }


# ── Checker ───────────────────────────────────────────────────────────────────

class SourceGroundingChecker:
    """Validate LLM output text against known-good repo facts.

    Args:
        source_files: list of dicts with keys ``path``, ``lines`` (int),
            optional ``content`` (str) — the files injected into the LLM.
        known_function_names: set of function names extracted from source.
        known_req_ids: set of requirement IDs from requirements docs.
    """

    def __init__(
        self,
        source_files: list[dict[str, Any]] | None = None,
        known_function_names: set[str] | None = None,
        known_req_ids: set[str] | None = None,
    ):
        self._file_line_counts: dict[str, int] = {}
        self._known_funcs: set[str] = known_function_names or set()
        self._known_reqs: set[str] = {r.upper() for r in (known_req_ids or [])}

        for sf in source_files or []:
            path = sf.get("path", "")
            if not path:
                continue
            lines = int(sf.get("lines") or 0)
            if not lines and sf.get("content"):
                lines = len(sf["content"].splitlines())
            self._file_line_counts[path] = lines

    # ── Public ────────────────────────────────────────────────────────────

    def check(self, text: str) -> GroundingReport:
        """Run all enabled grounding checks on ``text``.

        Only checks for which reference sets were provided are active:
        - file:line check always runs (against injected source_files).
        - func_name check only if ``known_function_names`` was non-empty.
        - req_id check only if ``known_req_ids`` was non-empty.
        """
        report = GroundingReport()

        self._check_file_lines(text, report)
        if self._known_funcs:
            self._check_func_names(text, report)
        if self._known_reqs:
            self._check_req_ids(text, report)

        if report.violations:
            log.info(
                "SourceGroundingChecker: %d violation(s) in LLM output",
                len(report.violations),
            )
        return report

    # ── Internal checks ───────────────────────────────────────────────────

    def _check_file_lines(self, text: str, report: GroundingReport) -> None:
        """Validate file:line references against injected source files."""
        if not self._file_line_counts:
            return
        seen: set[tuple] = set()
        for m in _FILE_LINE_RE.finditer(text):
            fname = m.group(1)
            line_str = m.group(2)
            key = (fname, line_str)
            if key in seen:
                continue
            seen.add(key)
            report.checked_file_lines += 1

            if fname not in self._file_line_counts:
                report.violations.append(GroundingViolation(
                    kind="file_line",
                    reference=m.group(0),
                    reason=f"file '{fname}' not in injected source set",
                ))
                continue

            if line_str is not None:
                try:
                    line_int = int(line_str)
                except ValueError:
                    report.violations.append(GroundingViolation(
                        kind="file_line",
                        reference=m.group(0),
                        reason=f"non-integer line '{line_str}' in '{fname}'",
                    ))
                    continue
                real = self._file_line_counts[fname]
                if line_int < 1 or line_int > real:
                    report.violations.append(GroundingViolation(
                        kind="file_line",
                        reference=m.group(0),
                        reason=(
                            f"line {line_int} out of range [1, {real}] "
                            f"for '{fname}'"
                        ),
                    ))

    def _check_func_names(self, text: str, report: GroundingReport) -> None:
        """Check that mentioned function names exist in known_function_names."""
        seen: set[str] = set()
        for m in _FUNC_CALL_RE.finditer(text):
            name = m.group(1)
            if name in seen:
                continue
            seen.add(name)
            report.checked_func_names += 1
            if name not in self._known_funcs:
                report.violations.append(GroundingViolation(
                    kind="func_name",
                    reference=f"{name}()",
                    reason=f"function '{name}' not found in repo source",
                ))

    def _check_req_ids(self, text: str, report: GroundingReport) -> None:
        """Check that requirement IDs exist in the declared requirements set."""
        seen: set[str] = set()
        for m in _REQ_ID_RE.finditer(text):
            rid = m.group(1).upper()
            if rid in seen:
                continue
            seen.add(rid)
            report.checked_req_ids += 1
            if rid not in self._known_reqs:
                report.violations.append(GroundingViolation(
                    kind="req_id",
                    reference=m.group(1),
                    reason=f"requirement ID '{rid}' not found in declared requirements",
                ))
