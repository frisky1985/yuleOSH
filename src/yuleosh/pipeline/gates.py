#!/usr/bin/env python3

# @req RS-001  @req SWR-001.1
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Pipeline 编排层 — 10 Gate 视图 (方案 B, 2026-08-19 老板第五轮拍板).

执行层保持 24 子步骤（外部 agent 独立超时 / P0 门禁 / --from-step /
step_cache 全保留）；编排层新增 GATES 视图，对外稳定契约（对齐 ASPICE
过程域），一旦约定不再变动（分层原则 R1-R4，见 RULES.md §12）。

gate status = 内部子步骤最差状态（failed > retry > skipped > passed）。

GATES ↔ PIPELINE_STEPS 契约（R3 守护，由 tests/test_step_handlers_init_deep.py
的 GATES 契约测试断言）:
  - 全覆盖: 每个 24 子步骤恰好属于一个 gate
  - 无重复: gate 内 step_keys 无重复
  - 无悬挂: gate 内 step_key 必须存在于 PIPELINE_STEPS
  - 顺序一致: gate 边界不跨越 PIPELINE_STEPS 顺序（子步骤按 pipeline 顺序）
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("pipeline.gates")

__all__ = [
    "GATES",
    "GATE_STATUS_ORDER",
    "aggregate_gate_status",
    "validate_gates_contract",
    "write_gate_summary",
]

# ═══════════════════════════════════════════════════════════════════════
# 编排层 10 Gate（对外稳定契约 — 变更须老板/架构评审拍板, R2）
# ═══════════════════════════════════════════════════════════════════════

GATES: list[dict] = [
    {
        "gate": "G1",
        "name": "SWE.1 需求 Gate",
        "step_keys": ["spec-check", "super-analysis", "prd", "prd-review"],
    },
    {
        "gate": "G2",
        "name": "SWE.2 架构 Gate",
        "step_keys": ["architecture", "arch-review"],
    },
    {
        "gate": "G3",
        "name": "SWE.3 实现 Gate",
        "step_keys": [
            "development", "development-review", "codegen-deploy",
            "internal-code-review",
        ],
    },
    {
        "gate": "G4",
        "name": "方案评审 Gate",
        "step_keys": ["claude-review"],
    },
    {
        "gate": "G5",
        "name": "测试规划 Gate",
        "step_keys": ["test-planning"],
    },
    {
        "gate": "G6",
        "name": "SWE.4 单元验证 Gate",
        "step_keys": ["verify-loop", "c-unit-test"],
    },
    {
        "gate": "G7",
        "name": "SWE.5 集成 Gate",
        "step_keys": [
            "code-review", "misra-review", "integration-test",
            "qemu-verify", "coverage-review",
        ],
    },
    {
        "gate": "G8",
        "name": "安全门禁 Gate",
        "step_keys": ["review-critical-safety", "fault-injection"],
    },
    {
        "gate": "G9",
        "name": "合并门禁 Gate",
        "step_keys": ["merge-gate"],
    },
    {
        "gate": "G10",
        "name": "SWE.6 合格性 Gate",
        "step_keys": ["test-qualification", "final-report"],
    },
]

# gate status 聚合优先级: failed > retry > skipped > passed
GATE_STATUS_ORDER = ["failed", "retry", "skipped", "passed"]


def gate_for_step(step_key: str) -> dict | None:
    """Return the gate dict owning ``step_key`` (None if not in any gate)."""
    for g in GATES:
        if step_key in g["step_keys"]:
            return g
    return None


def aggregate_gate_status(step_statuses: dict[str, str]) -> dict[str, str]:
    """Aggregate per-step statuses into per-gate status (worst-wins).

    Parameters
    ----------
    step_statuses : dict[str, str]
        Mapping step_key -> status (e.g. from session.steps).
        Unknown steps are ignored; missing steps contribute nothing.

    Returns
    -------
    dict[str, str]
        Mapping gate key (e.g. "G1") -> aggregated status.
    """
    result: dict[str, str] = {}
    for g in GATES:
        statuses: list[str] = []
        for key in g["step_keys"]:
            st = step_statuses.get(key, "").strip().lower()
            if st:
                statuses.append(st)
        result[g["gate"]] = _worst_status(statuses)
    return result


def _worst_status(statuses: list[str]) -> str:
    """Worst-wins merge of statuses (failed > retry > skipped > passed).

    Unknown statuses (e.g. "completed", "running") are treated as non-failed
    and fall to the lowest severity bucket; empty list → "passed" (gate has
    no executed steps in this run).
    """
    if not statuses:
        return "passed"
    # failed/incomplete → failed (fail-closed: 无法完成判定按失败)
    if any(s in ("failed", "incomplete", "error") for s in statuses):
        return "failed"
    if any(s == "retry" for s in statuses):
        return "retry"
    if any(s == "warning" for s in statuses):
        return "warning"
    # skipped outranks passed (per GATE_STATUS_ORDER): a gate where any
    # step did not actually run is not a green gate.  Previously this
    # required *all* steps to be skipped, so a gate mixing passed and
    # skipped steps reported "passed" while listing skipped children.
    if any(s == "skipped" for s in statuses):
        return "skipped"
    return "passed"


def _sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest of a file, or '' if unreadable."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def _statuses_from_session_steps(steps) -> dict[str, str]:
    """Build ``{step_key: status}`` from ``session.steps`` entries.

    ``session.steps`` entries look like::

        {"step": 1, "name": "spec-check", "agent": ..., "status": "completed"}

    The step key lives in ``"name"`` — ``"step"`` is the 1-based ordinal.
    Reading ``"step"`` (the previous behaviour) produced integer keys that
    never match ``GATES`` step_keys, so every gate collapsed to ``passed``
    no matter what actually ran (bug fixed 2026-09-03).
    """
    statuses: dict[str, str] = {}
    for entry in steps or []:
        if not isinstance(entry, dict):
            continue
        key = ""
        for field in ("name", "step_key", "step"):
            val = entry.get(field)
            if isinstance(val, str) and val.strip():
                key = val.strip()
                break
        if key:
            statuses[key] = entry.get("status", "")
    return statuses


# Artifact filenames that do not follow the "<step_key>.json" convention.
# Without these, the corresponding gate never sees its step's real verdict
# and silently stays "passed" (2026-09-03).
_ARTIFACT_CANDIDATES: dict[str, tuple[str, ...]] = {
    "code-review": ("code-review-unified.json",),
    "review-critical-safety": ("critical-safety-report.json",),
    "merge-gate": ("merge-gate-report.json",),
    "fault-injection": ("fault-injection-report.md", "fault-injection.json"),
}


def _artifact_paths(sdir: Path | None, step_key: str) -> list[Path]:
    """Return candidate artifact paths for ``step_key`` (existing ones only)."""
    if sdir is None:
        return []
    names = [f"{step_key}.json", *_ARTIFACT_CANDIDATES.get(step_key, ())]
    paths = [Path(sdir) / n for n in names]
    return [p for p in paths if p.exists()]


def _artifact_verdict(sdir: Path | None, step_key: str) -> str:
    """Derive a gate verdict from a step's own artifact JSON.

    Returns ``"skipped"``, ``"failed"``, or ``""`` (unknown — the caller
    then keeps the status recorded in ``session.steps``).

    Why this exists
    ---------------
    Step handlers that skip real work (mock mode, no generated code,
    diff pruning) write ``{"status": "skipped"}`` / ``{"skipped": true}``
    into *their own artifact*, but the orchestrator still marks the step
    ``completed`` in ``session.steps``.  Aggregating only ``session.steps``
    therefore reports every gate as ``passed`` for work that never ran.
    Reading the artifact restores the real verdict.

    Only explicit skip / explicit-false signals are honoured; anything
    else returns ``""`` so unknown schemas never flip a passing step.
    """
    for path in _artifact_paths(sdir, step_key):
        if path.suffix == ".json":
            verdict = _verdict_from_json(path)
        else:
            # Markdown artifacts (e.g. the fault-injection report) carry no
            # status field; an explicit skip banner is the only signal.
            verdict = _verdict_from_text(path)
        if verdict:
            return verdict
    return ""


def _verdict_from_json(path: Path) -> str:
    """Read a JSON artifact and return ``skipped`` / ``failed`` / ``""``."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    if data.get("skipped") is True or str(data.get("status", "")).strip().lower() == "skipped":
        return "skipped"
    # Explicit failure verdicts (e.g. merge-gate "passed": false,
    # c-coverage-gate "gate_passed": false).
    for key in ("passed", "gate_passed"):
        if key in data and data[key] is False:
            return "failed"
    return ""


def _verdict_from_text(path: Path) -> str:
    """Return ``skipped`` when a non-JSON artifact opens with a skip banner."""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:400]
    except OSError:
        return ""
    return "skipped" if "skipped" in head.lower() else ""


def write_gate_summary(session, step_statuses: dict[str, str] | None = None,
                       output_path: str | None = None) -> str:
    """Aggregate the session's step statuses into gate-summary.json.

    Parameters
    ----------
    session : PipelineSession
        Active pipeline session (session_dir carries the output).
    step_statuses : dict[str, str], optional
        Per-step status override; defaults to reading ``session.steps``.
    output_path : str, optional
        Explicit output path (default ``<session_dir>/gate-summary.json``).

    Returns
    -------
    str
        Path to the written gate-summary.json.
    """
    sdir = getattr(session, "session_dir", None)

    if step_statuses is None:
        step_statuses = _statuses_from_session_steps(getattr(session, "steps", []))
        # Artifact-verdict overlay (2026-09-03): a skipped step is still
        # marked "completed" by the orchestrator, so session.steps alone
        # would report passed gates for work that never ran.  Let each
        # artifact correct its own verdict.  An explicit step_statuses
        # argument (tests / callers that already know better) is never
        # overridden.
        if sdir is not None:
            for key in list(step_statuses):
                verdict = _artifact_verdict(Path(sdir), key)
                if verdict:
                    step_statuses[key] = verdict

    gate_statuses = aggregate_gate_status(step_statuses)

    summary = {
        "schema": "gate-summary-v1",
        "session": getattr(session, "name", ""),
        "timestamp": datetime.now(UTC).isoformat(),
        "orchestration": "10-stage gate orchestration over execution units",
        "gates": [],
        "worst_gate_status": _worst_status(list(gate_statuses.values())),
    }
    for g in GATES:
        # Q3: compute SHA-256 of each step's artifact file for tamper-evidence.
        artifact_hashes: dict[str, str] = {}
        if sdir is not None:
            for step_key in g["step_keys"]:
                artifact_path = Path(sdir) / f"{step_key}.json"
                digest = _sha256_file(artifact_path)
                if digest:
                    artifact_hashes[step_key] = digest
        gate_entry = {
            "gate": g["gate"],
            "name": g["name"],
            "status": gate_statuses.get(g["gate"], "passed"),
            "step_keys": g["step_keys"],
        }
        if artifact_hashes:
            gate_entry["artifact_hashes"] = artifact_hashes
        summary["gates"].append(gate_entry)

    if output_path is None:
        if sdir is None:
            raise ValueError("session has no session_dir — pass output_path explicitly")
        output_path = str(Path(sdir) / "gate-summary.json")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    log.info("gate-summary written: %s (worst=%s)", out, summary["worst_gate_status"])
    return str(out)


def validate_gates_contract(step_keys: list[str]) -> list[str]:
    """R3 契约守护: GATES ↔ PIPELINE_STEPS 全覆盖/无重复/无悬挂/顺序一致。

    Returns a list of contract violations (empty = contract holds).

    Rules:
      - every PIPELINE_STEPS key is covered by exactly one gate (全覆盖)
      - no duplicate step keys across gates (无重复)
      - every gate step key exists in PIPELINE_STEPS (无悬挂)
      - gate boundaries preserve PIPELINE_STEPS order: each gate's keys are
        contiguous in the pipeline order, and gates appear in ascending
        first-index order (顺序一致)
    """
    violations: list[str] = []

    all_gate_keys: list[str] = []
    seen: set[str] = set()
    for g in GATES:
        for k in g["step_keys"]:
            if k in seen:
                violations.append(f"duplicate step key across gates: {k}")
            seen.add(k)
            all_gate_keys.append(k)

    # 全覆盖 + 无悬挂
    for k in step_keys:
        if k not in seen:
            violations.append(f"step not covered by any gate: {k}")
    for k in seen:
        if k not in step_keys:
            violations.append(f"gate references unknown step: {k}")

    # 顺序一致: 每个 gate 的 keys 在 pipeline 顺序中连续，且 gate 首索引递增
    index_of = {k: i for i, k in enumerate(step_keys)}
    gate_first: list[tuple[int, str]] = []
    for g in GATES:
        idxs = [index_of[k] for k in g["step_keys"] if k in index_of]
        if not idxs:
            continue
        if idxs != sorted(idxs):
            violations.append(f"gate {g['gate']} keys out of order: {g['step_keys']}")
        if max(idxs) - min(idxs) + 1 != len(idxs):
            violations.append(f"gate {g['gate']} keys not contiguous: {g['step_keys']}")
        gate_first.append((min(idxs), g["gate"]))
    if gate_first != sorted(gate_first):
        violations.append("gate first-index order does not follow PIPELINE_STEPS order")

    return violations
