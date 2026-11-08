#!/usr/bin/env python3
"""variant_check.py — 产品配置（变体 ↔ 特性 ↔ 系统需求）校验与渲染

真源：<root>/variant.yaml；需求 ID 权威源：SYS.2 文档扫描（不信任映射表自述）。
视图：产品配置_变体需求矩阵_座椅控制器示例_V1.0.xlsx

门禁（fail-closed）：
  E-VAR-DUP         特性/变体 ID 重复
  E-VAR-FEATURE     变体引用了未定义特性
  E-VAR-REQ         特性映射的需求在 SYS.2 不存在
  E-VAR-ORPHAN-REQ  SYS.2 需求未被任何特性承接（存在即须归属至少一个产品配置）
  E-VAR-EMPTY       变体无特性 / 特性无需求
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
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

TOOLS_DIR = Path(__file__).resolve().parent
SYS_XLSX = "SYS.2_系统需求规格说明书_座椅控制器示例_V1.0.xlsx"
OUT = "产品配置_变体需求矩阵_座椅控制器示例_V1.0.xlsx"
DEMO_BANNER = "示例数据 · 不得作为项目证据"

THIN = Side(style="thin", color="D0D5DD")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(bold=True, color="FFFFFF", size=10)
BODY = Font(size=10)


def sys_requirement_ids(path: Path) -> set[str]:
    """从 SYS.2 扫描 SYS-SEAT-xxx 并去重；文档结构不受映射表影响。"""
    wb = load_workbook(path, data_only=True)
    ids: set[str] = set()
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        for row in ws.iter_rows():
            for c in row:
                v = str(c.value or "").strip()
                if v.startswith("SYS-SEAT-") and len(v) <= 20:
                    ids.add(v)
    return ids


def check(root: Path) -> list[dict]:
    data = yaml.safe_load((root / "variant.yaml").read_text(encoding="utf-8"))
    sys_ids = sys_requirement_ids(root / SYS_XLSX)
    features = data.get("features") or []
    variants = data.get("variants") or []
    errors: list[dict] = []
    fids, vids = set(), set()
    for f in features:
        if f["id"] in fids:
            errors.append({"rule": "E-VAR-DUP", "msg": f"特性 ID 重复：{f['id']}"})
        fids.add(f["id"])
        reqs = f.get("reqs") or []
        if not reqs:
            errors.append({"rule": "E-VAR-EMPTY", "msg": f"特性无需求：{f['id']}"})
        for r in reqs:
            if r not in sys_ids:
                errors.append({"rule": "E-VAR-REQ",
                               "msg": f"特性 {f['id']} 映射的需求在 SYS.2 不存在：{r}"})
    covered: set[str] = set()
    for v in variants:
        if v["id"] in vids:
            errors.append({"rule": "E-VAR-DUP", "msg": f"变体 ID 重复：{v['id']}"})
        vids.add(v["id"])
        fs = v.get("features") or []
        if not fs:
            errors.append({"rule": "E-VAR-EMPTY", "msg": f"变体无特性：{v['id']}"})
        by_id = {f["id"]: f for f in features}
        for fid in fs:
            if fid not in by_id:
                errors.append({"rule": "E-VAR-FEATURE",
                               "msg": f"变体 {v['id']} 引用未定义特性：{fid}"})
                continue
            covered.update(by_id[fid].get("reqs") or [])
    for r in sorted(sys_ids - covered):
        errors.append({"rule": "E-VAR-ORPHAN-REQ",
                       "msg": f"SYS 需求无任何变体承接：{r}（存在即须属于至少一个产品配置）"})
    return errors


def _style_header(ws, row: int, cols: int) -> None:
    for c in range(1, cols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[row].height = 30


def render(root: Path, errors: list[dict]) -> None:
    data = yaml.safe_load((root / "variant.yaml").read_text(encoding="utf-8"))
    features, variants = data["features"], data["variants"]
    sys_ids = sorted(sys_requirement_ids(root / SYS_XLSX))
    by_id = {f["id"]: f for f in features}

    wb = Workbook()
    # 0.示例声明
    ws = wb.active
    ws.title = "0.示例声明"
    ws["B2"] = DEMO_BANNER
    ws["B2"].font = Font(bold=True, color="CC0000", size=14)
    ws["B3"] = "产品配置矩阵为 pipeline 产物渲染视图；真源 variant.yaml，示例数据不得作为项目证据。"
    ws["B3"].font = Font(size=10, color="555555")
    ws.column_dimensions["B"].width = 90

    # 1.变体清单
    ws = wb.create_sheet("1.变体清单")
    heads = ["变体ID", "名称", "说明", "包含特性数", "包含特性"]
    ws.append(heads)
    for v in variants:
        ws.append([v["id"], v["name"], v.get("desc", ""), len(v["features"]),
                   ", ".join(v["features"])])
    _style_header(ws, 1, len(heads))
    for row in ws.iter_rows(min_row=2, max_col=len(heads)):
        for c in row:
            c.font, c.border = BODY, BORDER
            c.alignment = Alignment(vertical="top", wrap_text=True)
    for col, w in zip("ABCDE", (14, 16, 40, 12, 42)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"

    # 2.特性清单
    ws = wb.create_sheet("2.特性清单")
    heads = ["特性ID", "名称", "承接系统需求", "说明"]
    ws.append(heads)
    for f in features:
        ws.append([f["id"], f["name"], ", ".join(f["reqs"]), f.get("desc", "")])
    _style_header(ws, 1, len(heads))
    for row in ws.iter_rows(min_row=2, max_col=len(heads)):
        for c in row:
            c.font, c.border = BODY, BORDER
            c.alignment = Alignment(vertical="top", wrap_text=True)
    for col, w in zip("ABCD", (14, 20, 20, 52)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"

    # 3.覆盖矩阵
    ws = wb.create_sheet("3.覆盖矩阵")
    heads = ["系统需求ID", "系统需求"] + [f"{v['id']} {v['name']}" for v in variants] + ["承接特性"]
    ws.append(heads)
    titles = {}
    wbs = load_workbook(root / "ENG_需求追踪表_座椅控制器示例_V1.0.xlsx", data_only=True)
    tws = wbs["系统需求清单"]
    for r in range(5, tws.max_row + 1):
        k = str(tws.cell(row=r, column=2).value or "")
        if k.startswith("SYS-SEAT-"):
            titles[k] = tws.cell(row=r, column=3).value or ""
    for rid in sys_ids:
        fs = [f["id"] for f in features if rid in f["reqs"]]
        marks = ["●" if any(fid in v["features"] for fid in fs) else "" for v in variants]
        ws.append([rid, titles.get(rid, "")] + marks + [", ".join(fs)])
    _style_header(ws, 1, len(heads))
    for row in ws.iter_rows(min_row=2, max_col=len(heads)):
        for c in row:
            c.font, c.border = BODY, BORDER
            c.alignment = Alignment(horizontal="center" if c.column > 2 else "left",
                                    vertical="center")
    for col, w in zip("ABCDEFG", (16, 22, 18, 18, 18, 20, 6)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "C2"

    # 4.核验摘要
    ws = wb.create_sheet("4.核验摘要")
    ws.append(["核验项", "结果"])
    ws.append(["系统需求总数", len(sys_ids)])
    ws.append(["特性总数", len(features)])
    ws.append(["变体总数", len(variants)])
    ws.append(["后台需求数（无变体承接）", sum(1 for e in errors if e["rule"] == "E-VAR-ORPHAN-REQ")])
    ws.append(["门禁结论", f"PASS（0 ERROR）" if not errors else f"FAIL（{len(errors)} ERROR）"])
    ws.append(["生成日期", date.today().isoformat()])
    ws.append(["说明", "由 tools/variant_check.py 自动生成；真源 variant.yaml"])
    _style_header(ws, 1, 2)
    for row in ws.iter_rows(min_row=2, max_col=2):
        for c in row:
            c.font, c.border = BODY, BORDER
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 48

    wb.save(root / OUT)


def selftest() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="variant_selftest_"))
    # 造一个最小 SYS.2（两个需求）
    wb = Workbook()
    ws = wb.active
    ws.title = "3.系统需求"
    ws["B2"] = "SYS-SEAT-001"
    ws["B4"] = "SYS-SEAT-002"
    wb.save(tmp / SYS_XLSX)
    (tmp / "variant.yaml").write_text(yaml.safe_dump({
        "features": [
            {"id": "F-1", "name": "a", "reqs": ["SYS-SEAT-001"]},
            {"id": "F-1", "name": "dup", "reqs": ["SYS-SEAT-999"]},
            {"id": "F-3", "name": "empty", "reqs": []},
        ],
        "variants": [
            {"id": "V-1", "name": "v", "features": ["F-1", "F-X"]},
            {"id": "V-2", "name": "empty", "features": []},
        ]}, allow_unicode=True), encoding="utf-8")
    rules = {e["rule"] for e in check(tmp)}
    assert rules == {"E-VAR-DUP", "E-VAR-REQ", "E-VAR-EMPTY", "E-VAR-FEATURE",
                     "E-VAR-ORPHAN-REQ"}, rules
    print("[SELFTEST PASS] 5 类门禁断言全部通过（重复/未定义特性/需求不存在/孤儿需求/空配置）")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="产品配置校验与渲染（fail-closed）")
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
    errors = check(root)
    if args.render:
        render(root, errors)
        print(f"[RENDER] {OUT}：{len(errors)} ERROR")
        return 0 if not errors else 1
    result = {"errors": errors, "passed": not errors}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for e in errors:
            print(f"[ERROR][{e['rule']}] {e['msg']}")
        print("结论：" + ("FAIL ❌" if errors else "PASS ✅"))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
