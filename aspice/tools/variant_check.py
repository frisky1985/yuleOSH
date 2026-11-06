#!/usr/bin/env python3
"""variant_check.py — 产品配置（变体↔需求覆盖）校验与矩阵渲染（fail-closed，单文件）

真源：<root>/variant.yaml；需求 ID 权威来源：SYS.2 xlsx 中出现的 SYS-SEAT-\\d+。
门禁：E-VAR-DUP / E-VAR-FEATURE（引用未定义特性）/ E-VAR-REQ（特性映射的需求在 SYS.2 不存在）/
      E-VAR-ORPHAN-REQ（SYS 需求无任何变体承接）/ E-VAR-EMPTY（变体无特性）
视图：产品配置_变体需求矩阵_座椅控制器示例_V1.0.xlsx（从 scratch 生成，活文档）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

import yaml
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

DEMO_BANNER = "示例数据 · 不得作为项目证据"
OUT_NAME = "产品配置_变体需求矩阵_座椅控制器示例_V1.0.xlsx"
SYS2_NAME = "SYS.2_系统需求规格说明书_座椅控制器示例_V1.0.xlsx"
REQ_RE = re.compile(r"^SYS-SEAT-\d+$")


def load_sys_reqs(root: Path) -> set[str]:
    ids: set[str] = set()
    wb = load_workbook(root / SYS2_NAME, read_only=True)
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        for row in ws.iter_rows(values_only=True):
            for v in row:
                if v and REQ_RE.match(str(v).strip()):
                    ids.add(str(v).strip())
    wb.close()
    return ids


def check(root: Path) -> list[dict]:
    spec = yaml.safe_load((root / "variant.yaml").read_text(encoding="utf-8"))
    sys_reqs = load_sys_reqs(root)
    errors: list[dict] = []
    feats = {f["id"]: f for f in spec["features"]}
    for fid in feats:
        if list(f["id"] for f in spec["features"]).count(fid) > 1:
            errors.append({"rule": "E-VAR-DUP", "msg": f"特性 ID 重复：{fid}"})
        for rid in feats[fid].get("reqs", []):
            if rid not in sys_reqs:
                errors.append({"rule": "E-VAR-REQ",
                               "msg": f"特性 {fid} 映射的需求在 SYS.2 不存在：{rid}"})
    seen: set[str] = set()
    covered: set[str] = set()
    for v in spec["variants"]:
        vid = v["id"]
        if vid in seen:
            errors.append({"rule": "E-VAR-DUP", "msg": f"变体 ID 重复：{vid}"})
        seen.add(vid)
        if not v.get("features"):
            errors.append({"rule": "E-VAR-EMPTY", "msg": f"变体 {vid} 无特性"})
        for fid in v.get("features", []):
            if fid not in feats:
                errors.append({"rule": "E-VAR-FEATURE",
                               "msg": f"变体 {vid} 引用未定义特性：{fid}"})
            else:
                covered.update(feats[fid].get("reqs", []))
    for rid in sorted(sys_reqs - covered):
        errors.append({"rule": "E-VAR-ORPHAN-REQ",
                       "msg": f"SYS 需求无任何变体承接：{rid}（存在即须属于至少一个产品配置）"})
    return errors


def verify_result(root: Path) -> dict:
    errors = check(root)
    return {"errors": errors, "passed": not errors}


def cmd_render(root: Path) -> int:
    spec = yaml.safe_load((root / "variant.yaml").read_text(encoding="utf-8"))
    sys_reqs = sorted(load_sys_reqs(root))
    feats = {f["id"]: f for f in spec["features"]}
    req2feat: dict[str, str] = {}
    for f in spec["features"]:
        for rid in f.get("reqs", []):
            req2feat[rid] = f["name"]
    wb = Workbook()
    ws = wb.active
    ws.title = "变体需求矩阵"
    ws["A1"] = DEMO_BANNER
    ws["A1"].font = Font(bold=True, color="CC0000", size=14)
    ws.append([])
    header = ["SYS 需求", "对应特性"] + [v["name"] for v in spec["variants"]]
    ws.append(header)
    for c in ws[3]:
        c.font = Font(bold=True)
    for rid in sys_reqs:
        row = [rid, req2feat.get(rid, "—")]
        for v in spec["variants"]:
            reqs = set()
            for fid in v.get("features", []):
                reqs.update(feats.get(fid, {}).get("reqs", []))
            row.append("✓" if rid in reqs else "")
        ws.append(row)
    ws.append([])
    ws.append(["变体", "特性组合"])
    for v in spec["variants"]:
        ws.append([v["id"], "、".join(feats[f]["name"] for f in v.get("features", []) if f in feats)])
    for col, w in zip("ABCDEFGH", [16, 18, 12, 12, 14, 10, 10, 10]):
        ws.column_dimensions[col].width = w
    wb.save(root / OUT_NAME)
    print(f"[RENDER] {OUT_NAME}：{len(sys_reqs)} 需求 × {len(spec['variants'])} 变体")
    return 0


def selftest() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="var_selftest_"))
    (tmp / "variant.yaml").write_text(yaml.safe_dump({
        "features": [{"id": "F-A", "name": "a", "reqs": ["SYS-SEAT-001", "SYS-SEAT-099"]}],
        "variants": [{"id": "V-1", "features": ["F-A", "F-GHOST"]},
                     {"id": "V-1", "features": []}],
    }, allow_unicode=True), encoding="utf-8")
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active["A1"] = "SYS-SEAT-001"
    wb.active["A2"] = "SYS-SEAT-002"
    wb.save(tmp / SYS2_NAME)
    rules = {e["rule"] for e in check(tmp)}
    assert rules == {"E-VAR-REQ", "E-VAR-FEATURE", "E-VAR-DUP", "E-VAR-EMPTY", "E-VAR-ORPHAN-REQ"}, rules
    print("[SELFTEST PASS] 5 类门禁断言全部通过")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="产品配置变体覆盖校验（fail-closed）")
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
