# @step_handlers SUP.1 / SUP.8 / SUP.9 / SUP.10 / MAN.3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""SUP.1 / SUP.8 / SUP.9 / SUP.10 / MAN.3 支持与管理过程。

与 MAN.5 / MAN.6 / 管理支撑组 / HWE / MLE 一致：**确定性生成 + 确定性评审**。

- **只搬运客观产物**：问题、变更请求、里程碑只来自磁盘上真实存在的
  结构化记录（``.osh/issues/*.json``、``change-requests/*.json``、
  ``.osh/project/milestones.json`` 等）；扫描不到即如实记录「无条目」，
  绝不臆造问题、变更或里程碑。
- **结论不自封**：已关闭问题必须有 closure，已批准变更必须有 decision，
  已完成里程碑必须有 evidence；评审步骤逐条重校验，假声明即 RED。
- **配置基线可复核**：基线清单记录每个配置项的 SHA256 与清单摘要，
  评审步骤重算并比对，篡改即 RED。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.mgmt_support import (
    _cell,
    _load_yaml,
    _now,
    _require_sections,
    _save_yaml,
    _sha256,
    _write_doc,
)
from yuleosh.pipeline.step_handlers.validation import _write_step_marker

log = logging.getLogger("pipeline.step_handlers.sup_man")

# SUP.1
QA_PLAN = "docs/qa-plan.md"
QA_REGISTER = "docs/qa-record-register.yaml"
# SUP.8
CM_PLAN = "docs/configuration-management.md"
CM_ITEMS = "docs/configuration-items.yaml"
CM_BASELINE = "baselines/pipeline-baseline.json"
# SUP.9
ISSUES_DOC = "docs/known-issues.md"
ISSUE_REGISTER = "docs/issue-register.yaml"
# SUP.10
CR_DOC = "docs/change-requests.md"
CR_REGISTER = "docs/change-request-register.yaml"
# MAN.3
PROJECT_PLAN = "docs/project-plan.md"
MILESTONES = ".osh/project/milestones.json"
# MAN.1
PROJECT_CHARTER = "docs/project-charter.md"
CHARTER_FILE = ".osh/project/charter.json"
# MAN.2
REQUIREMENTS_BASELINE = "docs/requirements-baseline.md"
REQ_CHANGE_LOG = "docs/requirements-change-log.yaml"
# MAN.4
QM_DOC = "docs/quality-management.md"
QM_REGISTER = "docs/quality-register.yaml"

_EXCLUDE_DIRS = (".osh", ".git", ".venv", "node_modules",
                 "__pycache__", ".pytest_cache", "dist", "build-venv",
                 "baselines")
_MAX_BASELINE_FILES = 200
_MAX_RECORDS = 200

_NO_QA = "（无审计记录：未检测到评审/CI 审计产物）"
_NO_ISSUE = "（无条目：未检测到问题/缺陷记录）"
_NO_CR = "（无条目：未检测到变更请求记录）"
_NO_MILESTONE = "（无里程碑：未检测到项目里程碑记录）"

_QA_SECTIONS = ("## 质量保证范围", "## 审计计划", "## 审计记录", "## 数据来源")
_CM_SECTIONS = ("## 配置项识别", "## 基线", "## 变更控制", "## 数据来源")
_ISSUE_SECTIONS = ("## 问题列表", "## 处理状态", "## 数据来源")
_CR_SECTIONS = ("## 变更请求列表", "## 决策与状态", "## 数据来源")
_PLAN_SECTIONS = ("## 项目范围", "## 里程碑", "## 进度跟踪", "## 数据来源")

_CLOSED_STATES = ("closed", "done", "resolved", "已关闭", "已解决")
_APPROVED_STATES = ("approved", "accepted", "已批准", "已接受")
_DONE_STATES = ("done", "completed", "已完成")

_NO_CHARTER = "（无项目章程：未检测到 charter.json）"
_NO_REQ_CHANGE = "（无需求变更：未检测到需求变更记录）"
_NO_QUALITY = "（无质量记录：未检测到过程审计/改进记录）"

_CHARTER_SECTIONS = ("## 项目目的", "## 范围与交付", "## 角色与资源",
                     "## 预算与进度", "## 数据来源")
_REQ_BASELINE_SECTIONS = ("## 需求基线", "## 变更日志", "## 数据来源")
_QM_SECTIONS = ("## 质量策略", "## 过程审计", "## 质量改进", "## 数据来源")


# ── 通用扫描与写盘 ──────────────────────────────────────────────────────


def _walk_files(root: Path):
    """遍历项目文件；剪枝排除目录（不进入 .git/node_modules 等）。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _EXCLUDE_DIRS)
        for name in sorted(filenames):
            yield Path(dirpath) / name


def _write_json(session: PipelineSession, rel_path: str, payload: dict) -> Path:
    target = Path(session.project_dir) / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _scan_json_records(project_dir: str, patterns: tuple[str, ...],
                       label: str) -> tuple[list[dict], list[str]]:
    """按 glob 收集结构化记录；来源总是记录（含零命中）。"""
    root = Path(project_dir)
    records: list[dict] = []
    sources: list[str] = []
    for pattern in patterns:
        sources.append(f"glob:{pattern}")
        try:
            matches = sorted(root.glob(pattern))
        except OSError:
            continue
        for path in matches:
            if not path.is_file():
                continue
            data = _read_json(path)
            if data is None:
                continue
            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if not str(entry.get("id") or entry.get("name") or "").strip():
                    continue
                record = dict(entry)
                record.setdefault("source", str(path.relative_to(root)))
                records.append(record)
                if len(records) >= _MAX_RECORDS:
                    break
    log.info("[%s] 扫描完成: %d 条记录（来源 %d 类）",
             label, len(records), len(sources))
    return records, sources


def _record_id(record: dict) -> str:
    return str(record.get("id") or record.get("name") or "").strip()


# ══════════════════════════════════════════════════════════════════════
# SUP.1 质量保证
# ══════════════════════════════════════════════════════════════════════


def _scan_qa_records(project_dir: str) -> tuple[list[dict], list[str]]:
    records, sources = _scan_json_records(
        project_dir,
        (".osh/evidence/reviews/*.json", ".osh/ci/*qa*.json", ".osh/ci/*audit*.json"),
        "SUP.1")
    md = Path(project_dir) / "docs" / "review-records.md"
    sources.append("file:docs/review-records.md")
    if md.is_file():
        records.append({"id": "REVIEW-RECORDS", "kind": "review-records",
                        "source": "docs/review-records.md"})
    return records, sources


def _build_qa_plan(records: list[dict], sources: list[str]) -> str:
    rows = [
        f"| {_cell(_record_id(r))} | {_cell(r.get('kind') or 'record')} "
        f"| {_cell(r.get('source'))} |"
        for r in records
    ]
    listing = ("\n".join(rows) if rows
               else f"| — | {_NO_QA} | — |")
    return (
        "# 质量保证计划（SUP.1）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 自动识别的审计/评审记录：{len(records)} 项\n\n"
        "## 质量保证范围\n\n"
        "- 覆盖需求、设计、实现、测试与发布各阶段的工作产品。\n"
        "- 质量目标与出口准则以组织过程定义和项目计划为准。\n\n"
        "## 审计计划\n\n"
        "- 独立 QA 角色按里程碑执行过程与工作产品审计。\n"
        "- 待人工确认：审计责任人、审计日期、抽样比例与审计结论。\n\n"
        "## 审计记录\n\n"
        "| 记录 | 类型 | 来源 |\n|:---|:---|:---|\n"
        + listing + "\n\n"
        + ("" if records else
           "> 本次扫描未命中任何审计/评审记录；尚未执行审计，"
           "不得据此判定质量保证符合。\n\n")
        + "## 数据来源\n\n"
        + "\n".join(f"- `{s}`" for s in sources) + "\n"
    )


def step_sup1_quality(session: PipelineSession) -> str:
    """SUP.1 — 生成质量保证计划并登记可核实的审计来源。"""
    records, sources = _scan_qa_records(session.project_dir)
    _save_yaml(session.project_dir, QA_REGISTER, {
        "version": 1,
        "generated_at": _now(),
        "scan_sources": sources,
        "records": records,
    })
    doc_path = _write_doc(session, QA_PLAN, _build_qa_plan(records, sources))
    _write_step_marker(session, "sup1-quality", status="completed",
                       plan=QA_PLAN, register=QA_REGISTER,
                       record_count=len(records))
    return str(doc_path)


def step_review_sup1(session: PipelineSession) -> str:
    """SUP.1 门禁：计划章节 + 登记来源 + 审计记录逐条落盘。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, QA_PLAN,
                             _QA_SECTIONS, problems)
    data = _load_yaml(session.project_dir, QA_REGISTER)
    if not data:
        problems.append(f"缺少或无法解析 {QA_REGISTER}")
    else:
        if not data.get("scan_sources"):
            problems.append(f"{QA_REGISTER} 缺少 scan_sources（无扫描证据）")
        records = [r for r in data.get("records") or [] if isinstance(r, dict)]
        if not records and text and _NO_QA not in text:
            problems.append(f"{QA_PLAN} 未明示无审计记录（{_NO_QA}）")
        for record in records:
            rid = _record_id(record)
            if text and rid and rid not in text:
                problems.append(f"{QA_PLAN} 未列出审计记录 {rid}")
    if problems:
        raise PipelineStepError("SUP.1 质量保证门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "sup1-review", status="completed",
                       verified=[QA_PLAN, QA_REGISTER])
    return str(Path(session.project_dir) / QA_PLAN)


# ══════════════════════════════════════════════════════════════════════
# SUP.8 配置管理
# ══════════════════════════════════════════════════════════════════════


def _manifest_digest(files: dict[str, str]) -> str:
    payload = json.dumps(files, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _scan_baseline_files(project_dir: str) -> tuple[dict[str, str], list[str]]:
    root = Path(project_dir)
    files: dict[str, str] = {}
    for path in _walk_files(root):
        if len(files) >= _MAX_BASELINE_FILES:
            break
        rel = str(path.relative_to(root))
        digest = _sha256(path)
        if digest:
            files[rel] = digest
    return files, ["walk:project"]


def _build_cm_plan(files: dict[str, str], digest: str) -> str:
    listing = "\n".join(f"- `{_cell(rel)}`" for rel in sorted(files)[:20])
    more = (f"\n- ……共 {len(files)} 个配置项（完整清单见 `{CM_BASELINE}`）"
            if len(files) > 20 else "")
    body = (listing + more) if files else f"- {_NO_QA.replace('审计记录', '配置项')}"
    return (
        "# 配置管理计划（SUP.8）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 配置项数量：{len(files)}\n"
        f"- 清单摘要（manifest_sha256）：`{digest}`\n\n"
        "## 配置项识别\n\n"
        + body + "\n\n"
        "## 基线\n\n"
        f"- 基线清单：`{CM_BASELINE}`（逐项 SHA256 + 清单摘要）。\n"
        "- 基线一经批准不得原地修改；变更须走 `docs/change-requests.md`（SUP.10）。\n\n"
        "## 变更控制\n\n"
        "- 配置项变更须经变更请求评审与批准后实施。\n"
        "- 待人工确认：基线批准人、批准日期与版本标识。\n\n"
        "## 数据来源\n\n"
        f"- `walk:project`（排除 {', '.join(_EXCLUDE_DIRS)}）\n"
    )


def step_sup8_config(session: PipelineSession) -> str:
    """SUP.8 — 建立配置项清单与带 SHA256 摘要的基线。"""
    files, sources = _scan_baseline_files(session.project_dir)
    digest = _manifest_digest(files)
    _write_json(session, CM_BASELINE, {
        "version": 1,
        "generated_at": _now(),
        "files": files,
        "manifest_sha256": digest,
    })
    items = [
        {"path": rel, "sha256": sha, "category": Path(rel).suffix.lstrip(".") or "file"}
        for rel, sha in sorted(files.items())
    ]
    _save_yaml(session.project_dir, CM_ITEMS, {
        "version": 1,
        "generated_at": _now(),
        "scan_sources": sources,
        "items": items,
    })
    doc_path = _write_doc(session, CM_PLAN, _build_cm_plan(files, digest))
    _write_step_marker(session, "sup8-config", status="completed",
                       plan=CM_PLAN, baseline=CM_BASELINE,
                       item_count=len(files))
    return str(doc_path)


def step_review_sup8(session: PipelineSession) -> str:
    """SUP.8 门禁：基线摘要重算一致 + 配置项清单可解析。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, CM_PLAN,
                             _CM_SECTIONS, problems)
    baseline = _read_json(Path(session.project_dir) / CM_BASELINE)
    if not isinstance(baseline, dict):
        problems.append(f"缺少或无法解析 {CM_BASELINE}")
    else:
        files = baseline.get("files")
        digest = str(baseline.get("manifest_sha256") or "")
        if not isinstance(files, dict):
            problems.append(f"{CM_BASELINE} 缺少 files 映射")
        elif not digest:
            problems.append(f"{CM_BASELINE} 缺少 manifest_sha256")
        else:
            recomputed = _manifest_digest(files)
            if recomputed != digest:
                problems.append(f"{CM_BASELINE} 摘要不一致："
                                f"记录 {digest[:12]}… 实际 {recomputed[:12]}…")
        if isinstance(files, dict) and not files and text and "配置项" not in text:
            problems.append(f"{CM_PLAN} 未明示无配置项")
    data = _load_yaml(session.project_dir, CM_ITEMS)
    if not data:
        problems.append(f"缺少或无法解析 {CM_ITEMS}")
    elif not data.get("scan_sources"):
        problems.append(f"{CM_ITEMS} 缺少 scan_sources（无扫描证据）")
    if problems:
        raise PipelineStepError("SUP.8 配置管理门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "sup8-review", status="completed",
                       verified=[CM_PLAN, CM_ITEMS, CM_BASELINE])
    return str(Path(session.project_dir) / CM_PLAN)


# ══════════════════════════════════════════════════════════════════════
# SUP.9 问题解决管理
# ══════════════════════════════════════════════════════════════════════


def _normalize_issues(records: list[dict]) -> list[dict]:
    items: list[dict] = []
    for record in records:
        items.append({
            "id": _record_id(record),
            "title": str(record.get("title") or record.get("summary")
                         or record.get("description") or "").strip(),
            "status": str(record.get("status") or "待分析").strip(),
            "closure": str(record.get("closure") or record.get("resolution")
                           or record.get("fix") or "").strip(),
            "source": str(record.get("source") or ""),
        })
    return items


def _build_issue_doc(items: list[dict]) -> str:
    rows = [
        f"| {_cell(i['id'])} | {_cell(i['title'])} | {i['status']} "
        f"| {_cell(i['closure']) or '—'} |"
        for i in items
    ]
    listing = "\n".join(rows) if rows else f"| — | {_NO_ISSUE} | — | — |"
    return (
        "# 问题与缺陷记录（SUP.9）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 问题条目数：{len(items)}\n\n"
        "## 问题列表\n\n"
        "| ID | 描述 | 状态 | 关闭说明 |\n|:---|:---|:---|:---|\n"
        + listing + "\n\n"
        + ("" if items else
           "> 本次扫描未命中任何问题/缺陷记录；不推断、不补造条目。\n\n")
        + "## 处理状态\n\n"
        "- 已关闭条目必须填写关闭说明；未关闭条目保持跟踪。\n"
        "- 待人工确认：问题严重度、责任人与目标关闭日期。\n\n"
        "## 数据来源\n\n"
        "- `.osh/issues/*.json`、`.osh/ci/issue-*.json`（真实记录，含零命中）。\n"
    )


def step_sup9_problem(session: PipelineSession) -> str:
    """SUP.9 — 汇总真实问题/缺陷记录。"""
    records, sources = _scan_json_records(
        session.project_dir,
        (".osh/issues/*.json", ".osh/ci/issue-*.json"), "SUP.9")
    items = _normalize_issues(records)
    _save_yaml(session.project_dir, ISSUE_REGISTER, {
        "version": 1,
        "generated_at": _now(),
        "scan_sources": sources,
        "items": items,
    })
    doc_path = _write_doc(session, ISSUES_DOC, _build_issue_doc(items))
    _write_step_marker(session, "sup9-problem", status="completed",
                       doc=ISSUES_DOC, register=ISSUE_REGISTER,
                       item_count=len(items))
    return str(doc_path)


def step_review_sup9(session: PipelineSession) -> str:
    """SUP.9 门禁：登记结构 + 文档一致性 + 关闭说明。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, ISSUES_DOC,
                             _ISSUE_SECTIONS, problems)
    data = _load_yaml(session.project_dir, ISSUE_REGISTER)
    if not data:
        problems.append(f"缺少或无法解析 {ISSUE_REGISTER}")
    else:
        if not data.get("scan_sources"):
            problems.append(f"{ISSUE_REGISTER} 缺少 scan_sources（无扫描证据）")
        items = [i for i in data.get("items") or [] if isinstance(i, dict)]
        if not items and text and _NO_ISSUE not in text:
            problems.append(f"{ISSUES_DOC} 未明示无问题条目（{_NO_ISSUE}）")
        seen: set[str] = set()
        for item in items:
            iid = str(item.get("id") or "").strip()
            if not iid:
                problems.append(f"{ISSUE_REGISTER} 存在缺少 id 的条目")
                continue
            if iid in seen:
                problems.append(f"{ISSUE_REGISTER} 条目 id 重复: {iid}")
            seen.add(iid)
            if not str(item.get("title") or "").strip():
                problems.append(f"{iid} 缺少描述")
            if text and iid not in text:
                problems.append(f"{ISSUES_DOC} 未列出问题 {iid}")
            if (str(item.get("status") or "").lower() in _CLOSED_STATES
                    and not str(item.get("closure") or "").strip()):
                problems.append(f"{iid} 已关闭但缺少关闭说明")
    if problems:
        raise PipelineStepError("SUP.9 问题解决门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "sup9-review", status="completed",
                       verified=[ISSUES_DOC, ISSUE_REGISTER])
    return str(Path(session.project_dir) / ISSUES_DOC)


# ══════════════════════════════════════════════════════════════════════
# SUP.10 变更请求管理
# ══════════════════════════════════════════════════════════════════════


def _normalize_changes(records: list[dict]) -> list[dict]:
    items: list[dict] = []
    for record in records:
        items.append({
            "id": _record_id(record),
            "title": str(record.get("title") or record.get("summary")
                         or record.get("description") or "").strip(),
            "status": str(record.get("status") or "待分析").strip(),
            "decision": str(record.get("decision") or record.get("resolution")
                           or "").strip(),
            "source": str(record.get("source") or ""),
        })
    return items


def _build_change_doc(items: list[dict]) -> str:
    rows = [
        f"| {_cell(i['id'])} | {_cell(i['title'])} | {i['status']} "
        f"| {_cell(i['decision']) or '—'} |"
        for i in items
    ]
    listing = "\n".join(rows) if rows else f"| — | {_NO_CR} | — | — |"
    return (
        "# 变更请求记录（SUP.10）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 变更请求数：{len(items)}\n\n"
        "## 变更请求列表\n\n"
        "| ID | 标题 | 状态 | 决策 |\n|:---|:---|:---|:---|\n"
        + listing + "\n\n"
        + ("" if items else
           "> 本次扫描未命中任何变更请求记录；不推断、不补造条目。\n\n")
        + "## 决策与状态\n\n"
        "- 已批准变更必须填写决策依据；被拒绝变更保留原因。\n"
        "- 待人工确认：变更影响分析、批准人与实施批次。\n\n"
        "## 数据来源\n\n"
        "- `change-requests/*.json`、`.osh/ci/change-*.json`（真实记录，含零命中）。\n"
    )


def step_sup10_change(session: PipelineSession) -> str:
    """SUP.10 — 汇总真实变更请求记录。"""
    records, sources = _scan_json_records(
        session.project_dir,
        ("change-requests/*.json", ".osh/ci/change-*.json"), "SUP.10")
    items = _normalize_changes(records)
    _save_yaml(session.project_dir, CR_REGISTER, {
        "version": 1,
        "generated_at": _now(),
        "scan_sources": sources,
        "items": items,
    })
    doc_path = _write_doc(session, CR_DOC, _build_change_doc(items))
    _write_step_marker(session, "sup10-change", status="completed",
                       doc=CR_DOC, register=CR_REGISTER,
                       item_count=len(items))
    return str(doc_path)


def step_review_sup10(session: PipelineSession) -> str:
    """SUP.10 门禁：登记结构 + 文档一致性 + 批准决策。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, CR_DOC,
                             _CR_SECTIONS, problems)
    data = _load_yaml(session.project_dir, CR_REGISTER)
    if not data:
        problems.append(f"缺少或无法解析 {CR_REGISTER}")
    else:
        if not data.get("scan_sources"):
            problems.append(f"{CR_REGISTER} 缺少 scan_sources（无扫描证据）")
        items = [i for i in data.get("items") or [] if isinstance(i, dict)]
        if not items and text and _NO_CR not in text:
            problems.append(f"{CR_DOC} 未明示无变更请求（{_NO_CR}）")
        seen: set[str] = set()
        for item in items:
            cid = str(item.get("id") or "").strip()
            if not cid:
                problems.append(f"{CR_REGISTER} 存在缺少 id 的条目")
                continue
            if cid in seen:
                problems.append(f"{CR_REGISTER} 条目 id 重复: {cid}")
            seen.add(cid)
            if not str(item.get("title") or "").strip():
                problems.append(f"{cid} 缺少标题")
            if text and cid not in text:
                problems.append(f"{CR_DOC} 未列出变更请求 {cid}")
            if (str(item.get("status") or "").lower() in _APPROVED_STATES
                    and not str(item.get("decision") or "").strip()):
                problems.append(f"{cid} 已批准但缺少决策依据")
    if problems:
        raise PipelineStepError("SUP.10 变更请求门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "sup10-review", status="completed",
                       verified=[CR_DOC, CR_REGISTER])
    return str(Path(session.project_dir) / CR_DOC)


# ══════════════════════════════════════════════════════════════════════
# MAN.3 项目管理
# ══════════════════════════════════════════════════════════════════════


def _load_milestones(project_dir: str) -> list[dict]:
    data = _read_json(Path(project_dir) / MILESTONES)
    if not isinstance(data, list):
        return []
    return [m for m in data if isinstance(m, dict)]


def _build_project_plan(milestones: list[dict]) -> str:
    rows = [
        f"| {_cell(m.get('id') or m.get('name'))} | {_cell(m.get('title'))} "
        f"| {_cell(m.get('due') or m.get('date'))} | {_cell(m.get('status'))} |"
        for m in milestones
    ]
    listing = "\n".join(rows) if rows else f"| — | {_NO_MILESTONE} | — | — |"
    return (
        "# 项目计划（MAN.3）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 里程碑数量：{len(milestones)}\n\n"
        "## 项目范围\n\n"
        "- 范围以 `docs/system-requirements.md` 与项目任务分解为准。\n"
        "- 待人工确认：项目负责人、预算、资源与交付边界。\n\n"
        "## 里程碑\n\n"
        "| ID | 里程碑 | 计划日期 | 状态 |\n|:---|:---|:---|:---|\n"
        + listing + "\n\n"
        + ("" if milestones else
           "> 本次未检测到里程碑记录；里程碑待人工确认，"
           "不得据此判定项目计划已建立。\n\n")
        + "## 进度跟踪\n\n"
        "- 按里程碑跟踪进度与偏差；偏差须记录纠正措施。\n"
        "- 已完成里程碑必须提供完成证据。\n\n"
        "## 数据来源\n\n"
        f"- `{MILESTONES}`（真实里程碑记录，缺失时如实记录为空）。\n"
    )


def step_man3_project(session: PipelineSession) -> str:
    """MAN.3 — 汇总真实里程碑并生成项目计划。"""
    milestones = _load_milestones(session.project_dir)
    target = Path(session.project_dir) / MILESTONES
    if not target.is_file():
        # 仅创建空清单占位，不臆造任何里程碑；空列表不会被判为已建立计划。
        _write_json(session, MILESTONES, [])
    doc_path = _write_doc(session, PROJECT_PLAN,
                          _build_project_plan(milestones))
    _write_step_marker(session, "man3-project", status="completed",
                       plan=PROJECT_PLAN, milestones=MILESTONES,
                       milestone_count=len(milestones))
    return str(doc_path)


def step_review_man3(session: PipelineSession) -> str:
    """MAN.3 门禁：计划章节 + 里程碑结构 + 完成证据。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, PROJECT_PLAN,
                             _PLAN_SECTIONS, problems)
    raw = _read_json(Path(session.project_dir) / MILESTONES)
    if not isinstance(raw, list):
        problems.append(f"缺少或无法解析里程碑清单 {MILESTONES}（应为 JSON 数组）")
    else:
        milestones = [m for m in raw if isinstance(m, dict)]
        if len(milestones) != len(raw):
            problems.append(f"{MILESTONES} 存在非对象条目")
        if not milestones and text and _NO_MILESTONE not in text:
            problems.append(f"{PROJECT_PLAN} 未明示无里程碑（{_NO_MILESTONE}）")
        seen: set[str] = set()
        for milestone in milestones:
            mid = str(milestone.get("id") or milestone.get("name") or "").strip()
            if not mid:
                problems.append(f"{MILESTONES} 存在缺少 id 的里程碑")
                continue
            if mid in seen:
                problems.append(f"{MILESTONES} 里程碑 id 重复: {mid}")
            seen.add(mid)
            if not str(milestone.get("title") or "").strip():
                problems.append(f"{mid} 缺少标题")
            if text and mid not in text:
                problems.append(f"{PROJECT_PLAN} 未列出里程碑 {mid}")
            if (str(milestone.get("status") or "").lower() in _DONE_STATES
                    and not str(milestone.get("evidence") or "").strip()):
                problems.append(f"{mid} 已完成但缺少完成证据")
    if problems:
        raise PipelineStepError("MAN.3 项目管理门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "man3-review", status="completed",
                       verified=[PROJECT_PLAN, MILESTONES])
    return str(Path(session.project_dir) / PROJECT_PLAN)


# ══════════════════════════════════════════════════════════════════════
# MAN.1 项目管理（项目章程）
# ══════════════════════════════════════════════════════════════════════


def _load_charter(project_dir: str) -> dict | None:
    data = _read_json(Path(project_dir) / CHARTER_FILE)
    if not isinstance(data, dict):
        return None
    return data


def _build_charter_doc(charter: dict | None, sources: list[str]) -> str:
    if charter:
        purpose = str(charter.get("purpose") or charter.get("objective") or "—").strip()
        scope = str(charter.get("scope") or charter.get("deliverables") or "—").strip()
        owner = str(charter.get("owner") or charter.get("manager") or "待指定").strip()
        budget = str(charter.get("budget") or "未声明").strip()
        schedule = str(charter.get("schedule") or "未声明").strip()
        risk = str(charter.get("top_risk") or "未声明").strip()
        charter_row = (
            "| 字段 | 值 |\n|:---|:---|\n"
            f"| 项目目的 | {_cell(purpose)} |\n"
            f"| 范围与交付 | {_cell(scope)} |\n"
            f"| 负责人 | {_cell(owner)} |\n"
            f"| 预算 | {_cell(budget)} |\n"
            f"| 进度 | {_cell(schedule)} |\n"
            f"| 主要风险 | {_cell(risk)} |\n"
        )
    else:
        charter_row = f"> {_NO_CHARTER}\n\n"

    return (
        "# 项目章程（MAN.1）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 章程来源：{CHARTER_FILE}（存在={charter is not None}）\n\n"
        "## 项目目的\n\n"
        f"{charter_row if not charter else '见下表。'}\n\n"
        + (charter_row if charter else "")
        + "## 范围与交付\n\n"
        "- 范围以 `docs/system-requirements.md` 为准。\n"
        "- 待人工确认：交付物清单、验收标准、合同约束。\n\n"
        "## 角色与资源\n\n"
        "- 项目负责人、架构师、测试负责人角色待明确。\n"
        "- 待人工确认：资源分配、外包比例、关键技能缺口。\n\n"
        "## 预算与进度\n\n"
        "- 预算与进度基线以 MAN.3 的里程碑为准。\n"
        "- 待人工确认：风险储备预算与关键路径。\n\n"
        "## 数据来源\n\n"
        + "\n".join(f"- `{s}`" for s in sources) + "\n"
    )


def step_man1_charter(session: PipelineSession) -> str:
    """MAN.1 — 生成项目章程文档。"""
    charter = _load_charter(session.project_dir)
    target = Path(session.project_dir) / CHARTER_FILE
    sources: list[str] = [f"file:{CHARTER_FILE}"]
    if not target.is_file():
        # 不臆造章程，只写空壳占位文件让评审能检测到；
        # 空壳会被判定为"内容不足"，门禁会告警。
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_json(session, CHARTER_FILE, {})
        charter = {}
        sources.append("auto:placeholder")
    doc_path = _write_doc(session, PROJECT_CHARTER,
                          _build_charter_doc(charter, sources))
    _write_step_marker(session, "man1-charter", status="completed",
                       doc=PROJECT_CHARTER, charter=CHARTER_FILE,
                       charter_present=bool(charter and charter.get("purpose")))
    return str(doc_path)


def step_review_man1(session: PipelineSession) -> str:
    """MAN.1 门禁：章节齐全 + 章程字段非空。"""
    problems: list[str] = []
    _require_sections(session.project_dir, PROJECT_CHARTER,
                      _CHARTER_SECTIONS, problems)
    charter = _load_charter(session.project_dir)
    if charter is None:
        problems.append(f"缺少或无法解析 {CHARTER_FILE}")
    elif not charter.get("purpose"):
        problems.append(f"{CHARTER_FILE} 缺少项目目的字段 purpose")
    elif not charter.get("scope") and not charter.get("deliverables"):
        problems.append(f"{CHARTER_FILE} 缺少范围/交付物字段 scope 或 deliverables")
    if problems:
        raise PipelineStepError("MAN.1 项目管理门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "man1-review", status="completed",
                       verified=[PROJECT_CHARTER, CHARTER_FILE])
    return str(Path(session.project_dir) / PROJECT_CHARTER)


# ══════════════════════════════════════════════════════════════════════
# MAN.2 需求管理（基线 + 变更跟踪）
# ══════════════════════════════════════════════════════════════════════


def _normalize_req_changes(records: list[dict]) -> list[dict]:
    items: list[dict] = []
    for record in records:
        req_ids = record.get("req_ids") or record.get("affected") or record.get("requirements") or []
        if isinstance(req_ids, str):
            req_ids = [x.strip() for x in req_ids.split(",") if x.strip()]
        items.append({
            "id": _record_id(record),
            "title": str(record.get("title") or record.get("summary") or "").strip(),
            "status": str(record.get("status") or "待分析").strip(),
            "decision": str(record.get("decision") or "").strip(),
            "req_ids": req_ids if isinstance(req_ids, list) else [],
            "source": str(record.get("source") or ""),
        })
    return items


def _build_req_baseline_doc(items: list[dict]) -> str:
    rows = [
        f"| {_cell(i['id'])} | {_cell(i['title'])} | {i['status']} "
        f"| {_cell(', '.join(i['req_ids'])) or '—'} |"
        for i in items
    ]
    listing = "\n".join(rows) if rows else f"| — | {_NO_REQ_CHANGE} | — | — |"
    return (
        "# 需求基线与变更（MAN.2）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 变更记录数：{len(items)}\n\n"
        "## 需求基线\n\n"
        "- 基线来源：`docs/system-requirements.md`、`docs/spec.md`。\n"
        "- 需求 ID 应与 SYS.1/SWE.1 步骤的原文一致，不得改写或缩写。\n"
        "- 基线一经批准不得原地修改；变更须走 SUP.10 变更请求流程。\n\n"
        "## 变更日志\n\n"
        "| ID | 标题 | 状态 | 影响需求 |\n|:---|:---|:---|:---|\n"
        + listing + "\n\n"
        + ("" if items else
           "> 本次未检测到需求变更记录；不推断、不补造条目。\n\n")
        + "## 数据来源\n\n"
        "- `change-requests/*.json`、`.osh/ci/change-*.json`（真实记录，含零命中）。\n"
    )


def step_man2_requirements(session: PipelineSession) -> str:
    """MAN.2 — 汇总真实需求变更记录，建立基线文档。"""
    records, sources = _scan_json_records(
        session.project_dir,
        ("change-requests/*.json", ".osh/ci/change-*.json",
         ".osh/reqs/change-*.yaml", ".osh/reqs/change-*.json"),
        "MAN.2")
    items = _normalize_req_changes(records)
    _save_yaml(session.project_dir, REQ_CHANGE_LOG, {
        "version": 1,
        "generated_at": _now(),
        "scan_sources": sources,
        "items": items,
    })
    doc_path = _write_doc(session, REQUIREMENTS_BASELINE,
                          _build_req_baseline_doc(items))
    _write_step_marker(session, "man2-requirements", status="completed",
                       doc=REQUIREMENTS_BASELINE, register=REQ_CHANGE_LOG,
                       item_count=len(items))
    return str(doc_path)


def step_review_man2(session: PipelineSession) -> str:
    """MAN.2 门禁：章节齐全 + 登记结构 + 已批准变更有决策。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, REQUIREMENTS_BASELINE,
                             _REQ_BASELINE_SECTIONS, problems)
    data = _load_yaml(session.project_dir, REQ_CHANGE_LOG)
    if not data:
        problems.append(f"缺少或无法解析 {REQ_CHANGE_LOG}")
    else:
        if not data.get("scan_sources"):
            problems.append(f"{REQ_CHANGE_LOG} 缺少 scan_sources（无扫描证据）")
        items = [i for i in data.get("items") or [] if isinstance(i, dict)]
        if not items and text and _NO_REQ_CHANGE not in text:
            problems.append(f"{REQUIREMENTS_BASELINE} 未明示无变更记录（{_NO_REQ_CHANGE}）")
        seen: set[str] = set()
        for item in items:
            cid = str(item.get("id") or "").strip()
            if not cid:
                problems.append(f"{REQ_CHANGE_LOG} 存在缺少 id 的条目")
                continue
            if cid in seen:
                problems.append(f"{REQ_CHANGE_LOG} 条目 id 重复: {cid}")
            seen.add(cid)
            if not str(item.get("title") or "").strip():
                problems.append(f"{cid} 缺少标题")
            if text and cid not in text:
                problems.append(f"{REQUIREMENTS_BASELINE} 未列出变更 {cid}")
            if (str(item.get("status") or "").lower() in _APPROVED_STATES
                    and not str(item.get("decision") or "").strip()):
                problems.append(f"{cid} 已批准但缺少决策依据")
    if problems:
        raise PipelineStepError("MAN.2 需求管理门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "man2-review", status="completed",
                       verified=[REQUIREMENTS_BASELINE, REQ_CHANGE_LOG])
    return str(Path(session.project_dir) / REQUIREMENTS_BASELINE)


# ══════════════════════════════════════════════════════════════════════
# MAN.4 质量管理（过程审计 + 质量改进）
# ══════════════════════════════════════════════════════════════════════


def _normalize_quality_records(records: list[dict]) -> list[dict]:
    items: list[dict] = []
    for record in records:
        kind = str(record.get("kind") or record.get("type") or "audit").strip().lower()
        if kind in ("improvement", "改进", "fix", "correction"):
            kind = "improvement"
        else:
            kind = "audit"
        items.append({
            "id": _record_id(record),
            "kind": kind,
            "title": str(record.get("title") or record.get("finding") or "").strip(),
            "status": str(record.get("status") or "待分析").strip(),
            "closure": str(record.get("closure") or record.get("resolution") or "").strip(),
            "source": str(record.get("source") or ""),
        })
    return items


def _build_qm_doc(items: list[dict]) -> str:
    audit_rows = [
        f"| {_cell(i['id'])} | {_cell(i['title'])} | {i['status']} | {_cell(i['closure']) or '—'} |"
        for i in items if i["kind"] == "audit"
    ]
    improv_rows = [
        f"| {_cell(i['id'])} | {_cell(i['title'])} | {i['status']} | {_cell(i['closure']) or '—'} |"
        for i in items if i["kind"] == "improvement"
    ]
    audit_listing = ("\n".join(audit_rows) if audit_rows
                     else f"| — | {_NO_QUALITY} | — | — |")
    improv_listing = ("\n".join(improv_rows) if improv_rows
                      else f"| — | {_NO_QUALITY} | — | — |")
    return (
        "# 质量管理（MAN.4）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 审计记录数：{len(audit_rows)}；改进记录数：{len(improv_rows)}\n\n"
        "## 质量策略\n\n"
        "- 质量目标以组织过程定义与 SUP.1 质量保证计划为准。\n"
        "- 过程审计独立执行；发现须跟踪至关闭。\n\n"
        "## 过程审计\n\n"
        "| ID | 发现 | 状态 | 关闭说明 |\n|:---|:---|:---|:---|\n"
        + audit_listing + "\n\n"
        + ("" if audit_rows else
           "> 本次未检测到过程审计记录；不推断、不补造条目。\n\n")
        + "## 质量改进\n\n"
        "| ID | 改进项 | 状态 | 关闭说明 |\n|:---|:---|:---|:---|\n"
        + improv_listing + "\n\n"
        + ("" if improv_rows else
           "> 本次未检测到质量改进记录；不推断、不补造条目。\n\n")
        + "## 数据来源\n\n"
        "- `.osh/ci/*quality*.json`、`.osh/ci/*audit*.json`、"
        "`.osh/project/improvements/*.json`（真实记录，含零命中）。\n"
    )


def step_man4_quality(session: PipelineSession) -> str:
    """MAN.4 — 汇总真实质量审计与改进记录。"""
    records, sources = _scan_json_records(
        session.project_dir,
        (".osh/ci/*quality*.json", ".osh/ci/*audit*.json",
         ".osh/project/improvements/*.json"),
        "MAN.4")
    items = _normalize_quality_records(records)
    _save_yaml(session.project_dir, QM_REGISTER, {
        "version": 1,
        "generated_at": _now(),
        "scan_sources": sources,
        "items": items,
    })
    doc_path = _write_doc(session, QM_DOC, _build_qm_doc(items))
    _write_step_marker(session, "man4-quality", status="completed",
                       doc=QM_DOC, register=QM_REGISTER,
                       item_count=len(items))
    return str(doc_path)


def step_review_man4(session: PipelineSession) -> str:
    """MAN.4 门禁：章节齐全 + 登记结构 + 已关闭有说明。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, QM_DOC,
                             _QM_SECTIONS, problems)
    data = _load_yaml(session.project_dir, QM_REGISTER)
    if not data:
        problems.append(f"缺少或无法解析 {QM_REGISTER}")
    else:
        if not data.get("scan_sources"):
            problems.append(f"{QM_REGISTER} 缺少 scan_sources（无扫描证据）")
        items = [i for i in data.get("items") or [] if isinstance(i, dict)]
        if not items and text and _NO_QUALITY not in text:
            problems.append(f"{QM_DOC} 未明示无质量记录（{_NO_QUALITY}）")
        seen: set[str] = set()
        for item in items:
            qid = str(item.get("id") or "").strip()
            if not qid:
                problems.append(f"{QM_REGISTER} 存在缺少 id 的条目")
                continue
            if qid in seen:
                problems.append(f"{QM_REGISTER} 条目 id 重复: {qid}")
            seen.add(qid)
            if not str(item.get("title") or "").strip():
                problems.append(f"{qid} 缺少标题/发现描述")
            if text and qid not in text:
                problems.append(f"{QM_DOC} 未列出质量记录 {qid}")
            if (str(item.get("status") or "").lower() in _CLOSED_STATES
                    and not str(item.get("closure") or "").strip()):
                problems.append(f"{qid} 已关闭但缺少关闭说明")
    if problems:
        raise PipelineStepError("MAN.4 质量管理门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "man4-review", status="completed",
                       verified=[QM_DOC, QM_REGISTER])
    return str(Path(session.project_dir) / QM_DOC)
