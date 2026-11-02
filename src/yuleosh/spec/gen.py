# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Natural-language → OpenSpec requirement document generation (spec gen).

Converts a free-text requirement / prompt into an OpenSpec markdown document
that passes ``yuleosh.spec.validate`` (RFC 2119 SHALL/SHOULD/MAY +
GIVEN/WHEN/THEN scenarios + ``PREFIX-NNN`` requirement IDs), so the output
can feed ``yuleosh pipeline run docs/spec.md`` directly.

Two modes:
  - LLM mode (default): calls ``LLMClient.call_sync`` with a strict format
    prompt, then runs a validate-and-repair loop (up to ``max_repairs``
    rounds) feeding validator errors back into the LLM.
  - Mock mode (``--mock`` / ``mock=True``): deterministic offline
    rule-based generation — no LLM call, suitable for CI and demos.

Testability: ``llm_fn`` injects a fake LLM callable with the signature
``fn(system_prompt, user_prompt) -> {"content": str, ...}``.
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

log = logging.getLogger("yuleosh.spec.gen")

# ── LLM prompt ───────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an OpenSpec requirement engineer for embedded automotive software.
Convert the user's natural-language requirement into an OpenSpec markdown document.

STRICT output grammar (the document is machine-validated; deviations fail the gate):

1. Document title: one `# <title>` line.
2. Each requirement uses EXACTLY this structure:

### {PREFIX}-001: <short requirement name>
- The system SHALL <observable, testable behavior>

#### Reason
<why this requirement exists, one or two sentences>

3. SHALL bullets MUST start with "- The system SHALL " / "- The system SHOULD " / "- The system MAY "
   (RFC 2119 keyword in upper case). Non-binding quality targets use SHOULD.
4. Requirement IDs are sequential: {PREFIX}-001, {PREFIX}-002, ... (prefix may differ if instructed).
5. After the requirements, add a scenarios section; every requirement MUST have at least one scenario:

## Scenarios

#### Scenario: <scenario name>
- GIVEN <precondition>
- WHEN <trigger>
- THEN <observable expected outcome>
- AND <optional additional outcome>

6. Scenario bullets MUST start with "- GIVEN " / "- WHEN " / "- THEN " / "- AND ".
7. Write requirement names, reasons and scenario text in the SAME language as the user's input
   (Chinese input → Chinese text). Keep the English scaffolding keywords
   (The system SHALL / GIVEN / WHEN / THEN / Scenario / Reason) EXACTLY as specified.
8. Output ONLY the markdown document. No preamble, no explanation, no code fences.
"""

_REPAIR_PROMPT = """The previously generated OpenSpec document failed validation with these errors:
{errors}

Regenerate the COMPLETE corrected document. Output ONLY the markdown, no code fences, no commentary.
Remember: requirement headings "### {PREFIX}-NNN: <name>", SHALL bullets "- The system SHALL ...",
scenarios "#### Scenario: <name>" with "- GIVEN / - WHEN / - THEN" bullets.
"""


def _default_llm_fn(system_prompt: str, user_prompt: str) -> dict:
    """Production LLM entry — unified client (budget check + provider fallback)."""
    from yuleosh.llm.client import LLMClient

    return LLMClient.call_sync(prompt=user_prompt, system_prompt=system_prompt,
                               task_type="spec-gen")


def _extract_markdown(content: str) -> str:
    """Strip code fences / stray commentary around the markdown document."""
    text = content.strip()
    fence = re.search(r"```(?:markdown|md)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Drop leading non-document lines (e.g. "Here is the spec:") before first heading
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            return "\n".join(lines[i:]).strip() + "\n"
    return text + "\n"


def _validate_markdown(markdown: str) -> tuple[list[dict], dict]:
    """Validate a markdown string via the standard OpenSpec validator.

    Returns (issues, stats). Writes to a temp file because ``parse_spec``
    is file-based.
    """
    from yuleosh.spec.validate import parse_spec, validate_spec

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as f:
        f.write(markdown)
        tmp = f.name
    try:
        doc = parse_spec(tmp)
        issues = validate_spec(doc)
    finally:
        Path(tmp).unlink(missing_ok=True)
    stats = {
        "requirements": len(doc.requirements),
        "scenarios": len(doc.scenarios),
        "total_shall": sum(len(r.shall) for r in doc.requirements),
        "total_should": sum(len(r.should) for r in doc.requirements),
        "total_may": sum(len(r.may) for r in doc.requirements),
    }
    return issues, stats


def _has_errors(issues: list[dict], stats: dict) -> bool:
    """True when the generated document must enter the repair loop.

    Besides validator ERRORs, a document with zero parseable requirements
    is an error: the validator checks parsed objects only, so garbage LLM
    output would otherwise "pass" vacuously and skip repair.
    """
    if stats["requirements"] == 0:
        if not any(i.get("type") == "no_requirements" for i in issues):
            issues.append({
                "severity": "ERROR",
                "type": "no_requirements",
                "item": "",
                "message": "Document contains no parseable requirements",
            })
        return True
    return any(i.get("severity") == "ERROR" for i in issues)


# ── Mock (offline) generation ────────────────────────────────────────────────

_INTENT_SPLIT = re.compile(r"[。；;！!？?\n]+")


def _split_intents(text: str) -> list[str]:
    """Split free text into requirement intents (deterministic, offline)."""
    parts = [p.strip(" ，,、") for p in _INTENT_SPLIT.split(text)]
    return [p for p in parts if len(p) >= 4]


def _mock_generate(text: str, prefix: str, title: str | None) -> str:
    """Deterministic offline generation: one REQ + one scenario per intent.

    Used by ``--mock`` (CI / demo without LLM). The output is intentionally
    minimal but fully validator-clean, so downstream pipeline steps can run.
    """
    intents = _split_intents(text) or [text.strip() or "未命名需求"]
    doc_title = title or "自动生成需求规范"
    out = [f"# {doc_title}", ""]
    for i, intent in enumerate(intents, 1):
        name = intent if len(intent) <= 30 else intent[:28] + "…"
        out += [
            f"### {prefix}-{i:03d}: {name}",
            f"- The system SHALL {intent}",
            "",
            "#### Reason",
            f"由自然语言输入离线生成（mock 模式）：「{intent}」。",
            "",
        ]
    out += ["## Scenarios", ""]
    for i, intent in enumerate(intents, 1):
        out += [
            f"#### Scenario: {prefix}-{i:03d} 主场景",
            "- GIVEN 系统已完成初始化并处于正常运行状态",
            f"- WHEN 需求「{intent}」的触发条件满足",
            f"- THEN 系统应完成「{intent}」所描述的可观测行为",
            "",
        ]
    return "\n".join(out).rstrip() + "\n"


# ── Public API ───────────────────────────────────────────────────────────────

def generate_spec(text: str, *, prefix: str = "REQ", title: str | None = None,
                  mock: bool = False, llm_fn=None, max_repairs: int = 2) -> dict:
    """Generate an OpenSpec markdown document from natural-language input.

    Args:
        text: free-text requirement / prompt (Chinese or English).
        prefix: requirement ID prefix (must match ``[A-Z][A-Z0-9]*``).
        title: optional document title.
        mock: deterministic offline generation, no LLM call.
        llm_fn: injected LLM callable for tests; defaults to LLMClient.
        max_repairs: validate-and-repair rounds in LLM mode.

    Returns:
        dict with ``markdown``, ``stats``, ``issues`` (final validator state),
        ``error_count``, ``repairs`` (rounds used), ``mock`` and ``model``.
    """
    if not text or not text.strip():
        raise ValueError("requirement text must not be empty")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", prefix):
        raise ValueError(f"invalid requirement ID prefix: {prefix!r}")
    prefix = prefix.upper()

    if mock:
        markdown = _mock_generate(text.strip(), prefix, title)
        issues, stats = _validate_markdown(markdown)
        return {"markdown": markdown, "stats": stats, "issues": issues,
                "error_count": sum(1 for i in issues if i.get("severity") == "ERROR"),
                "repairs": 0, "mock": True, "model": "mock-offline"}

    fn = llm_fn or _default_llm_fn
    system = _SYSTEM_PROMPT.replace("{PREFIX}", prefix)
    user = f"Requirement input:\n{text.strip()}\n\nDocument title: {title or '(choose a concise one)'}"
    resp = fn(system, user)
    model = resp.get("model", "unknown")
    markdown = _extract_markdown(resp.get("content", ""))

    repairs = 0
    issues, stats = _validate_markdown(markdown)
    _has_errors(issues, stats)  # surface zero-requirement docs as an ERROR issue
    while _has_errors(issues, stats) and repairs < max_repairs:
        repairs += 1
        errors = "\n".join(f"- [{i.get('type')}] {i.get('message')} "
                           f"(item: {i.get('item', '')})"
                           for i in issues if i.get("severity") == "ERROR")
        log.info("spec gen repair round %d: %d error(s)", repairs,
                 sum(1 for i in issues if i.get("severity") == "ERROR"))
        repair_sys = system + "\n\n" + _REPAIR_PROMPT.replace("{errors}", errors).replace("{PREFIX}", prefix)
        resp = fn(repair_sys, user)
        markdown = _extract_markdown(resp.get("content", ""))
        issues, stats = _validate_markdown(markdown)

    return {"markdown": markdown, "stats": stats, "issues": issues,
            "error_count": sum(1 for i in issues if i.get("severity") == "ERROR"),
            "repairs": repairs, "mock": False, "model": model}
