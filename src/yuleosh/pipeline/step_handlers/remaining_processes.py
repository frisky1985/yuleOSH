"""剩余 13 个 ASPICE 过程域 — 确定性生成 + 确定性评审。

覆盖 ACQ.1~3 / SPL.1 / SUP.2~7 / PIM.1~2 / REU.1。所有域共用同一套
「扫描 → 合并人工字段 → 写登记/文档 → 结构门禁」引擎，差异只来自
``compliance/remaining_specs.py`` 的配置。

反假绿原则（与 SUP/MAN 一致）：
- 扫描不到记录时，文档如实写「无条目」，不臆造条目。
- 自动记录默认「待分析」，终态（approved/passed/closed/...）必须带
  spec 指定的证据字段，否则门禁 RED。
- 人工维护的字段跨轮次保留，不被自动扫描覆盖。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from yuleosh.compliance.remaining_specs import SPECS
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.mgmt_support import (
    _cell,
    _load_yaml,
    _now,
    _save_yaml,
    _write_doc,
)
from yuleosh.pipeline.step_handlers.validation import _write_step_marker

log = logging.getLogger("pipeline.step_handlers.remaining_processes")


def _slug(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", str(text).upper()).strip("-")


def _scan_records(project_dir: str, spec: dict) -> tuple[list[dict], list[str]]:
    """按显式扫描模式收集记录；不存在的来源只记录模式，不推断条目。"""
    root = Path(project_dir)
    records: list[dict] = []
    sources: list[str] = []

    if spec.get("scanner") == "docs":
        sources = [f"glob:{spec['patterns'][0]}"]
        for path in sorted((root / "docs").glob("*.md")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root))
            records.append({
                "id": f"{spec['id_prefix']}-{_slug(rel)}",
                "title": rel,
                "source": rel,
                "status": "indexed",
                "origin": "auto",
            })
        return records, sources

    for pattern in spec["patterns"]:
        sources.append(f"glob:{pattern}")
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                log.warning("[%s] %s 无法解析，跳过: %s",
                            spec.get("title"), path, exc)
                continue
            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                rid = str(entry.get("id") or "").strip()
                if not rid:
                    continue
                record = {
                    "id": rid,
                    "title": str(
                        entry.get("title") or entry.get("name") or rid),
                    "source": str(path.relative_to(root)),
                    "origin": "auto",
                }
                for field in ("status", spec["required"]):
                    if str(entry.get(field) or "").strip():
                        record[field] = entry[field]
                records.append(record)
    return records, sources


def _merge_records(existing: dict, scanned: list[dict], spec: dict) -> list[dict]:
    """按 id 合并：自动字段覆盖同名键，人工字段与人工条目保留。"""
    prev = {
        str(item.get("id")): item
        for item in existing.get("items") or []
        if isinstance(item, dict) and item.get("id")
    }
    merged: list[dict] = []
    seen: set[str] = set()
    for gen in scanned:
        rid = gen["id"]
        if rid in seen:
            continue
        seen.add(rid)
        entry = {**prev.pop(rid, {}), **gen}
        entry.setdefault("status", "待分析")
        entry.setdefault(spec["required"], "")
        entry.setdefault("owner", "待指定")
        merged.append(entry)

    for rid, item in prev.items():
        entry = {
            "status": "待分析",
            spec["required"]: "",
            "owner": "待指定",
            "origin": "manual",
        }
        entry.update(item)
        merged.append(entry)

    merged.sort(key=lambda item: str(item.get("id")))
    return merged


def _build_doc(spec: dict, records: list[dict], sources: list[str]) -> str:
    rows = [
        f"| {_cell(r.get('id'))} | {_cell(r.get('title'))} "
        f"| {_cell(r.get('status'))} "
        f"| {_cell(r.get(spec['required']) or '—')} "
        f"| {_cell(r.get('source'))} |"
        for r in records
    ]
    table = "\n".join(rows) if rows else (
        f"| — | {spec['no_data']} | — | — | — |")
    terminal = "、".join(spec["terminal"])
    return (
        f"# {spec['title']}（{spec['doc']}）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 自动识别条目：{len(records)}\n"
        f"- 扫描来源：{'、'.join(sources)}\n\n"
        f"{spec['sections'][0]}\n\n"
        f"{spec['policy'][0]}\n\n"
        f"- 过程责任人：待指定（人工维护）\n"
        f"- 终态要求：{terminal} 必须提供「{spec['required_label']}」。\n\n"
        f"{spec['sections'][1]}\n\n"
        f"{spec['policy'][1]}\n\n"
        "1. 识别：按扫描模式收集记录，不臆造条目。\n"
        f"2. 评估：人工填写状态与「{spec['required_label']}」。\n"
        f"3. 复核：终态缺少「{spec['required_label']}」即门禁 RED。\n\n"
        f"{spec['sections'][2]}\n\n"
        f"| ID | 条目 | 状态 | {spec['required_label']} | 来源 |\n"
        "|:---|:---|:---|:---|:---|\n"
        f"{table}\n\n"
        f"{spec['sections'][3]}\n\n"
        + "\n".join(f"- `{src}`" for src in sources)
        + "\n"
    )


def _generate(session: PipelineSession, spec: dict, step_key: str) -> str:
    scanned, sources = _scan_records(session.project_dir, spec)
    existing = _load_yaml(session.project_dir, spec["register"])
    records = _merge_records(existing, scanned, spec)

    _save_yaml(session.project_dir, spec["register"], {
        "version": 1,
        "generated_at": _now(),
        "scan_sources": sources,
        "items": records,
    })
    doc_path = _write_doc(
        session, spec["doc"], _build_doc(spec, records, sources))
    pending = sum(1 for r in records if r.get("status") == "待分析")

    _write_step_marker(
        session, step_key,
        status="completed",
        doc=spec["doc"],
        register=spec["register"],
        record_count=len(records),
        pending_count=pending,
    )
    log.info("[%s] %s 生成完成: %d 条（待分析 %d）",
             step_key, spec["title"], len(records), pending)
    return str(doc_path)


def _review(session: PipelineSession, spec: dict, step_key: str) -> str:
    problems: list[str] = []
    doc = Path(session.project_dir) / spec["doc"]
    text = ""
    if not doc.is_file():
        problems.append(f"缺少产物 {spec['doc']}")
    else:
        text = doc.read_text(encoding="utf-8", errors="replace")
        if len(text.strip()) < 100:
            problems.append(f"{spec['doc']} 内容不足，无法作为计划证据")
        for section in spec["sections"]:
            if section not in text:
                problems.append(f"{spec['doc']} 缺少章节 {section}")

    register = _load_yaml(session.project_dir, spec["register"])
    items: list[dict] = []
    if not register:
        problems.append(f"缺少登记 {spec['register']}")
    else:
        if not register.get("scan_sources"):
            problems.append("登记缺少扫描来源，无法证明已开展识别")
        raw = register.get("items")
        if not isinstance(raw, list):
            problems.append("登记 items 字段格式错误")
        else:
            items = [i for i in raw if isinstance(i, dict)]

        seen: set[str] = set()
        for idx, item in enumerate(items):
            rid = str(item.get("id") or "").strip()
            if not rid:
                problems.append(f"第 {idx + 1} 条记录缺少 id")
                continue
            if rid in seen:
                problems.append(f"记录 id 重复: {rid}")
            seen.add(rid)
            if not str(item.get("title") or "").strip():
                problems.append(f"{rid} 缺少条目名称")
            if item.get("status") not in spec["statuses"]:
                problems.append(f"{rid} 状态非法: {item.get('status')}")
            if (item.get("status") in spec["terminal"]
                    and not str(item.get(spec["required"]) or "").strip()):
                problems.append(
                    f"{rid} 为终态 {item.get('status')}，缺少"
                    f"「{spec['required_label']}」")
            if text and rid not in text:
                problems.append(f"{spec['doc']} 缺少记录 {rid}")

        if not items and spec["no_data"] not in text:
            problems.append(
                f"无记录时 {spec['doc']} 必须显式写「{spec['no_data']}」")

    if problems:
        raise PipelineStepError(
            f"{spec['title']} 门禁 RED：" + "；".join(problems))
    _write_step_marker(
        session, step_key,
        status="completed",
        verified=[spec["doc"], spec["register"]],
        record_count=len(items),
    )
    return str(Path(session.project_dir) / spec["doc"])


# ══════════════════════════════════════════════════════════════════════
# 生成 / 评审步骤（26 个）
# ══════════════════════════════════════════════════════════════════════


def step_acq1_preparation(session: PipelineSession) -> str:
    return _generate(session, SPECS["ACQ.1"], "acq1-preparation")


def step_review_acq1(session: PipelineSession) -> str:
    return _review(session, SPECS["ACQ.1"], "acq1-review")


def step_acq2_selection(session: PipelineSession) -> str:
    return _generate(session, SPECS["ACQ.2"], "acq2-selection")


def step_review_acq2(session: PipelineSession) -> str:
    return _review(session, SPECS["ACQ.2"], "acq2-review")


def step_acq3_contract(session: PipelineSession) -> str:
    return _generate(session, SPECS["ACQ.3"], "acq3-contract")


def step_review_acq3(session: PipelineSession) -> str:
    return _review(session, SPECS["ACQ.3"], "acq3-review")


def step_spl1_tendering(session: PipelineSession) -> str:
    return _generate(session, SPECS["SPL.1"], "spl1-tendering")


def step_review_spl1(session: PipelineSession) -> str:
    return _review(session, SPECS["SPL.1"], "spl1-review")


def step_sup2_verification(session: PipelineSession) -> str:
    return _generate(session, SPECS["SUP.2"], "sup2-verification")


def step_review_sup2(session: PipelineSession) -> str:
    return _review(session, SPECS["SUP.2"], "sup2-review")


def step_sup3_validation(session: PipelineSession) -> str:
    return _generate(session, SPECS["SUP.3"], "sup3-validation")


def step_review_sup3(session: PipelineSession) -> str:
    return _review(session, SPECS["SUP.3"], "sup3-review")


def step_sup4_joint_review(session: PipelineSession) -> str:
    return _generate(session, SPECS["SUP.4"], "sup4-joint-review")


def step_review_sup4(session: PipelineSession) -> str:
    return _review(session, SPECS["SUP.4"], "sup4-review")


def step_sup5_audit(session: PipelineSession) -> str:
    return _generate(session, SPECS["SUP.5"], "sup5-audit")


def step_review_sup5(session: PipelineSession) -> str:
    return _review(session, SPECS["SUP.5"], "sup5-review")


def step_sup6_evaluation(session: PipelineSession) -> str:
    return _generate(session, SPECS["SUP.6"], "sup6-evaluation")


def step_review_sup6(session: PipelineSession) -> str:
    return _review(session, SPECS["SUP.6"], "sup6-review")


def step_sup7_documentation(session: PipelineSession) -> str:
    return _generate(session, SPECS["SUP.7"], "sup7-documentation")


def step_review_sup7(session: PipelineSession) -> str:
    return _review(session, SPECS["SUP.7"], "sup7-review")


def step_pim1_establishment(session: PipelineSession) -> str:
    return _generate(session, SPECS["PIM.1"], "pim1-establishment")


def step_review_pim1(session: PipelineSession) -> str:
    return _review(session, SPECS["PIM.1"], "pim1-review")


def step_pim2_assessment(session: PipelineSession) -> str:
    return _generate(session, SPECS["PIM.2"], "pim2-assessment")


def step_review_pim2(session: PipelineSession) -> str:
    return _review(session, SPECS["PIM.2"], "pim2-review")


def step_reu1_assets(session: PipelineSession) -> str:
    return _generate(session, SPECS["REU.1"], "reu1-assets")


def step_review_reu1(session: PipelineSession) -> str:
    return _review(session, SPECS["REU.1"], "reu1-review")
