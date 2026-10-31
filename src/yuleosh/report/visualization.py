# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Self-contained SVG chart generators for ASPICE audit visualisation (P6).

Produces pure SVG (no matplotlib / plotly / CDN) so the generated
dashboard is a single self-contained HTML file — suitable for offline
audit delivery.

Charts:
  * :func:`coverage_bar`        — evidence-coverage % per process domain
  * :func:`bp_pass_donut`       — overall base-practice pass rate (donut)
  * :func:`score_distribution`  — count of domains per E1/E2/E3/NI grade
  * :func:`gap_heatmap`         — failed/missing-evidence gaps per domain
  * :func:`render_dashboard`    — full HTML page assembling all charts

E1–E3 are **evidence-coverage grades**, not ASPICE capability levels —
the disclaimer is injected into every dashboard.
"""

from __future__ import annotations

import html
from typing import Iterable, Optional

# Score → colour (matches audit_report.py legend).
SCORE_COLOR = {"E3": "#22c55e", "E2": "#eab308", "E1": "#f97316", "NI": "#ef4444"}

DISCLAIMER = (
    "E1–E3 仅为证据覆盖度分级，由通过状态证据的占比计算得出，"
    "<strong>不是 Automotive SPICE 能力等级（Capability Level）</strong>，"
    "也不构成任何正式的 ASPICE 评估结论。"
)


def coverage_bar(domains: list[dict], width: int = 760, bar_h: int = 28) -> str:
    """Horizontal bar chart of evidence-coverage % per process domain.

    Each domain is a dict with keys: ``id``, ``title``, ``coverage_pct``,
    ``score``.  Returns an SVG string.
    """
    if not domains:
        return ""
    margin = {"l": 90, "r": 80, "t": 10, "b": 10}
    inner_w = width - margin["l"] - margin["r"]
    row_h = bar_h + 6
    height = margin["t"] + margin["b"] + row_h * len(domains)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'style="font-family:sans-serif;font-size:12px;">',
        f'<line x1="{margin["l"]}" y1="{margin["t"]}" '
        f'x2="{margin["l"]}" y2="{height - margin["b"]}" '
        f'stroke="#d1d5db" stroke-width="1"/>',
    ]
    for i, d in enumerate(domains):
        y = margin["t"] + i * row_h
        pct = max(0.0, min(100.0, float(d.get("coverage_pct", 0) or 0)))
        bar_w = (pct / 100.0) * inner_w
        color = SCORE_COLOR.get(d.get("score", "NI"), "#6b7280")
        label = f'{d.get("id", "")}'
        parts.append(
            f'<text x="{margin["l"] - 8}" y="{y + bar_h / 2 + 4}" '
            f'text-anchor="end" fill="#374151">{html.escape(label)}</text>'
        )
        # Track
        parts.append(
            f'<rect x="{margin["l"]}" y="{y}" width="{inner_w}" '
            f'height="{bar_h}" rx="4" fill="#f3f4f6"/>'
        )
        # Fill
        parts.append(
            f'<rect x="{margin["l"]}" y="{y}" width="{bar_w:.1f}" '
            f'height="{bar_h}" rx="4" fill="{color}"/>'
        )
        # Value label
        parts.append(
            f'<text x="{margin["l"] + inner_w + 8}" y="{y + bar_h / 2 + 4}" '
            f'fill="#1f2937">{pct:.0f}% ({d.get("score","NI")})</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def bp_pass_donut(passed: int, total: int, size: int = 200) -> str:
    """Donut chart of overall base-practice pass rate.

    Returns an SVG string (or empty if total <= 0).
    """
    if total <= 0:
        return ""
    import math

    cx = cy = size / 2
    r = size / 2 - 16
    rate = passed / total
    # Angle for the pass arc (start at top, clockwise).
    start_angle = -math.pi / 2
    end_angle = start_angle + 2 * math.pi * rate
    large = 1 if rate > 0.5 else 0

    def polar(angle):
        return cx + r * math.cos(angle), cy + r * math.sin(angle)

    x1, y1 = polar(start_angle)
    x2, y2 = polar(end_angle)
    pass_color = "#22c55e"
    bg_color = "#e5e7eb"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" '
        f'height="{size}" viewBox="0 0 {size} {size}">',
        # Background ring
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
        f'stroke="{bg_color}" stroke-width="18"/>',
    ]
    if rate > 0:
        parts.append(
            f'<path d="M {x1:.2f} {y1:.2f} A {r} {r} 0 {large} 1 '
            f'{x2:.2f} {y2:.2f}" fill="none" stroke="{pass_color}" '
            f'stroke-width="18" stroke-linecap="round"/>'
        )
    pct = rate * 100
    parts.append(
        f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" '
        f'font-size="30" font-weight="bold" fill="#1f2937">'
        f'{pct:.0f}%</text>'
    )
    parts.append(
        f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" '
        f'font-size="11" fill="#6b7280">BP pass rate</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def score_distribution(scores: Iterable[str], width: int = 320, height: int = 180) -> str:
    """Vertical bar chart: count of domains per evidence-coverage grade."""
    counts = {"E3": 0, "E2": 0, "E1": 0, "NI": 0}
    for s in scores:
        if s in counts:
            counts[s] += 1
    max_v = max(counts.values()) or 1
    margin = {"l": 30, "r": 10, "t": 15, "b": 30}
    inner_w = width - margin["l"] - margin["r"]
    inner_h = height - margin["t"] - margin["b"]
    slot = inner_w / 4
    bar_w = slot * 0.6
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'style="font-family:sans-serif;font-size:12px;">',
    ]
    for i, (grade, cnt) in enumerate(counts.items()):
        x = margin["l"] + i * slot + (slot - bar_w) / 2
        bar_h = (cnt / max_v) * inner_h
        y = margin["t"] + inner_h - bar_h
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{bar_h:.1f}" rx="3" fill="{SCORE_COLOR[grade]}"/>'
        )
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 4:.1f}" '
            f'text-anchor="middle" fill="#1f2937" font-weight="bold">{cnt}</text>'
        )
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{height - 12}" '
            f'text-anchor="middle" fill="#374151">{grade}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def gap_heatmap(domains: list[dict], width: int = 760) -> str:
    """Per-domain gap breakdown: failed evidence + missing evidence counts.

    Each domain dict should include ``gap_count`` and optionally
    ``failed_count`` / ``missing_count``.  Returns an SVG string.
    """
    if not domains:
        return ""
    margin = {"l": 90, "r": 20, "t": 10, "b": 10}
    bar_h = 18
    row_h = bar_h + 6
    inner_w = width - margin["l"] - margin["r"]
    height = margin["t"] + margin["b"] + row_h * len(domains)
    max_gap = max((int(d.get("gap_count", 0) or 0) for d in domains), default=1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'style="font-family:sans-serif;font-size:12px;">',
    ]
    for i, d in enumerate(domains):
        y = margin["t"] + i * row_h
        gaps = int(d.get("gap_count", 0) or 0)
        w = (gaps / max_gap) * inner_w if max_gap else 0
        color = "#ef4444" if gaps else "#22c55e"
        parts.append(
            f'<text x="{margin["l"] - 8}" y="{y + bar_h / 2 + 4}" '
            f'text-anchor="end" fill="#374151">{html.escape(d.get("id",""))}</text>'
        )
        parts.append(
            f'<rect x="{margin["l"]}" y="{y}" width="{inner_w}" '
            f'height="{bar_h}" rx="3" fill="#f3f4f6"/>'
        )
        if w:
            parts.append(
                f'<rect x="{margin["l"]}" y="{y}" width="{w:.1f}" '
                f'height="{bar_h}" rx="3" fill="{color}"/>'
            )
        parts.append(
            f'<text x="{margin["l"] + inner_w + 8}" y="{y + bar_h / 2 + 4}" '
            f'fill="#1f2937">{gaps} gap{"s" if gaps != 1 else ""}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def workflow_status_html(workflow: Optional[dict]) -> str:
    """Render the SUP.1 / SUP.9 / MAN.3 workflow-status section.

    ``workflow`` is a dict with optional keys ``qa``, ``issues``, ``risks``,
    ``milestones``; each value is a dict of counts.  Returns an empty
    string when no workflow data is supplied (fail-closed: no empty
    section implying "all good").
    """
    if not workflow:
        return ""

    qa = workflow.get("qa") or {}
    iss = workflow.get("issues") or {}
    rsk = workflow.get("risks") or {}
    ms = workflow.get("milestones") or {}

    rows = [
        ("SUP.1 QA audits",
         f"total {qa.get('total', 0)} · open {qa.get('open', 0)}"),
        ("SUP.9 Issues",
         f"total {iss.get('total', 0)} · open {iss.get('open', 0)}"),
        ("MAN.3 Risks",
         f"total {rsk.get('total', 0)} · open {rsk.get('open', 0)}"
         f" · critical {rsk.get('critical', 0)}"),
        ("MAN.3 Milestones",
         f"completed {ms.get('completed', 0)} / {ms.get('total', 0)}"),
    ]
    body = "".join(
        f'<tr><td><strong>{html.escape(name)}</strong></td>'
        f'<td>{html.escape(detail)}</td></tr>'
        for name, detail in rows
    )
    return f"""
<div class="card">
  <h2>Workflow Status (SUP.1 / SUP.9 / MAN.3)</h2>
  <table>
    <thead><tr><th>Workflow</th><th>Status</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
  <p style="color:#6b7280;font-size:0.85em;margin-bottom:0;">
    以上为过程工作流的记录数量，不代表过程能力等级；证据覆盖度见上方图表。
  </p>
</div>
"""


def render_dashboard(
    project_name: str,
    version: str,
    generated_at: str,
    overall_score: str,
    overall_coverage_pct: float,
    domains: list[dict],
    bp_passed: int = 0,
    bp_total: int = 0,
    extra_html: str = "",
    workflow: Optional[dict] = None,
) -> str:
    """Render a self-contained HTML dashboard with all visualisations.

    ``domains`` is a list of dicts: ``{id, title, score, coverage_pct,
    evidence_count, gap_count}``.  ``workflow`` optionally carries the
    SUP.1/SUP.9/MAN.3 counts rendered as an extra status card.
    """
    cov_svg = coverage_bar(domains)
    donut_svg = bp_pass_donut(bp_passed, bp_total)
    dist_svg = score_distribution(d.get("score") for d in domains)
    gap_svg = gap_heatmap(domains)
    workflow_html = workflow_status_html(workflow)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>ASPICE Audit Dashboard — {html.escape(project_name)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          max-width: 1100px; margin: 2em auto; padding: 0 1em; color: #1f2937; background: #f8fafc; }}
  h1, h2, h3 {{ color: #111827; }}
  .meta {{ color: #6b7280; font-size: 0.9em; }}
  .card {{ background: white; border-radius: 8px; padding: 1.5em; margin: 1em 0;
           box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .grid {{ display: flex; flex-wrap: wrap; gap: 1em; }}
  .grid > .card {{ flex: 1 1 300px; }}
  .overall {{ font-size: 3em; font-weight: bold; text-align: center; }}
  .disclaimer {{ border-left: 4px solid #f97316; background: #fff7ed;
                 padding: 1em 1.5em; margin: 1em 0; border-radius: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1em 0; background: white;
           box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: 0.75em 1em; text-align: left; border-bottom: 1px solid #e5e7eb; }}
  th {{ background: #374151; color: white; font-weight: 600; }}
</style>
</head>
<body>

<h1>🔍 ASPICE Audit Dashboard</h1>
<div class="meta">
  <p><strong>Project:</strong> {html.escape(project_name)} | <strong>Version:</strong> {html.escape(version)}</p>
  <p><strong>Generated:</strong> {html.escape(generated_at)}</p>
</div>

<div class="grid">
  <div class="card">
    <div class="overall" style="color:{SCORE_COLOR.get(overall_score, '#6b7280')};">{html.escape(overall_score)}</div>
    <p style="text-align:center; color:#6b7280;">Evidence Coverage (overall {overall_coverage_pct:.0f}%)</p>
  </div>
  <div class="card" style="display:flex; align-items:center; justify-content:center;">
    {donut_svg}
  </div>
  <div class="card" style="display:flex; align-items:center; justify-content:center;">
    {dist_svg}
  </div>
</div>

<div class="card">
  <h2>Process Domain Coverage</h2>
  {cov_svg}
</div>

<div class="card">
  <h2>Gap Distribution by Domain</h2>
  {gap_svg}
</div>

<div class="card">
  <h2>Domain Detail</h2>
  <table>
    <thead><tr><th>Process</th><th>Title</th><th>Score</th><th>Coverage</th>
      <th>Evidence</th><th>Gaps</th></tr></thead>
    <tbody>
      {''.join(
        f'<tr><td><strong>{html.escape(d.get("id",""))}</strong></td>'
        f'<td>{html.escape(d.get("title",""))}</td>'
        f'<td style="color:{SCORE_COLOR.get(d.get("score","NI"),"#6b7280")}; font-weight:bold;">'
        f'{html.escape(d.get("score","NI"))}</td>'
        f'<td>{float(d.get("coverage_pct",0) or 0):.0f}%</td>'
        f'<td>{int(d.get("evidence_count",0) or 0)}</td>'
        f'<td>{int(d.get("gap_count",0) or 0)}</td></tr>'
        for d in domains
      )}
    </tbody>
  </table>
</div>

{workflow_html}

{extra_html}

<div class="disclaimer">
  <strong>⚠️ 重要说明（非 ASPICE 能力等级）：</strong>{DISCLAIMER}
  如需正式评估，请咨询经认可的评估机构。
</div>

</body>
</html>"""
