#!/usr/bin/env python3
"""evidence_explorer.py — 把 ASPICE 证据链生成单文件交互式 HTML（fail-closed）

数据源全部来自既有真源，不新增：
  ENG_需求追踪表 xlsx（节点 + 上下游边）、ENG_测试规范 xlsx（用例）、
  evidence_check JSON（产物↔槽位填充）、cm_registry.yaml（受控配置项）、
  gate_registry.yaml（问题/变更）、metrics.yaml + metrics_history.jsonl、
  risk_registry.yaml、plan.yaml、variant.yaml、八个校验器的实时结果。

输出 证据链总览_座椅控制器示例.html：单文件、无外部依赖、可离线打开。
  视图一 追溯链：V 模型列布局 + SVG 贝塞尔边 + 点击节点开详情抽屉
  视图二 证据库：56 个配置项按过程域分组，附问题/度量关联
  视图三 过程闭环：问题单/变更/风险/度量/里程碑
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from openpyxl import load_workbook

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from gate_sync import all_checkers  # noqa: E402

DEMO_BANNER = "示例数据 · 不得作为项目证据"
OUT_NAME = "证据链总览_座椅控制器示例.html"
TRACE_XLSX = "ENG_需求追踪表_座椅控制器示例_V1.0.xlsx"
CASES_XLSX = "ENG_测试规范_座椅控制器示例_V1.0.xlsx"

ID_RE = re.compile(r"^[A-Z][A-Za-z0-9_.\-]{2,}$")

# sheet → (列序号, 过程组, 泳道)
SHEET_MAP = {
    "涉众需求清单": (0, "STK", None),
    "系统需求清单": (1, "SYS", None),
    "系统架构元素清单": (2, "SYSARCH", None),
    "软件需求清单": (3, "SWREQ", "SW"),
    "硬件需求清单": (3, "HWREQ", "HW"),
    "软件架构元素清单": (4, "SWARCH", "SW"),
    "硬件设计元素清单": (4, "HWDES", "HW"),
    "软件详设清单": (5, "DD", None),
}
COL_TITLES = [
    ("涉众需求", "STK · 来源"),
    ("系统需求", "SYS.2"),
    ("系统架构", "SYS.3"),
    ("软 / 硬需求", "SWE.1 · HWE.1"),
    ("软 / 硬设计", "SWE.2 · HWE.2"),
    ("详细设计", "SWE.3"),
    ("系统测试用例", "ENG 测试规范"),
]
GROUP_LABEL = {
    "STK": "涉众需求", "SYS": "系统需求", "SYSARCH": "系统架构",
    "SWREQ": "软件需求", "HWREQ": "硬件需求", "SWARCH": "软件架构",
    "HWDES": "硬件设计", "DD": "详细设计", "TC": "测试用例",
}
GROUP_COLOR = {
    "STK": "#64748b", "SYS": "#2563eb", "SYSARCH": "#0ea5e9",
    "SWREQ": "#7c3aed", "SWARCH": "#7c3aed", "DD": "#6d28d9",
    "HWREQ": "#f59e0b", "HWDES": "#f59e0b", "TC": "#10b981",
}

CARD_W, CARD_H, COL_GAP, X0, Y0, YGAP, LANE_GAP = 210, 46, 250, 24, 64, 12, 22


def hdr_map(ws) -> tuple[int, dict[int, str]] | None:
    for r in range(1, 11):
        vals = [str(ws.cell(row=r, column=c).value or "").replace("\n", " ")
                for c in range(1, 13)]
        if any("上游元素" in v for v in vals) or any(v.startswith("标识") for v in vals):
            return r, {i + 1: v for i, v in enumerate(vals)}
    return None


def parse_trace(path: Path) -> tuple[list[dict], list[dict]]:
    wb = load_workbook(path, data_only=True)
    nodes, raw = [], []
    for ws in wb.worksheets:
        if ws.sheet_state != "visible" or ws.title not in SHEET_MAP:
            continue
        found = hdr_map(ws)
        if not found:
            continue
        hrow, hm = found
        col, group, lane = SHEET_MAP[ws.title]
        id_c = next((c for c, v in hm.items() if "标识" in v), 2)
        title_c = next((c for c, v in hm.items() if "标题" in v), 3)
        up_c = next((c for c, v in hm.items() if "上游" in v), None)
        down_c = next((c for c, v in hm.items() if "下游" in v), None)
        case_c = next((c for c, v in hm.items() if "测试用例" in v), None)
        for r in range(hrow + 1, ws.max_row + 1):
            nid = str(ws.cell(row=r, column=id_c).value or "").strip()
            if not ID_RE.match(nid):
                continue
            title = str(ws.cell(row=r, column=title_c).value or "").strip()
            cells = {
                "up": str(ws.cell(row=r, column=up_c).value or "") if up_c else "",
                "down": str(ws.cell(row=r, column=down_c).value or "") if down_c else "",
                "cases": str(ws.cell(row=r, column=case_c).value or "") if case_c else "",
            }
            raw.append({"id": nid, "title": title, "sheet": ws.title,
                        "col": col, "group": group, "lane": lane, **cells})
    known = {n["id"] for n in raw}
    split_re = re.compile(r"[,，;；、\s]+")

    def ids_in(text: str) -> list[str]:
        return [t for t in split_re.split(text) if t in known]

    edges: dict[tuple[str, str], str] = {}
    for n in raw:
        n["up"] = ids_in(n["up"])
        n["down"] = ids_in(n["down"])
        n["cases"] = [t for t in split_re.split(n["cases"]) if ID_RE.match(t)]
        for u in n["up"]:
            edges.setdefault((u, n["id"]), "trace")
        for d in n["down"]:
            edges.setdefault((n["id"], d), "trace")
        nodes.append(n)
    return nodes, [{"from": a, "to": b, "kind": k} for (a, b), k in edges.items()]


def parse_cases(path: Path) -> list[dict]:
    wb = load_workbook(path, data_only=True)
    out: list[dict] = []
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        found = None
        for r in range(1, 11):
            for c in range(1, 15):
                if "测试用例ID" in str(ws.cell(row=r, column=c).value or ""):
                    found = (r, c)
                    break
            if found:
                break
        if not found:
            continue
        hr, hc = found
        title_c = hc + 1
        for r in range(hr + 1, ws.max_row + 1):
            cid = str(ws.cell(row=r, column=hc).value or "").strip()
            if not ID_RE.match(cid):
                continue
            out.append({"id": cid, "title": str(ws.cell(row=r, column=title_c).value or ""),
                        "sheet": ws.title, "file": path.name})
    return out


def run_checkers(root: Path) -> list[dict]:
    results = []
    for name, cmd in all_checkers(root):
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            results.append({"name": name, "passed": False, "errors": 1,
                            "msg": "校验器未输出合法 JSON"})
            continue
        errs = data.get("errors") or []
        if name == "trace_check":
            errs = [i for i in data.get("issues", []) if str(i.get("severity", "")).upper() == "ERROR"]
        results.append({"name": name, "passed": bool(data.get("passed", not errs)),
                        "errors": len(errs)})
    return results


def layout(nodes: list[dict]) -> dict:
    max_y = Y0
    for col in range(7):
        y = Y0
        col_nodes = sorted([n for n in nodes if n["col"] == col],
                           key=lambda n: ({"SW": 0, "HW": 1}.get(n["lane"], 0), n["id"]))
        for lane in (None, "SW", "HW"):
            lane_nodes = [n for n in col_nodes if n["lane"] == lane]
            if lane == "HW" and lane_nodes:
                y += LANE_GAP
            for n in lane_nodes:
                n["x"], n["y"], n["w"], n["h"] = X0 + col * COL_GAP, y, CARD_W, CARD_H
                y += CARD_H + (YGAP if lane is None else 10)
            if lane_nodes:
                y += 10
        max_y = max(max_y, y)
    return {"width": X0 + 7 * COL_GAP, "height": max(max_y + 40, 420)}


def load_optional(path: Path, default):
    if not path.exists():
        return default
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def group_of_ci(path: str) -> tuple[str, str]:
    name = Path(path).name
    for pref, gid, label in [
        ("SYS.2_", "SYS", "SYS.2 系统需求"), ("SYS.3_", "SYSARCH", "SYS.3 系统架构"),
        ("SWE.1_", "SWREQ", "SWE.1 软件需求"), ("SWE.2_", "SWARCH", "SWE.2 软件架构"),
        ("SWE.3_", "DD", "SWE.3 软件详设"), ("HWE.1_", "HWREQ", "HWE.1 硬件需求"),
        ("HWE.2_", "HWDES", "HWE.2 硬件设计"), ("ENG_", "TEST", "ENG 追溯/测试"),
        ("SUP.1_", "SUP", "SUP.1 评审"), ("SUP.8_", "SUP", "SUP.8 配置管理"),
        ("SUP.9_", "SUP", "SUP.9 问题管理"), ("SUP.10_", "SUP", "SUP.10 变更管理"),
        ("MAN.3_", "MAN", "MAN.3 项目计划"), ("MAN.5_", "MAN", "MAN.5 风险"),
        ("横切_", "MAN", "MAN.1 度量"), ("产品配置_", "VAR", "产品配置"),
    ]:
        if name.startswith(pref):
            return gid, label
    if name.startswith("evidence"):
        return "TEST", "测试证据产物"
    if name.endswith((".yaml", ".py")):
        return "TOOL", "真源 / 工具"
    return "OTHER", "其他"


def build_data(root: Path) -> dict:
    nodes, edges = parse_trace(root / TRACE_XLSX)
    cases = parse_cases(root / CASES_XLSX)
    for tc in cases:
        nodes.append({"id": tc["id"], "title": tc["title"], "sheet": tc["sheet"],
                      "col": 6, "group": "TC", "lane": None,
                      "up": [], "down": [], "cases": [], "file": tc["file"]})
    known = {n["id"] for n in nodes}
    for n in nodes:
        for cid in list(n["cases"]):
            if cid in known:
                edges.append({"from": n["id"], "to": cid, "kind": "verify"})
    layout(nodes)
    for n in nodes:
        n["groupLabel"] = GROUP_LABEL.get(n["group"], n["group"])
        n["color"] = GROUP_COLOR.get(n["group"], "#475569")
    node_map = {n["id"]: n for n in nodes}

    # evidence：产物 ↔ 槽位
    proc = subprocess.run([sys.executable, str(TOOLS_DIR / "evidence_check.py"),
                           "--cases", CASES_XLSX, "--evidence", "evidence",
                           "--slots", "slots.yaml", "--json"],
                          cwd=root, capture_output=True, text=True)
    ev = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    for art in ev.get("artifacts", []):
        for fill in art.get("fills", []):
            parts = fill.split("::")
            if len(parts) >= 2 and parts[1] in node_map:
                node_map[parts[1]].setdefault("evidence", []).append(
                    {"path": art["path"], "verdict": art.get("verdict"), "slot": parts[-1]})

    # CI / 问题 / 变更 / 度量 / 风险 / 计划 / 变体
    cm = yaml.safe_load((root / "cm_registry.yaml").read_text(encoding="utf-8"))
    cis = []
    for it in cm["items"]:
        gid, label = group_of_ci(it["path"])
        cis.append({**it, "group": gid, "groupLabel": label,
                    "sizeKB": round(it.get("size", 0) / 1024, 1)})
    gate = load_optional(root / "gate_registry.yaml", {"problems": [], "changes": []})
    metrics_spec = (load_optional(root / "metrics.yaml", {"metrics": []}))["metrics"]
    snap = {}
    hp = root / "metrics_history.jsonl"
    if hp.exists():
        for line in hp.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            snap[r["id"]] = r
    metrics = [{**m, "value": snap.get(m["id"], {}).get("value"),
                "status": snap.get(m["id"], {}).get("status", "未采集"),
                "date": snap.get(m["id"], {}).get("date")} for m in metrics_spec]
    risk = load_optional(root / "risk_registry.yaml", {"meta": {"exposure_threshold": 6}, "risks": []})
    plans = load_optional(root / "plan.yaml", {"milestones": [], "wbs": []})
    variants = load_optional(root / "variant.yaml", {"features": [], "variants": []})

    checkers = run_checkers(root)
    return {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "banner": DEMO_BANNER,
        "health": {"passed": all(c["passed"] for c in checkers), "checkers": checkers},
        "columns": [{"title": a, "sub": b} for a, b in COL_TITLES],
        "nodes": nodes, "edges": edges,
        "evidence": {"expected": ev.get("slots_expected"), "filled": ev.get("slots_filled"),
                     "artifacts": ev.get("artifacts", [])},
        "cis": cis, "baseline": cm["baseline"],
        "problems": gate.get("problems", []), "changes": gate.get("changes", []),
        "metrics": metrics, "risks": risk["risks"],
        "riskThreshold": risk["meta"]["exposure_threshold"],
        "milestones": plans["milestones"], "wbs": plans["wbs"],
        "variants": variants,
    }


def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"),
                         default=str).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASPICE 证据链总览 · 座椅控制器示例</title>
<style>
:root{{--bg:#f6f7f9;--panel:#fff;--ink:#14181f;--muted:#6b7280;--line:#e5e7eb;
--blue:#2563eb;--green:#10b981;--red:#dc2626;--amber:#d97706;--purple:#6d28d9;}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Noto Sans CJK SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
background:var(--bg);color:var(--ink);font-size:13px}}
.demo{{background:#dc2626;color:#fff;text-align:center;padding:5px;font-weight:600;
font-size:12px;letter-spacing:.5px}}
header{{background:var(--panel);border-bottom:1px solid var(--line);padding:14px 22px;
display:flex;align-items:center;gap:18px;flex-wrap:wrap}}
h1{{font-size:17px;font-weight:700;letter-spacing:-.2px}}
h1 small{{font-weight:400;color:var(--muted);font-size:11px;margin-left:8px}}
.health{{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}}
.chip{{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:20px;
font-size:11px;background:#f1f5f9;color:var(--muted);border:1px solid var(--line)}}
.chip.ok{{background:#ecfdf5;color:#047857;border-color:#a7f3d0}}
.chip.bad{{background:#fef2f2;color:#b91c1c;border-color:#fecaca}}
.dot{{width:6px;height:6px;border-radius:50%;background:currentColor}}
.tabs{{display:flex;gap:4px;background:var(--panel);border-bottom:1px solid var(--line);
padding:0 22px}}
.tab{{padding:10px 16px;font-size:13px;cursor:pointer;color:var(--muted);
border-bottom:2px solid transparent;font-weight:500}}
.tab.on{{color:var(--ink);border-bottom-color:var(--blue);font-weight:600}}
.toolbar{{display:flex;gap:10px;align-items:center;padding:10px 22px;background:var(--panel);
border-bottom:1px solid var(--line);flex-wrap:wrap}}
input[type=search]{{width:230px;padding:7px 11px;border:1px solid var(--line);border-radius:8px;
font-size:12px;outline:none}}
input[type=search]:focus{{border-color:var(--blue)}}
.fbtn{{padding:5px 11px;border:1px solid var(--line);background:#fff;border-radius:20px;
font-size:11px;cursor:pointer;color:var(--muted)}}
.fbtn.on{{background:#eff6ff;border-color:#bfdbfe;color:var(--blue);font-weight:600}}
.legend{{margin-left:auto;display:flex;gap:12px;font-size:11px;color:var(--muted)}}
.legend i{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px}}
main{{position:relative;height:calc(100vh - 148px);overflow:auto}}
#graph{{position:relative}}
.colhead{{position:absolute;top:8px;font-weight:600;font-size:11px;color:var(--muted);
white-space:nowrap}}
.colhead b{{display:block;color:var(--ink);font-size:12px;margin-bottom:1px}}
.node{{position:absolute;background:#fff;border:1px solid var(--line);border-left:3px solid #999;
border-radius:7px;padding:6px 9px;cursor:pointer;transition:box-shadow .15s,transform .15s,
opacity .15s;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.node:hover{{box-shadow:0 4px 14px rgba(0,0,0,.12);transform:translateY(-1px);z-index:5}}
.node.dim{{opacity:.18}}
.node .nid{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10.5px;
font-weight:600;color:var(--muted);letter-spacing:.2px}}
.node .ntitle{{font-size:11.5px;line-height:1.35;margin-top:2px;display:-webkit-box;
-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden;white-space:nowrap;
text-overflow:ellipsis}}
.node .badge{{position:absolute;top:5px;right:7px;font-size:9px;padding:1px 5px;border-radius:3px;
background:#f1f5f9;color:var(--muted)}}
svg#edges{{position:absolute;top:0;left:0;pointer-events:none}}
.path{{stroke:#cbd5e1;stroke-width:1.4;fill:none;transition:opacity .15s,stroke .15s}}
.path.hi{{stroke:var(--blue);stroke-width:2.4}}
.path.dim{{opacity:.08}}
.drawer{{position:fixed;top:0;right:0;width:400px;height:100vh;background:#fff;
border-left:1px solid var(--line);box-shadow:-8px 0 30px rgba(0,0,0,.08);transform:translateX(100%);
transition:transform .22s;z-index:30;overflow-y:auto;padding:18px 20px}}
.drawer.open{{transform:translateX(0)}}
.drawer .close{{position:absolute;top:12px;right:16px;border:none;background:none;font-size:20px;
cursor:pointer;color:var(--muted)}}
.drawer h2{{font-size:14px;margin:6px 26px 2px 0;line-height:1.4}}
.drawer .sub{{font-family:ui-monospace,monospace;font-size:11px;color:var(--muted)}}
.sec{{margin-top:16px}}
.sec h3{{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);
margin-bottom:6px;font-weight:600}}
.kv{{display:grid;grid-template-columns:88px 1fr;gap:5px 8px;font-size:12px}}
.kv .k{{color:var(--muted)}}
.chip2{{display:inline-block;padding:2px 7px;margin:2px 3px 2px 0;border-radius:5px;
background:#f8fafc;border:1px solid var(--line);font-family:ui-monospace,monospace;font-size:10.5px;
cursor:pointer}}
.chip2:hover{{border-color:var(--blue);color:var(--blue)}}
.file{{font-family:ui-monospace,monospace;font-size:10.5px;color:var(--muted);word-break:break-all}}
table{{width:calc(100% - 44px);margin:14px 22px;border-collapse:collapse;background:#fff;
font-size:12px}}
th,td{{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line)}}
th{{background:#f8fafc;font-size:11px;color:var(--muted);font-weight:600;position:sticky;top:0}}
tr:hover td{{background:#fafbfc}}
.pill{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10.5px;font-weight:600}}
.pill.ok{{background:#ecfdf5;color:#047857}} .pill.bad{{background:#fef2f2;color:#b91c1c}}
.pill.info{{background:#eff6ff;color:#1d4ed8}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:14px;
padding:16px 22px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:9px;padding:14px}}
.card h3{{font-size:12px;margin-bottom:8px;display:flex;justify-content:space-between}}
.card .big{{font-size:22px;font-weight:700;letter-spacing:-.5px}}
.card .u{{font-size:11px;color:var(--muted);margin-top:2px}}
.bar{{height:4px;background:#f1f5f9;border-radius:2px;margin-top:10px;overflow:hidden}}
.bar i{{display:block;height:100%;background:var(--green)}}
.hidden{{display:none}}
@media print{{.toolbar,.tabs,.drawer{{display:none}} main{{height:auto;overflow:visible}}}}
</style>
</head>
<body>
<div class="demo">{DEMO_BANNER}</div>
<header>
  <h1>ASPICE 证据链总览<small>主驾座椅控制器（SCM）示例 · 由 pipeline 产物自动生成</small></h1>
  <div class="health" id="health"></div>
</header>
<div class="tabs">
  <div class="tab on" data-view="graph">追溯链</div>
  <div class="tab" data-view="evid">证据库</div>
  <div class="tab" data-view="proc">过程闭环</div>
</div>
<div class="toolbar" id="tools">
  <input id="q" type="search" placeholder="搜索 ID / 名称…">
  <button class="fbtn on" data-f="all">全部</button>
  <button class="fbtn" data-f="req">需求</button>
  <button class="fbtn" data-f="design">架构/设计</button>
  <button class="fbtn" data-f="tc">测试</button>
  <div class="legend" id="legend"></div>
</div>
<main>
  <div id="graph"></div>
  <div id="evid" class="hidden"></div>
  <div id="proc" class="hidden"></div>
</main>
<div class="drawer" id="drawer">
  <button class="close" id="dclose">×</button>
  <div id="dbody"></div>
</div>
<script id="DATA" type="application/json">{payload}</script>
<script>
const D = JSON.parse(document.getElementById('DATA').textContent);
const $ = s => document.querySelector(s);
const el = (t, c, h) => {{ const e = document.createElement(t); if(c) e.className=c;
  if(h!==undefined) e.innerHTML=h; return e; }};
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, m => ({{'&':'&amp;','<':'&lt;',
  '>':'&gt;','"':'&quot;'}}[m]));

/* ---------- 健康度 ---------- */
(function(){{
  const h = D.health;
  const box = $('#health');
  const b = el('span', 'chip ' + (h.passed?'ok':'bad'),
    '<i class="dot"></i>' + (h.passed?'全部门禁通过':'存在失败门禁'));
  box.appendChild(b);
  h.checkers.forEach(c => box.appendChild(el('span','chip '+(c.passed?'ok':'bad'),
    esc(c.name)+(c.errors?' · '+c.errors+' ERROR':''))));
  box.appendChild(el('span','chip','<i class="dot"></i>'+D.cis.length+' 配置项 · '+D.baseline));
  box.appendChild(el('span','chip','生成 '+esc(D.generatedAt.slice(0,16).replace('T',' '))));
}}());

/* ---------- 图 ---------- */
const NM = {{}}; D.nodes.forEach(n => NM[n.id] = n);
const G = $('#graph');
const W = Math.max(...D.nodes.map(n=>n.x+n.w)) + 30;
const H = Math.max(...D.nodes.map(n=>n.y+n.h)) + 40;
G.style.width = W+'px'; G.style.height = H+'px';

D.columns.forEach((c, i) => {{
  const h = el('div','colhead', '<b>'+esc(c.title)+'</b>'+esc(c.sub));
  h.style.left = (24 + i*250) + 'px';
  G.appendChild(h);
}});

const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
svg.id='edges'; svg.setAttribute('width',W); svg.setAttribute('height',H);
G.appendChild(svg);

const paths = [];
D.edges.forEach(e => {{
  const a = NM[e.from], b = NM[e.to];
  if(!a || !b || (a.col>=b.col && a.col===b.col)) return;
  const x1 = a.x + a.w, y1 = a.y + a.h/2, x2 = b.x, y2 = b.y + b.h/2;
  const dx = Math.max(28, (x2-x1)*0.45);
  const p = document.createElementNS('http://www.w3.org/2000/svg','path');
  p.setAttribute('d', `M${{x1}},${{y1}} C${{x1+dx}},${{y1}} ${{x2-dx}},${{y2}} ${{x2}},${{y2}}`);
  p.setAttribute('class','path');
  if(e.kind==='verify') p.style.strokeDasharray='4 3';
  p.dataset.from=e.from; p.dataset.to=e.to;
  svg.appendChild(p); paths.push(p);
}});

const cards = {{}};
D.nodes.forEach(n => {{
  const c = el('div','node');
  c.style.left=n.x+'px'; c.style.top=n.y+'px'; c.style.width=n.w+'px';
  c.style.height=n.h+'px'; c.style.borderLeftColor=n.color;
  c.dataset.id=n.id; c.dataset.group=n.group;
  c.innerHTML = '<div class="nid">'+esc(n.id)+'</div>'
    + '<div class="ntitle" title="'+esc(n.title)+'">'+esc(n.title)+'</div>'
    + '<div class="badge" style="color:'+n.color+'">'+esc(n.groupLabel)+'</div>';
  c.onmouseenter = () => focusNode(n.id);
  c.onmouseleave = resetFocus;
  c.onclick = () => openDrawer(n.id);
  G.appendChild(c); cards[n.id]=c;
}});

function focusNode(id){{
  const nb = new Set([id]);
  D.edges.forEach(e => {{ if(e.from===id) nb.add(e.to); if(e.to===id) nb.add(e.from); }});
  Object.entries(cards).forEach(([k,c]) => c.classList.toggle('dim', !nb.has(k)));
  paths.forEach(p => {{
    const on = p.dataset.from===id || p.dataset.to===id;
    p.classList.toggle('hi', on); p.classList.toggle('dim', !on);
  }});
}}
function resetFocus(){{
  Object.values(cards).forEach(c => c.classList.remove('dim'));
  paths.forEach(p => p.classList.remove('hi','dim'));
}}

/* ---------- 详情抽屉 ---------- */
function openDrawer(id){{
  const n = NM[id]; if(!n) return;
  const up = n.up||[], down = n.down||[];
  const ci = D.cis.find(c => c.path === n.file || c.path.includes(id));
  const relPr = D.problems.filter(p => (p.summary||'').includes(id) ||
    (p.source||'').includes(id)).slice(0,6);
  const ev = D.evidence.artifacts.filter(a => a.fills.some(f => f.split('::')[1]===id));
  let h = '<h2>'+esc(n.title||n.id)+'</h2><div class="sub">'+esc(n.id)+'</div>';
  h += '<div class="sec"><h3>来源位置</h3><div class="kv">'
    + '<div class="k">过程</div><div>'+esc(n.groupLabel)+'</div>'
    + '<div class="k">文档</div><div class="file">'+esc(n.file||'ENG_需求追踪表_座椅控制器示例_V1.0.xlsx')+'</div>'
    + '<div class="k">工作表</div><div>'+esc(n.sheet||'')+'</div></div></div>';
  if(n.extra) h += '<div class="sec"><h3>属性</h3><div class="kv">'
    + Object.entries(n.extra).map(([k,v])=>'<div class="k">'+esc(k)+'</div><div>'+esc(v)+'</div>').join('')
    + '</div></div>';
  const linkList = (title, arr, dir) => {{
    if(!arr.length) return '';
    return '<div class="sec"><h3>'+title+'（'+arr.length+'）</h3>'
      + arr.map(x => '<span class="chip2" data-go="'+esc(x)+'">'+dir+' '+esc(x)+'</span>').join('')
      + '</div>';
  }};
  h += linkList('上游', up, '↑') + linkList('下游', down, '↓');
  if(ev.length) h += '<div class="sec"><h3>测试证据产物</h3>'
    + ev.map(a => '<div class="file">'+esc(a.path)+' · '+(a.verdict||'')+'</div>').join('') + '</div>';
  if(ci) h += '<div class="sec"><h3>配置项</h3><div class="kv">'
    + '<div class="k">CI</div><div>'+esc(ci.id)+'</div>'
    + '<div class="k">管理</div><div>'+esc(ci.management)+'</div>'
    + '<div class="k">基线</div><div>'+esc(ci.baseline)+'</div>'
    + '<div class="k">sha256</div><div class="file">'+esc(ci.sha256.slice(0,20))+'…</div></div></div>';
  if(relPr.length) h += '<div class="sec"><h3>关联问题单</h3>'
    + relPr.map(p => '<div class="file">'+esc(p.id)+' · '+esc(p.status)+' · '+esc(p.rule)
    + '<br>'+esc((p.summary||'').slice(0,90))+'</div>').join('') + '</div>';
  $('#dbody').innerHTML = h;
  $('#dbody').querySelectorAll('[data-go]').forEach(b =>
    b.onclick = () => openDrawer(b.dataset.go));
  $('#drawer').classList.add('open');
}}
$('#dclose').onclick = () => $('#drawer').classList.remove('open');

/* ---------- 过滤 ---------- */
const reqGroups = ['STK','SYS','SYSARCH','SWREQ','HWREQ'];
const desGroups = ['SWARCH','HWDES','DD'];
let filter='all', query='';
function applyFilter(){{
  Object.entries(cards).forEach(([id,c]) => {{
    const n = NM[id];
    let ok = filter==='all' || (filter==='req'&&reqGroups.includes(n.group))
      || (filter==='design'&&desGroups.includes(n.group))
      || (filter==='tc'&&n.group==='TC');
    if(ok && query) ok = (n.id+' '+(n.title||'')).toLowerCase().includes(query);
    c.classList.toggle('hidden', !ok);
  }});
  paths.forEach(p => {{
    const a=cards[p.dataset.from], b=cards[p.dataset.to];
    p.style.display = (a&&b&&!a.classList.contains('hidden')&&!b.classList.contains('hidden'))
      ? '' : 'none';
  }});
}}
$('#q').oninput = e => {{ query = e.target.value.trim().toLowerCase(); applyFilter(); }};
document.querySelectorAll('.fbtn').forEach(b => b.onclick = () => {{
  document.querySelectorAll('.fbtn').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); filter=b.dataset.f; applyFilter();
}});

/* ---------- 图例 ---------- */
(function(){{
  const seen = {{}};
  D.nodes.forEach(n => {{ if(!seen[n.group]) {{ seen[n.group]=1;
    const s = el('span','','<i style="background:'+n.color+'"></i>'+esc(n.groupLabel));
    $('#legend').appendChild(s); }} }});
}}());

/* ---------- 证据库 ---------- */
(function(){{
  const box = $('#evid');
  const hdr = el('div','grid');
  const stat = [['配置项', D.cis.length, D.baseline],
    ['证据槽位', (D.evidence.filled||0)+' / '+(D.evidence.expected||0), '产物闭合'],
    ['测试产物', D.evidence.artifacts.length, 'evidence/*.md'],
    ['打开问题', D.problems.filter(p=>p.status==='打开').length, 'SUP.9']];
  stat.forEach(([k,v,u]) => {{
    const c = el('div','card');
    c.innerHTML = '<h3>'+k+'</h3><div class="big">'+v+'</div><div class="u">'+u+'</div>';
    hdr.appendChild(c);
  }});
  box.appendChild(hdr);
  const groups = {{}};
  D.cis.forEach(c => (groups[c.groupLabel] = groups[c.groupLabel] || []).push(c));
  Object.entries(groups).forEach(([label, list]) => {{
    const t = el('table');
    t.innerHTML = '<thead><tr><th style="width:90px">CI</th><th>工作产品</th>'
      + '<th style="width:80px">管理方式</th><th style="width:70px">基线</th>'
      + '<th style="width:60px">大小</th></tr></thead><tbody>'
      + list.map(c => '<tr><td><span class="pill info">'+esc(c.id)+'</span></td>'
        + '<td><a href="'+encodeURI(c.path)+'" target="_blank" style="color:var(--ink);'
        + 'text-decoration:none">'+esc(c.path)+'</a></td>'
        + '<td>'+esc(c.management)+'</td><td>'+esc(c.baseline)+'</td>'
        + '<td>'+esc(c.sizeKB)+'kB</td></tr>').join('')
      + '</tbody>';
    const cap = el('div','', '<h3 style="margin:16px 22px 0;font-size:12px;color:var(--muted)">'
      + esc(label)+' · '+list.length+' 项</h3>');
    box.appendChild(cap); box.appendChild(t);
  }});
}}());

/* ---------- 过程闭环 ---------- */
(function(){{
  const box = $('#proc');
  const cardsWrap = el('div','grid');
  const openPr = D.problems.filter(p=>p.status==='打开').length;
  const cr = D.changes.length;
  const riskOpen = D.risks.filter(r=>r.status==='识别'||r.status==='缓解中').length;
  const mPass = D.metrics.filter(m=>m.status==='PASS'||m.status==='INFO').length;
  [['打开问题', openPr, 'SUP.9 · 共 '+D.problems.length+' 条历史'],
   ['变更请求', cr, 'SUP.10 · 自动登记'],
   ['开放风险', riskOpen, 'MAN.5 · 共 '+D.risks.length+' 项'],
   ['度量达标', mPass+' / '+D.metrics.length, 'MAN.1 · 最近一次采集']].forEach(([k,v,u]) => {{
    const c = el('div','card');
    c.innerHTML = '<h3>'+k+'</h3><div class="big">'+v+'</div><div class="u">'+u+'</div>'
      + '<div class="bar"><i style="width:'+(k==='度量达标'&&D.metrics.length?
        (mPass/D.metrics.length*100):60)+'%"></i></div>';
    cardsWrap.appendChild(c);
  }});
  box.appendChild(cardsWrap);

  const mkTable = (title, head, rows) => {{
    const cap = el('div','', '<h3 style="margin:18px 22px 0;font-size:12px;color:var(--muted)">'
      + title+'</h3>');
    const t = el('table');
    t.innerHTML = '<thead><tr>'+head.map(h=>'<th>'+h+'</th>').join('')+'</tr></thead><tbody>'
      + rows+'</tbody>';
    box.appendChild(cap); box.appendChild(t);
  }};
  mkTable('问题单（SUP.9）', ['ID','状态','来源','规则','摘要'],
    D.problems.slice(-14).reverse().map(p=>'<tr><td><span class="pill info">'+esc(p.id)
      +'</span></td><td><span class="pill '+(p.status==='打开'?'bad':'ok')+'">'+esc(p.status)
      +'</span></td><td>'+esc(p.source)+'</td><td class="file">'+esc(p.rule)+'</td><td>'
      +esc((p.summary||'').slice(0,80))+'</td></tr>').join(''));
  mkTable('风险登记册（MAN.5）', ['ID','分类','描述','P×I','策略','状态','复审'],
    D.risks.map(r=>{{ const e=r.p*r.i; return '<tr><td><span class="pill info">'+esc(r.id)
      +'</span></td><td>'+esc(r.category)+'</td><td>'+esc(r.desc.slice(0,50))+'</td><td><b>'
      +e+'</b></td><td>'+esc(r.strategy)+'</td><td>'+esc(r.status)+'</td><td class="file">'
      +esc(r.review)+'</td></tr>'; }}).join(''));
  mkTable('度量（MAN.1）', ['ID','度量项','当前值','目标','状态','采集日'],
    D.metrics.map(m=>'<tr><td><span class="pill info">'+esc(m.id)+'</span></td><td>'
      +esc(m.name)+'</td><td><b>'+esc(m.value==null?'—':
        (typeof m.value==='number'?Math.round(m.value*1000)/1000:m.value))+'</b></td><td>'
      +esc(m.target_text)+'</td><td><span class="pill '+(m.status==='FAIL'?'bad':'ok')+'">'
      +esc(m.status)+'</span></td><td class="file">'+esc(m.date||'—')+'</td></tr>').join(''));
  mkTable('计划（MAN.3）', ['ID','活动','类别','计划完成','实际完成','进度'],
    D.milestones.map(m=>'<tr><td><span class="pill info">'+esc(m.id)+'</span></td><td>'
      +esc(m.name)+'</td><td>里程碑</td><td class="file">'+esc(m.plan)+'</td><td class="file">'
      +esc(m.actual||'—')+'</td><td>'+(m.actual?'100%':'0%')+'</td></tr>').join('')
    + D.wbs.map(w=>'<tr><td><span class="pill info">'+esc(w.id)+'</span></td><td>'+esc(w.name)
      +'</td><td>'+esc(w.category)+'</td><td class="file">'+esc(w.plan_end)+'</td><td class="file">'
      +esc(w.actual_end||'—')+'</td><td>'+w.progress+'%</td></tr>').join(''));
  mkTable('产品配置（变体覆盖）', ['变体','名称','特性数','承接需求'],
    (D.variants.variants.length ? D.variants.variants.map(v=>{{ const f=D.variants.features.filter(x=>v.features.includes(x.id));
      const reqs=new Set(f.flatMap(x=>x.reqs)); return '<tr><td><span class="pill info">'+esc(v.id)
      +'</span></td><td>'+esc(v.name)+'</td><td>'+f.length+'</td><td>'+reqs.size+'</td></tr>'; }})
      .join('') : '<tr><td colspan="4" style="color:var(--muted)">本示例暂无产品配置真源</td></tr>'));
}}());

/* ---------- 视图切换 ---------- */
document.querySelectorAll('.tab').forEach(t => t.onclick = () => {{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
  t.classList.add('on');
  ['graph','evid','proc'].forEach(v => $('#'+v).classList.toggle('hidden', v!==t.dataset.view));
  $('#tools').classList.toggle('hidden', t.dataset.view!=='graph');
}});
</script>
</body>
</html>"""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="ASPICE 证据链 HTML 总览生成器")
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args(argv)
    root = args.root.resolve()
    data = build_data(root)
    html = render_html(data)
    out = root / OUT_NAME
    out.write_text(html, encoding="utf-8")
    print(f"[RENDER] {OUT_NAME}：{len(data['nodes'])} 节点 / {len(data['edges'])} 边 / "
          f"{len(data['cis'])} 配置项 / {len(data['problems'])} 问题 / "
          f"{out.stat().st_size // 1024} KB · 门禁{'通过' if data['health']['passed'] else '失败'}")
    return 0 if data["health"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
