"""管理支撑过程 — ACQ.4 / REU.2 / PIM.3 / SPL.2（ASPICE 3.1）。

四类过程均为 **确定性生成 + 确定性评审**（与 MAN.5 / MAN.6 一致）：

- **ACQ.4 供应商监控**：自动盘点第三方依赖（``pyproject.toml`` /
  ``requirements*.txt``）作为供应商清单的初始输入；人工评估字段在登记
  文件中保留并跨轮次生效。
- **REU.2 复用管理**：自动识别 ``src/`` 下的内部组件作为复用候选；
  是否复用由人决定，流水线不代替人做决策。
- **PIM.3 过程改进**：改进项只从客观输入派生（MAN.6 FAIL 度量项、MAN.5
  开放高风险），无输入时如实记录「无改进输入」，绝不臆造改进项。
- **SPL.2 产品发布**：发布清单来自 ``session.artifacts`` 的真实文件与
  SHA256；批准状态默认「待批准」，只能由人修改。

反假绿原则：自动条目一律标「待评估 / 待指定」，门禁只校验结构、一致性
与摘要，不推断"已批准 / 已复用 / 已改进"。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.validation import _write_step_marker

log = logging.getLogger("pipeline.step_handlers.mgmt_support")

ACQ_REGISTER = "docs/supplier-register.yaml"
ACQ_REPORT = "docs/supplier-monitoring-report.md"

REUSE_REGISTER = "docs/reuse-register.yaml"
REUSE_REPORT = "docs/reuse-report.md"

PIM_PLAN = "docs/process-improvement-plan.md"
PIM_REGISTER = "docs/process-improvement-register.yaml"
PIM_REPORT = "docs/process-improvement-report.md"

RELEASE_PLAN = "docs/release-plan.md"
RELEASE_MANIFEST = "docs/release-manifest.yaml"

ACQ_STATUSES = (
    "approved", "conditionally-approved", "under-review", "rejected", "待评估",
)
REUSE_STATUSES = ("candidate", "approved", "in-use", "rejected", "待评估")
REUSE_KINDS = ("internal", "external")
PIM_STATUSES = ("open", "in-progress", "verified", "closed")
APPROVAL_STATUSES = ("待批准", "approved", "rejected")

_ACQ_REPORT_SECTIONS = ("## 供应商清单", "## 监控结果", "## 纠正措施", "## 可追溯性")
_REUSE_REPORT_SECTIONS = ("## 复用清单", "## 评估结果", "## 复用决策", "## 可追溯性")
_PIM_PLAN_SECTIONS = ("## 改进范围", "## 改进流程", "## 角色与升级")
_PIM_REPORT_SECTIONS = ("## 改进输入", "## 改进项", "## 可追溯性")
_RELEASE_PLAN_SECTIONS = ("## 发布范围", "## 发布准则", "## 发布清单", "## 批准与归档")

_DEP_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(.*)$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cell(text: object) -> str:
    return " ".join(str(text).replace("|", "\\|").split())


def _slug(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", str(text).upper()).strip("-")


def _write_doc(session: PipelineSession, rel_path: str, content: str) -> Path:
    target = Path(session.project_dir) / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _load_yaml(project_dir: str, rel_path: str) -> dict:
    path = Path(project_dir) / rel_path
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        log.warning("[mgmt-support] %s 无法解析，按空处理: %s", rel_path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _save_yaml(project_dir: str, rel_path: str, payload: dict) -> Path:
    path = Path(project_dir) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _require_sections(project_dir: str, rel_path: str,
                      sections: tuple[str, ...], problems: list[str]) -> str:
    target = Path(project_dir) / rel_path
    if not target.is_file():
        problems.append(f"缺少产物 {rel_path}")
        return ""
    text = target.read_text(encoding="utf-8", errors="replace")
    for sec in sections:
        if sec not in text:
            problems.append(f"{rel_path} 缺少章节 {sec}")
    return text


# ══════════════════════════════════════════════════════════════════════
# ACQ.4 供应商监控
# ══════════════════════════════════════════════════════════════════════


def _dep_entry(spec: str, source: str, scope: str) -> dict | None:
    m = _DEP_RE.match(str(spec))
    if not m:
        return None
    name = m.group(1)
    requirement = ((m.group(2) or "") + (m.group(3) or "")).strip() or "*"
    return {
        "id": "ACQ-" + _slug(name),
        "name": name,
        "requirement": requirement,
        "source": source,
        "scope": scope,
        "origin": "auto",
    }


def _read_requirements(project_dir: str) -> list[dict]:
    root = Path(project_dir)
    out: list[dict] = []
    for path in sorted(root.glob("requirements*.txt")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith(("-", "git+", "http://", "https://")):
                continue
            entry = _dep_entry(line, str(path.relative_to(root)), "runtime")
            if entry:
                out.append(entry)
    return out


def _read_pyproject(project_dir: str) -> list[dict]:
    path = Path(project_dir) / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        import tomllib

        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (ImportError, OSError, ValueError) as exc:
        log.warning("[ACQ.4] 无法读取 pyproject.toml: %s", exc)
        return []

    project = data.get("project") or {}
    out: list[dict] = []
    rel = "pyproject.toml"
    for spec in project.get("dependencies") or []:
        entry = _dep_entry(str(spec), rel, "runtime")
        if entry:
            out.append(entry)
    for group, specs in (project.get("optional-dependencies") or {}).items():
        for spec in specs or []:
            entry = _dep_entry(str(spec), rel, f"optional:{group}")
            if entry:
                out.append(entry)
    return out


def _scan_suppliers(project_dir: str) -> list[dict]:
    """自动盘点第三方依赖；同名供应商合并来源与版本约束。"""
    merged: dict[str, dict] = {}
    for dep in _read_pyproject(project_dir) + _read_requirements(project_dir):
        key = dep["name"].lower()
        prev = merged.get(key)
        if prev is None:
            dep["sources"] = [dep["source"]]
            merged[key] = dep
            continue
        if dep["source"] not in prev["sources"]:
            prev["sources"].append(dep["source"])
        if dep["requirement"] != "*" and prev["requirement"] == "*":
            prev["requirement"] = dep["requirement"]
    return sorted(merged.values(), key=lambda d: d["name"].lower())


def _merge_suppliers(existing: dict, scanned: list[dict]) -> list[dict]:
    prev = {
        str(s.get("id")): s
        for s in existing.get("suppliers") or []
        if isinstance(s, dict) and s.get("id")
    }
    merged: list[dict] = []
    seen: set[str] = set()
    for gen in scanned:
        entry = {**prev.get(gen["id"], {}), **gen}
        entry.setdefault("owner", "待指定")
        entry.setdefault("status", "待评估")
        entry.setdefault("requirements_agreed", False)
        entry.setdefault("monitoring_method", "")
        entry.setdefault("corrective_action", "")
        entry.setdefault("notes", "")
        entry["last_seen"] = _now()
        merged.append(entry)
        seen.add(gen["id"])

    for sid, item in prev.items():
        if sid in seen:
            continue
        merged.append({
            "owner": "待指定", "status": "待评估", "requirements_agreed": False,
            "monitoring_method": "", "corrective_action": "", "notes": "",
            "sources": [], "origin": "manual", **item,
        })

    merged.sort(key=lambda s: str(s.get("id")))
    return merged


def _build_acq_report(suppliers: list[dict], sources: list[str]) -> str:
    rows = []
    for s in suppliers:
        rows.append(
            f"| {_cell(s.get('id'))} | {_cell(s.get('name'))} "
            f"| {_cell(s.get('requirement'))} "
            f"| {_cell('、'.join(s.get('sources') or [s.get('source') or '—']))} "
            f"| {_cell(s.get('scope'))} | {_cell(s.get('status'))} "
            f"| {'是' if s.get('requirements_agreed') else '否'} "
            f"| {_cell(s.get('owner'))} |"
        )
    pending = [s for s in suppliers if s.get("status") == "待评估"]
    rejected = [s for s in suppliers if s.get("status") == "rejected"]
    if rejected:
        actions = "\n".join(
            f"- **{s['id']}**（{s.get('name')}）："
            f"{s.get('corrective_action') or '未填写纠正措施'}"
            for s in rejected
        )
    else:
        actions = "- 当前无被拒绝的供应商，无需纠正措施。"

    return (
        "# 供应商监控报告（ACQ.4）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 扫描来源：{'、'.join(sources)}\n"
        f"- 供应商总数：{len(suppliers)}（待评估 {len(pending)} / 已拒绝 {len(rejected)}）\n\n"
        "## 供应商清单\n\n"
        "| ID | 供应商 | 版本要求 | 来源 | 范围 | 状态 | 需求已确认 | 责任人 |\n"
        "|:---|:---|:---|:---|:---|:---|:---|:---|\n"
        + ("\n".join(rows) if rows else "| — | 未发现第三方依赖 | — | — | — | — | — | — |")
        + "\n\n"
        "## 监控结果\n\n"
        + (
            "\n".join(
                f"- {s['id']}（{s.get('name')}）：{s.get('status')}，"
                f"监控方式 {s.get('monitoring_method') or '未定义'}"
                for s in suppliers
            )
            if suppliers else "- 未识别到需要监控的供应商。"
        )
        + "\n\n"
        "## 纠正措施\n\n"
        f"{actions}\n\n"
        "## 可追溯性\n\n"
        "- 供应商清单：`docs/supplier-register.yaml`。\n"
        "- 自动条目来自 `pyproject.toml` / `requirements*.txt`；"
        "评估结论与纠正措施由人维护。\n"
    )


def step_acq4_monitoring(session: PipelineSession) -> str:
    """ACQ.4 — 扫描第三方依赖、合并人工评估并输出监控报告。"""
    scanned = _scan_suppliers(session.project_dir)
    existing = _load_yaml(session.project_dir, ACQ_REGISTER)
    suppliers = _merge_suppliers(existing, scanned)
    sources = ["pyproject.toml", "requirements*.txt"]

    _save_yaml(session.project_dir, ACQ_REGISTER, {
        "version": 1,
        "generated_at": _now(),
        "scan_sources": sources,
        "suppliers": suppliers,
    })
    report_path = _write_doc(
        session, ACQ_REPORT, _build_acq_report(suppliers, sources))
    pending = sum(1 for s in suppliers if s.get("status") == "待评估")

    _write_step_marker(
        session, "acq4-monitoring",
        status="completed",
        register=ACQ_REGISTER,
        report=ACQ_REPORT,
        supplier_count=len(suppliers),
        pending_count=pending,
    )
    log.info("[ACQ.4] 供应商登记完成: %d 家（待评估 %d）", len(suppliers), pending)
    return str(report_path)


def _validate_suppliers(suppliers: list[dict]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for idx, s in enumerate(suppliers):
        sid = str(s.get("id") or "").strip()
        if not sid:
            problems.append(f"第 {idx + 1} 条供应商缺少 id")
            continue
        if sid in seen:
            problems.append(f"供应商 id 重复: {sid}")
        seen.add(sid)
        if not str(s.get("name") or "").strip():
            problems.append(f"{sid} 缺少供应商名称")
        if not (s.get("sources") or s.get("source")):
            problems.append(f"{sid} 缺少来源，无法证明其为受监控供应商")
        if s.get("status") not in ACQ_STATUSES:
            problems.append(f"{sid} 状态非法: {s.get('status')}")
        if s.get("status") == "rejected" and not str(
                s.get("corrective_action") or "").strip():
            problems.append(f"{sid} 已被拒绝但未填写纠正措施")
    return problems


def step_review_acq4(session: PipelineSession) -> str:
    """ACQ.4 门禁：校验登记完整性与报告一致性，不推断供应商已批准。"""
    problems: list[str] = []
    report = _require_sections(
        session.project_dir, ACQ_REPORT, _ACQ_REPORT_SECTIONS, problems)

    register = _load_yaml(session.project_dir, ACQ_REGISTER)
    if not register:
        problems.append(f"缺少供应商登记 {ACQ_REGISTER}")
    else:
        if not register.get("scan_sources"):
            problems.append("供应商登记缺少扫描来源，无法证明已开展盘点")
        suppliers = register.get("suppliers")
        if not isinstance(suppliers, list):
            problems.append("供应商登记 suppliers 字段格式错误")
            suppliers = []
        problems.extend(_validate_suppliers(suppliers))
        for s in suppliers:
            sid = str(s.get("id") or "")
            if sid and report and sid not in report:
                problems.append(f"监控报告缺少供应商 {sid}")

    if problems:
        raise PipelineStepError("ACQ.4 供应商监控门禁 RED：" + "；".join(problems))
    _write_step_marker(
        session, "acq4-review",
        status="completed",
        verified=[ACQ_REGISTER, ACQ_REPORT],
    )
    return str(Path(session.project_dir) / ACQ_REPORT)


# ══════════════════════════════════════════════════════════════════════
# REU.2 复用管理
# ══════════════════════════════════════════════════════════════════════


def _scan_components(project_dir: str) -> list[dict]:
    root = Path(project_dir) / "src"
    if not root.is_dir():
        return []
    out: list[dict] = []
    for pkg in sorted(root.iterdir()):
        if not pkg.is_dir() or not (pkg / "__init__.py").is_file():
            continue
        modules = [p for p in pkg.rglob("*.py") if p.is_file()]
        out.append({
            "id": "REU-" + _slug(pkg.name),
            "name": pkg.name,
            "path": str(pkg.relative_to(project_dir)),
            "kind": "internal",
            "module_count": len(modules),
            "origin": "auto",
        })
    return out


def _merge_reuse(existing: dict, scanned: list[dict]) -> list[dict]:
    prev = {
        str(r.get("id")): r
        for r in existing.get("components") or []
        if isinstance(r, dict) and r.get("id")
    }
    merged: list[dict] = []
    seen: set[str] = set()
    for gen in scanned:
        entry = {**prev.get(gen["id"], {}), **gen}
        entry.setdefault("reuse_status", "待评估")
        entry.setdefault("owner", "待指定")
        entry.setdefault("rationale", "")
        entry.setdefault("license", "")
        entry.setdefault("notes", "")
        entry["last_seen"] = _now()
        merged.append(entry)
        seen.add(gen["id"])

    for rid, item in prev.items():
        if rid in seen:
            continue
        merged.append({
            "reuse_status": "待评估", "owner": "待指定", "rationale": "",
            "license": "", "notes": "", "origin": "manual", **item,
        })

    merged.sort(key=lambda r: str(r.get("id")))
    return merged


def _build_reuse_report(components: list[dict], sources: list[str]) -> str:
    rows = [
        f"| {_cell(c.get('id'))} | {_cell(c.get('name'))} | {_cell(c.get('kind'))} "
        f"| {_cell(c.get('path'))} | {_cell(c.get('module_count'))} "
        f"| {_cell(c.get('reuse_status'))} | {_cell(c.get('owner'))} |"
        for c in components
    ]
    pending = [c for c in components if c.get("reuse_status") == "待评估"]
    rejected = [c for c in components if c.get("reuse_status") == "rejected"]
    decisions = (
        "\n".join(
            f"- **{c['id']}**（{c.get('name')}）：{c.get('reuse_status')} — "
            f"{c.get('rationale') or '未填写理由'}"
            for c in components
        )
        if components else "- 未识别到可复用组件。"
    )
    return (
        "# 复用报告（REU.2）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 扫描来源：{'、'.join(sources)}\n"
        f"- 组件总数：{len(components)}（待评估 {len(pending)} / 已拒绝 {len(rejected)}）\n\n"
        "## 复用清单\n\n"
        "| ID | 组件 | 类型 | 路径 | 模块数 | 复用状态 | 责任人 |\n"
        "|:---|:---|:---|:---|:---|:---|:---|\n"
        + ("\n".join(rows) if rows else "| — | 未识别到组件 | — | — | — | — | — |")
        + "\n\n"
        "## 评估结果\n\n"
        "- 自动识别的组件在人工评估前标记为「待评估」，不得视为已复用。\n"
        "- 复用决策需记录理由；拒绝复用同样需要理由。\n\n"
        "## 复用决策\n\n"
        f"{decisions}\n\n"
        "## 可追溯性\n\n"
        "- 复用登记：`docs/reuse-register.yaml`。\n"
        "- 自动条目来自 `src/` 下含 `__init__.py` 的包。\n"
    )


def step_reu2_reuse(session: PipelineSession) -> str:
    """REU.2 — 识别内部组件、合并人工复用决策并输出复用报告。"""
    scanned = _scan_components(session.project_dir)
    existing = _load_yaml(session.project_dir, REUSE_REGISTER)
    components = _merge_reuse(existing, scanned)
    sources = ["src/**/__init__.py"]

    _save_yaml(session.project_dir, REUSE_REGISTER, {
        "version": 1,
        "generated_at": _now(),
        "scan_sources": sources,
        "components": components,
    })
    report_path = _write_doc(
        session, REUSE_REPORT, _build_reuse_report(components, sources))
    pending = sum(1 for c in components if c.get("reuse_status") == "待评估")

    _write_step_marker(
        session, "reu2-reuse",
        status="completed",
        register=REUSE_REGISTER,
        report=REUSE_REPORT,
        component_count=len(components),
        pending_count=pending,
    )
    log.info("[REU.2] 复用登记完成: %d 个组件（待评估 %d）", len(components), pending)
    return str(report_path)


def _validate_reuse(components: list[dict]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for idx, c in enumerate(components):
        rid = str(c.get("id") or "").strip()
        if not rid:
            problems.append(f"第 {idx + 1} 个组件缺少 id")
            continue
        if rid in seen:
            problems.append(f"组件 id 重复: {rid}")
        seen.add(rid)
        if c.get("reuse_status") not in REUSE_STATUSES:
            problems.append(f"{rid} 复用状态非法: {c.get('reuse_status')}")
        if c.get("kind") not in REUSE_KINDS:
            problems.append(f"{rid} 组件类型非法: {c.get('kind')}")
        if c.get("reuse_status") == "rejected" and not str(
                c.get("rationale") or "").strip():
            problems.append(f"{rid} 被拒绝复用但未说明理由")
    return problems


def step_review_reu2(session: PipelineSession) -> str:
    """REU.2 门禁：校验复用登记与报告一致性，不推断复用已批准。"""
    problems: list[str] = []
    report = _require_sections(
        session.project_dir, REUSE_REPORT, _REUSE_REPORT_SECTIONS, problems)

    register = _load_yaml(session.project_dir, REUSE_REGISTER)
    if not register:
        problems.append(f"缺少复用登记 {REUSE_REGISTER}")
    else:
        if not register.get("scan_sources"):
            problems.append("复用登记缺少扫描来源，无法证明已开展识别")
        components = register.get("components")
        if not isinstance(components, list):
            problems.append("复用登记 components 字段格式错误")
            components = []
        problems.extend(_validate_reuse(components))
        for c in components:
            rid = str(c.get("id") or "")
            if rid and report and rid not in report:
                problems.append(f"复用报告缺少组件 {rid}")

    if problems:
        raise PipelineStepError("REU.2 复用门禁 RED：" + "；".join(problems))
    _write_step_marker(
        session, "reu2-review",
        status="completed",
        verified=[REUSE_REGISTER, REUSE_REPORT],
    )
    return str(Path(session.project_dir) / REUSE_REPORT)


# ══════════════════════════════════════════════════════════════════════
# PIM.3 过程改进
# ══════════════════════════════════════════════════════════════════════


def _kpi_improvements(project_dir: str) -> list[dict]:
    """MAN.6 FAIL 度量项 → 改进项（无原始数据不生成）。"""
    from yuleosh.ci.kpi.report import kpi_status
    from yuleosh.pipeline.step_handlers.measurement import _has_data

    try:
        data = json.loads(kpi_status(project_dir, as_json=True))
    except (TypeError, ValueError, OSError) as exc:
        log.warning("[PIM.3] KPI 面板不可用，跳过该改进来源: %s", exc)
        return []

    out: list[dict] = []
    for entry in data.get("entries") or []:
        if str(entry.get("status", "")).upper() != "FAIL":
            continue
        metric = str(entry.get("metric") or "")
        if not metric:
            continue
        if not _has_data(project_dir, metric):
            log.info("[PIM.3] 度量 %s 无原始数据，跳过改进项生成", metric)
            continue
        label = entry.get("label") or metric
        out.append({
            "id": "PIM-KPI-" + _slug(metric),
            "source": "MAN.6/KPI",
            "origin": "auto",
            "title": f"度量项未达标: {label}",
            "objective": f"使 {label} 回到阈值 {entry.get('threshold')} 以内",
        })
    return out


def _risk_improvements(project_dir: str) -> list[dict]:
    """MAN.5 开放高风险 → 改进项。"""
    register = _load_yaml(project_dir, "docs/risk-register.yaml")
    out: list[dict] = []
    for risk in register.get("risks") or []:
        if not isinstance(risk, dict):
            continue
        try:
            score = int(risk.get("score"))
        except (TypeError, ValueError):
            continue
        if score < 8 or risk.get("status") not in ("open", "monitoring"):
            continue
        rid = str(risk.get("id") or "").strip()
        if not rid:
            continue
        out.append({
            "id": "PIM-" + rid,
            "source": "MAN.5/Risk",
            "origin": "auto",
            "title": f"高风险待处置: {risk.get('title') or rid}",
            "objective": f"将 {rid} 降至可接受水平并关闭",
        })
    return out


def _merge_improvements(existing: dict, generated: list[dict]) -> list[dict]:
    prev = {
        str(i.get("id")): i
        for i in existing.get("improvements") or []
        if isinstance(i, dict) and i.get("id")
    }
    merged: list[dict] = []
    seen: set[str] = set()
    for gen in generated:
        entry = {**prev.get(gen["id"], {}), **gen}
        entry.setdefault("owner", "待指定")
        entry.setdefault("due", "")
        entry.setdefault("status", "open")
        entry.setdefault("result", "")
        entry["last_seen"] = _now()
        merged.append(entry)
        seen.add(gen["id"])

    for iid, item in prev.items():
        if iid in seen:
            continue
        merged.append({
            "origin": "manual", "owner": "待指定", "due": "", "status": "open",
            "result": "", **item,
        })

    merged.sort(key=lambda i: str(i.get("id")))
    return merged


def _build_pim_plan() -> str:
    return (
        "# 过程改进计划（PIM.3）\n\n"
        "> 自动生成：改进流程与输入口径由 `step_handlers/mgmt_support.py` 维护，"
        "人工修订请直接编辑本文件。\n\n"
        "## 改进范围\n\n"
        "- 覆盖流水线执行的管理与工程过程，重点是度量未达标项与开放高风险。\n"
        "- 改进输入只允许来自客观记录：MAN.6 测量报告、MAN.5 风险报告。\n"
        "- 无输入时记录「无改进输入」，不得为了改进而臆造问题。\n\n"
        "## 改进流程\n\n"
        "1. **识别**：从 MAN.6 FAIL 度量项与 MAN.5 开放高风险派生改进项。\n"
        "2. **评估**：由过程责任人对改进项排序并确认目标。\n"
        "3. **计划**：为每项指定责任人、期限（`docs/process-improvement-register.yaml`）。\n"
        "4. **实施与监控**：状态 open → in-progress → verified → closed，仅由人修改。\n\n"
        "## 角色与升级\n\n"
        "- 过程责任人：制定并推进改进项。\n"
        "- 项目负责人（MAN.3）：批准跨过程改进并分配资源。\n"
        "- 质量负责人（SUP.1）：验证改进有效性，未达标项升级处理。\n"
    )


def _build_pim_report(improvements: list[dict], inputs: dict) -> str:
    rows = [
        f"| {_cell(i.get('id'))} | {_cell(i.get('source'))} "
        f"| {_cell(i.get('title'))} | {_cell(i.get('objective'))} "
        f"| {_cell(i.get('owner'))} | {_cell(i.get('due') or '—')} "
        f"| {_cell(i.get('status'))} |"
        for i in improvements
    ]
    pending = [i for i in improvements if i.get("origin") == "auto"
               and str(i.get("owner") or "待指定") == "待指定"]
    return (
        "# 过程改进报告（PIM.3）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 改进输入：MAN.6 FAIL {inputs.get('kpi_fail', 0)} 项、"
        f"MAN.5 开放高风险 {inputs.get('high_risks', 0)} 项\n"
        f"- 改进项总数：{len(improvements)}（待指定责任人 {len(pending)}）\n\n"
        "## 改进输入\n\n"
        f"- MAN.6 测量报告：{'已读取' if inputs.get('measurement_report') else '不存在'}。\n"
        f"- MAN.5 风险登记：{'已读取' if inputs.get('risk_register') else '不存在'}。\n"
        + (
            "- 无改进输入：未发现 FAIL 度量项或开放高风险，本报告不生成改进项。\n"
            if not improvements else
            "- 自动改进项在人工指定责任人前标记为「待指定」，"
            "列入下表但不视为已启动改进。\n"
        )
        + "\n## 改进项\n\n"
        "| 改进ID | 来源 | 问题 | 目标 | 责任人 | 期限 | 状态 |\n"
        "|:---|:---|:---|:---|:---|:---|:---|\n"
        + ("\n".join(rows) if rows else "| — | — | 无改进项 | — | — | — | — |")
        + "\n\n## 可追溯性\n\n"
        "- 改进计划：`docs/process-improvement-plan.md`。\n"
        "- 改进登记：`docs/process-improvement-register.yaml`。\n"
        "- 输入真源：`docs/measurement-report.md`、`docs/risk-register.yaml`。\n"
    )


def step_pim3_improvement(session: PipelineSession) -> str:
    """PIM.3 — 从客观输入派生改进项，生成计划/登记/报告。"""
    generated = (
        _kpi_improvements(session.project_dir)
        + _risk_improvements(session.project_dir)
    )
    existing = _load_yaml(session.project_dir, PIM_REGISTER)
    improvements = _merge_improvements(existing, generated)
    sources = ["docs/measurement-report.md", "docs/risk-register.yaml"]
    # 输入计数以派生结果为准（派生本身已过滤无数据项）
    kpi_count = sum(1 for i in generated if i["source"] == "MAN.6/KPI")
    risk_count = sum(1 for i in generated if i["source"] == "MAN.5/Risk")
    inputs = {
        "kpi_fail": kpi_count,
        "high_risks": risk_count,
        "measurement_report": (Path(session.project_dir)
                               / "docs/measurement-report.md").is_file(),
        "risk_register": (Path(session.project_dir)
                          / "docs/risk-register.yaml").is_file(),
    }

    _write_doc(session, PIM_PLAN, _build_pim_plan())
    _save_yaml(session.project_dir, PIM_REGISTER, {
        "version": 1,
        "generated_at": _now(),
        "scan_sources": sources,
        "improvements": improvements,
    })
    report_path = _write_doc(
        session, PIM_REPORT, _build_pim_report(improvements, inputs))
    pending = sum(1 for i in improvements if i.get("origin") == "auto"
                  and str(i.get("owner") or "待指定") == "待指定")

    _write_step_marker(
        session, "pim3-improvement",
        status="completed",
        plan=PIM_PLAN,
        register=PIM_REGISTER,
        report=PIM_REPORT,
        improvement_count=len(improvements),
        pending_count=pending,
    )
    log.info("[PIM.3] 过程改进已生成: %d 项（待指定责任人 %d）",
             len(improvements), pending)
    return str(report_path)


def _validate_improvements(items: list[dict]) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    pending: list[str] = []
    seen: set[str] = set()
    for idx, item in enumerate(items):
        iid = str(item.get("id") or "").strip()
        if not iid:
            problems.append(f"第 {idx + 1} 条改进项缺少 id")
            continue
        if iid in seen:
            problems.append(f"改进项 id 重复: {iid}")
        seen.add(iid)
        if not str(item.get("source") or "").strip():
            problems.append(f"{iid} 缺少改进来源")
        if not str(item.get("objective") or "").strip():
            problems.append(f"{iid} 缺少改进目标")
        if item.get("status") not in PIM_STATUSES:
            problems.append(f"{iid} 状态非法: {item.get('status')}")

        if item.get("status") not in ("open", "in-progress"):
            continue
        owner = str(item.get("owner") or "").strip()
        if str(item.get("origin") or "manual") == "auto" and owner in ("", "待指定"):
            pending.append(iid)
            continue
        if not owner or owner == "待指定":
            problems.append(f"{iid} 为进行中的改进项，必须指定责任人")
        try:
            date.fromisoformat(str(item.get("due")))
        except (TypeError, ValueError):
            problems.append(f"{iid} 为进行中的改进项，due 必须为 YYYY-MM-DD")
    return problems, pending


def step_review_pim3(session: PipelineSession) -> str:
    """PIM.3 门禁：校验计划/登记/报告的结构与一致性。"""
    problems: list[str] = []
    _require_sections(session.project_dir, PIM_PLAN, _PIM_PLAN_SECTIONS, problems)
    report = _require_sections(
        session.project_dir, PIM_REPORT, _PIM_REPORT_SECTIONS, problems)

    register = _load_yaml(session.project_dir, PIM_REGISTER)
    pending: list[str] = []
    if not register:
        problems.append(f"缺少改进登记 {PIM_REGISTER}")
    else:
        if not register.get("scan_sources"):
            problems.append("改进登记缺少扫描来源，无法证明已评估过程")
        items = register.get("improvements")
        if not isinstance(items, list):
            problems.append("改进登记 improvements 字段格式错误")
            items = []
        item_problems, pending = _validate_improvements(items)
        problems.extend(item_problems)
        for item in items:
            iid = str(item.get("id") or "")
            if iid and report and iid not in report:
                problems.append(f"改进报告缺少改进项 {iid}")

    if problems:
        raise PipelineStepError("PIM.3 过程改进门禁 RED：" + "；".join(problems))
    _write_step_marker(
        session, "pim3-review",
        status="completed",
        verified=[PIM_PLAN, PIM_REGISTER, PIM_REPORT],
        pending_triage=pending,
    )
    return str(Path(session.project_dir) / PIM_REPORT)


# ══════════════════════════════════════════════════════════════════════
# SPL.2 产品发布
# ══════════════════════════════════════════════════════════════════════


def _release_version(project_dir: str) -> str:
    path = Path(project_dir) / "pyproject.toml"
    if not path.is_file():
        return "unversioned"
    try:
        import tomllib

        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (ImportError, OSError, ValueError):
        return "unversioned"
    version = str((data.get("project") or {}).get("version") or "").strip()
    return version or "unversioned"


def _gate_snapshot(session: PipelineSession) -> dict:
    path = Path(session.session_dir) / "gate-summary.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"available": False, "worst_gate_status": "not-run"}
    if not isinstance(data, dict):
        return {"available": False, "worst_gate_status": "not-run"}
    return {
        "available": True,
        "worst_gate_status": str(data.get("worst_gate_status") or "not-run"),
        "not_run_gates": data.get("not_run_gates") or [],
    }


def _release_artifacts(session: PipelineSession) -> list[dict]:
    root = Path(session.project_dir).resolve()
    out: list[dict] = []
    seen: set[str] = set()
    for key, raw in sorted((session.artifacts or {}).items()):
        path = Path(str(raw))
        try:
            rel = str(path.resolve().relative_to(root))
        except ValueError:
            rel = str(path)
        if rel in seen:
            continue
        seen.add(rel)
        out.append({
            "key": str(key),
            "path": rel,
            "sha256": _sha256(path) if path.is_file() else "",
        })
    return out


def _build_release_plan(version: str, manifest: dict) -> str:
    artifacts = manifest.get("artifacts") or []
    rows = [
        f"| {_cell(a.get('key'))} | {_cell(a.get('path'))} "
        f"| `{_cell(a.get('sha256') or '—')}` |"
        for a in artifacts
    ]
    gate = manifest.get("gate_status") or {}
    return (
        "# 发布计划（SPL.2）\n\n"
        "## 发布范围\n\n"
        f"- 发布版本：`{_cell(version)}`。\n"
        f"- 发布会话：`{_cell(manifest.get('session'))}`。\n"
        "- 范围：本轮流水线产出的全部受控工作产物。\n\n"
        "## 发布准则\n\n"
        "- 所有硬门禁通过（`worst_gate_status = passed`）方可批准发布。\n"
        "- 发布清单中的每个文件必须有 SHA256 摘要，摘要不符即拒绝发布。\n"
        "- 未验证门禁（not-run / stale / skipped）不得被表述为已通过。\n"
        "- 批准状态只能由人修改，流水线默认「待批准」。\n\n"
        "## 发布清单\n\n"
        f"- 门禁快照：{'可用' if gate.get('available') else '不可用'}，"
        f"worst = `{_cell(gate.get('worst_gate_status'))}`。\n"
        f"- 发布产物：{len(artifacts)} 个。\n\n"
        "| 产物键 | 路径 | SHA256 |\n|:---|:---|:---|\n"
        + ("\n".join(rows) if rows else "| — | 无产物 | — |")
        + "\n\n## 批准与归档\n\n"
        f"- 当前批准状态：{_cell(manifest.get('approval_status'))}。\n"
        "- 批准记录写入 `docs/release-manifest.yaml` 的 `approval_status` 字段。\n"
        "- 发布包与清单一并归档，供后续审计复核。\n"
    )


def step_spl2_release(session: PipelineSession) -> str:
    """SPL.2 — 从 session.artifacts 生成发布清单与发布计划。"""
    version = _release_version(session.project_dir)
    artifacts = _release_artifacts(session)
    manifest = {
        "version": 1,
        "generated_at": _now(),
        "session": session.name,
        "release_version": version,
        "approval_status": "待批准",
        "gate_status": _gate_snapshot(session),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "scan_sources": [
            "session.artifacts",
            f".osh/sessions/{session.name}/gate-summary.json",
        ],
    }
    _save_yaml(session.project_dir, RELEASE_MANIFEST, manifest)
    plan_path = _write_doc(
        session, RELEASE_PLAN, _build_release_plan(version, manifest))

    _write_step_marker(
        session, "spl2-release",
        status="completed",
        plan=RELEASE_PLAN,
        manifest=RELEASE_MANIFEST,
        release_version=version,
        artifact_count=len(artifacts),
        approval_status="待批准",
    )
    log.info("[SPL.2] 发布清单已生成: %s (%d 个产物)", version, len(artifacts))
    return str(plan_path)


def _resolve_artifact_path(project_dir: str, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = Path(project_dir) / path
    return path


def step_review_spl2(session: PipelineSession) -> str:
    """SPL.2 门禁：校验发布清单完整性、摘要一致性与批准状态合法性。"""
    problems: list[str] = []
    _require_sections(
        session.project_dir, RELEASE_PLAN, _RELEASE_PLAN_SECTIONS, problems)

    manifest = _load_yaml(session.project_dir, RELEASE_MANIFEST)
    if not manifest:
        problems.append(f"缺少发布清单 {RELEASE_MANIFEST}")
        manifest = {}

    if manifest:
        if str(manifest.get("session") or "") != session.name:
            problems.append("发布清单的 session 与本轮不一致（疑似旧轮次产物）")
        if not str(manifest.get("release_version") or "").strip():
            problems.append("发布清单缺少 release_version")
        approval = manifest.get("approval_status")
        if approval not in APPROVAL_STATUSES:
            problems.append(f"批准状态非法: {approval}")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            problems.append("发布清单为空，无法证明已生成发布包")
            artifacts = []
        for idx, art in enumerate(artifacts):
            if not isinstance(art, dict):
                problems.append(f"第 {idx + 1} 个发布产物格式错误")
                continue
            rel = str(art.get("path") or "").strip()
            digest = str(art.get("sha256") or "").strip()
            if not rel or not digest:
                problems.append(f"第 {idx + 1} 个发布产物缺少路径或摘要")
                continue
            target = _resolve_artifact_path(session.project_dir, rel)
            if not target.is_file():
                problems.append(f"发布产物不存在: {rel}")
                continue
            if _sha256(target) != digest:
                problems.append(f"发布产物摘要不一致: {rel}")

        gate = _gate_snapshot(session)
        if not gate.get("available"):
            # 生成时 gate-summary 尚未落盘（SPL.2 位于流水线尾部），
            # 复核时优先采用当前快照；仍不可用才回退到清单内记录。
            gate = manifest.get("gate_status") or {}
        worst = str(gate.get("worst_gate_status") or "not-run")
        if approval == "approved" and worst in ("failed", "stale", "not-run"):
            problems.append(
                f"门禁状态为 {worst} 时不得批准发布（不得假绿）")

    if problems:
        raise PipelineStepError("SPL.2 发布门禁 RED：" + "；".join(problems))
    _write_step_marker(
        session, "spl2-review",
        status="completed",
        verified=[RELEASE_PLAN, RELEASE_MANIFEST],
        approval_status=manifest.get("approval_status"),
    )
    return str(Path(session.project_dir) / RELEASE_PLAN)
