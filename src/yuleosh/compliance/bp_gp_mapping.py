# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""BP ↔ GP/RP mapping and process-capability map for ASPICE evaluation evidence.

ASPICE v3.1 assesses each process against:

* **Base Practices (BP)** — the activities a process performs.
* **Generic Practices (GP)** — the capability attributes that raise a process
  through capability levels (CL):

    - CL1: GP1.1 (perform BP), GP1.2 (traceability), GP1.3 (consistency)
    - CL2: GP2.1–GP2.10 (process management & institutionalization)
    - CL3: GP3.1, GP3.2 (process standardization & improvement)

* **Process Products (RP)** — the work products a process must deliver.

This module:

1. Maps every BP declared in the loaded ASPICE profiles to the GPs that must
   hold for each capability level, the expected RPs, and the evidence yuleOSH
   generates for it.
2. Writes ``.osh/evidence/process-capability-map.{json,md}`` so the compliance
   pack carries an explicit BP→GP/RP correspondence table.
3. Emits a capability boundary statement: **CL1 evidence prep supported,
   CL2 partially supported, CL3 not applicable** — aligned with the
   ``audit_report`` E1–E3 stance (evidence-coverage grades, not capability levels).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Generic Practice definitions (ASPICE v3.1) ────────────────────────────

GPs: dict[str, dict[str, str]] = {
    # CL1
    "GP1.1": {"level": 1, "title": "Perform the base practice"},
    "GP1.2": {"level": 1, "title": "Maintain bidirectional traceability"},
    "GP1.3": {"level": 1, "title": "Ensure consistency of work products"},
    # CL2
    "GP2.1": {"level": 2, "title": "Perform the process"},
    "GP2.2": {"level": 2, "title": "Manage the process"},
    "GP2.3": {"level": 2, "title": "Establish process definition"},
    "GP2.4": {"level": 2, "title": "Control the process"},
    "GP2.5": {"level": 2, "title": "Monitor the process"},
    "GP2.6": {"level": 2, "title": "Verify work products"},
    "GP2.7": {"level": 2, "title": "Verify the process"},
    "GP2.8": {"level": 2, "title": "Record process execution and results"},
    "GP2.9": {"level": 2, "title": "Assess process performance"},
    "GP2.10": {"level": 2, "title": "Improve the process"},
    # CL3
    "GP3.1": {"level": 3, "title": "Define standard process"},
    "GP3.2": {"level": 3, "title": "Improve organization's process assets"},
}

# 工具支持声明：CL3（组织级）超出工具边界；CL2 部分支持（追溯/基线/变更/评审
# 有实体与证据，但过程绩效指标、组织级标准化缺失）。
SUPPORT_LEVEL = {
    "GP1.1": "CL1", "GP1.2": "CL1", "GP1.3": "CL1",
    "GP2.1": "CL2", "GP2.2": "CL2", "GP2.3": "CL2", "GP2.4": "CL2",
    "GP2.5": "CL2", "GP2.6": "CL2", "GP2.7": "CL2", "GP2.8": "CL2",
    "GP2.9": "CL2-partial", "GP2.10": "CL2-partial",
    "GP3.1": "CL3-N/A", "GP3.2": "CL3-N/A",
}

# 工具对各过程域生成的证据路径（用于映射表的 evidence 列）。
AREA_EVIDENCE: dict[str, list[str]] = {
    "SWE.1": ["docs/software-requirements.md", "requirements/requirements.md",
              ".osh/evidence/traceability-matrix.json"],
    "SWE.2": ["design/architecture.md", "design/sdd.md",
              ".osh/evidence/traceability-matrix.json"],
    "SWE.3": ["code/src", "tests", "evidence/review.json",
              ".osh/evidence/traceability-matrix.json"],
    "SWE.4": ["tests", ".osh/ci/", ".osh/evidence/traceability-matrix.json"],
    "SWE.5": ["tests/integration", ".osh/ci/"],
    "SWE.6": [".osh/evidence/acceptance-matrix.md",
              ".osh/evidence/requirement-coverage.md"],
    "SYS.1": ["docs/system-requirements.md",
              ".osh/evidence/sys-to-swe-trace.json"],
    "SYS.2": ["docs/system-architecture.md"],
    "SYS.3": ["docs/system-verification.md"],
    "SYS.4": ["docs/system-integration.md"],
    "SYS.5": ["docs/system-validation.md"],
    "SUP.1": ["docs/qa-plan.md", ".osh/ci/qa-audit*.json", "evidence/review.json"],
    "SUP.8": ["baselines/*.json", ".osh/evidence/baseline-diff-*.json", ".git"],
    "SUP.9": ["docs/known-issues.md", ".osh/ci/issue-*.json"],
    "SUP.10": ["change-requests/*.json",
               ".osh/evidence/impact-analysis-*.json"],
    "MAN.1": ["docs/project-plan.md"],
    "MAN.2": ["docs/project-plan.md"],
    "MAN.3": ["docs/risk-register.md"],
}

# 每个过程域预期的主要 Process Product 类型。
AREA_RPS: dict[str, list[str]] = {
    "SWE.1": ["Software Requirements Specification",
              "Software Requirement Status", "Impact Analysis Record"],
    "SWE.2": ["Software Architecture Description", "Interface Description"],
    "SWE.3": ["Software Detailed Design", "Source Code", "Unit Test Specification"],
    "SWE.4": ["Unit Verification Results", "Traceability Matrix",
              "Defect Analysis Record"],
    "SWE.5": ["Integration Strategy", "Integration Test Specification",
              "Integration Test Results"],
    "SWE.6": ["Qualification Test Specification", "Qualification Test Results",
              "Acceptance Matrix"],
    "SYS.1": ["System Requirements", "Stakeholder Requirements Traceability"],
    "SYS.2": ["System Architecture Description"],
    "SYS.3": ["System Verification Plan & Results"],
    "SYS.4": ["System Integration Strategy & Results"],
    "SYS.5": ["System Validation Plan & Results"],
    "SUP.1": ["Quality Assurance Plan", "Audit Records"],
    "SUP.8": ["Baseline", "Configuration Status Accounting", "Release Record"],
    "SUP.9": ["Problem/Issue Report", "Resolution Record"],
    "SUP.10": ["Change Request", "Impact Analysis", "Change Status"],
    "MAN.1": ["Project Plan"],
    "MAN.2": ["Project Monitoring Report"],
    "MAN.3": ["Risk Register"],
}

# 每个 BP 适用的 GP 列表。CL1 三 GP 适用所有 BP；CL2/CL3 在此基础上逐层叠加。
def _gps_for(bp_id: str) -> list[str]:
    """Return the GP set that must hold for this BP (CL1 ∪ CL2 ∪ CL3)."""
    return [
        # CL1 — 基础实践执行与双向追溯、一致性
        "GP1.1", "GP1.2", "GP1.3",
        # CL2 — 过程管理与制度化
        "GP2.1", "GP2.2", "GP2.3", "GP2.4", "GP2.5", "GP2.6",
        "GP2.7", "GP2.8", "GP2.9", "GP2.10",
        # CL3 — 组织级标准化
        "GP3.1", "GP3.2",
    ]


def _bp_rps(bp_id: str, area_id: str) -> list[str]:
    return AREA_RPS.get(area_id, [])


def _bp_evidence(bp_id: str, area_id: str) -> list[str]:
    return AREA_EVIDENCE.get(area_id, [])


def build_bp_gp_rp_map() -> dict[str, Any]:
    """Build the BP→GP/RP mapping from the loaded ASPICE profiles.

    Returns a dict with:
      - ``standard``, ``version``
      - ``gps``: full GP catalog
      - ``areas``: list of {id, title, bps:[{id, title, gps, gps_support,
        rps, evidence, support_level}]}
      - ``capability_boundary``: explicit CL1/CL2/CL3 support statement
    """
    from yuleosh.compliance.profile import load_profile

    profiles = ["aspice_v3.1", "aspice_sys_v3.1", "aspice_support_mgmt_v3.1"]
    areas: list[dict] = []
    standard = "ASPICE"
    version = "3.1"

    for name in profiles:
        try:
            profile = load_profile(name)
        except Exception:  # noqa: BLE001 — profile optional for mapping
            continue
        standard = profile.meta.standard
        version = profile.meta.version
        for area in profile.areas:
            bps = []
            for bp in area.base_practices:
                gps = _gps_for(bp.id)
                bps.append({
                    "id": bp.id,
                    "title": bp.title,
                    "gps": gps,
                    "gps_support": {gp: SUPPORT_LEVEL.get(gp, "CL1") for gp in gps},
                    "rps": _bp_rps(bp.id, area.id),
                    "evidence": _bp_evidence(bp.id, area.id),
                    "support_level": _support_for_area(area.id),
                })
            areas.append({"id": area.id, "title": area.title, "bps": bps})

    return {
        "schema": "process-capability-map-v1",
        "standard": standard,
        "version": version,
        "generated_at": datetime.now().isoformat(),
        "gps": GPs,
        "areas": areas,
        "capability_boundary": CAPABILITY_BOUNDARY,
    }


def _support_for_area(area_id: str) -> str:
    """工具对该过程域的能力等级支持声明。"""
    if area_id in ("SWE.1", "SWE.2", "SWE.3", "SWE.4", "SWE.5", "SWE.6"):
        return "CL1-supported (CL2 partial)"
    if area_id in ("SUP.8", "SUP.10"):
        return "CL1-supported (CL2 partial — baselines & change records)"
    if area_id == "SUP.1":
        return "CL1-partial (QA plan & review records; no full audit workflow)"
    if area_id == "SUP.9":
        return "CL1-partial (issue records; no state machine)"
    if area_id in ("MAN.1", "MAN.2", "MAN.3"):
        return "CL1-not-supported (project mgmgr out of tool scope)"
    if area_id.startswith("SYS."):
        return "CL1-partial"
    return "CL1-not-supported"


CAPABILITY_BOUNDARY = {
    "CL1": {
        "supported": True,
        "statement": ("支持 ASPICE CL1 证据准备：SWE/SYS/SUP 过程可产出工作产品，"
                      "并通过证据覆盖度（E1–E3）评估。"),
    },
    "CL2": {
        "supported": "partial",
        "statement": ("CL2 部分支持：追溯矩阵、配置基线、变更请求、评审记录等过程管理与"
                      "工作产品管理证据已实现；过程绩效指标（KPI）、组织级过程度量尚未纳入。"),
    },
    "CL3": {
        "supported": False,
        "statement": ("CL3 不适用：组织级过程标准化与复用资产超出工具边界，需由组织级"
                      "质量体系承接。"),
    },
    "note": ("本工具的 E1–E3 为「证据覆盖度」等级，并非 ASPICE 能力等级（CL）。"
             "本表仅用于评估准备的证据范围，不构成正式 ASPICE 评估结论。"),
}


def write_process_capability_map(project_dir: str | Path) -> dict[str, str]:
    """Write the BP→GP/RP map as JSON + Markdown under ``.osh/evidence/``.

    Returns ``{"json": path, "md": path}``.
    """
    proj = Path(project_dir)
    ev_dir = proj / ".osh" / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)

    data = build_bp_gp_rp_map()

    json_path = ev_dir / "process-capability-map.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    md_path = ev_dir / "process-capability-map.md"
    md_path.write_text(_render_markdown(data), encoding="utf-8")

    cap_path = ev_dir / "capability-statement.md"
    cap_path.write_text(_render_capability_statement(data), encoding="utf-8")

    return {"json": str(json_path), "md": str(md_path),
            "capability_statement": str(cap_path)}


def _render_markdown(data: dict) -> str:
    lines = [
        "# Process Capability Map — BP → GP/RP Mapping",
        "",
        f"> Standard: {data['standard']} v{data['version']}  ",
        f"> Generated: {data['generated_at']}",
        "",
        "## Capability Boundary",
        "",
        "| Level | Supported | Statement |",
        "|---|---|---|",
    ]
    for level in ("CL1", "CL2", "CL3"):
        cb = data["capability_boundary"][level]
        lines.append(
            f"| {level} | {cb['supported']} | {cb['statement']} |"
        )
    lines.extend(["", f"> {data['capability_boundary']['note']}", "", "## GP Catalog", ""])
    lines.append("| GP | Level | Title | Tool Support |")
    lines.append("|---|---|---|---|")
    for gp_id, gp in data["gps"].items():
        lines.append(
            f"| {gp_id} | CL{gp['level']} | {gp['title']} | "
            f"{SUPPORT_LEVEL.get(gp_id, '—')} |"
        )

    lines.extend(["", "## BP → GP/RP Mapping", ""])
    for area in data["areas"]:
        lines.append(f"### {area['id']} — {area['title']}")
        lines.append("")
        lines.append("| BP | Title | RPs | Evidence | Support |")
        lines.append("|---|---|---|---|---|")
        for bp in area["bps"]:
            rps = "<br>".join(bp["rps"][:3])
            ev = "<br>".join(bp["evidence"][:3])
            lines.append(
                f"| {bp['id']} | {bp['title']} | {rps} | {ev} | {bp['support_level']} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def _render_capability_statement(data: dict) -> str:
    lines = [
        "# Capability Statement — ASPICE Evidence Preparation Boundary",
        "",
        f"> Standard: {data['standard']} v{data['version']}",
        f"> Generated: {data['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for level in ("CL1", "CL2", "CL3"):
        cb = data["capability_boundary"][level]
        lines.append(f"### {level}")
        lines.append(f"- Supported: **{cb['supported']}**")
        lines.append(f"- {cb['statement']}")
        lines.append("")
    lines.extend([
        "## Important Note",
        "",
        data["capability_boundary"]["note"],
        "",
    ])
    return "\n".join(lines)
