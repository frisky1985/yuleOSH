# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Project document template generators (ASPICE SUP/MAN evidence).

The compliance checker recognizes several documents under ``docs/`` (qa-plan,
known-issues, risk-register, project-plan, change-requests, impact-analysis,
...). Without them the corresponding SUP/MAN base practices stay RED. This
module generates starter templates with the right sections so users can fill
in real content instead of hand-writing empty files.

Templates are intentionally **minimal skeletons** — they create documents with
the sections the checker looks for, populated with placeholders, so the
project never claims compliance from a stub.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from yuleosh.desktop import workspace

DOCS_DIR = "docs"


def _docs_dir(project_id: str) -> Path:
    d = workspace._project_dir(project_id) / DOCS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _header(title: str, doc_id: str, project_id: str) -> str:
    return (
        f"# {title}\n\n"
        f"> Document ID: {doc_id}\n"
        f"> Project: {_project_name(project_id)}\n"
        f"> Generated: {datetime.now():%Y-%m-%d %H:%M}\n"
        f"> Status: DRAFT — fill in real content before using as evidence.\n\n"
    )


def _project_name(project_id: str) -> str:
    try:
        return workspace._load_meta(project_id).get("name", project_id)
    except FileNotFoundError:
        return project_id


# ── Template bodies ───────────────────────────────────────────────────────

def _qa_plan() -> str:
    return (
        "## 1. Scope\n"
        "- [ ] Define quality objectives for this project.\n"
        "- [ ] Identify applicable standards (ASPICE, ISO 26262, ...).\n\n"
        "## 2. Quality Assurance Activities\n"
        "| Activity | Responsible | Frequency | Output |\n"
        "|---|---|---|---|\n"
        "| Requirements review | | | |\n"
        "| Architecture review | | | |\n"
        "| Code review | | | |\n"
        "| Test review | | | |\n"
        "| Configuration audit | | | |\n\n"
        "## 3. Audit Schedule\n"
        "- [ ] Planned audit dates and criteria.\n\n"
        "## 4. Nonconformity Handling\n"
        "- [ ] Escalation and closure process for audit findings.\n"
    )


def _known_issues() -> str:
    return (
        "## Issue Log\n\n"
        "| ID | Title | Severity | Status | Opened | Closed | Owner | Description |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| ISSUE-001 | (sample) | Low | Open | | | | Replace with real issues. |\n\n"
        "## Resolution Process\n"
        "- [ ] Each issue has a root-cause analysis.\n"
        "- [ ] Each issue has a verified fix and closure evidence.\n"
    )


def _risk_register() -> str:
    return (
        "## Risk Register\n\n"
        "| ID | Risk | Likelihood | Impact | Level | Mitigation | Owner | Status |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| RSK-001 | (sample) | Low | Low | Low | | | Open |\n\n"
        "## Review\n"
        "- [ ] Risks reviewed at each project milestone.\n"
    )


def _project_plan() -> str:
    return (
        "## 1. Objectives\n"
        "- [ ] Project goals and success criteria.\n\n"
        "## 2. Schedule\n"
        "| Milestone | Date | Deliverable |\n"
        "|---|---|---|\n\n"
        "## 3. Resources\n"
        "- [ ] Team roles and responsibilities.\n\n"
        "## 4. Estimation\n"
        "- [ ] Effort and cost estimates.\n\n"
        "## 5. Monitoring\n"
        "- [ ] Progress metrics and reporting cadence.\n"
    )


def _change_requests() -> str:
    return (
        "> Changes are also tracked as first-class entities via the change-request "
        "API (see `change-requests/*.json`). This document provides the human-readable "
        "register.\n\n"
        "## Change Register\n\n"
        "| CR ID | Title | Status | Approver | Opened | Closed |\n"
        "|---|---|---|---|---|---|\n\n"
        "## Process\n"
        "- [ ] Every change request goes through impact analysis.\n"
        "- [ ] Approved changes are baselined after implementation.\n"
    )


def _impact_analysis() -> str:
    return (
        "## Impact Analysis Template\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Change Request | |\n"
        "| Affected Requirements | |\n"
        "| Affected Components | |\n"
        "| Schedule Impact | |\n"
        "| Resource Impact | |\n"
        "| Risk Impact | |\n\n"
        "> Automated impact analysis is also available via the change-request "
        "API (`.osh/evidence/impact-analysis-*.json`).\n"
    )


# name → (filename, title, generator)
TEMPLATES: dict[str, tuple[str, str, Any]] = {
    "qa-plan": ("qa-plan.md", "Quality Assurance Plan", _qa_plan),
    "known-issues": ("known-issues.md", "Known Issues Log", _known_issues),
    "risk-register": ("risk-register.md", "Risk Register", _risk_register),
    "project-plan": ("project-plan.md", "Project Plan", _project_plan),
    "change-requests": ("change-requests.md", "Change Request Register", _change_requests),
    "impact-analysis": ("impact-analysis.md", "Impact Analysis", _impact_analysis),
}


def list_templates() -> list[str]:
    return sorted(TEMPLATES)


def generate_doc_template(project_id: str, name: str, overwrite: bool = False) -> dict:
    """Generate one template document under ``docs/``.

    Args:
        project_id: target project.
        name: template key from :data:`TEMPLATES`.
        overwrite: if True, replace an existing file.

    Returns:
        ``{"name", "path", "created"}`` — ``created`` is False when an existing
        file was left untouched (and ``overwrite`` was False).
    """
    if name not in TEMPLATES:
        raise ValueError(f"Unknown template '{name}'. Available: {list_templates()}")

    filename, title, gen = TEMPLATES[name]
    workspace._load_meta(project_id)  # project must exist
    path = _docs_dir(project_id) / filename
    doc_id = f"{name.upper().replace('-', '_')}-{datetime.now():%Y%m%d}"

    if path.exists() and not overwrite:
        return {"name": name, "path": f"{DOCS_DIR}/{filename}", "created": False}

    content = _header(title, doc_id, project_id) + gen()
    path.write_text(content, encoding="utf-8")
    return {"name": name, "path": f"{DOCS_DIR}/{filename}", "created": True}


def generate_doc_templates(project_id: str, names: list[str] | None = None,
                           overwrite: bool = False) -> list[dict]:
    """Generate multiple templates; defaults to all when ``names`` is None."""
    targets = names or list_templates()
    results = []
    for name in targets:
        try:
            results.append(generate_doc_template(project_id, name, overwrite=overwrite))
        except ValueError:
            results.append({"name": name, "path": None, "created": False,
                            "error": "unknown template"})
    return results


# ── Project presets (new-project wizard) ──────────────────────────────────

_AUTOMOTIVE_REQS = """# 需求（汽车电子模板）

> 请把下面的占位条目替换为真实需求，保留 `REQ-xxx` 编号便于追溯。

## 功能需求
- [ ] FR-001 描述主体功能行为与输入输出
- [ ] FR-002 描述安全相关约束（ISO 26262 ASIL 等级）
- [ ] FR-003 描述故障处理与降级策略

## 非功能需求
- [ ] NFR-001 时序 / 性能指标（响应时间、周期）
- [ ] NFR-002 诊断与可维护性要求
- [ ] NFR-003 环境与接口约束（总线、供电）
"""

_ASPICE_REQS = """# 需求（ASPICE 精简模板）

> 按 SYS.2 / SWE.1 组织需求，保留可追溯编号。

## 系统需求
- [ ] SYS-001 系统级功能描述

## 软件需求
- [ ] SWE-001 软件功能需求
- [ ] SWE-002 软件接口需求
- [ ] SWE-003 资源与性能约束
"""

_WEB_REQS = """# 需求（Web 应用模板）

## 用户故事
- [ ] US-001 作为<角色>，我希望<能力>，以便<价值>

## 验收标准
- [ ] AC-001 可验证的验收条件

## 非功能需求
- [ ] NFR-001 性能 / 可用性 / 安全要求
"""

# template id → preset. Presets only seed documents; they never fabricate
# compliance evidence (generated docs stay DRAFT).
PROJECT_TEMPLATES: dict[str, dict] = {
    "blank": {
        "id": "blank",
        "name": "空白工程",
        "tag": "自定义",
        "description": "只创建标准产出物目录，需求与文档自行编写。",
        "doc_templates": [],
        "requirements_seed": None,
    },
    "aspice-lite": {
        "id": "aspice-lite",
        "name": "ASPICE 精简",
        "tag": "ASPICE",
        "description": "预置项目计划、风险登记、质量计划三份骨架文档，适合中小项目快速起步。",
        "doc_templates": ["project-plan", "risk-register", "qa-plan"],
        "requirements_seed": _ASPICE_REQS,
    },
    "automotive": {
        "id": "automotive",
        "name": "汽车电子",
        "tag": "ISO 26262",
        "description": "完整 ASPICE 文档骨架 + 功能安全需求模板，适合车控 / ECU 类项目。",
        "doc_templates": [
            "project-plan", "risk-register", "qa-plan",
            "change-requests", "impact-analysis", "known-issues",
        ],
        "requirements_seed": _AUTOMOTIVE_REQS,
    },
    "web-app": {
        "id": "web-app",
        "name": "Web 应用",
        "tag": "通用",
        "description": "以用户故事组织需求，预置项目计划与已知问题文档。",
        "doc_templates": ["project-plan", "known-issues"],
        "requirements_seed": _WEB_REQS,
    },
}


def list_project_templates() -> list[dict]:
    """Return wizard-facing preset metadata (no requirement text bodies)."""
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "tag": t["tag"],
            "description": t["description"],
            "doc_templates": list(t["doc_templates"]),
            "has_requirements_seed": bool(t["requirements_seed"]),
        }
        for t in PROJECT_TEMPLATES.values()
    ]


def apply_project_template(project_id: str, template_id: str) -> dict:
    """Seed a freshly created project from a wizard preset.

    Returns ``{"template", "created_docs", "requirements_saved"}``. Unknown
    template ids raise ``ValueError``; the project itself is left untouched
    by the caller in that case.
    """
    preset = PROJECT_TEMPLATES.get(template_id)
    if preset is None:
        raise ValueError(
            f"Unknown project template '{template_id}'. "
            f"Available: {sorted(PROJECT_TEMPLATES)}"
        )

    created_docs: list[str] = []
    # An empty list means "no documents" (blank preset) — unlike
    # generate_doc_templates(), which treats a falsy ``names`` as "all".
    if preset["doc_templates"]:
        for result in generate_doc_templates(project_id, preset["doc_templates"]):
            if result.get("created") and result.get("path"):
                created_docs.append(result["path"])

    requirements_saved = False
    if preset["requirements_seed"]:
        workspace.save_requirements(project_id, preset["requirements_seed"], source="template")
        requirements_saved = True

    return {
        "template": preset["id"],
        "created_docs": created_docs,
        "requirements_saved": requirements_saved,
    }
