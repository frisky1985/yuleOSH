#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Step-aware skill selection for automatic prompt injection.

The bundled automotive pack contains thousands of skills; injecting all of
them is impossible.  This module deterministically picks the skills that
match the current pipeline step (and, lightly, the prompt text) so the LLM
receives relevant domain guidance without any per-project configuration.

Selection is pure and deterministic: same step + prompt + pack → same names.
"""

from __future__ import annotations

import hashlib
import logging
import re

log = logging.getLogger("yuleosh.skills.selector")

# Pipeline step → preferred automotive categories (highest priority first).
STEP_PROFILES: dict[str, tuple[str, ...]] = {
    "sys-requirements": ("automotive-workflow", "safety", "regulatory-compliance"),
    "sys-req-review": ("automotive-workflow", "safety", "regulatory-compliance"),
    "sys-architecture": ("architecture", "autosar", "embedded", "middleware"),
    "sys-verification": ("testing", "safety", "sotif", "hil-sil"),
    "sys-integration": ("testing", "automotive-protocols", "embedded", "hil-sil"),
    "sys-validation": ("testing", "safety", "sotif"),
    "spec-check": ("automotive-workflow", "testing"),
    "super-analysis": ("automotive-workflow", "oem-decision-making"),
    "prd": ("automotive-workflow", "oem-decision-making"),
    "prd-review": ("automotive-workflow", "oem-decision-making"),
    "architecture": ("architecture", "autosar", "embedded", "network"),
    "arch-review": ("architecture", "autosar", "safety", "security"),
    "development": ("embedded", "autosar", "safety", "security"),
    "codegen-deploy": ("embedded", "autosar", "safety"),
    "misra-review": ("embedded", "autosar", "safety"),
    "code-review": ("embedded", "autosar", "safety", "security"),
    "internal-code-review": ("embedded", "autosar", "safety", "security"),
    "claude-review": ("embedded", "autosar", "safety"),
    "test-planning": ("testing", "safety", "sotif", "hil-sil"),
    "test-case-gen": ("testing", "safety", "sotif"),
    "test-codegen": ("testing", "embedded", "safety"),
    "verify-loop": ("testing", "safety"),
    "c-unit-test": ("testing", "embedded"),
    "integration-test": ("testing", "hil-sil", "automotive-protocols"),
    "test-qualification": ("testing", "safety", "sotif"),
    "fault-injection": ("safety", "security", "testing"),
    "review-critical-safety": ("safety", "sotif"),
    "risk-assessment": ("safety", "sotif", "security"),
    "risk-review": ("safety", "sotif", "security"),
    "coverage-review": ("testing", "safety"),
    "hwe1": ("safety", "advanced-materials"),
    "hwe2": ("safety", "advanced-materials"),
    "hwe3": ("embedded", "safety"),
    "hwe4": ("testing", "safety"),
    "mle1": ("sotif", "testing"),
    "mle2": ("sotif", "embedded"),
    "mle3": ("sotif", "testing"),
    "mle4": ("sotif", "testing"),
    "val-": ("testing", "calibration"),
    "measurement": ("testing", "calibration", "testing-metrology"),
    "sup": ("automotive-workflow", "regulatory-compliance"),
    "man": ("project-management", "automotive-workflow", "oem-decision-making"),
    "acq": ("project-management", "automotive-workflow", "oem-decision-making"),
    "spl": ("project-management", "automotive-workflow", "oem-decision-making"),
    "pim": ("automotive-workflow",),
    "reu": ("automotive-workflow",),
    "final-report": ("automotive-workflow",),
}

# Step → keywords that break ties inside a preferred category (deterministic).
STEP_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sys-requirements": ("requirement", "specification", "traceab", "v-model", "management"),
    "sys-req-review": ("requirement", "review", "traceab", "quality"),
    "sys-architecture": ("architecture", "interface", "design", "software"),
    "sys-verification": ("verification", "test", "coverage", "review"),
    "sys-integration": ("integration", "interface", "bus", "test"),
    "sys-validation": ("validation", "test", "acceptance", "vehicle"),
    "spec-check": ("requirement", "quality", "check", "review"),
    "architecture": ("architecture", "design", "interface", "zonal"),
    "arch-review": ("architecture", "review", "safety", "interface"),
    "development": ("driver", "implementation", "coding", "c ", "autosar"),
    "development-review": ("review", "coding", "static analysis", "misra"),
    "misra-review": ("misra", "coding", "static analysis", "c "),
    "code-review": ("review", "coding", "static analysis", "misra"),
    "internal-code-review": ("review", "coding", "static analysis", "safety"),
    "claude-review": ("review", "coding", "quality"),
    "codegen-deploy": ("coding", "implementation", "driver", "deploy"),
    "test-planning": ("test", "strategy", "plan", "verification"),
    "test-case-gen": ("test", "case", "equivalence", "boundary"),
    "test-codegen": ("unit test", "test", "coverage", "assert"),
    "verify-loop": ("test", "verification", "coverage"),
    "c-unit-test": ("unit test", "test", "coverage", "c "),
    "integration-test": ("integration", "test", "hil", "bus"),
    "test-qualification": ("test", "acceptance", "qualification", "coverage"),
    "review-critical-safety": ("safety", "fmea", "hazard", "asil"),
    "risk-assessment": ("risk", "hazard", "assessment", "safety"),
    "risk-review": ("risk", "review", "safety"),
    "hwe1": ("hardware", "requirement", "safety"),
    "hwe2": ("hardware", "design", "safety"),
    "hwe3": ("hardware", "implementation", "diagnostic"),
    "hwe4": ("hardware", "verification", "test"),
    "mle1": ("machine learning", "requirement", "safety"),
    "mle2": ("machine learning", "architecture", "design"),
    "mle3": ("machine learning", "training", "data"),
    "mle4": ("machine learning", "evaluation", "test"),
    "man": ("project", "planning", "charter", "management", "v-model"),
    "sup": ("quality", "process", "audit", "configuration"),
    "acq": ("supplier", "acquisition", "contract", "selection"),
    "spl": ("supplier", "release", "tender", "contract"),
    "pim": ("process", "improvement", "assessment", "measurement"),
    "final-report": ("report", "summary", "release", "v-model"),
}

_KEYWORD_RE = re.compile(r"[a-z0-9][a-z0-9-]{3,}")
_content_hashes: dict[str, str] = {}


def _lookup(table: dict[str, tuple[str, ...]], step_key: str) -> tuple[str, ...]:
    key = (step_key or "").strip().lower()
    if key in table:
        return table[key]
    for prefix in sorted(table, key=len, reverse=True):
        if key.startswith(prefix):
            return table[prefix]
    return ()


def profile_for(step_key: str) -> tuple[str, ...]:
    """Return the preferred categories for ``step_key`` (empty when unknown)."""
    return _lookup(STEP_PROFILES, step_key)


def keywords_for(step_key: str) -> tuple[str, ...]:
    """Return the tie-break keywords for ``step_key``."""
    return _lookup(STEP_KEYWORDS, step_key)


def _content_hash(skill) -> str:
    h = _content_hashes.get(skill.name)
    if h is None:
        h = hashlib.sha1(skill.content.encode("utf-8")).hexdigest()
        _content_hashes[skill.name] = h
    return h


def select_skill_names(
    step_key: str,
    query: str = "",
    *,
    limit: int = 3,
    categories: list[str] | tuple[str, ...] | None = None,
    registry=None,
) -> list[str]:
    """Pick up to ``limit`` pack skills relevant to a pipeline step."""
    preferred = tuple(categories) if categories else profile_for(step_key)
    if not preferred or limit <= 0:
        return []
    if registry is None:
        from yuleosh.skills.registry import get_registry

        registry = get_registry()

    keywords = keywords_for(step_key)
    tokens = set(_KEYWORD_RE.findall((query or "").lower()))
    scored: list[tuple[int, str]] = []
    for skill in registry.list():
        tags = {t.lower() for t in skill.tags}
        if "automotive" not in tags:
            continue
        score = 0
        for idx, category in enumerate(preferred):
            if category.lower() in tags:
                score += (len(preferred) - idx) * 10
        if "curated" in tags:
            score += 3
        text = f"{skill.name} {skill.title} {skill.description}".lower()
        score += min(9, 3 * sum(1 for kw in keywords if kw in text))
        if tokens:
            score += min(3, sum(1 for token in tokens if token in text))
        if score > 0:
            scored.append((score, skill.name))

    scored.sort(key=lambda item: (-item[0], item[1]))

    picked: list[str] = []
    seen_hashes: set[str] = set()
    for _, name in scored:
        skill = registry.get(name)
        if skill is None:
            continue
        digest = _content_hash(skill)
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        picked.append(name)
        if len(picked) >= limit:
            break
    return picked
