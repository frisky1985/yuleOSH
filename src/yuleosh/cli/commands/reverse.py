#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Reverse-Engineering Scan CLI (B-M1 / T-011 B1-11).

``yuleosh reverse scan <path>`` 对指定 C 项目做逆向扫描，输出：

  - 扫描统计（文件数 / code vs test / 解析成功率 / 平均错误率）
  - 实体计数（CFunction / CGlobalVar / CMacro / ISR / 边）
  - 置信度分布报告（按实体类型分桶 0.9 / 0.5 / 0.35，对齐 B1-10 D4 规则）

默认写入一个**临时** KG store 以复用与 ``scan_directory`` 一致的真实入库路径，
报告产出后清理该临时库（不污染项目 .yuleosh/knowledge_graph.db）。
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.c_code_scanner import scan_directory

log = logging.getLogger("yuleosh.cli.commands.reverse")

# 参与置信度分布统计的 C 专属实体类型（B1-10）
_C_ENTITY_TYPES = ("CFunction", "CGlobalVar", "CMacro", "ISR")


def _confidence_distribution(store: KGStore) -> dict:
    """从临时 store 回读各 C 实体类型的置信度分桶。

    与 B1-10 ``c_entity_confidence`` 写入的值完全一致（回读而非重算）。
    """
    dist: dict[str, dict] = {}
    for et in _C_ENTITY_TYPES:
        nodes = store.list_nodes(et)
        buckets: dict = {}
        for n in nodes:
            c = n.confidence
            key = round(c, 4) if c is not None else None
            buckets[key] = buckets.get(key, 0) + 1
        dist[et] = buckets
    return dist


def _build_report(project_base: str, summary: dict, dist: dict) -> dict:
    """组装报告 dict（扫描统计 + 实体计数 + 置信度分布）。"""
    files = summary.get("files", [])
    files_scanned = len(files)
    parse_ok = sum(1 for f in files if f.get("parse_ok"))
    files_with_error = files_scanned - parse_ok
    rates = [f.get("error_rate", 0.0) for f in files if isinstance(f.get("error_rate"), (int, float))]
    avg_error_rate = (sum(rates) / len(rates)) if rates else 0.0

    entity_counts = {
        "CFunction": summary.get("functions", 0),
        "CGlobalVar": summary.get("globals", 0),
        "CMacro": summary.get("macros", 0),
        "ISR": summary.get("isrs", 0),
    }

    # 总实体置信度分布（合并所有 C 实体类型）
    overall: dict = {}
    for et, buckets in dist.items():
        for conf, cnt in buckets.items():
            overall[conf] = overall.get(conf, 0) + cnt

    return {
        "command": "reverse scan",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_base": str(Path(project_base).resolve()),
        "scan_stats": {
            "files_scanned": files_scanned,
            "code_files": summary.get("code_files", 0),
            "test_files": summary.get("test_files", 0),
            "parse_ok": parse_ok,
            "files_with_error": files_with_error,
            "avg_error_rate": round(avg_error_rate, 6),
        },
        "entity_counts": entity_counts,
        "edges": {
            "contains": summary.get("contains_edges", 0),
            "calls": summary.get("call_edges_resolved", 0),
            "potential_calls": summary.get("potential_edges_resolved", 0),
            "total": summary.get("edges", 0),
        },
        "confidence_distribution": dist,
        "confidence_overall": overall,
    }


def _render_text(report: dict) -> str:
    """把报告 dict 渲染为人类可读文本。"""
    s = report["scan_stats"]
    e = report["edges"]
    lines = [
        "🔍 yuleOSH Reverse-Engineering Scan Report",
        "=" * 52,
        f"Project : {report['project_base']}",
        f"Scanned : {report['generated_at']}",
        "",
        "📁 Scan Statistics",
        f"  Files scanned      : {s['files_scanned']}",
        f"  Code files         : {s['code_files']}",
        f"  Test files         : {s['test_files']}",
        f"  Parse OK           : {s['parse_ok']}",
        f"  Files w/ errors    : {s['files_with_error']}",
        f"  Avg error rate     : {s['avg_error_rate'] * 100:.2f}%",
        "",
        "🧩 Entity Counts",
    ]
    for et, cnt in report["entity_counts"].items():
        lines.append(f"  {et:<12} : {cnt}")
    lines += [
        "",
        "🔗 Edges",
        f"  contains       : {e['contains']}",
        f"  calls          : {e['calls']}",
        f"  potential_calls: {e['potential_calls']}",
        f"  total          : {e['total']}",
        "",
        "📊 Confidence Distribution (per entity type)",
    ]
    for et in _C_ENTITY_TYPES:
        buckets = report["confidence_distribution"].get(et, {})
        if not buckets:
            lines.append(f"  {et:<12} : (none)")
            continue
        parts = " | ".join(
            f"{c if c is not None else 'n/a'} × {n}"
            for c, n in sorted(buckets.items(), key=lambda kv: (kv[0] is None, kv[0]))
        )
        lines.append(f"  {et:<12} : {parts}")
    lines.append("  ── Overall ──")
    overall = report["confidence_overall"]
    overall_parts = " | ".join(
        f"{c if c is not None else 'n/a'} × {n}"
        for c, n in sorted(overall.items(), key=lambda kv: (kv[0] is None, kv[0]))
    )
    lines.append(f"  {'':<12} : {overall_parts}")
    return "\n".join(lines)


def cmd_reverse_scan(args) -> int:
    """``yuleosh reverse scan <path>`` — 逆向扫描并输出报告。

    Returns:
        int: 进程退出码（0=成功）。
    """
    project_base = getattr(args, "path", None) or "."
    project_path = Path(project_base).resolve()
    if not project_path.exists():
        print(f"❌ 路径不存在: {project_path}")
        return 2
    if not project_path.is_dir():
        print(f"❌ 不是目录: {project_path}")
        return 2

    # 临时 store：复用真实入库路径（scan_directory），报告后清理。
    tmp = tempfile.NamedTemporaryFile(prefix="yuleosh-reverse-", suffix=".db", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        store = KGStore(tmp_path)
        summary = scan_directory(store, str(project_path))
        dist = _confidence_distribution(store)
    finally:
        try:
            store.close()
        except Exception:
            pass
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    report = _build_report(str(project_path), summary, dist)

    as_json = getattr(args, "json", False)
    if as_json:
        out = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    else:
        out = _render_text(report)

    print(out)

    save_path = getattr(args, "save", None)
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        Path(save_path).write_text(out, encoding="utf-8")
        print(f"\n📄 Report saved: {save_path}")

    return 0


def build_parser(sub):
    """向主解析器注册 ``reverse`` 命令组 (B1-11)。"""
    p_reverse = sub.add_parser(
        "reverse",
        help="Reverse-engineering scan (C AST → entities/confidence report)",
    )
    rsub = p_reverse.add_subparsers(dest="reverse_sub")
    p_scan = rsub.add_parser(
        "scan",
        help="Scan a C project and report scan stats + entity counts + confidence distribution",
    )
    p_scan.add_argument(
        "path", nargs="?", default=".",
        help="Project root to scan (default: current dir)",
    )
    p_scan.add_argument(
        "--json", action="store_true",
        help="Output the report as JSON",
    )
    p_scan.add_argument(
        "--save", "-o", default=None,
        help="Write the report to a file (path)",
    )
    return p_reverse
