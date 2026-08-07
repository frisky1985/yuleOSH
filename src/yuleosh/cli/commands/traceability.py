# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH CLI — Traceability matrix command group.

A5 (v3.8.0): extracted from cli/main.py (monolith split).  Behavior is
identical to the v3.7.0 inline implementation; cli/main.py re-exports
these functions for backward-compatible imports.
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("yuleosh.cli.traceability")

# OSH_HOME / sys.path bootstrap — mirrored from cli/main.py so command
# modules run standalone under pytest (SHALL-A5.5: no import of cli.main).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = Path(_SCRIPT_DIR).resolve().parent.parent.parent.parent / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _osh_home() -> str:
    """Resolve OSH_HOME, honoring cli.main's live value (A5 compat).

    cli.main re-exports these commands; tests monkeypatch
    ``yuleosh.cli.main.OSH_HOME``.  A lazy lookup keeps the single source
    of truth in cli.main without a top-level circular import (SHALL-A5.5).
    """
    try:
        import yuleosh.cli.main as _m
        return _m.OSH_HOME
    except Exception:
        return os.environ.get("OSH_HOME", os.getcwd())


def cmd_traceability_report(args):
    """Generate full traceability report (Requirement ↔ Code ↔ Test ↔ Review)."""
    from yuleosh.alm.traceability import generate_traceability_report

    project_dir = getattr(args, "project_dir", _osh_home())
    spec_path = getattr(args, "spec", None)

    report = generate_traceability_report(
        project_dir=project_dir,
        spec_path=spec_path,
        output_dir=os.path.join(project_dir, ".yuleosh", "reports"),
    )

    summary = report.get("coverage_summary", {})
    print(f"\n  📊 追溯完整性报告")
    print(f"  {'─' * 50}")
    print(f"  需求总数:        {summary.get('requirements_total', 'N/A')}")
    print(f"  测试覆盖率:      {summary.get('test_coverage_pct', 0):.1f}%")
    print(f"  代码覆盖率:      {summary.get('code_coverage', 'N/A')}")
    print(f"  评审覆盖率:      {summary.get('review_coverage', 'N/A')}")
    print(f"  覆盖缺口数:      {summary.get('total_gaps', 0)}")
    print(f"  孤立测试文件:    {summary.get('orphaned_tests', 0)}")

    recs = report.get("recommendations", [])
    if recs:
        print()
        for r in recs:
            print(f"  {r}")

    # ── 问题与知识闭环（需求 ↔ 工单 ↔ lessons）──────────────────────────
    # 扫描 improvement_tickets/*.yaml 与 KB lessons，统计每个需求的
    # 开放工单数与关联知识数，展示「需求↔问题↔知识」闭环。
    closure = _build_closure_stats(
        report.get("lrm", {}).get("requirements", []),
        _load_improvement_tickets(project_dir),
        _load_kb_lessons(project_dir),
    )
    report["closure"] = closure
    _print_closure_section(closure)

    # 合并写入同一份 JSON 报告（在 alm 生成的报告上追加 closure 一节）
    report_path = os.path.join(project_dir, ".yuleosh", "reports", "traceability-report.json")
    try:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("Cannot write merged traceability report: %s", e)

    print(f"\n  完整报告: {report_path}\n")


def cmd_traceability_export(args):
    """Export traceability matrix in OEM-compatible format."""
    from yuleosh.evidence.oem_templates import export_traceability_matrix
    from yuleosh.knowledge_graph import get_store

    project_dir = getattr(args, "project_dir", _osh_home())
    template_name = getattr(args, "template", "generic")
    output_format = getattr(args, "output_format", "markdown")
    filter_layer = getattr(args, "layer", None)
    include_evidence = not getattr(args, "no_evidence", False)

    store = get_store()

    result = export_traceability_matrix(
        store,
        template=template_name,
        output_format=output_format,
        filter_layer=filter_layer,
        include_test_evidence=include_evidence,
    )

    print(result)

    # Also save to file
    ext_map = {"markdown": "md", "csv": "csv", "json": "json"}
    ext = ext_map.get(output_format, "md")
    out_dir = Path(project_dir) / ".yuleosh" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"traceability-{template_name}-matrix.{ext}"
    out_path.write_text(result, encoding="utf-8")
    print(f"\n  💾 Saved to: {out_path}\n", file=sys.stderr)


def cmd_traceability_matrix(args):
    """Generate LRM / LRT matrix as JSON and print formatted overview."""
    from yuleosh.alm.traceability import generate_lrm, generate_lrt

    project_dir = getattr(args, "project_dir", _osh_home())
    spec_path = getattr(args, "spec", None)
    build_id = getattr(args, "build_id", None)

    lrt = generate_lrt(project_dir, spec_path)

    # Filter by build_id if provided
    if build_id:
        lrm = lrt.get("lrm", {})
        requirements = lrm.get("requirements", [])
        lrm["requirements"] = [
            r for r in requirements
            if r.get("req_id", "").startswith(build_id) or r.get("id", "").startswith(build_id)
        ]
        lrm["summary"] = {
            "total": len(lrm["requirements"]),
            "with_code": sum(1 for r in lrm["requirements"] if r.get("has_code")),
            "with_test": sum(1 for r in lrm["requirements"] if r.get("has_test")),
            "with_review": sum(1 for r in lrm["requirements"] if r.get("has_review")),
            "without_code": sum(1 for r in lrm["requirements"] if not r.get("has_code")),
            "without_test": sum(1 for r in lrm["requirements"] if not r.get("has_test")),
            "without_review": sum(1 for r in lrm["requirements"] if not r.get("has_review")),
            "coverage_pct": (sum(1 for r in lrm["requirements"] if r.get("has_test")) / max(len(lrm["requirements"]), 1)) * 100,
        } if lrm["requirements"] else {
            "total": 0, "with_code": 0, "with_test": 0, "with_review": 0,
            "without_code": 0, "without_test": 0, "without_review": 0, "coverage_pct": 0.0,
        }
        lrt["lrm"] = lrm
    lrm = lrt.get("lrm", {})
    requirements = lrm.get("requirements", [])
    summary = lrm.get("summary", {})
    gaps = lrt.get("gap_analysis", {})

    # Print formatted overview
    print(f"\n  {'=' * 70}")
    print(f"  📋 需求追溯矩阵 (LRM / LRT)")
    print(f"  {'=' * 70}")
    print(f"  生成时间: {lrm.get('generated_at', '')[:19]}")
    print(f"  {'─' * 70}")

    # Table header
    header = f"  {'req_id':<20} {'SHALL':<8} {'Code':<6} {'Test':<6} {'Review':<6} {'StepHdlr':<8} Section"
    print(header)
    print(f"  {'─' * 70}")

    for req in requirements:
        req_id = req.get("req_id") or "—"
        shall_id = req.get("id", "—")
        code_icon = "✅" if req.get("has_code") else "❌"
        test_icon = "✅" if req.get("has_test") else "❌"
        review_icon = "✅" if req.get("has_review") else "❌"
        steps = req.get("step_handlers", [])
        step_str = f"{len(steps)}" if steps else "—"
        section = (req.get("section", "") or "")[:30]
        print(f"  {req_id:<20} {shall_id:<8} {code_icon:<6} {test_icon:<6} {review_icon:<6} {step_str:<8} {section}")

    print(f"  {'─' * 70}")
    total = summary.get("total", 0)
    cov = summary.get("coverage_pct", 0.0)
    print(f"  需求总数: {total}  |  测试覆盖率: {cov}%")
    print(f"  Code: {summary.get('with_code', 0)}/{total}  Test: {summary.get('with_test', 0)}/{total}  Review: {summary.get('with_review', 0)}/{total}")

    gap_list = gaps.get("gaps", [])
    if gap_list:
        print(f"\n  ⚠️  覆盖缺口: {len(gap_list)}")
        for g in gap_list[:10]:
            rid = g.get("req_id", "?")
            stmt = g.get("statement", "")[:50]
            print(f"    • [{g['type']}] {rid}: {stmt}...")
        if len(gap_list) > 10:
            print(f"    ... 还有 {len(gap_list) - 10} 个缺口")

    print()

    # Also output full JSON to stdout for pipe/redirect
    print(">>> Full JSON:", file=sys.stderr)
    print(json.dumps(lrt, indent=2, ensure_ascii=False, default=str))


# ── 问题与知识闭环（需求 ↔ 工单 ↔ lessons）────────────────────────────
# 统计每个需求关联的 improvement tickets 与 KB lessons，
# 展示「需求↔问题↔知识」闭环（A 评审闭环要求）。
# 全部为只读扫描：不修改 alm/traceability.py，不修改 kb 数据。

# 工单 ID 形如 IMP-2026-08-04-misra_vi
_TICKET_ID_RE = re.compile(r"\bIMP-\d{4}-\d{2}-\d{2}-[A-Za-z0-9][A-Za-z0-9._-]*\b")
# 需求 ID 形如 REQ-MISRA-S1 / SWE-MISRA-S1 / KL-SHALL-01（与
# alm.traceability 的 spec_id_pattern / section_req_id_pattern 风格一致）
_REQ_ID_RE = re.compile(
    r"\b(?:REQ|SWE|KL|SYS|HIL|FUSA)-[A-Z0-9][A-Z0-9._-]*\b", re.IGNORECASE
)
# 视为已关闭的工单状态（其余一律按开放统计）
_CLOSED_STATUSES = frozenset({
    "closed", "done", "resolved", "complete", "completed",
    "已关闭", "已完成", "已解决", "取消", "cancelled", "canceled",
})


def _load_improvement_tickets(project_dir: str) -> list[dict]:
    """扫描 ``improvement_tickets/*.yaml``，提取工单的需求关联。

    每个工单读取 ``id`` / ``title`` / ``status`` / ``requirement_id``
    （requirement_id 可为单个字符串或列表；缺失时视为未关联工单）。
    目录不存在、YAML 不可解析或 PyYAML 未安装时优雅降级为空列表。
    """
    tickets: list[dict] = []
    tickets_dir = Path(project_dir) / "improvement_tickets"
    if not tickets_dir.is_dir():
        return tickets
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        log.warning("PyYAML not installed — cannot scan improvement tickets")
        return tickets
    for tfile in sorted(tickets_dir.glob("*.y*ml")):
        try:
            data = yaml.safe_load(tfile.read_text(encoding="utf-8")) or {}
        except Exception as e:  # noqa: BLE001 — 单文件解析失败不阻塞整体
            log.warning("Cannot parse ticket file %s: %s", tfile, e)
            continue
        if not isinstance(data, dict):
            continue
        rid = data.get("requirement_id")
        if isinstance(rid, list):
            req_ids = [str(r).strip() for r in rid if str(r).strip()]
        elif rid is not None:
            req_ids = [str(rid).strip()]
        else:
            req_ids = []
        status = str(data.get("status", "open")).strip().lower()
        tickets.append({
            "id": str(data.get("id") or tfile.stem),
            "title": str(data.get("title", "")),
            "status": status,
            "open": status not in _CLOSED_STATUSES,
            "requirement_ids": req_ids,
            "file": str(tfile),
        })
    return tickets


def _extract_requirement_ids(text: str) -> list[str]:
    """从文本中提取 REQ 风格需求 ID（去重、保序、大写归一）。"""
    if not text:
        return []
    return list(dict.fromkeys(m.group(0).upper() for m in _REQ_ID_RE.finditer(text)))


def _extract_ticket_ids(text: str) -> list[str]:
    """从文本中提取 IMP- 风格工单 ID（去重、保序）。"""
    if not text:
        return []
    return list(dict.fromkeys(m.group(0) for m in _TICKET_ID_RE.finditer(text)))


def _load_kb_lessons(project_dir: str) -> list[dict]:
    """读取 KB lessons 并提取需求 / 工单关联（只读，不修改 kb）。

    - 优先使用项目内 ``.yuleosh/kb.db``（若存在）；
    - 否则若设置了 ``YULEOSH_KB_DB`` 环境变量则使用它（显式指定）；
    - 都不存在时返回空列表（**不回退全局默认库**——避免把其他项目的
      lessons 混入本项目的追溯闭环，也保证测试隔离）。
    - 关联方式（三层信号，取并集）：
        1. lesson.requirement_id / lesson.ticket_id 结构化字段
           （kb.models.Lesson 新增列，getattr 兼容旧版本模型）；
        2. lesson.project_id 精确匹配需求 ID；
        3. 从 title/problem/solution/root_cause 文本中正则提取需求 ID
           与工单 ID（旧数据兜底）。
    - 无 kb 库 / 表结构缺失 / 任意异常时优雅降级为空列表。
    """
    try:
        from yuleosh.kb.store import KbStore
    except ImportError:
        return []
    local_db = Path(project_dir) / ".yuleosh" / "kb.db"
    try:
        if local_db.is_file():
            store = KbStore(db_path=str(local_db))
        elif os.environ.get("YULEOSH_KB_DB"):
            store = KbStore(db_path=os.environ["YULEOSH_KB_DB"])
        else:
            # No project-local KB and no explicit override — empty closure,
            # never fall back to the global default store (test isolation).
            return []
    except Exception as e:  # noqa: BLE001
        log.warning("Cannot open KB store for traceability closure: %s", e)
        return []
    lessons: list[dict] = []
    try:
        offset = 0
        while True:
            batch = store.list_lessons(limit=500, offset=offset)
            if not batch:
                break
            for lesson in batch:
                text = " ".join([
                    lesson.title or "", lesson.problem or "",
                    lesson.solution or "", lesson.root_cause or "",
                ])
                req_ids = _extract_requirement_ids(text)
                ticket_ids = _extract_ticket_ids(text)
                # 结构化字段（新模型才有；getattr 兼容旧版本）
                struct_req = str(getattr(lesson, "requirement_id", "") or "").strip()
                struct_ticket = str(getattr(lesson, "ticket_id", "") or "").strip()
                if struct_req:
                    req_ids.append(struct_req.upper())
                if struct_ticket:
                    ticket_ids.append(struct_ticket)
                pid = (lesson.project_id or "").strip()
                if pid and _REQ_ID_RE.fullmatch(pid):
                    req_ids.append(pid.upper())
                lessons.append({
                    "id": lesson.id,
                    "title": lesson.title,
                    "project_id": pid,
                    "severity": lesson.severity,
                    "requirement_ids": list(dict.fromkeys(req_ids)),
                    "ticket_ids": list(dict.fromkeys(ticket_ids)),
                })
            offset += len(batch)
    except Exception as e:  # noqa: BLE001
        log.warning("Cannot read lessons from KB store: %s", e)
    finally:
        try:
            store.close()
        except Exception:  # noqa: BLE001
            pass
    return lessons


def _build_closure_stats(requirements: list[dict],
                         tickets: list[dict],
                         lessons: list[dict]) -> dict:
    """构建每需求（requirement_id）的工单 / lesson 关联统计。

    - ``requirements``：来自 report['lrm']['requirements']，取
      ``req_id``（spec 定义 ID）优先、``id``（SHALL ID）兜底；
    - 工单按 ``requirement_id`` 精确关联；lessons 按需求 ID 直接关联，
      另统计经由工单（lesson 文本引用 IMP-xxx）的间接知识关联；
    - 未关联到已知需求的工单 / lessons 计入 orphan 列表。
    """
    known: dict[str, str] = {}  # upper-id -> canonical id
    for r in requirements:
        rid = (r.get("req_id") or r.get("id") or "").strip()
        if rid:
            known[rid.upper()] = rid
    per_req = {
        rid: {
            "req_id": rid,
            "open_tickets": 0,
            "total_tickets": 0,
            "ticket_ids": [],
            "lessons": 0,
            "lesson_ids": [],
            "lessons_via_tickets": 0,
            "lesson_via_ticket_ids": [],
        }
        for rid in known.values()
    }
    ticket_by_id = {t["id"]: t for t in tickets}
    orphan_tickets: list[dict] = []
    orphan_lessons: list[dict] = []

    for t in tickets:
        linked = False
        for rid in t["requirement_ids"]:
            rec = per_req.get(rid.upper())
            if rec is not None:
                rec["total_tickets"] += 1
                rec["ticket_ids"].append(t["id"])
                if t["open"]:
                    rec["open_tickets"] += 1
                linked = True
        if not linked:
            orphan_tickets.append({
                "id": t["id"], "status": t["status"],
                "requirement_ids": t["requirement_ids"],
            })

    for lesson in lessons:
        direct = {rid for rid in lesson["requirement_ids"] if rid.upper() in known}
        via_tickets = set()
        for tid in lesson["ticket_ids"]:
            t = ticket_by_id.get(tid)
            if t:
                for rid in t["requirement_ids"]:
                    if rid.upper() in known:
                        via_tickets.add(known[rid.upper()])
        for rid in direct:
            rec = per_req[known[rid.upper()]]
            rec["lessons"] += 1
            rec["lesson_ids"].append(lesson["id"])
        for rid in via_tickets:
            rec = per_req[rid]
            rec["lessons_via_tickets"] += 1
            rec["lesson_via_ticket_ids"].append(lesson["id"])
        if not direct and not via_tickets:
            orphan_lessons.append({
                "id": lesson["id"], "title": lesson["title"],
                "requirement_ids": lesson["requirement_ids"],
                "ticket_ids": lesson["ticket_ids"],
            })

    rows = sorted(per_req.values(), key=lambda x: x["req_id"])
    total_open = sum(r["open_tickets"] for r in rows)
    total_linked_lessons = sum(r["lessons"] + r["lessons_via_tickets"] for r in rows)
    return {
        "requirements": rows,
        "summary": {
            "requirements_total": len(rows),
            "with_tickets": sum(1 for r in rows if r["total_tickets"] > 0),
            "with_lessons": sum(1 for r in rows if r["lessons"] + r["lessons_via_tickets"] > 0),
            "closed_loop": sum(1 for r in rows
                               if r["total_tickets"] > 0
                               and r["lessons"] + r["lessons_via_tickets"] > 0),
            "open_tickets_total": total_open,
            "tickets_total": len(tickets),
            "lessons_linked_total": total_linked_lessons,
            "lessons_total": len(lessons),
            "orphan_tickets": len(orphan_tickets),
            "orphan_lessons": len(orphan_lessons),
        },
        "orphan_tickets": orphan_tickets,
        "orphan_lessons": orphan_lessons,
    }


def _print_closure_section(closure: dict):
    """打印「问题与知识闭环」统计表（与控制台整体风格一致）。"""
    rows = closure.get("requirements", [])
    summary = closure.get("summary", {})
    print()
    print(f"  🔄 问题与知识闭环（需求 ↔ 工单 ↔ lessons）")
    print(f"  {'─' * 70}")
    if not rows:
        print(f"  （无需求可统计 — 跳过闭环分析）")
        return
    print(f"  {'req_id':<22} {'工单(开放/总)':<16} {'Lessons':<9} {'经工单Lesson':<13} 闭环")
    print(f"  {'─' * 70}")
    for r in rows:
        loop = "✅" if (r["total_tickets"] > 0
                        and r["lessons"] + r["lessons_via_tickets"] > 0) else "—"
        print(f"  {r['req_id']:<22} "
              f"{r['open_tickets']}/{r['total_tickets']:<12} "
              f"{r['lessons']:<9} {r['lessons_via_tickets']:<13} {loop}")
    print(f"  {'─' * 70}")
    print(f"  需求数: {summary.get('requirements_total', 0)}"
          f"  |  有工单: {summary.get('with_tickets', 0)}"
          f"  |  有知识: {summary.get('with_lessons', 0)}"
          f"  |  闭环: {summary.get('closed_loop', 0)}")
    print(f"  开放工单: {summary.get('open_tickets_total', 0)}"
          f"/{summary.get('tickets_total', 0)}"
          f"  |  关联 lessons: {summary.get('lessons_linked_total', 0)}"
          f"/{summary.get('lessons_total', 0)}")
    if summary.get("orphan_tickets") or summary.get("orphan_lessons"):
        print(f"  ⚠️  未关联工单: {summary.get('orphan_tickets', 0)} 个"
              f" | 未关联 lessons: {summary.get('orphan_lessons', 0)} 条"
              f" — 建议补全 requirement_id / 需求 ID 关联")


def build_parser(sub):
    """Register the traceability command group (A5)."""
    p_trace = sub.add_parser("traceability", help="Traceability matrix management")
    tsub = p_trace.add_subparsers(dest="traceability_sub")
    p_trace_report = tsub.add_parser("report", help="Generate full traceability report")
    p_trace_report.add_argument("--project-dir", default=_osh_home(), help="Project root directory")
    p_trace_report.add_argument("--spec", default=None, help="Path to spec file")
    p_trace_matrix = tsub.add_parser("matrix", help="Generate LRM/LRT matrix (JSON output)")
    p_trace_matrix.add_argument("--project-dir", default=_osh_home(), help="Project root directory")
    p_trace_matrix.add_argument("--spec", default=None, help="Path to spec file")
    p_trace_matrix.add_argument("--build-id", default=None, help="Filter by build ID")
    p_trace_export = tsub.add_parser("export", help="Export traceability matrix in OEM-compatible format")
    p_trace_export.add_argument("--template", default="generic",
                                choices=["generic", "vw", "bmw", "mercedes", "oem_common"],
                                help="OEM template (default: generic)")
    p_trace_export.add_argument("--format", default="markdown", dest="output_format",
                                choices=["markdown", "csv", "json"],
                                help="Output format (default: markdown)")
    p_trace_export.add_argument("--layer", default=None, help="Filter by test layer (unit/integration/sil/hil)")
    p_trace_export.add_argument("--project-dir", default=_osh_home(), help="Project root directory")
    p_trace_export.add_argument("--no-evidence", action="store_true",
                                help="Exclude test evidence links from output")
    return p_trace
