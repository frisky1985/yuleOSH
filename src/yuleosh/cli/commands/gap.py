#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH CLI — gap close: ASPICE 差距分析 → 改进工单（受控生成）.

命令:
  yuleosh gap close [--project-dir DIR] [--yes | --no | --list] [--req REQ-xxx]

分层原则（四专家评审 + 老板确认）:
  - 判断性差距（ASPICE 过程域缺口）→ 受控生成工单：默认逐个交互确认（y/N）
  - 确定性 KPI 差距 → Loop3 自动生成（rca_engine），本命令不干预

工单↔知识闭环:
  生成的 GAP-*.yaml 与 Loop3 的 IMP-*.yaml 保持同一 YAML 结构（improvement_ticket 根节点），
  可被 `yuleosh lesson create --ticket GAP-...` 读取，一键沉淀为 Lessons Learned。

SHALL-A5.5 纪律: 本模块不 import cli.main（避免循环依赖），_osh_home() 延迟解析。
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# status（❌=完全未就绪 / ⚠️=部分就绪）→ (priority, severity) 映射。
# 与 rca_engine 的 P0~P3 / low~critical 体系保持一致。
_STATUS_MAP = {
    "❌": ("P1", "high"),    # 判断性差距：完全未通过 → 高优
    "⚠️": ("P2", "medium"),  # 部分就绪 → 中优
}


def _osh_home() -> str:
    """延迟解析 OSH_HOME（默认当前目录）。"""
    return os.environ.get("OSH_HOME", os.getcwd())


# ── 差距加载 ────────────────────────────────────────────────────────────

def _load_gap_details(project_dir: str) -> list[dict]:
    """运行 aspice_gap_check(json) 并解析 gap_detail 列表。

    gap_detail 结构（来自 aspice_check._format_gap_json）:
      swe_id / swe_title / bp_id / bp_title / status（❌|⚠️）/
      failed_checks / total_checks / missing_items / fix_steps
    """
    from yuleosh.evidence.aspice_check import aspice_gap_check  # 延迟 import 便于测试 mock

    raw = aspice_gap_check(project_dir=project_dir, output_format="json")
    data = json.loads(raw)
    return data.get("gaps", [])


# ── 工单构造 ────────────────────────────────────────────────────────────

def _status_priority(status: str) -> tuple[str, str]:
    """status（❌/⚠️）→ (priority, severity)。"""
    return _STATUS_MAP.get(status, ("P2", "medium"))


def _summarize_missing(gap: dict) -> str:
    """missing_items 摘要（无缺失项时用 bp_title 兜底）。"""
    items = gap.get("missing_items") or []
    if items:
        return "; ".join(str(item).strip() for item in items)
    return str(gap.get("bp_title", ""))


def _compute_deadline(priority: str, now: Optional[str] = None) -> str:
    """与 rca_engine._compute_deadline 一致：P0=24h / P1=3d / P2=7d / P3=14d。"""
    base = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
    if priority == "P0":
        return (base + timedelta(hours=24)).isoformat()
    if priority == "P1":
        return (base + timedelta(days=3)).isoformat()
    if priority == "P2":
        return (base + timedelta(days=7)).isoformat()
    if priority == "P3":
        return (base + timedelta(days=14)).isoformat()
    return (base + timedelta(days=30)).isoformat()


def _build_gap_ticket(gap: dict, req: str = "", created_at: Optional[str] = None) -> dict:
    """构造与 Loop3 IMP-* 同构的改进工单 dict（ticket_id 用 GAP- 前缀）。

    字段映射（见任务书）:
      problem_description = missing_items 摘要
      root_cause          = 差距来源（bp_id + failed_checks）
      recommended_actions = fix_steps
      metric              = bp_id
      requirement_id      = --req 或默认空
      tags                = ["gap", "aspice", bp_id, swe_id]
      priority/severity   = status 映射（❌=P1/high, ⚠️=P2/medium）
    """
    now = created_at or datetime.now(timezone.utc).isoformat()
    bp_id = str(gap.get("bp_id", "UNKNOWN"))
    swe_id = str(gap.get("swe_id", "SWE.?"))
    bp_title = str(gap.get("bp_title", ""))
    status = str(gap.get("status", "⚠️"))
    priority, severity = _status_priority(status)

    failed = int(gap.get("failed_checks") or 0)
    total = int(gap.get("total_checks") or 0)
    missing = _summarize_missing(gap)
    missing_n = len(gap.get("missing_items") or [])

    problem_description = (
        f"ASPICE {swe_id} {bp_id}（{bp_title}）未完全就绪："
        f"{failed}/{total} 项检查未通过，缺失 {missing_n} 项产出物/证据。"
        f"缺口明细: {missing}"
    )
    root_cause = (
        f"差距来源: {bp_id}（{bp_title}）在 ASPICE {swe_id} 过程域中 "
        f"{failed}/{total} 项检查未通过，状态 {status}"
    )
    fix_steps = gap.get("fix_steps") or []
    if isinstance(fix_steps, list):
        recommended_actions = "\n".join(f"- {step}" for step in fix_steps)
    else:
        recommended_actions = str(fix_steps)

    return {
        "ticket_id": f"GAP-{now[:10]}-{bp_id}",
        "problem_description": problem_description,
        "root_cause": root_cause,
        "recommended_actions": recommended_actions,
        "priority": priority,
        "severity": severity,
        "metric": bp_id,
        "current_value": failed,
        "threshold": total,
        "deadline": _compute_deadline(priority, now=now),
        "assigned_to": "",
        "status": "open",
        "created_at": now,
        "requirement_id": req or "",
        "requirements": [req] if req else [],
        "tags": ["gap", "aspice", bp_id, swe_id],
    }


# ── YAML 写入 ───────────────────────────────────────────────────────────

def _indent_block(value: Any) -> str:
    """多行文本 → 每行 4 空格缩进（YAML folded scalar `>` 兼容）。"""
    lines = [str(line).strip() for line in str(value).splitlines()]
    return "\n".join("    " + line for line in lines if line)


def write_gap_ticket(ticket: dict, output_dir: str) -> str:
    """写入 improvement_tickets/{ticket_id}.yaml。

    结构与 rca_engine.write_improvement_ticket 保持一致（improvement_ticket 根节点、
    requirement_id/requirements/tags 等字段齐全），保证 kb lesson create 可直接读取。
    """
    tickets_dir = os.path.join(output_dir, "improvement_tickets")
    os.makedirs(tickets_dir, exist_ok=True)
    filepath = os.path.join(tickets_dir, f"{ticket['ticket_id']}.yaml")

    yaml_lines = [
        "---",
        "improvement_ticket:",
        f"  ticket_id: \"{ticket['ticket_id']}\"",
        f"  status: {ticket['status']}",
        f"  priority: {ticket['priority']}",
        f"  severity: {ticket['severity']}",
        f"  metric: {ticket['metric']}",
        f"  current_value: {ticket['current_value']}",
        f"  threshold: {ticket['threshold']}",
        f"  deadline: {ticket['deadline']}",
        f"  assigned_to: \"{ticket['assigned_to']}\"",
        f"  created_at: {ticket['created_at']}",
        f"  requirement_id: \"{ticket['requirement_id']}\"",
        f"  requirements: {ticket['requirements']}",
        "  problem_description: >",
        _indent_block(ticket["problem_description"]),
        "  root_cause: >",
        _indent_block(ticket["root_cause"]),
        "  recommended_actions: >",
        _indent_block(ticket["recommended_actions"]),
        "  tags:",
    ]
    for tag in ticket["tags"]:
        yaml_lines.append(f"    - {tag}")
    yaml_lines.append("...\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(yaml_lines))
    return filepath


# ── 交互确认 ────────────────────────────────────────────────────────────

def _confirm(prompt: str) -> bool:
    """交互确认（y/yes → True，其余/EOF → False）。"""
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


# ── 命令入口 ────────────────────────────────────────────────────────────

def cmd_gap_close(args) -> int:
    """`yuleosh gap close` — 从 ASPICE 差距分析受控生成改进工单。

    模式:
      - 默认交互: 逐个 gap 询问 y/N
      - --yes: 跳过确认全部接受
      - --no:  跳过全部，不生成
      - --list: 只列出差距，不生成
    """
    project_dir = getattr(args, "project_dir", None) or _osh_home()
    yes = bool(getattr(args, "yes", False))
    no = bool(getattr(args, "no", False))
    list_only = bool(getattr(args, "list", False))
    req = getattr(args, "req", "") or ""

    gaps = _load_gap_details(project_dir)
    if not gaps:
        print("✅ 未发现 ASPICE 差距（所有 BP 均已通过），无需生成工单。")
        return 0

    print(f"\n🔍 ASPICE 差距分析 → 改进工单（共 {len(gaps)} 个差距，项目: {project_dir}）")
    print("=" * 70)

    created: list[str] = []
    skipped: list[str] = []

    for idx, gap in enumerate(gaps, start=1):
        swe_id = gap.get("swe_id", "?")
        bp_id = gap.get("bp_id", "?")
        bp_title = gap.get("bp_title", "")
        status = gap.get("status", "⚠️")
        missing_n = len(gap.get("missing_items") or [])
        line = f"[{idx}/{len(gaps)}] [{swe_id}] {bp_id}: {bp_title}（状态: {status}）— 缺口 {missing_n} 项"

        if list_only:
            print(f"  📋 {line}")
            continue

        if yes:
            accept = True
        elif no:
            accept = False
        else:
            accept = _confirm(f"  {line}\n  生成改进工单? [y/N]: ")

        if not accept:
            skipped.append(bp_id)
            print(f"  ⏭️  跳过 {bp_id}")
            continue

        ticket = _build_gap_ticket(gap, req=req)
        path = write_gap_ticket(ticket, output_dir=project_dir)
        created.append(ticket["ticket_id"])
        print(f"  ✅ 工单已生成: {ticket['ticket_id']} → {path}")

    print("=" * 70)
    if list_only:
        print(f"📋 --list 模式: 列出 {len(gaps)} 个差距，未生成任何工单。")
    else:
        print(f"📊 汇总: 共 {len(gaps)} 个差距，生成 {len(created)} 个工单，跳过 {len(skipped)} 个。")
        for tid in created:
            print(f"     - {tid}")
        if created:
            print(f"💡 知识闭环: 运行 `yuleosh lesson create --ticket {created[0]}` 将工单一键沉淀为 Lesson。")
    return 0


# ── 解析器注册 ──────────────────────────────────────────────────────────

def build_parser(subparsers) -> argparse.ArgumentParser:
    """注册 gap 子命令组: yuleosh gap close。"""
    p_gap = subparsers.add_parser(
        "gap", help="ASPICE 差距 → 改进工单（受控生成，需人工确认）"
    )
    gsub = p_gap.add_subparsers(dest="gap_sub")
    p_close = gsub.add_parser(
        "close", help="从 ASPICE 差距分析结果生成改进工单（默认交互确认 y/N）"
    )
    p_close.add_argument("--project-dir", default=None,
                         help="项目根目录（默认 OSH_HOME/当前目录）")
    p_close.add_argument("--yes", action="store_true",
                         help="跳过确认，全部接受生成")
    p_close.add_argument("--no", action="store_true",
                         help="跳过全部差距，不生成工单")
    p_close.add_argument("--list", action="store_true",
                         help="只列出差距，不生成工单")
    p_close.add_argument("--req", default="",
                         help="需求 ID（REQ-xxx，可选，写入工单 requirement_id）")
    return p_gap
