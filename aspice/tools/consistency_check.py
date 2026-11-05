#!/usr/bin/env python3
"""consistency_check.py — 跨文档一致性校验（fail-closed，单文件，依赖 openpyxl + pyyaml）

两类检查（由 consistency.yaml 规格驱动）：
  entities —— 实体名一致性：同一 ID 在设计文档与「需求追踪表」（名称真源）中的名称必须一致
  facts    —— 数值事实一致性：同一阈值/指标（如欠压 8.5V）在所有文档中的取值必须一致

用法：
  python3 consistency_check.py --spec consistency.yaml [--json] [--strict]
  python3 consistency_check.py --selftest
退出码：0=PASS，1=存在 ERROR（--strict 时 WARN 也计失败），2=用法/环境错误
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from openpyxl import load_workbook

TOOLS_DIR = Path(__file__).resolve().parent


def _num_eq(a: str, b: str) -> bool:
    """数值等价比较：7.0 == 7；非数值退化为字符串比较。"""
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def norm(v: object) -> str:
    return re.sub(r"\s+", "", str(v)) if v is not None else ""


def norm_header(v: object) -> str:
    return str(v).split("\n")[0].strip() if v is not None else ""


def iter_string_cells(path: Path):
    """产出 (sheet, 单元格地址, 文本)：所有字符串/数值单元格。"""
    wb = load_workbook(path, read_only=True)
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        for row in ws.iter_rows(values_only=False):
            for c in row:
                if c.value is None:
                    continue
                s = str(c.value)
                if s.strip():
                    yield ws.title, c.coordinate, s


def extract_entities(path: Path, sheet_name: str, id_header: str, name_header: str,
                     id_pattern: str | None = None) -> dict[str, str]:
    """从指定 sheet 提取 {ID: 名称}。表头行 = 同时含 id/name 表头文本的行（前 40 行内）。
    id_pattern 用于过滤同 sheet 内其他表格（接口表/状态机）的非实体行。"""
    id_re = re.compile(id_pattern) if id_pattern else None
    wb = load_workbook(path, read_only=True)
    if sheet_name not in wb.sheetnames:
        raise KeyError(f"sheet「{sheet_name}」不存在于 {path.name}")
    ws = wb[sheet_name]
    header_row = id_col = name_col = None
    for ridx, row in enumerate(ws.iter_rows(min_row=1, max_row=40, values_only=True), 1):
        cells = [norm_header(c) for c in row]
        if id_header in cells and name_header in cells:
            header_row, id_col, name_col = ridx, cells.index(id_header), cells.index(name_header)
            break
    if header_row is None:
        raise ValueError(f"{path.name}「{sheet_name}」前 40 行未找到表头 {id_header}/{name_header}")
    out: dict[str, str] = {}
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        ident = norm(row[id_col]) if id_col < len(row) else ""
        name = str(row[name_col]).strip() if name_col < len(row) and row[name_col] else ""
        if ident and (id_re is None or id_re.match(ident)):
            out[ident] = name
    return out


def check_entities(spec: dict, root: Path) -> tuple[list[dict], list[dict], int]:
    errors: list[dict] = []
    warnings: list[dict] = []
    compared = 0
    can = spec["entities"]["canonical"]
    can_file = root / can["file"]
    canonical: dict[str, dict[str, str]] = {}
    for sheet, cols in can["sheets"].items():
        canonical[sheet] = extract_entities(can_file, sheet, cols["id"], cols["name"])
    for src in spec["entities"]["sources"]:
        got = extract_entities(root / src["file"], src["sheet"], src["id"], src["name"],
                               src.get("id_pattern"))
        canon = canonical[src["canonical_sheet"]]
        for ident, name in got.items():
            if ident not in canon:
                warnings.append({"rule": "W-ENTITY-NOT-IN-CANONICAL",
                                 "msg": f"{src['file']}「{src['sheet']}」的 {ident} 未出现在追踪表"
                                        f"「{src['canonical_sheet']}」（追溯完整性由 trace_check 负责）"})
                continue
            compared += 1
            if norm(name) != norm(canon[ident]):
                errors.append({"rule": "E-NAME-MISMATCH",
                               "msg": f"{ident} 名称不一致：{src['file']}「{src['sheet']}」=「{name}」，"
                                      f"追踪表「{src['canonical_sheet']}」=「{canon[ident]}」"})
    return errors, warnings, compared


def check_facts(spec: dict, root: Path) -> tuple[list[dict], list[dict], int]:
    errors: list[dict] = []
    warnings: list[dict] = []
    checked = 0
    cells: list[tuple[str, str, str, str]] = []  # (file, sheet, coord, text)
    for fname in spec["scan"]:
        for sheet, coord, text in iter_string_cells(root / fname):
            cells.append((fname, sheet, coord, text))
    for fact in spec["facts"]:
        pats = [re.compile(p) for p in (fact.get("patterns") or [fact["pattern"]])]
        hits = 0
        for fname, sheet, coord, text in cells:
            for pat in pats:
                for m in pat.finditer(text):
                    hits += 1
                    checked += 1
                    if not _num_eq(m.group(1), fact["expect"]):
                        errors.append({"rule": "E-FACT-MISMATCH",
                                       "msg": f"{fact['name']}不一致：期望 {fact['expect']}{fact['unit']}，"
                                              f"{fname}「{sheet}」{coord} 出现 {m.group(1)}{fact['unit']}"
                                              f"（原文：{text.strip()[:60]}）"})
        if hits == 0:
            warnings.append({"rule": "W-FACT-ABSENT",
                             "msg": f"{fact['name']}（{fact['expect']}{fact['unit']}）在扫描范围内未出现"})
    return errors, warnings, checked


def analyze(spec_path: Path) -> dict:
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    root = spec_path.resolve().parent
    result = {"spec": spec_path.name,
              "entities_compared": 0, "facts_checked": 0,
              "errors": [], "warnings": []}
    for fname in spec.get("scan", []):
        if not (root / fname).exists():
            result["errors"].append({"rule": "E-FILE-MISSING", "msg": f"扫描对象不存在：{fname}"})
    if not result["errors"]:
        e1, w1, n1 = check_entities(spec, root)
        e2, w2, n2 = check_facts(spec, root)
        result["errors"] += e1 + e2
        result["warnings"] += w1 + w2
        result["entities_compared"] = n1
        result["facts_checked"] = n2
    result["passed"] = not result["errors"]
    return result


def selftest() -> int:
    import tempfile
    from openpyxl import Workbook

    tmp = Path(tempfile.mkdtemp(prefix="consistency_selftest_"))
    # 真源 + 设计文档（含一处名称不一致）
    wb = Workbook(); ws = wb.active; ws.title = "软件架构元素清单"
    ws.append(["软件架构元素标识", "标题"]); ws.append(["SW-X-001", "座椅调节"]); ws.append(["SW-X-002", "记忆管理"])
    wb.save(tmp / "trace.xlsx")
    wb = Workbook(); ws = wb.active; ws.title = "3.架构"
    ws.append(["模块ID", "模块名"]); ws.append(["SW-X-001", "座椅调节"]); ws.append(["SW-X-002", "记忆服务"])  # 不一致
    ws.append(["事实：欠压阈值 8.5V"]); ws.append(["PWM 10kHz"])
    wb.save(tmp / "design.xlsx")
    (tmp / "spec.yaml").write_text(
        "scan: [design.xlsx]\n"
        "entities:\n"
        "  canonical: {file: trace.xlsx, sheets: {软件架构元素清单: {id: 软件架构元素标识, name: 标题}}}\n"
        "  sources:\n"
        "    - {file: design.xlsx, sheet: 3.架构, id: 模块ID, name: 模块名, canonical_sheet: 软件架构元素清单}\n"
        "facts:\n"
        "  - {name: 欠压保护阈值, pattern: '欠压[^\\d]{0,8}(\\d+(?:\\.\\d+)?)\\s*V', expect: '8.5', unit: V}\n"
        "  - {name: PWM 频率, pattern: '(\\d+(?:\\.\\d+)?)\\s*kHz', expect: '10', unit: kHz}\n",
        encoding="utf-8")
    r = analyze(tmp / "spec.yaml")
    assert not r["passed"], "名称不一致应判失败"
    assert any(e["rule"] == "E-NAME-MISMATCH" for e in r["errors"]), r["errors"]
    assert r["entities_compared"] == 2 and r["facts_checked"] == 2, r

    # 修复名称 + 制造数值不一致
    wb = load_workbook(tmp / "design.xlsx"); ws = wb["3.架构"]
    ws.cell(row=3, column=2, value="记忆管理")
    ws.cell(row=5, column=1, value="事实：欠压阈值 8.0V")  # 不一致
    wb.save(tmp / "design.xlsx")
    r = analyze(tmp / "spec.yaml")
    assert not r["passed"]
    assert any(e["rule"] == "E-FACT-MISMATCH" for e in r["errors"]), r["errors"]

    # 全部修复 → PASS
    ws.cell(row=5, column=1, value="事实：欠压阈值 8.5V")
    wb.save(tmp / "design.xlsx")
    r = analyze(tmp / "spec.yaml")
    assert r["passed"], r["errors"]
    print("[SELFTEST PASS] 3 组断言全部通过（名称不一致/数值不一致/全绿）")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="跨文档一致性校验（fail-closed）")
    ap.add_argument("--spec", type=Path, help="consistency.yaml 规格文件")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="WARN 也计失败")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.spec:
        print("ERROR: 需要 --spec", file=sys.stderr)
        return 2

    result = analyze(args.spec)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for e in result["errors"]:
            print(f"[ERROR][{e['rule']}] {e['msg']}")
        for w in result["warnings"]:
            print(f"[WARN ][{w['rule']}] {w['msg']}")
        print("===== consistency_check 结果 =====")
        print(f"实体名比对   : {result['entities_compared']}")
        print(f"数值事实核对 : {result['facts_checked']}")
        print(f"ERROR        : {len(result['errors'])}")
        print(f"WARN         : {len(result['warnings'])}")
        failed = bool(result["errors"]) or (args.strict and result["warnings"])
        print("结论：" + ("FAIL ❌" if failed else "PASS ✅"))
    return 1 if result["errors"] or (args.strict and result["warnings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
