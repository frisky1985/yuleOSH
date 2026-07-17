#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Reporter — RTM + Metrics auto-generation (KG-40-RTM, KG-METRICS).

Generates traceability matrix and metrics reports from the KG store.
Supports Markdown, HTML, and CSV formats.

Usage:
    from yuleosh.knowledge_graph.reporter import generate_rtm, generate_metrics

    store = get_store()
    rtm_md = generate_rtm(store, fmt="markdown")
    metrics = generate_metrics(store)
"""

import csv
import io
import json
import logging
from datetime import datetime
from typing import Optional

from yuleosh.knowledge_graph.store import KGStore

log = logging.getLogger("yuleosh.knowledge_graph.reporter")

# ── Layer definitions for ASPICE mapping ───────────────────────────────

LAYER_NAMES = {
    "unit": "SWE.4 单元测试",
    "integration": "SWE.5 集成测试",
    "sil": "SIL 仿真测试",
    "hil": "HIL 硬件测试",
    "system": "SWE.6 系统测试",
}

LAYER_ASPICE = {
    "unit": "SWE.4",
    "integration": "SWE.5",
    "sil": "SWE.5",
    "hil": "SWE.6",
    "system": "SWE.6",
}


# ═══════════════════════════════════════════════════════════════════════
# RTM 追溯矩阵生成 (KG-40-RTM)
# ═══════════════════════════════════════════════════════════════════════

def _build_rtm_rows(store: KGStore,
                    layer: Optional[str] = None) -> list[dict]:
    """Build RTM rows from the KG store.

    For each active requirement node, find covering tests and implementing code.

    Returns:
        List of dicts with keys:
          req_id, statement, test_files, test_functions, code_files,
          status, confidence
    """
    reqs = store.list_nodes("requirement", active_only=True)
    rows = []

    for req in reqs:
        req_id = req.entity_id
        statement = req.label
        # Truncate long statements for display
        if len(statement) > 80:
            statement = statement[:77] + "..."

        # Find covering test files and functions via outgoing covers edges
        test_files: set[str] = set()
        test_functions: list[str] = []
        code_files: set[str] = set()
        confidence_scores: list[float] = []

        outgoing = store.get_outgoing_edges(req.id)
        for edge, target in outgoing:
            if edge.edge_type == "covers":
                # Check layer filter
                if layer is not None:
                    edge_layer = edge.properties.get("layer") or edge.layer
                    if edge_layer != layer:
                        continue

                score = edge.properties.get("confidence", 1.0)
                if isinstance(score, (int, float)):
                    confidence_scores.append(float(score))

                if target.entity_type == "test_file":
                    test_files.add(target.entity_id)
                    test_functions.append(f"[file] {target.entity_id}")
                elif target.entity_type == "test_function":
                    tf_name = target.label
                    tf_path = target.properties.get(
                        "file_path",
                        target.entity_id.split("::")[0] if "::" in target.entity_id else target.entity_id
                    )
                    test_files.add(tf_path)
                    test_functions.append(tf_name)

            elif edge.edge_type == "implements" and target.entity_type in ("code_file", "code_function"):
                score = edge.properties.get("confidence", 1.0)
                if isinstance(score, (int, float)):
                    confidence_scores.append(float(score))
                if target.entity_type == "code_file":
                    code_files.add(target.entity_id)
                else:
                    # For code_function, try to get file_path from properties
                    cf_path = target.properties.get("file_path", target.entity_id)
                    code_files.add(cf_path)

        # Determine coverage status
        if len(test_files) > 0:
            status = "covered"
        elif req.properties.get("testable", True) is False:
            status = "non-testable"
        else:
            status = "uncovered"

        # Determine best confidence label
        if confidence_scores:
            avg_conf = sum(confidence_scores) / len(confidence_scores)
        else:
            avg_conf = 1.0

        if avg_conf >= 0.95:
            confidence = "explicit"
        elif avg_conf >= 0.8:
            confidence = "derived"
        else:
            confidence = "heuristic"

        rows.append({
            "req_id": req_id,
            "statement": statement,
            "test_files": ", ".join(sorted(test_files)) if test_files else "—",
            "test_functions": ", ".join(test_functions[:10]) if test_functions else "—",
            "test_count": len(test_files),
            "function_count": len(test_functions),
            "code_files": ", ".join(sorted(code_files)) if code_files else "—",
            "status": status,
            "confidence": confidence,
            "confidence_score": round(avg_conf, 2),
        })

    return rows


def generate_rtm_markdown(store: KGStore,
                          layer: Optional[str] = None,
                          title: Optional[str] = None) -> str:
    """Generate a Markdown traceability matrix from the KG.

    Args:
        store: KGStore instance.
        layer: Optional test layer filter.
        title: Optional report title.

    Returns:
        Markdown string.
    """
    rows = _build_rtm_rows(store, layer=layer)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = title or f"yuleOSH 追溯矩阵 (知识图谱自动生成)"
    layer_label = LAYER_NAMES.get(layer, "全部层") if layer else "全部层"

    lines = [
        f"# {title}",
        "",
        f"> 生成时间: {now}",
        f"> 来源: 知识图谱 (v2.3.0)",
        f"> 过滤层: {layer_label}",
        f"> 总需求数: {len(rows)}",
        "",
    ]

    # Summary stats
    covered = sum(1 for r in rows if r["status"] == "covered")
    uncovered = sum(1 for r in rows if r["status"] == "uncovered")
    non_testable = sum(1 for r in rows if r["status"] == "non-testable")
    coverage_pct = round(covered / (len(rows) - non_testable) * 100, 1) if (len(rows) - non_testable) > 0 else 0

    lines.extend([
        "## 覆盖概览",
        "",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 已覆盖需求 | {covered} |",
        f"| 未覆盖需求 | {uncovered} |",
        f"| 非可测试需求 (管理类) | {non_testable} |",
        f"| 覆盖率 | {coverage_pct}% |",
        f"| 显式追溯 (explicit) | {sum(1 for r in rows if r['confidence'] == 'explicit')} |",
        f"| 推导追溯 (derived) | {sum(1 for r in rows if r['confidence'] == 'derived')} |",
        f"| 启发式追溯 (heuristic) | {sum(1 for r in rows if r['confidence'] == 'heuristic')} |",
        "",
    ])

    # Detailed table
    lines.extend([
        "## 详细追溯矩阵",
        "",
        "| 需求 ID | 陈述 | 覆盖状态 | 置信度 | 测试文件 | 代码文件 |",
        "|---------|------|:--------:|:------:|----------|----------|",
    ])

    for r in rows:
        status_icon = {"covered": "✅", "uncovered": "❌", "non-testable": "⏭️"}
        icon = status_icon.get(r["status"], "❓")
        status_display = f"{icon} {r['status']}"
        confidence_display = f"{r['confidence']} ({r['confidence_score']})"

        # Shorten test_files and code_files for table readability
        test_files_short = r["test_files"]
        if len(test_files_short) > 60:
            test_files_short = test_files_short[:57] + "..."

        code_files_short = r["code_files"]
        if len(code_files_short) > 60:
            code_files_short = code_files_short[:57] + "..."

        lines.append(
            f"| {r['req_id']} | {r['statement']} | {status_display} | "
            f"{confidence_display} | {test_files_short} | {code_files_short} |"
        )

    lines.append("")

    # Test layer distribution
    if layer is None:
        lines.extend([
            "## 测试层分布",
            "",
            "| 测试层 | ASPICE 过程 | 测试文件数 | 覆盖需求数 |",
            "|--------|:-----------:|:----------:|:----------:|",
        ])
        for lname, llabel in sorted(LAYER_NAMES.items()):
            # Count covers edges with this layer
            layer_rows = _build_rtm_rows(store, layer=lname)
            layer_covered = sum(1 for r in layer_rows if r["status"] == "covered")
            layer_files = sum(r["test_count"] for r in layer_rows)
            aspice = LAYER_ASPICE.get(lname, "—")
            lines.append(f"| {llabel} | {aspice} | {layer_files} | {layer_covered} |")

        lines.append("")

    # Uncovered requirements section
    uncovered_rows = [r for r in rows if r["status"] == "uncovered"]
    if uncovered_rows:
        lines.extend([
            "## 未覆盖需求详情",
            "",
            "以下需求没有测试覆盖，需人工关注：",
            "",
        ])
        for r in uncovered_rows[:20]:
            lines.append(f"- **{r['req_id']}**: {r['statement']}")
        if len(uncovered_rows) > 20:
            lines.append(f"  *...以及 {len(uncovered_rows) - 20} 条更多*")
        lines.append("")

    return "\n".join(lines)


def generate_rtm_html(store: KGStore,
                      layer: Optional[str] = None,
                      title: Optional[str] = None) -> str:
    """Generate an HTML traceability matrix from the KG.

    Produces a self-contained HTML page with styled table.
    """
    rows = _build_rtm_rows(store, layer=layer)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = title or "yuleOSH Traceability Matrix"

    covered = sum(1 for r in rows if r["status"] == "covered")
    uncovered = sum(1 for r in rows if r["status"] == "uncovered")
    non_testable = sum(1 for r in rows if r["status"] == "non-testable")
    total_tracked = len(rows) - non_testable
    coverage_pct = round(covered / total_tracked * 100, 1) if total_tracked > 0 else 0

    # Build table rows HTML
    table_rows = ""
    for r in rows:
        status_class = r["status"]
        status_icon = {"covered": "✅", "uncovered": "❌", "non-testable": "⏭️"}
        icon = status_icon.get(r["status"], "❓")

        table_rows += (
            f"<tr class='row-{status_class}'>"
            f"<td><code>{r['req_id']}</code></td>"
            f"<td>{r['statement'][:60]}</td>"
            f"<td class='status-{status_class}'>{icon} {r['status']}</td>"
            f"<td>{r['confidence']} ({r['confidence_score']})</td>"
            f"<td class='cell-limited' title='{r['test_files']}'>{r['test_files'][:50]}</td>"
            f"<td class='cell-limited' title='{r['code_files']}'>{r['code_files'][:50]}</td>"
            f"</tr>\n"
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
              margin: 2em; background: #f8f9fa; color: #222; }}
  h1 {{ color: #1a1a2e; border-bottom: 2px solid #e94560; padding-bottom: 0.3em; }}
  h2 {{ color: #16213e; margin-top: 2em; }}
  .meta {{ color: #666; font-size: 0.9em; }}
  .stats {{ display: flex; gap: 1em; flex-wrap: wrap; margin: 1em 0; }}
  .stat-card {{ background: #fff; border-radius: 8px; padding: 1em 1.5em;
                box-shadow: 0 1px 3px rgba(0,0,0,0.12); flex: 1; min-width: 120px; }}
  .stat-card .value {{ font-size: 1.8em; font-weight: bold; }}
  .stat-card .label {{ font-size: 0.85em; color: #666; margin-top: 0.3em; }}
  .stat-card.coverage {{ border-left: 4px solid #2ecc71; }}
  .stat-card.uncovered {{ border-left: 4px solid #e74c3c; }}
  .stat-card.total {{ border-left: 4px solid #3498db; }}

  table {{ width: 100%; border-collapse: collapse; background: #fff;
           box-shadow: 0 1px 3px rgba(0,0,0,0.12); border-radius: 8px; overflow: hidden; }}
  th {{ background: #16213e; color: #fff; padding: 10px 12px; text-align: left;
        font-weight: 600; white-space: nowrap; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 0.9em; }}
  tr:hover {{ background: #f0f0f5; }}
  tr.row-uncovered {{ background: #fff5f5; }}
  tr.row-non-testable {{ background: #fafafa; opacity: 0.7; }}

  .status-covered {{ color: #27ae60; font-weight: 600; }}
  .status-uncovered {{ color: #e74c3c; font-weight: 600; }}
  .status-non-testable {{ color: #95a5a6; }}

  .cell-limited {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis;
                   white-space: nowrap; cursor: help; }}
  code {{ background: #f0f0f0; padding: 2px 4px; border-radius: 3px; font-size: 0.9em; }}

  .footer {{ margin-top: 2em; padding-top: 1em; border-top: 1px solid #ddd;
             font-size: 0.85em; color: #888; }}
</style>
</head>
<body>

<h1>{title}</h1>
<p class="meta">生成时间: {now} | 来源: 知识图谱 (v2.3.0) | 总需求数: {len(rows)}</p>

<div class="stats">
  <div class="stat-card coverage">
    <div class="value">{coverage_pct}%</div>
    <div class="label">测试覆盖率</div>
  </div>
  <div class="stat-card" style="border-left-color: #2ecc71;">
    <div class="value">{covered}</div>
    <div class="label">已覆盖需求</div>
  </div>
  <div class="stat-card uncovered">
    <div class="value">{uncovered}</div>
    <div class="label">未覆盖需求</div>
  </div>
  <div class="stat-card total">
    <div class="value">{non_testable}</div>
    <div class="label">管理需求 (非测试)</div>
  </div>
</div>

<h2>详细追溯矩阵</h2>

<table>
<thead>
<tr>
  <th>需求 ID</th>
  <th>陈述</th>
  <th>覆盖状态</th>
  <th>置信度</th>
  <th>测试文件</th>
  <th>代码文件</th>
</tr>
</thead>
<tbody>
{table_rows}
</tbody>
</table>

<div class="footer">
  <p>Generated by yuleOSH Knowledge Graph Reporter | ASPICE-compatible Traceability Matrix</p>
</div>

</body>
</html>"""
    return html


def generate_rtm_csv(store: KGStore,
                     layer: Optional[str] = None) -> str:
    """Generate a CSV traceability matrix from the KG.

    Returns:
        CSV string suitable for Excel/openpyxl import.
    """
    rows = _build_rtm_rows(store, layer=layer)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Requirement ID", "Statement", "Status", "Confidence",
        "Confidence Score", "Test Count", "Test Files",
        "Test Functions", "Code Files",
    ])
    for r in rows:
        writer.writerow([
            r["req_id"],
            r["statement"],
            r["status"],
            r["confidence"],
            r["confidence_score"],
            r["test_count"],
            r["test_files"],
            r["test_functions"],
            r["code_files"],
        ])
    return output.getvalue()


def generate_rtm(store: KGStore, fmt: str = "markdown",
                 layer: Optional[str] = None,
                 title: Optional[str] = None) -> str:
    """Generate traceability matrix in the specified format.

    Args:
        store: KGStore instance.
        fmt: Output format: "markdown", "html", or "csv".
        layer: Optional test layer filter.
        title: Optional report title.

    Returns:
        Formatted string content.
    """
    fmt = fmt.lower()
    if fmt == "html":
        return generate_rtm_html(store, layer=layer, title=title)
    elif fmt == "csv":
        return generate_rtm_csv(store, layer=layer)
    else:
        return generate_rtm_markdown(store, layer=layer, title=title)


# ═══════════════════════════════════════════════════════════════════════
# 度量报告生成 (KG-METRICS)
# ═══════════════════════════════════════════════════════════════════════

def generate_metrics(store: KGStore,
                     trend_snapshots: int = 5,
                     as_text: bool = True) -> dict:
    """Generate comprehensive metrics from the KG.

    Args:
        store: KGStore instance.
        trend_snapshots: Number of recent snapshots to include in trend.

    Returns:
        Dict with metric categories: coverage, tests, graph_health, trends
    """
    stats = store.get_stats()

    # ── Coverage metrics ──────────────────────────────────────────────
    reqs = store.list_nodes("requirement", active_only=True)
    total_reqs = len(reqs)
    covered_reqs = 0
    uncovered_reqs_list = []
    non_testable_reqs = 0

    for req in reqs:
        is_testable = req.properties.get("testable", True)
        if not is_testable:
            non_testable_reqs += 1
            continue

        # Check for outgoing covers edges
        outgoing = store.get_outgoing_edges(req.id)
        has_coverage = any(e.edge_type == "covers" for e, _ in outgoing)
        if has_coverage:
            covered_reqs += 1
        else:
            uncovered_reqs_list.append({
                "req_id": req.entity_id,
                "label": req.label,
            })

    total_trackable = total_reqs - non_testable_reqs
    coverage_pct = round(covered_reqs / total_trackable * 100, 1) if total_trackable > 0 else 0

    # ── Test distribution by layer ────────────────────────────────────
    all_edges = store.list_edges(edge_type="covers")
    tests_by_layer: dict[str, dict] = {}
    tests_by_status: dict[str, int] = {}

    for layer_name in LAYER_NAMES:
        tests_by_layer[layer_name] = {"count": 0, "files": set()}

    for edge in all_edges:
        lyr = edge.properties.get("layer") or edge.layer or "_unknown"
        if lyr not in tests_by_layer:
            tests_by_layer[lyr] = {"count": 0, "files": set()}
        tests_by_layer[lyr]["count"] += 1

        # Try to get target file info
        target = store.get_node_by_id(edge.target_id)
        if target:
            if target.entity_type == "test_file":
                tests_by_layer[lyr]["files"].add(target.entity_id)
            elif target.entity_type == "test_function":
                fpath = target.properties.get("file_path", "")
                if fpath:
                    tests_by_layer[lyr]["files"].add(fpath)

    # ── Graph health ──────────────────────────────────────────────────
    orphan_code = store.get_orphan_code_files()
    orphan_test: list[str] = []

    # Explicitly check for test_file nodes with no edges
    for tn in store.list_nodes("test_file", active_only=True):
        outgoing = store.get_outgoing_edges(tn.id)
        incoming = store.get_incoming_edges(tn.id)
        if not outgoing and not incoming:
            orphan_test.append(tn.entity_id)

    # Low confidence edges
    low_conf_edges = 0
    edges_by_type: dict[str, int] = {}
    for e in all_edges:
        edges_by_type[e.edge_type] = edges_by_type.get(e.edge_type, 0) + 1
        conf = e.properties.get("confidence", 1.0)
        if isinstance(conf, (int, float)) and conf < 0.8:
            low_conf_edges += 1

    # ── Trends ────────────────────────────────────────────────────────
    snapshots = store.list_snapshots(limit=trend_snapshots)
    trends = {
        "nodes": [{"build_id": s.build_id, "count": s.node_count} for s in reversed(snapshots)],
        "edges": [{"build_id": s.build_id, "count": s.edge_count} for s in reversed(snapshots)],
    }

    result = {
        "generated_at": datetime.now().isoformat(),
        "coverage": {
            "total_requirements": total_reqs,
            "covered_requirements": covered_reqs,
            "uncovered_requirements": len(uncovered_reqs_list),
            "non_testable_requirements": non_testable_reqs,
            "coverage_percentage": coverage_pct,
        },
        "tests": {
            "by_layer": {
                ln: {
                    "aspice_process": LAYER_ASPICE.get(ln, "—"),
                    "total_covers": info["count"],
                    "total_files": len(info["files"]),
                    "files": sorted(info["files"])[:20],  # limit to 20
                }
                for ln, info in sorted(tests_by_layer.items())
                if info["count"] > 0
            },
            "by_status": tests_by_status,
        },
        "graph_health": {
            "total_nodes": stats.get("total_nodes", 0),
            "total_edges": stats.get("total_edges", 0),
            "orphan_code_files": len(orphan_code),
            "orphan_test_files": len(orphan_test),
            "low_confidence_edges": low_conf_edges,
            "edges_by_type": edges_by_type,
            "nodes_by_type": stats.get("nodes_by_type", {}),
        },
        "trends": trends,
        "uncovered_requirements": uncovered_reqs_list[:50],  # limit
    }

    return result


def format_metrics_text(metrics: dict) -> str:
    """Format metrics dict as human-readable text report."""
    now = metrics.get("generated_at", "")[:19]
    cov = metrics.get("coverage", {})
    health = metrics.get("graph_health", {})
    tests = metrics.get("tests", {})
    trends = metrics.get("trends", {})

    lines = [
        f"📊 yuleOSH 知识图谱度量报告",
        f"{'=' * 55}",
        f"生成时间: {now}",
        "",
    ]

    # Coverage
    lines.extend([
        "📋 覆盖率指标",
        f"{'─' * 55}",
        f"  总需求:           {cov.get('total_requirements', '?')}",
        f"  已覆盖:           {cov.get('covered_requirements', '?')}",
        f"  未覆盖:           {cov.get('uncovered_requirements', '?')}",
        f"  不可测试 (管理):  {cov.get('non_testable_requirements', '?')}",
        f"  覆盖率:           {cov.get('coverage_percentage', '?')}%",
        "",
    ])

    # Test distribution
    by_layer = tests.get("by_layer", {})
    if by_layer:
        lines.extend([
            "🧪 测试层分布",
            f"{'─' * 55}",
            f"  {'层':<15} {'ASPICE':<10} {'覆盖边数':<10} {'文件数':<8}",
            f"  {'─' * 50}",
        ])
        for lname, info in sorted(by_layer.items()):
            label = LAYER_NAMES.get(lname, lname)
            aspice = info.get("aspice_process", "—")
            lines.append(
                f"  {label:<15} {aspice:<10} {info['total_covers']:<10} {info['total_files']:<8}"
            )
        lines.append("")

    # Graph health
    lines.extend([
        "💚 图健康度",
        f"{'─' * 55}",
        f"  总节点:           {health.get('total_nodes', 0)}",
        f"  总边:             {health.get('total_edges', 0)}",
        f"  孤立代码文件:     {health.get('orphan_code_files', 0)}",
        f"  孤立测试文件:     {health.get('orphan_test_files', 0)}",
        f"  低置信度边:       {health.get('low_confidence_edges', 0)}",
        "",
    ])

    # Edges by type
    ebt = health.get("edges_by_type", {})
    if ebt:
        lines.append(f"  边类型分布:")
        for etype, count in sorted(ebt.items(), key=lambda x: -x[1]):
            lines.append(f"    {etype:<15} {count}")
        lines.append("")

    # Trends
    trend_nodes = trends.get("nodes", [])
    trend_edges = trends.get("edges", [])
    if len(trend_nodes) >= 2:
        lines.extend([
            "📈 趋势 (最近快照)",
            f"{'─' * 55}",
            f"  {'快照':<30} {'节点数':<10} {'边数':<10}",
            f"  {'─' * 50}",
        ])
        for i in range(min(len(trend_nodes), len(trend_edges))):
            n = trend_nodes[i]
            e = trend_edges[i]
            bid = n.get("build_id", "?").ljust(28)[:28]
            nc = str(n.get("count", "?"))
            ec = str(e.get("count", "?"))
            lines.append(f"  {bid} {nc:<10} {ec:<10}")

        # Delta
        first_nodes = trend_nodes[0].get("count", 0)
        last_nodes = trend_nodes[-1].get("count", 0)
        delta_nodes = last_nodes - first_nodes
        delta_sign = "+" if delta_nodes >= 0 else ""
        lines.append(f"  {'─' * 50}")
        lines.append(f"  节点变化: {delta_sign}{delta_nodes} | 边变化: "
                     f"{'+' if (trend_edges[-1].get('count',0)-trend_edges[0].get('count',0)) >= 0 else ''}"
                     f"{trend_edges[-1].get('count',0)-trend_edges[0].get('count',0)}")
        lines.append("")

    # Uncovered requirements
    uncovered = metrics.get("uncovered_requirements", [])
    if uncovered:
        lines.extend([
            "⚠️ 未覆盖需求",
            f"{'─' * 55}",
        ])
        for u in uncovered[:15]:
            lines.append(f"  - {u.get('req_id', '?')}: {u.get('label', '')[:60]}")
        if len(uncovered) > 15:
            lines.append(f"  ...以及 {len(uncovered) - 15} 条更多")
        lines.append("")

    lines.append(f"{'=' * 55}")
    lines.append("报告由 yuleOSH 知识图谱自动生成 (v2.3.0)")

    return "\n".join(lines)
