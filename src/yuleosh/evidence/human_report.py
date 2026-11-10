# @req SYS-REQ-004
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""人类可读证据导出（HTML / Excel / Markdown）。

分层约定
--------
* **人类阅读层**：``docs/evidence/<session>/`` 下的 .html / .xlsx / .md。
  由本模块在 pipeline 收尾时生成，供评审、归档与甲方审计直接打开。
* **机器验证层**：``.osh/sessions/<session>/*.json``、``docs/*.yaml``。
  只供确定性门禁与证据链校验，不出现在 UI 的产物列表中。

反假绿：所有内容均取自 session.steps 与 gate-summary.json 的真实状态；
门禁汇总缺失时显式写「未生成」，不臆造 passed。
"""

from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from yuleosh.pipeline.step_handlers.mgmt_support import _sha256

# 人类可读格式：UI 只展示这三类，json/yaml 留在后台。
HUMAN_EXTENSIONS = (".md", ".html", ".xlsx")

_EXCLUDE_DIRS = (
    ".osh", ".git", ".venv", "node_modules", "__pycache__",
    ".pytest_cache", "dist", "build-venv", "htmlcov", "baselines",
)
_MAX_ARTIFACTS = 300


def _load_gate_summary(session) -> dict:
    """读取本次 session 的 gate-summary.json；缺失时返回空 dict。"""
    sdir = getattr(session, "session_dir", None)
    if not sdir:
        return {}
    path = Path(sdir) / "gate-summary.json"
    if not path.is_file():
        return {}
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _human_artifacts(project_dir: Path) -> list[dict]:
    """扫描项目内的人类可读产物（排除机器证据与自带导出目录）。"""
    out: list[dict] = []
    skip = (project_dir / "docs" / "evidence").resolve()
    for dirpath, dirnames, filenames in os.walk(project_dir):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in _EXCLUDE_DIRS and (Path(dirpath) / d).resolve() != skip
        )
        for name in sorted(filenames):
            if not name.lower().endswith(HUMAN_EXTENSIONS):
                continue
            fp = Path(dirpath) / name
            try:
                size = fp.stat().st_size
            except OSError:
                continue
            out.append({
                "path": str(fp.relative_to(project_dir)),
                "size": size,
                "sha256": _sha256(fp),
            })
            if len(out) >= _MAX_ARTIFACTS:
                return out
    return out


def _gate_rows(gate_summary: dict) -> list[dict]:
    rows: list[dict] = []
    for g in gate_summary.get("gates", []) or []:
        rows.append({
            "gate": g.get("gate", ""),
            "name": g.get("name", ""),
            "status": g.get("status", ""),
            "steps": len(g.get("step_keys") or []),
            "advisory": bool(g.get("advisory", False)),
        })
    return rows


def _step_rows(session) -> list[dict]:
    rows: list[dict] = []
    for s in getattr(session, "steps", []) or []:
        output = s.get("output_path", "") or ""
        # 人类可读报告中只展示人类可读产物；机器证据统一折叠为占位说明。
        if output and Path(str(output)).suffix.lower() not in HUMAN_EXTENSIONS:
            output = "机器证据（后台）"
        rows.append({
            "step": s.get("name") or s.get("key") or "",
            "status": s.get("status", ""),
            "output": output,
            "errors": "; ".join(s.get("errors") or []),
        })
    return rows


def _summary_stats(steps: list[dict], gates: list[dict]) -> dict:
    statuses = [s["status"] for s in steps]
    gate_statuses = [g["status"] for g in gates]
    return {
        "steps": len(steps),
        "steps_completed": statuses.count("completed"),
        "steps_failed": statuses.count("failed"),
        "steps_skipped": statuses.count("skipped"),
        "gates": len(gates),
        "gates_passed": gate_statuses.count("passed"),
        "gates_failed": gate_statuses.count("failed"),
        "gates_skipped": gate_statuses.count("skipped"),
        "gates_not_run": gate_statuses.count("not-run"),
    }


def _verdict_of(session) -> dict:
    v = getattr(session, "gate_verdict", None)
    return v if isinstance(v, dict) else {}


def _render_markdown(session, stats: dict, gates: list[dict],
                     steps: list[dict], artifacts: list[dict]) -> str:
    v = _verdict_of(session)
    lines = [
        f"# 证据摘要 — {session.name}",
        "",
        f"- 会话：`{session.name}`",
        f"- 状态：{getattr(session, 'status', '')}",
        f"- 门禁结论：{v.get('outcome', '未分类')}"
        + (f"（{v.get('reason')}）" if v.get("reason") else ""),
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 统计",
        "",
        "| 维度 | 总数 | 通过 | 失败 | 跳过 | 未运行 |",
        "| --- | --- | --- | --- | --- | --- |",
        f"| 门禁 | {stats['gates']} | {stats['gates_passed']} | "
        f"{stats['gates_failed']} | {stats['gates_skipped']} | "
        f"{stats['gates_not_run']} |",
        f"| 步骤 | {stats['steps']} | {stats['steps_completed']} | "
        f"{stats['steps_failed']} | {stats['steps_skipped']} | - |",
        "",
        "## 门禁明细",
        "",
        "| 门禁 | 名称 | 状态 | 步骤数 |",
        "| --- | --- | --- | --- |",
    ]
    for g in gates:
        name = g["name"] + ("（咨询）" if g["advisory"] else "")
        lines.append(f"| {g['gate']} | {name} | {g['status']} | {g['steps']} |")
    lines += [
        "",
        "## 人类可读产物",
        "",
        "| 文件 | 大小 (bytes) |",
        "| --- | --- |",
    ]
    for a in artifacts:
        lines.append(f"| `{a['path']}` | {a['size']} |")
    lines += [
        "",
        "## 机器证据位置",
        "",
        f"- 步骤标记与门禁汇总：`.osh/sessions/{session.name}/`（JSON，供门禁校验）",
        "- 结构化登记表：`docs/*.yaml`（供人工维护与脚本读取）",
        "",
    ]
    return "\n".join(lines)


def _render_html(session, stats: dict, gates: list[dict],
                 steps: list[dict], artifacts: list[dict]) -> str:
    v = _verdict_of(session)
    outcome = html.escape(str(v.get("outcome", "未分类")))
    reason = html.escape(str(v.get("reason", "")))
    color = {"GREEN": "#10b981", "UNVERIFIED": "#f59e0b",
             "RED": "#ef4444"}.get(str(v.get("outcome", "")).upper(), "#64748b")

    def gate_rows() -> str:
        out = []
        for g in gates:
            name = html.escape(g["name"]) + ("（咨询）" if g["advisory"] else "")
            out.append(
                f"<tr><td>{html.escape(g['gate'])}</td><td>{name}</td>"
                f"<td class='st-{html.escape(g['status'])}'>{html.escape(g['status'])}</td>"
                f"<td>{g['steps']}</td></tr>"
            )
        return "\n".join(out) or "<tr><td colspan='4'>未生成门禁汇总</td></tr>"

    def step_rows() -> str:
        out = []
        for s in steps:
            out.append(
                f"<tr><td>{html.escape(s['step'])}</td>"
                f"<td class='st-{html.escape(s['status'])}'>{html.escape(s['status'])}</td>"
                f"<td><code>{html.escape(s['output'])}</code></td>"
                f"<td>{html.escape(s['errors'])}</td></tr>"
            )
        return "\n".join(out) or "<tr><td colspan='4'>无步骤记录</td></tr>"

    def artifact_rows() -> str:
        out = []
        for a in artifacts:
            out.append(
                f"<tr><td><code>{html.escape(a['path'])}</code></td>"
                f"<td>{a['size']}</td>"
                f"<td><code class='digest'>{html.escape(a['sha256'])}</code></td></tr>"
            )
        return "\n".join(out) or "<tr><td colspan='3'>无人类可读产物</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>证据摘要 — {html.escape(session.name)}</title>
<style>
  :root {{ --bg:#0a0e17; --surface:#111827; --line:#1e293b; --text:#e2e8f0; --muted:#94a3b8; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:32px; background:var(--bg); color:var(--text);
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  h1 {{ font-size:22px; margin:0 0 6px; }}
  .badge {{ display:inline-block; padding:4px 10px; border-radius:999px;
            font-size:12px; font-weight:700; color:#04121f; background:{color}; }}
  .meta {{ color:var(--muted); font-size:13px; margin-bottom:24px; }}
  section {{ background:var(--surface); border:1px solid var(--line);
             border-radius:12px; padding:18px 20px; margin-bottom:20px; }}
  h2 {{ font-size:15px; margin:0 0 14px; color:#cbd5e1; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); }}
  th {{ color:var(--muted); font-weight:600; }}
  code {{ color:#93c5fd; }}
  .digest {{ color:var(--muted); font-size:11px; }}
  .kpis {{ display:flex; gap:16px; flex-wrap:wrap; }}
  .kpi {{ background:#0f172a; border:1px solid var(--line); border-radius:10px;
          padding:12px 16px; min-width:120px; }}
  .kpi b {{ display:block; font-size:22px; margin-bottom:4px; }}
  .kpi span {{ color:var(--muted); font-size:12px; }}
  .st-passed {{ color:#10b981; }} .st-completed {{ color:#10b981; }}
  .st-failed {{ color:#ef4444; }} .st-skipped {{ color:#f59e0b; }}
  .st-not-run {{ color:#94a3b8; }} .st-stale {{ color:#f59e0b; }}
</style>
</head>
<body>
  <h1>证据摘要 — {html.escape(session.name)}</h1>
  <div class="meta">状态 {html.escape(str(getattr(session, 'status', '')))} ·
    门禁结论 <span class="badge">{outcome}</span>
    {('· ' + reason) if reason else ''} ·
    生成于 {datetime.now().isoformat(timespec='seconds')}</div>

  <section>
    <h2>统计</h2>
    <div class="kpis">
      <div class="kpi"><b>{stats['gates']}</b><span>门禁总数</span></div>
      <div class="kpi"><b>{stats['gates_passed']}</b><span>门禁通过</span></div>
      <div class="kpi"><b>{stats['gates_failed']}</b><span>门禁失败</span></div>
      <div class="kpi"><b>{stats['gates_not_run']}</b><span>门禁未运行</span></div>
      <div class="kpi"><b>{stats['steps']}</b><span>步骤总数</span></div>
      <div class="kpi"><b>{stats['steps_failed']}</b><span>步骤失败</span></div>
    </div>
  </section>

  <section>
    <h2>门禁明细</h2>
    <table><thead><tr><th>门禁</th><th>名称</th><th>状态</th><th>步骤数</th></tr></thead>
    <tbody>{gate_rows()}</tbody></table>
  </section>

  <section>
    <h2>步骤明细</h2>
    <table><thead><tr><th>步骤</th><th>状态</th><th>产物</th><th>错误</th></tr></thead>
    <tbody>{step_rows()}</tbody></table>
  </section>

  <section>
    <h2>人类可读产物</h2>
    <table><thead><tr><th>文件</th><th>大小 (bytes)</th><th>SHA256</th></tr></thead>
    <tbody>{artifact_rows()}</tbody></table>
  </section>

  <section>
    <h2>机器证据位置</h2>
    <p class="meta">以下内容仅用于门禁与证据链校验，不在 UI 中展示：<br>
      <code>.osh/sessions/{html.escape(session.name)}/</code>（步骤标记、门禁汇总）<br>
      <code>docs/*.yaml</code>（结构化登记表）</p>
  </section>
</body>
</html>
"""


def _write_excel(path: Path, session, stats: dict, gates: list[dict],
                 steps: list[dict], artifacts: list[dict]) -> bool:
    """写 Excel 证据清单；openpyxl 不可用时返回 False（不阻断收尾）。"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:  # pragma: no cover - 依赖缺失时降级
        return False

    wb = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1E293B")

    def sheet(title: str, headers: list[str], rows: list[list[Any]]):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
        for row in rows:
            ws.append(row)
        ws.freeze_panes = "A2"
        for idx, width in enumerate([28, 24, 18, 40], start=1):
            ws.column_dimensions[chr(64 + idx)].width = width
        return ws

    wb.remove(wb.active)
    v = _verdict_of(session)
    sheet("概览", ["项", "值"], [
        ["会话", session.name],
        ["状态", getattr(session, "status", "")],
        ["门禁结论", v.get("outcome", "未分类")],
        ["结论说明", v.get("reason", "")],
        ["门禁总数", stats["gates"]],
        ["门禁通过", stats["gates_passed"]],
        ["门禁失败", stats["gates_failed"]],
        ["门禁未运行", stats["gates_not_run"]],
        ["步骤总数", stats["steps"]],
        ["步骤失败", stats["steps_failed"]],
        ["生成时间", datetime.now().isoformat(timespec="seconds")],
    ])
    sheet("门禁", ["门禁", "名称", "状态", "步骤数"],
          [[g["gate"], g["name"] + ("（咨询）" if g["advisory"] else ""),
            g["status"], g["steps"]] for g in gates])
    sheet("步骤", ["步骤", "状态", "产物", "错误"],
          [[s["step"], s["status"], s["output"], s["errors"]] for s in steps])
    sheet("人类可读产物", ["文件", "大小 (bytes)", "SHA256", ""],
          [[a["path"], a["size"], a["sha256"], ""] for a in artifacts])
    wb.save(path)
    return True


def write_human_evidence(session, gate_summary: Optional[dict] = None) -> dict[str, str]:
    """生成 HTML / Excel / Markdown 三种人类可读证据。

    输出到 ``<project_dir>/docs/evidence/<session>/``，覆盖同名文件（同一
    session 重跑以最新为准）。返回实际写出的 ``{格式: 路径}``；Excel 依赖缺失
    时不含 ``excel`` 键，不抛异常。
    """
    project_dir = Path(getattr(session, "project_dir", ".") or ".").resolve()
    out_dir = project_dir / "docs" / "evidence" / str(session.name)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = gate_summary if isinstance(gate_summary, dict) else _load_gate_summary(session)
    gates = _gate_rows(summary)
    steps = _step_rows(session)
    artifacts = _human_artifacts(project_dir)
    stats = _summary_stats(steps, gates)

    written: dict[str, str] = {}
    md_path = out_dir / "evidence-summary.md"
    md_path.write_text(
        _render_markdown(session, stats, gates, steps, artifacts),
        encoding="utf-8",
    )
    written["markdown"] = str(md_path)

    html_path = out_dir / "evidence-summary.html"
    html_path.write_text(
        _render_html(session, stats, gates, steps, artifacts),
        encoding="utf-8",
    )
    written["html"] = str(html_path)

    xlsx_path = out_dir / "evidence-list.xlsx"
    if _write_excel(xlsx_path, session, stats, gates, steps, artifacts):
        written["excel"] = str(xlsx_path)

    return written


def write_bundle_evidence(
    bundle_dir: str | Path, manifest: dict[str, Any]
) -> dict[str, str]:
    """为 CL2 证据包生成 HTML / Excel / Markdown 三件套。

    与流水线证据同一分层：只渲染 ``manifest`` 中真实存在的组件与产物，
    不补造条目；``integrity.manifest_sha256`` 缺失时如实留空。

    输出至 ``bundle_dir`` 根目录，文件名固定为 ``bundle-summary.*`` 与
    ``bundle-manifest.xlsx``。返回 ``{格式: 路径}``，Excel 依赖缺失时
    不含 ``excel`` 键。
    """
    target = Path(bundle_dir)
    target.mkdir(parents=True, exist_ok=True)

    bundle = manifest.get("bundle") or {}
    components = manifest.get("components") or {}
    artifacts = manifest.get("artifacts") or []
    integrity = manifest.get("integrity") or {}
    swe_status = manifest.get("swe_status") or {}
    generated_at = str(bundle.get("generated_at")
                       or datetime.now().isoformat(timespec="seconds"))
    project_dir = str(bundle.get("project_dir") or "")
    manifest_sha = str(integrity.get("manifest_sha256") or "")

    comp_rows = [
        {
            "key": key,
            "label": str((comp or {}).get("label") or key),
            "count": len((comp or {}).get("artifacts") or []),
        }
        for key, comp in components.items()
    ]
    art_rows = [
        {
            "type": str(a.get("type") or ""),
            "dest": _rel_dest(a.get("dest"), target),
            "sha256": str(a.get("sha256") or ""),
        }
        for a in artifacts
        if isinstance(a, dict)
    ]
    swe_rows = [
        {
            "id": key,
            "name": str((val or {}).get("name") or key),
            "status": str((val or {}).get("status") or ""),
        }
        for key, val in swe_status.items()
    ]

    written: dict[str, str] = {}

    md_lines = [
        "# 证据包摘要",
        "",
        f"- 项目目录：`{project_dir or '（未记录）'}`",
        f"- 生成时间：{generated_at}",
        f"- 组件数：{len(comp_rows)}",
        f"- 产物数：{len(art_rows)}",
        f"- Manifest SHA256：`{manifest_sha or '（未生成）'}`",
        "",
        "## 组件",
        "",
        "| 组件 | 说明 | 产物数 |",
        "| --- | --- | --- |",
    ]
    md_lines += [f"| {c['key']} | {c['label']} | {c['count']} |" for c in comp_rows] or [
        "| （无组件） | - | 0 |"]
    md_lines += ["", "## 产物", "", "| 类型 | 路径 | SHA256 |", "| --- | --- | --- |"]
    md_lines += [
        f"| {a['type']} | `{a['dest']}` | `{a['sha256'][:16]}` |" for a in art_rows
    ] or ["| （无产物） | - | - |"]
    if swe_rows:
        md_lines += ["", "## 过程域状态", "", "| 过程域 | 名称 | 状态 |", "| --- | --- | --- |"]
        md_lines += [f"| {s['id']} | {s['name']} | {s['status']} |" for s in swe_rows]
    md_path = target / "bundle-summary.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    written["markdown"] = str(md_path)

    def comp_html() -> str:
        rows = "".join(
            f"<tr><td><code>{html.escape(c['key'])}</code></td>"
            f"<td>{html.escape(c['label'])}</td><td>{c['count']}</td></tr>"
            for c in comp_rows
        )
        return rows or "<tr><td colspan='3'>无组件</td></tr>"

    def art_html() -> str:
        rows = "".join(
            f"<tr><td>{html.escape(a['type'])}</td>"
            f"<td><code>{html.escape(a['dest'])}</code></td>"
            f"<td><code class='digest'>{html.escape(a['sha256'])}</code></td></tr>"
            for a in art_rows
        )
        return rows or "<tr><td colspan='3'>无产物</td></tr>"

    def swe_html() -> str:
        rows = "".join(
            f"<tr><td>{html.escape(s['id'])}</td><td>{html.escape(s['name'])}</td>"
            f"<td class='st-{html.escape(s['status'])}'>{html.escape(s['status'])}</td></tr>"
            for s in swe_rows
        )
        return rows or "<tr><td colspan='3'>未评估过程域</td></tr>"

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>证据包摘要 — CL2 Audit Bundle</title>
<style>
  :root {{ --bg:#0a0e17; --surface:#111827; --line:#1e293b; --text:#e2e8f0; --muted:#94a3b8; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:32px; background:var(--bg); color:var(--text);
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  h1 {{ font-size:22px; margin:0 0 6px; }}
  .meta {{ color:var(--muted); font-size:13px; margin-bottom:24px; }}
  section {{ background:var(--surface); border:1px solid var(--line);
             border-radius:12px; padding:18px 20px; margin-bottom:20px; }}
  h2 {{ font-size:15px; margin:0 0 14px; color:#cbd5e1; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); }}
  th {{ color:var(--muted); font-weight:600; }}
  code {{ color:#93c5fd; }}
  .digest {{ color:var(--muted); font-size:11px; }}
  .kpis {{ display:flex; gap:16px; flex-wrap:wrap; }}
  .kpi {{ background:#0f172a; border:1px solid var(--line); border-radius:10px;
          padding:12px 16px; min-width:120px; }}
  .kpi b {{ display:block; font-size:22px; margin-bottom:4px; }}
  .kpi span {{ color:var(--muted); font-size:12px; }}
  .st-completed {{ color:#10b981; }} .st-partial {{ color:#f59e0b; }}
  .st-not_started {{ color:#94a3b8; }}
</style>
</head>
<body>
  <h1>证据包摘要 — CL2 Audit Bundle</h1>
  <div class="meta">项目 {html.escape(project_dir or '（未记录）')} · 生成于 {html.escape(generated_at)}</div>
  <section>
    <h2>概览</h2>
    <div class="kpis">
      <div class="kpi"><b>{len(comp_rows)}</b><span>组件</span></div>
      <div class="kpi"><b>{len(art_rows)}</b><span>产物</span></div>
      <div class="kpi"><b>{len(swe_rows)}</b><span>过程域</span></div>
    </div>
  </section>
  <section><h2>组件</h2>
    <table><thead><tr><th>组件</th><th>说明</th><th>产物数</th></tr></thead>
    <tbody>{comp_html()}</tbody></table>
  </section>
  <section><h2>产物</h2>
    <table><thead><tr><th>类型</th><th>路径</th><th>SHA256</th></tr></thead>
    <tbody>{art_html()}</tbody></table>
  </section>
  <section><h2>过程域状态</h2>
    <table><thead><tr><th>过程域</th><th>名称</th><th>状态</th></tr></thead>
    <tbody>{swe_html()}</tbody></table>
  </section>
  <section><h2>完整性</h2>
    <p class="meta">Manifest SHA256：<code class="digest">{html.escape(manifest_sha or '（未生成）')}</code></p>
  </section>
</body>
</html>
"""
    html_path = target / "bundle-summary.html"
    html_path.write_text(html_doc, encoding="utf-8")
    written["html"] = str(html_path)

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:  # pragma: no cover - 依赖缺失时降级为两件套
        return written

    wb = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1E293B")

    def sheet(title: str, headers: list[str], rows: list[list[Any]],
              widths: list[int]):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
        for row in rows:
            ws.append(row)
        ws.freeze_panes = "A2"
        for idx, width in enumerate(widths, start=1):
            ws.column_dimensions[chr(64 + idx)].width = width
        return ws

    wb.remove(wb.active)
    sheet("概览", ["项", "值"], [
        ["项目目录", project_dir],
        ["生成时间", generated_at],
        ["组件数", len(comp_rows)],
        ["产物数", len(art_rows)],
        ["Manifest SHA256", manifest_sha],
    ], [26, 60])
    sheet("组件", ["组件", "说明", "产物数"],
          [[c["key"], c["label"], c["count"]] for c in comp_rows], [22, 34, 12])
    sheet("产物", ["类型", "路径", "SHA256"],
          [[a["type"], a["dest"], a["sha256"]] for a in art_rows], [18, 60, 70])
    sheet("过程域状态", ["过程域", "名称", "状态"],
          [[s["id"], s["name"], s["status"]] for s in swe_rows], [12, 34, 16])
    xlsx_path = target / "bundle-manifest.xlsx"
    wb.save(xlsx_path)
    written["excel"] = str(xlsx_path)
    return written


def _rel_dest(dest: Any, base: Path) -> str:
    """把 manifest 中的绝对/相对产物路径统一成相对 bundle 根的路径。"""
    if not dest:
        return ""
    try:
        return str(Path(str(dest)).resolve().relative_to(base.resolve()))
    except (ValueError, OSError):
        return str(dest)
