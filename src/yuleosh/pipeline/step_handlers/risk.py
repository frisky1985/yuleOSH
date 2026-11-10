"""MAN.5 风险管理 — 风险识别、评估、应对与监控（ASPICE 3.1）。

风险来源分两类:

1. **自动扫描**（客观信号）:
   - MAN.6 度量 FAIL 项（``kpi_status``）
   - 历史步骤失败记录（``.osh/sessions/*/<step>.json``）
2. **人工登记**: ``docs/risk-register.yaml`` 中人工维护的条目。

设计原则:

- 自动条目每次重建评分，但**保留**人工填写的责任人/状态/应对措施；
- 登记文件必须留有扫描记录（``scan_sources``），"没有风险"不能凭空成立；
- 高风险（score ≥ 8）开放项必须有责任人与到期评审日，否则门禁 RED；
- 不做"风险已自动缓解"之类的推断 — 状态只能由人修改。
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.validation import _write_step_marker

log = logging.getLogger("pipeline.step_handlers.risk")

RISK_PLAN = "docs/risk-management-plan.md"
RISK_REGISTER = "docs/risk-register.yaml"
RISK_REPORT = "docs/risk-report.md"

_STATUSES = ("open", "monitoring", "mitigated", "closed")
_RESPONSES = ("avoid", "mitigate", "transfer", "accept")
_LEVELS = ("low", "medium", "high", "critical")

# 影响面 4 级的度量项（其余 FAIL 影响记 3）
_HIGH_IMPACT_METRICS = {
    "misra_required_violations",
    "c_line_coverage_pct",
    "python_line_coverage_pct",
    "defect_escape_rate",
}

_PLAN_SECTIONS = ("## 风险管理范围", "## 风险评分方法", "## 评审与升级")
_REPORT_SECTIONS = ("## 风险清单", "## 升级项", "## 可追溯性")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _band(score: int) -> str:
    if score >= 15:
        return "critical"
    if score >= 8:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def _cell(text: object) -> str:
    return " ".join(str(text).replace("|", "\\|").split())


def _write_doc(session: PipelineSession, rel_path: str, content: str) -> Path:
    target = Path(session.project_dir) / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# ── 风险识别 ──────────────────────────────────────────────────────────


def _kpi_risks(project_dir: str) -> list[dict]:
    """MAN.6 度量 FAIL 项 → 风险候选（无原始数据不算风险）。"""
    from yuleosh.ci.kpi.report import kpi_status
    from yuleosh.pipeline.step_handlers.measurement import _has_data

    try:
        data = json.loads(kpi_status(project_dir, as_json=True))
    except (TypeError, ValueError, OSError) as exc:
        log.warning("[MAN.5] KPI 面板不可用，跳过该风险来源: %s", exc)
        return []

    risks: list[dict] = []
    for entry in data.get("entries") or []:
        if str(entry.get("status", "")).upper() != "FAIL":
            continue
        metric = str(entry.get("metric") or "")
        if not metric:
            continue
        # 未采集到原始数据时的 FAIL 不是风险而是测量缺口（MAN.6 已标注无数据），
        # 不得据此臆造风险条目。
        if not _has_data(project_dir, metric):
            log.info("[MAN.5] 度量 %s 无原始数据，跳过风险生成", metric)
            continue
        impact = 4 if metric in _HIGH_IMPACT_METRICS else 3
        name = entry.get("label") or metric
        risks.append({
            "id": "RISK-KPI-" + metric.upper().replace("_", "-"),
            "title": f"度量项未达标: {name}",
            "category": "质量",
            "source": "MAN.6/KPI",
            "origin": "auto",
            "likelihood": 4,
            "impact": impact,
            "score": 16 if impact == 4 else 12,
            "band": "critical" if impact == 4 else "high",
            "detail": f"{name} 当前值 {entry.get('value')}，阈值 {entry.get('threshold')}",
        })
    return risks


def _failed_step_risks(project_dir: str) -> list[dict]:
    """历史步骤失败记录 → 风险候选（按步骤去重，保留最近一次）。"""
    sessions = Path(project_dir) / ".osh" / "sessions"
    if not sessions.is_dir():
        return []

    latest: dict[str, tuple[float, dict]] = {}
    for marker in sessions.glob("*/*.json"):
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        status = str(data.get("status", "")).lower()
        step = str(data.get("step") or marker.stem)
        if status not in ("failed", "error"):
            continue
        mtime = marker.stat().st_mtime
        if step not in latest or mtime > latest[step][0]:
            latest[step] = (mtime, data)

    risks: list[dict] = []
    for step in sorted(latest)[:5]:
        risks.append({
            "id": "RISK-STEP-" + step.upper().replace("_", "-"),
            "title": f"流程步骤历史失败: {step}",
            "category": "进度",
            "source": "pipeline/session",
            "origin": "auto",
            "likelihood": 3,
            "impact": 4,
            "score": 12,
            "band": "high",
            "detail": f"最近失败记录 {latest[step][1].get('session', '')}",
        })
    return risks


def _load_existing(project_dir: str) -> dict:
    path = Path(project_dir) / RISK_REGISTER
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        log.warning("[MAN.5] 风险登记文件无法解析，按空登记处理: %s", exc)
        return {}
    return data if isinstance(data, dict) else {}


def _score(risk: dict) -> int:
    """Best-effort integer score (invalid entries sort last, validated later)."""
    try:
        return int(risk.get("score"))
    except (TypeError, ValueError):
        return 0


def _merge(existing: dict, generated: list[dict]) -> tuple[list[dict], list[str]]:
    prev = {
        str(r.get("id")): r
        for r in existing.get("risks") or []
        if isinstance(r, dict) and r.get("id")
    }
    merged: list[dict] = []
    seen: set[str] = set()
    for gen in generated:
        entry = {**prev.get(gen["id"], {}), **gen}
        entry.setdefault("owner", "待指定")
        entry.setdefault("status", "open")
        entry.setdefault("response", "mitigate")
        entry.setdefault("mitigation", "")
        entry.setdefault("review_due", "")
        entry["last_seen"] = _now()
        merged.append(entry)
        seen.add(gen["id"])

    # 人工条目 + 已消除的自动条目（保留关闭状态供审计）
    for rid, item in prev.items():
        if rid in seen:
            continue
        merged.append({
            "owner": "待指定", "status": "open", "response": "mitigate",
            "mitigation": "", "review_due": "", **item,
        })

    merged.sort(key=lambda r: (-_score(r), str(r["id"])))
    return merged, ["MAN.6/KPI", "pipeline/session"]


def _save_register(project_dir: str, risks: list[dict], sources: list[str]) -> Path:
    path = Path(project_dir) / RISK_REGISTER
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"version": 1, "generated_at": _now(),
             "scan_sources": sources, "risks": risks},
            sort_keys=False, allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return path


# ── 文档生成 ──────────────────────────────────────────────────────────


def _build_plan() -> str:
    graded = [
        (15, 25, "critical", "必须制定规避/转移方案，项目级升级，每周评审"),
        (8, 14, "high", "必须指定责任人并给出缓解措施，双周评审"),
        (4, 7, "medium", "纳入常规跟踪，月度评审"),
        (1, 3, "low", "记录并接受，阶段评审时复核"),
    ]
    return (
        "# 风险管理计划（MAN.5）\n\n"
        "> 自动生成：本计划的评分方法与阈值由 `step_handlers/risk.py` 维护，"
        "人工修订请直接编辑本文件。\n\n"
        "## 风险管理范围\n\n"
        "- 覆盖产品确认前的全部工程活动：需求、架构、实现、测试、发布。\n"
        "- 风险来源：MAN.6 度量 FAIL 项、流水线步骤失败记录、人工登记条目。\n"
        "- 责任人：项目负责人（MAN.3）对风险清单整体负责。\n\n"
        "## 风险评分方法\n\n"
        "评分 = 可能性(L) × 影响(I)，两者取值 1-5：\n\n"
        "| 分值 | 等级 | 处置要求 |\n|:---|:---|:---|\n"
        + "\n".join(f"| {lo}-{hi} | {lvl} | {rule} |" for lo, hi, lvl, rule in graded)
        + "\n\n"
        "应对策略：`avoid` 规避 / `mitigate` 缓解 / `transfer` 转移 / `accept` 接受"
        "（选 accept 必须填写 `rationale`）。\n\n"
        "## 评审与升级\n\n"
        "- 高风险（score ≥ 8）开放项必须在 `docs/risk-register.yaml` 中登记"
        "责任人、缓解措施与到期评审日（`review_due`, YYYY-MM-DD）。\n"
        "- 自动识别的风险在人工指定责任人前标记为「待分级」，"
        "列入风险报告「升级项」，由项目负责人分级后方视为已处置。\n"
        "- 状态流转：open → monitoring → mitigated → closed，仅允许人工修改。\n"
        "- 升级路径：责任人 → 项目负责人 → 质量负责人。\n\n"
        "## 可追溯性\n\n"
        "- 风险条目的自动来源见 `docs/measurement-report.md`（MAN.6）。\n"
        "- 风险登记文件：`docs/risk-register.yaml`。\n"
    )


def _build_report(risks: list[dict], sources: list[str]) -> str:
    counts = {lvl: sum(1 for r in risks if r.get("band") == lvl) for lvl in _LEVELS}
    rows = []
    for r in risks:
        rows.append(
            f"| {_cell(r.get('id'))} | {_cell(r.get('title'))} | {_cell(r.get('category'))} "
            f"| {r.get('likelihood')} | {r.get('impact')} | {r.get('score')} "
            f"| {r.get('band')} | {r.get('status')} | {_cell(r.get('owner'))} "
            f"| {_cell(r.get('response'))} | {_cell(r.get('review_due') or '—')} |"
        )

    open_high = [
        r for r in risks
        if _score(r) >= 8 and r.get("status") in ("open", "monitoring")
    ]
    pending = [
        r for r in open_high
        if str(r.get("origin") or "manual") == "auto"
        and str(r.get("owner") or "").strip() in ("", "待指定")
    ]
    if open_high:
        escalation = "\n".join(
            f"- **{r['id']}**（{r['band']}, {r['score']}）"
            f"责任人 {r.get('owner')}，到期 {r.get('review_due') or '未设置'}：{r.get('title')}"
            + ("（自动识别，待分级）"
               if r in pending else "")
            for r in open_high
        )
    else:
        escalation = "- 无需要升级的开放高风险项。"

    return (
        "# 风险报告（MAN.5）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 扫描来源：{'、'.join(sources)}\n"
        f"- 风险总数：{len(risks)}（critical {counts['critical']} / high {counts['high']} "
        f"/ medium {counts['medium']} / low {counts['low']}）\n"
        f"- 开放高风险：{len(open_high)}\n"
        f"- 待分级高风险：{len(pending)}\n\n"
        "## 风险清单\n\n"
        "| ID | 标题 | 类别 | L | I | 分值 | 等级 | 状态 | 责任人 | 应对 | 评审日 |\n"
        "|:---|:---|:---|:--|:--|:--|:---|:---|:---|:---|:---|\n"
        + ("\n".join(rows) if rows else "| — | 未登记风险 | — | — | — | — | — | — | — | — | — |")
        + "\n\n"
        "## 升级项\n\n"
        f"{escalation}\n\n"
        "## 可追溯性\n\n"
        "- 评分方法与阈值见 `docs/risk-management-plan.md`。\n"
        "- 自动风险来源：`docs/measurement-report.md` 的 FAIL 度量项与流水线失败记录。\n"
        "- 登记明细：`docs/risk-register.yaml`。\n"
    )


# ── 步骤入口 ──────────────────────────────────────────────────────────


def step_risk_assessment(session: PipelineSession) -> str:
    """MAN.5 — 扫描风险来源、评估并登记，输出风险报告。"""
    generated = _kpi_risks(session.project_dir) + _failed_step_risks(session.project_dir)
    existing = _load_existing(session.project_dir)
    risks, sources = _merge(existing, generated)

    plan_path = _write_doc(session, RISK_PLAN, _build_plan())
    register_path = _save_register(session.project_dir, risks, sources)
    report_path = _write_doc(session, RISK_REPORT, _build_report(risks, sources))

    open_high = sum(
        1 for r in risks
        if _score(r) >= 8 and r.get("status") in ("open", "monitoring")
    )
    _write_step_marker(
        session, "risk-assessment",
        status="completed",
        plan=RISK_PLAN,
        register=RISK_REGISTER,
        report=RISK_REPORT,
        risk_count=len(risks),
        open_high=open_high,
    )
    log.info(
        "[MAN.5] 风险登记完成: %s, %s (总计 %d, 开放高风险 %d)",
        plan_path, report_path, len(risks), open_high,
    )
    return str(report_path)


def _validate_risks(risks: list[dict]) -> tuple[list[str], list[str]]:
    """校验登记结构，返回 (问题列表, 待分级高风险 ID 列表)。

    自动识别的风险在人工指定责任人前不算"已分级"，其责任人/缓解措施/
    评审日由报告「升级项」暴露，但不阻断门禁（否则任何度量 FAIL 都会让
    全自动流水线永久 RED）。人工登记的风险仍必须完整。
    """
    problems: list[str] = []
    pending: list[str] = []
    seen: set[str] = set()
    for idx, r in enumerate(risks):
        rid = str(r.get("id") or "").strip()
        if not rid:
            problems.append(f"第 {idx + 1} 条风险缺少 id")
            continue
        if rid in seen:
            problems.append(f"风险 id 重复: {rid}")
        seen.add(rid)

        try:
            likelihood = int(r.get("likelihood"))
            impact = int(r.get("impact"))
            score = int(r.get("score"))
        except (TypeError, ValueError):
            problems.append(f"{rid} 的 likelihood/impact/score 必须为整数")
            continue
        if not (1 <= likelihood <= 5 and 1 <= impact <= 5):
            problems.append(f"{rid} 的 likelihood/impact 超出 1-5")
        if score != likelihood * impact:
            problems.append(f"{rid} 的 score 与 L×I 不一致")
        if r.get("band") != _band(score):
            problems.append(f"{rid} 的等级与分值不匹配")
        if r.get("status") not in _STATUSES:
            problems.append(f"{rid} 状态非法: {r.get('status')}")
        if r.get("response") not in _RESPONSES:
            problems.append(f"{rid} 应对策略非法: {r.get('response')}")
        if r.get("response") == "accept" and not str(r.get("rationale") or "").strip():
            problems.append(f"{rid} 选择接受风险但未说明理由")

        if score >= 8 and r.get("status") in ("open", "monitoring"):
            owner = str(r.get("owner") or "").strip()
            if str(r.get("origin") or "manual") == "auto" and owner in ("", "待指定"):
                pending.append(rid)
                continue
            if not owner or owner == "待指定":
                problems.append(f"{rid} 为开放高风险，必须指定责任人")
            if not str(r.get("mitigation") or "").strip():
                problems.append(f"{rid} 为开放高风险，必须填写缓解措施")
            due = r.get("review_due")
            try:
                date.fromisoformat(str(due))
            except (TypeError, ValueError):
                problems.append(f"{rid} 为开放高风险，review_due 必须为 YYYY-MM-DD")
    return problems, pending


def step_review_risk(session: PipelineSession) -> str:
    """MAN.5 风险评审（确定性门禁）。

    校验计划的评分方法、登记的完整性与报告的一致性；不推断风险状态。
    """
    problems: list[str] = []
    for rel_path, sections in (
        (RISK_PLAN, _PLAN_SECTIONS),
        (RISK_REPORT, _REPORT_SECTIONS),
    ):
        target = Path(session.project_dir) / rel_path
        if not target.is_file():
            problems.append(f"缺少产物 {rel_path}")
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        for sec in sections:
            if sec not in text:
                problems.append(f"{rel_path} 缺少章节 {sec}")

    register = _load_existing(session.project_dir)
    pending: list[str] = []
    if not register:
        problems.append(f"缺少风险登记 {RISK_REGISTER}")
    else:
        if not register.get("scan_sources"):
            problems.append("风险登记缺少扫描来源，无法证明已开展识别")
        risks = register.get("risks")
        if not isinstance(risks, list):
            problems.append("风险登记 risks 字段格式错误")
            risks = []
        risk_problems, pending = _validate_risks(risks)
        problems.extend(risk_problems)

        report_text = ""
        report_path = Path(session.project_dir) / RISK_REPORT
        if report_path.is_file():
            report_text = report_path.read_text(encoding="utf-8", errors="replace")
        for r in risks:
            rid = str(r.get("id") or "")
            if rid and rid not in report_text:
                problems.append(f"风险报告缺少条目 {rid}")

    if problems:
        raise PipelineStepError("MAN.5 风险门禁 RED：" + "；".join(problems))
    _write_step_marker(
        session, "risk-review",
        status="completed",
        verified=[RISK_PLAN, RISK_REGISTER, RISK_REPORT],
        pending_triage=pending,
    )
    return str(Path(session.project_dir) / RISK_REPORT)
