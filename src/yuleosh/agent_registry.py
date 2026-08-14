# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Agent Registry — role classification and per-role constraint loading.

A1-A4 (2026-08-08): agent constraints are isolated per role instead of
being concatenated into a single blob that is injected into every step's
system prompt.  This module provides:

  - AGENT_ROLES            : agent label -> role classification
  - STEP_AGENT_MAP         : pipeline step key -> agent label (lazy)
  - resolve_agent_for_step : step key -> agent label (or None)
  - resolve_agent_role     : agent label -> role (or None)
  - load_agent_constraints_by_role : .yuleosh/agents/*.md -> {role: text}

Import chain note: PIPELINE_STEPS lives in
``yuleosh.pipeline.step_handlers`` (the ``pipeline/run.py`` shim only
re-exports it).  ``STEP_AGENT_MAP`` is therefore built lazily on first
access to avoid import cycles.
"""

from pathlib import Path

# ── Role classification ──────────────────────────────────────────────
# 每个 agent 标签 -> 唯一角色（1:1，可反查）。

AGENT_ROLES: dict[str, str] = {
    "小明": "pm",
    "小克": "developer",
    "小马": "qa",
    "Hermes": "requirements",
    "Claude": "architect",
    "Codex": "verifier",
    "QEMU": "tool",
}

# Reverse lookup: role -> agent label (each role maps to exactly one agent).
_ROLE_TO_AGENT: dict[str, str] = {
    role: agent for agent, role in AGENT_ROLES.items()
}

# Pinyin / ASCII aliases so that e.g. xiaoke.md / xiaoming.md also resolve.
_AGENT_ALIASES: dict[str, str] = {
    "xiaoming": "小明",
    "xiaoke": "小克",
    "xiaoma": "小马",
    "hermes": "Hermes",
    "claude": "Claude",
    "codex": "Codex",
    "qemu": "QEMU",
}

# ── Shared minimal safety baseline (role-agnostic) ───────────────────
# A2: 从原 _DEFAULT_AGENT_SPEC 拆出的无角色通用规则。所有角色的 system
# prompt 都注入这份基线，但绝不混入其他角色的专属规则。

AGENT_SAFE_BASELINE = """# 共享安全基线（所有角色通用）
- 审计诚信：输出必须真实反映实际执行结果，禁止编造证据或虚报通过。
- 上下文安全：上下文使用超过 50% 时主动拆分，避免截断导致误判。
- 不静默降质：任何降级/跳过/回退必须显式记录，禁止悄悄降低质量。
"""


# ── Step -> agent map (lazy) ─────────────────────────────────────────

_STEP_AGENT_MAP_CACHE: dict[str, str] | None = None


def get_step_agent_map() -> dict[str, str]:
    """Build ``{step_key: agent_label}`` from PIPELINE_STEPS.

    PIPELINE_STEPS tuples are ``(step_key, agent, step_name, handler)``.
    The import is deferred to avoid a cycle: ``pipeline/run.py`` is a
    re-export shim and the real definition lives in
    ``yuleosh.pipeline.step_handlers``.
    """
    global _STEP_AGENT_MAP_CACHE
    if _STEP_AGENT_MAP_CACHE is None:
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS

        _STEP_AGENT_MAP_CACHE = {
            step[0]: step[1] for step in PIPELINE_STEPS if len(step) >= 2
        }
    return _STEP_AGENT_MAP_CACHE


def __getattr__(name: str):
    """PEP 562 — expose ``STEP_AGENT_MAP`` lazily."""
    if name == "STEP_AGENT_MAP":
        return get_step_agent_map()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def resolve_agent_for_step(step_key: str | None) -> str | None:
    """Return the agent label for a pipeline step key, or None."""
    if not step_key:
        return None
    return get_step_agent_map().get(step_key)


def resolve_agent_role(agent_label: str | None) -> str | None:
    """Return the role for an agent label, or None if unknown."""
    if not agent_label:
        return None
    return AGENT_ROLES.get(agent_label)


# ── Per-role constraint loading ──────────────────────────────────────

def _match_agent_label(stem: str) -> str | None:
    """Match a filename stem (extension removed) to an agent label.

    Matching rules (A2):
      - exact Chinese label (``小克.md``) or ASCII label (``hermes.md``);
      - pinyin alias (``xiaoke.md`` -> 小克);
      - stem *contains* a Chinese label, a pinyin alias, or a role name
        (resolved via AGENT_ROLES reverse lookup), e.g. ``qa.md`` ->
        小马, ``developer-notes.md`` -> 小克.

    Returns the agent label, or None when the file cannot be attributed
    to a single agent (such files never leak into any role's prompt).
    """
    norm = stem.strip().lower()
    if not norm:
        return None

    # exact match: Chinese label / ASCII label / pinyin alias
    if stem in AGENT_ROLES:
        return stem
    if norm in _AGENT_ALIASES:
        return _AGENT_ALIASES[norm]

    # containment: Chinese labels (e.g. 小克-notes.md)
    for label in AGENT_ROLES:
        if label in stem:
            return label
    # containment: pinyin aliases (e.g. xiaoke-extra.md)
    for alias, label in _AGENT_ALIASES.items():
        if alias in norm:
            return label
    # containment: role names -> reverse lookup (e.g. qa.md, pm.md)
    for role, label in _ROLE_TO_AGENT.items():
        if role in norm:
            return label
    return None


def load_agent_constraints_by_role(project_dir: str) -> dict[str, str]:
    """Scan ``.yuleosh/agents/*.md`` and group constraints by role.

    Each ``*.md`` file is attributed to an agent via its filename stem
    (Chinese label, ASCII label, pinyin alias or role name — see
    ``_match_agent_label``).  Files that cannot be attributed to a
    single agent are skipped so they never mix into another role's
    prompt.  Returns an empty dict when there is no ``agents/`` dir or
    no attributable files.

    Returns:
        ``{role: combined_markdown}`` — e.g. ``{"developer": "..."}``.
    """
    agents_dir = Path(project_dir) / ".yuleosh" / "agents"
    if not agents_dir.is_dir():
        return {}

    per_role: dict[str, list[str]] = {}
    for f in sorted(agents_dir.glob("*.md")):
        agent = _match_agent_label(f.stem)
        if agent is None:
            continue
        role = AGENT_ROLES.get(agent)
        if role is None:
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        per_role.setdefault(role, []).append(
            f"<!-- from: {f.name} -->\n{content}"
        )

    return {role: "\n\n".join(parts) for role, parts in per_role.items()}
