#!/usr/bin/env python3
"""man_check.py — MAN.5 风险登记册 + MAN.3 项目计划 校验与渲染（fail-closed，单文件）

真源：<root>/risk_registry.yaml、<root>/plan.yaml（活登记册，人填语义、机器管规则）。
视图：MAN.5_风险登记册_座椅控制器示例_V1.0.xlsx、MAN.3_项目进度计划_座椅控制器示例_V1.0.xlsx。

风险门禁：E-RISK-VOCAB（定级/状态/策略越词表）/ E-RISK-EXPOSURE（登记值≠P×I）/
  E-RISK-NO-MITIGATION（exposure≥阈值缺应对或复审日期）/ E-RISK-EXPIRED（复审逾期）
计划门禁：E-PLAN-DATE（开始>完成）/ E-MILESTONE-SLIP（里程碑逾期无实际日期）/
  E-WP-NO-CI（WBS 产出物不在配置库）/ E-CI-NO-WP（顶层文档无 WBS 认领）
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

import yaml
from openpyxl import load_workbook
from openpyxl.styles import Font

TOOLS_DIR = Path(__file__).resolve().parent
RISK_TEMPLATE = TOOLS_DIR.parent / "templates_new" / "MAN.5_风险登记册_V1.0.xlsx"
PLAN_TEMPLATE = TOOLS_DIR.parent / "templates_clean" / "MAN.3_项目进度计划_V1.0.xlsx"
RISK_OUT = "MAN.5_风险登记册_座椅控制器示例_V1.0.xlsx"
PLAN_OUT = "MAN.3_项目进度计划_座椅控制器示例_V1.0.xlsx"
DEMO_BANNER = "示例数据 · 不得作为项目证据"

P_I_RANGE = range(1, 6)
STATUSES = {"识别", "缓解中", "已关闭", "已接受"}
STRATEGIES = {"规避", "减轻", "转移", "接受"}
# E-CI-NO-WP 的覆盖范围：顶层文档类配置项（pipeline 产物与工具脚本不算计划交付物）
CI_SCOPE_SUFFIX = (".xlsx", ".docx")


def _d(v) -> date | None:
    if v in (None, "", "null"):
        return None
    return date.fromisoformat(str(v))


def check_risks(root: Path, today: date) -> list[dict]:
    reg = yaml.safe_load((root / "risk_registry.yaml").read_text(encoding="utf-8"))
    th = reg["meta"]["exposure_threshold"]
    errors, ids = [], set()
    for r in reg["risks"]:
        rid = r["id"]
        if rid in ids:
            errors.append({"rule": "E-RISK-ID", "msg": f"风险 ID 重复：{rid}"})
        ids.add(rid)
        if r["p"] not in P_I_RANGE or r["i"] not in P_I_RANGE:
            errors.append({"rule": "E-RISK-VOCAB", "msg": f"{rid} 可能性/影响须为 1-5：p={r['p']} i={r['i']}"})
        if r["status"] not in STATUSES:
            errors.append({"rule": "E-RISK-VOCAB", "msg": f"{rid} 非法状态：{r['status']}"})
        if r["strategy"] not in STRATEGIES:
            errors.append({"rule": "E-RISK-VOCAB", "msg": f"{rid} 非法处置策略：{r['strategy']}"})
        exposure = r["p"] * r["i"]
        if "exposure" in r and r["exposure"] != exposure:
            errors.append({"rule": "E-RISK-EXPOSURE",
                           "msg": f"{rid} 登记 exposure={r['exposure']} ≠ P×I={exposure}"})
        if exposure >= th and (not r.get("mitigation") or not _d(r.get("review"))):
            errors.append({"rule": "E-RISK-NO-MITIGATION",
                           "msg": f"{rid} exposure={exposure} ≥ {th}，缺应对措施或复审日期"})
        review = _d(r.get("review"))
        if review and review < today and r["status"] not in ("已关闭", "已接受"):
            errors.append({"rule": "E-RISK-EXPIRED",
                           "msg": f"{rid} 复审日期 {review} 已逾期，状态仍为「{r['status']}」"})
    return errors


def check_plan(root: Path, today: date) -> list[dict]:
    plan = yaml.safe_load((root / "plan.yaml").read_text(encoding="utf-8"))
    cm = yaml.safe_load((root / "cm_registry.yaml").read_text(encoding="utf-8"))
    cm_paths = {it["path"] for it in cm["items"]}
    errors = []
    claimed: set[str] = set()
    ids = {w["id"] for w in plan["wbs"]}
    for w in plan["wbs"]:
        s, e = _d(w.get("plan_start")), _d(w.get("plan_end"))
        if s and e and s > e:
            errors.append({"rule": "E-PLAN-DATE", "msg": f"{w['id']} 计划开始 {s} 晚于计划完成 {e}"})
        if w.get("pred") and w["pred"] not in ids:
            errors.append({"rule": "E-PLAN-PRED", "msg": f"{w['id']} 前置活动不存在：{w['pred']}"})
        for d in w.get("deliverables", []):
            claimed.add(d)
            if d not in cm_paths:
                errors.append({"rule": "E-WP-NO-CI",
                               "msg": f"{w['id']} 声明的产出物未纳入配置库：{d}"})
    for it in cm["items"]:
        p = it["path"]
        if "/" not in p and p.endswith(CI_SCOPE_SUFFIX) and p not in claimed:
            errors.append({"rule": "E-CI-NO-WP",
                           "msg": f"顶层文档无 WBS 认领：{p}（{it['id']}）"})
    for m in plan["milestones"]:
        pd, ad = _d(m["plan"]), _d(m.get("actual"))
        if pd and pd < today and ad is None:
            errors.append({"rule": "E-MILESTONE-SLIP",
                           "msg": f"{m['id']} {m['name']} 计划 {pd} 已逾期，实际完成日期为空"})
    return errors


def verify_result(root: Path, today: date | None = None) -> dict:
    today = today or date.today()
    errors = check_risks(root, today) + check_plan(root, today)
    return {"errors": errors, "passed": not errors}


def cmd_render(root: Path) -> int:
    today = date.today().isoformat()
    reg = yaml.safe_load((root / "risk_registry.yaml").read_text(encoding="utf-8"))

    out = root / RISK_OUT
    shutil.copy(RISK_TEMPLATE, out)
    wb = load_workbook(out)
    wb["封面"]["B1"] = DEMO_BANNER
    wb["封面"]["B1"].font = Font(bold=True, color="CC0000", size=14)
    ws = wb["2.风险登记册"]
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= 2:
            ws.unmerge_cells(str(rng))
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    for i, r in enumerate(reg["risks"]):
        row = i + 2
        exp = r["p"] * r["i"]
        level = "高" if exp >= 12 else ("中" if exp >= reg["meta"]["exposure_threshold"] else "低")
        vals = [r["id"], r["category"], r["desc"], r["trigger"], r["p"], r["i"],
                f"{level}（{exp}）", r["strategy"], r.get("mitigation"), r["owner"],
                r.get("plan_close"), r.get("actual_close") or "—", r["status"], r.get("linked_pr") or "—"]
        for c, v in enumerate(vals, 1):
            ws.cell(row=row, column=c, value=v)
    ws3 = wb["3.风险评审记录"]
    for rng in list(ws3.merged_cells.ranges):
        if rng.min_row >= 2:
            ws3.unmerge_cells(str(rng))
    if ws3.max_row > 1:
        ws3.delete_rows(2, ws3.max_row - 1)
    open_risks = [r for r in reg["risks"] if r["status"] in ("识别", "缓解中")]
    ws3.cell(row=2, column=1, value=today)
    ws3.cell(row=2, column=2, value="示例（门禁自动生成）")
    ws3.cell(row=2, column=3, value=len(reg["risks"]))
    ws3.cell(row=2, column=4, value=0)
    ws3.cell(row=2, column=5, value=sum(1 for r in reg["risks"] if r["status"] == "已关闭"))
    ws3.cell(row=2, column=6, value=sum(1 for r in open_risks if r["p"] * r["i"] >= 12))
    ws3.cell(row=2, column=7, value="首次登记，按复审日期滚动评审")
    ws3.cell(row=2, column=8, value=min(str(r["review"]) for r in open_risks))
    wb.save(out)

    plan = yaml.safe_load((root / "plan.yaml").read_text(encoding="utf-8"))
    out = root / PLAN_OUT
    shutil.copy(PLAN_TEMPLATE, out)
    wb = load_workbook(out)
    wb["封面"]["B1"] = DEMO_BANNER
    wb["封面"]["B1"].font = Font(bold=True, color="CC0000", size=14)
    ws = wb["进度表&估算"]
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= 2:
            ws.unmerge_cells(str(rng))
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    row = 2
    seq = 1
    for m in plan["milestones"]:
        ws.cell(row=row, column=2, value=seq); seq += 1
        ws.cell(row=row, column=3, value=f"里程碑：{m['name']}")
        ws.cell(row=row, column=4, value="里程碑")
        ws.cell(row=row, column=6, value=m["id"])
        ws.cell(row=row, column=7, value="项目经理")
        ws.cell(row=row, column=9, value=str(m["plan"]))
        ws.cell(row=row, column=11, value=str(m["actual"]) if m.get("actual") else "—")
        ws.cell(row=row, column=12, value="100%" if m.get("actual") else "0%")
        row += 1
    for w in plan["wbs"]:
        ws.cell(row=row, column=2, value=seq); seq += 1
        ws.cell(row=row, column=3, value=w["name"])
        ws.cell(row=row, column=4, value=w["category"])
        ws.cell(row=row, column=5, value=w.get("pred") or "—")
        ws.cell(row=row, column=6, value="；".join(w.get("deliverables", [])))
        ws.cell(row=row, column=7, value=w["owner"])
        ws.cell(row=row, column=8, value=str(w.get("plan_start")))
        ws.cell(row=row, column=9, value=str(w.get("plan_end")))
        ws.cell(row=row, column=10, value=str(w["actual_start"]) if w.get("actual_start") else "—")
        ws.cell(row=row, column=11, value=str(w["actual_end"]) if w.get("actual_end") else "—")
        ws.cell(row=row, column=12, value=f"{w['progress']}%")
        row += 1
    wb.save(out)
    print(f"[RENDER] {RISK_OUT}（{len(reg['risks'])} 风险）+ {PLAN_OUT}"
          f"（{len(plan['milestones'])} 里程碑 + {len(plan['wbs'])} WBS）")
    return 0


def selftest() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="man_selftest_"))
    today = date(2026, 11, 6)
    (tmp / "risk_registry.yaml").write_text(yaml.safe_dump({
        "meta": {"exposure_threshold": 6},
        "risks": [
            {"id": "R-1", "category": "技术", "desc": "x", "trigger": "t", "p": 2, "i": 5,
             "strategy": "减轻", "mitigation": None, "owner": "o", "status": "缓解中", "review": "2026-10-01"},
            {"id": "R-2", "category": "技术", "desc": "y", "trigger": "t", "p": 6, "i": 1,
             "strategy": "接受", "mitigation": "m", "owner": "o", "status": "已接受", "review": "2027-01-01"},
        ]}, allow_unicode=True), encoding="utf-8")
    errs = check_risks(tmp, today)
    rules = {e["rule"] for e in errs}
    assert "E-RISK-NO-MITIGATION" in rules and "E-RISK-EXPIRED" in rules and "E-RISK-VOCAB" in rules, rules
    (tmp / "cm_registry.yaml").write_text(yaml.safe_dump({"items": [
        {"path": "a.xlsx", "id": "CI-1"}, {"path": "orphan.xlsx", "id": "CI-2"},
        {"path": "evidence/x.md", "id": "CI-3"}]}), encoding="utf-8")
    (tmp / "plan.yaml").write_text(yaml.safe_dump({
        "milestones": [{"id": "MS-1", "name": "m", "plan": "2026-11-01", "actual": None}],
        "wbs": [{"id": "WP-1", "name": "w", "category": "ENG", "pred": "WP-9",
                 "deliverables": ["a.xlsx", "ghost.xlsx"], "owner": "o",
                 "plan_start": "2026-11-10", "plan_end": "2026-11-01"}],
    }, allow_unicode=True), encoding="utf-8")
    errs = check_plan(tmp, today)
    rules = {e["rule"] for e in errs}
    assert rules == {"E-MILESTONE-SLIP", "E-WP-NO-CI", "E-CI-NO-WP", "E-PLAN-DATE", "E-PLAN-PRED"}, rules
    print("[SELFTEST PASS] 8 组断言全部通过（风险 4 类 + 计划 5 类门禁）")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="MAN.5/MAN.3 校验与渲染（fail-closed）")
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--json", action="store_true")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--verify", action="store_true")
    g.add_argument("--render", action="store_true")
    g.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    root = args.root.resolve()
    if args.render:
        return cmd_render(root)
    result = verify_result(root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for e in result["errors"]:
            print(f"[ERROR][{e['rule']}] {e['msg']}")
        print("结论：" + ("FAIL ❌" if not result["passed"] else "PASS ✅"))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
