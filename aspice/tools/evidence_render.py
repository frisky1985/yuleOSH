#!/usr/bin/env python3
"""evidence_render.py — 把 pipeline 产物按槽位回写 ASPICE 模板 xlsx（闭环最后一公里）

定位：manifest 是唯一真源，xlsx 是渲染视图。本工具是「视图渲染器」：
读取 evidence_check 校验通过的产物，按 slots.yaml 的槽位地址把
frontmatter 字段值写入对应单元格（第 1 轮证据列组）。

fail-closed 纪律：
- 先跑 evidence_check.analyze 做门禁，存在 ERROR 即中止，不写任何单元格；
- 目标单元格已有内容且与待写值不同 → 冲突 ERROR（除非 --force 覆盖）；
- 渲染后自动重读校验：写出的值与来源字段不一致即 ERROR。

用法：
    python3 evidence_render.py --cases 测试规范.xlsx --evidence evidence/ \
        --slots slots.yaml [--out 输出.xlsx] [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence_check import (DEFAULT_DOC_ALIAS, analyze, load_slots,  # noqa: E402
                            parse_frontmatter, sha256_file)


def locate_grid(ws, locator: str, row_key: str, columns: tuple[str, ...]):
    """定位表头行、行键列、证据列索引（每类列取首次出现 = 第 1 轮列组）。"""
    header = None
    header_row = 0
    for ridx, row in enumerate(ws.iter_rows(min_row=1, max_row=10, values_only=True), 1):
        cells = [str(c).replace("\n", "").strip() if c else "" for c in row]
        if locator in cells:
            header, header_row = cells, ridx
            break
    if header is None:
        raise ValueError(f"前 10 行内找不到含「{locator}」的表头行")
    key_col = header.index(row_key) + 1
    col_idx = {}
    for name in columns:
        if name not in header:
            raise ValueError(f"表头缺少证据列「{name}」")
        col_idx[name] = header.index(name) + 1
    rows = {}
    for r in range(header_row + 1, ws.max_row + 1):
        key = ws.cell(row=r, column=key_col).value
        if key is not None and str(key).strip():
            rows[str(key).strip()] = r
    return col_idx, rows


def render(cases_path: Path, evidence_dir: Path, spec: dict, doc_alias: str,
           out_path: Path | None, dry_run: bool, force: bool) -> tuple[int, list[str]]:
    """返回 (写入单元格数, 错误列表)。"""
    from openpyxl import load_workbook

    errors: list[str] = []
    sheet_name = spec["sheet"]
    locator = spec["header_locator"]["contains"]
    row_key = spec["row_key"]["column"]
    ec = spec["evidence_columns"]
    columns = tuple(c["name"] for c in ec)
    fields = {c["name"]: c["field"] for c in spec["evidence_columns"] if c.get("field")}
    vocab = {c["name"]: list(c["vocabulary"]) for c in spec["evidence_columns"] if c.get("vocabulary")}

    # ---- 门禁：evidence_check 全绿才允许渲染 ----
    gate = analyze(cases_path, evidence_dir, doc_alias, columns, sheet_name,
                   None, False, row_key=row_key, locator=locator,
                   fields=fields, vocab=vocab)
    if gate.errors:
        return 0, [f"门禁未通过，中止渲染：{e}" for e in gate.errors]

    wb = load_workbook(cases_path)
    if sheet_name not in wb.sheetnames:
        return 0, [f"找不到工作表「{sheet_name}」"]
    ws = wb[sheet_name]
    col_idx, rows = locate_grid(ws, locator, row_key, columns)

    # ---- 槽位 → (行, 列, 值) 计划 ----
    plan: dict[tuple[int, int], tuple[str, str]] = {}  # (row,col) -> (value, source)
    for artifact in gate.artifacts:
        for slot in artifact.fills:
            parts = slot.split("::")
            if len(parts) != 3 or parts[0] != doc_alias:
                continue
            _, tc_id, col = parts
            if tc_id not in rows:
                errors.append(f"E-RENDER-ROW: 用例行不存在：{tc_id}")
                continue
            value = str(artifact.meta.get(fields.get(col, ""), "")).strip()
            plan[(rows[tc_id], col_idx[col])] = (value, artifact.rel_path)

    # ---- 冲突检查 + 写入 ----
    written = 0
    for (r, c), (value, source) in sorted(plan.items()):
        cell = ws.cell(row=r, column=c)
        old = "" if cell.value is None else str(cell.value).strip()
        if old and old != value and not force:
            errors.append(
                f"E-RENDER-CONFLICT: {cell.coordinate} 已有内容 {old!r}，"
                f"与 {source} 的值 {value!r} 不一致（--force 可覆盖）")
            continue
        if old != value:
            if not dry_run:
                cell.value = value
            written += 1

    if errors:
        return written, errors

    # ---- 保存 + 重读校验 ----
    target = out_path or cases_path
    if not dry_run:
        wb.save(target)
        wb2 = load_workbook(target, read_only=True)
        ws2 = wb2[sheet_name]
        for (r, c), (value, source) in sorted(plan.items()):
            got = ws2.cell(row=r, column=c).value
            if str(got or "").strip() != value:
                errors.append(
                    f"E-RENDER-VERIFY: 重读 {ws2.cell(row=r, column=c).coordinate}"
                    f" 值与来源 {source} 不一致")
        wb2.close()
    wb.close()
    return written, errors


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="evidence_render.py",
        description="pipeline 产物按槽位回写 ASPICE 模板 xlsx（渲染前自动过 evidence_check 门禁）",
    )
    p.add_argument("--cases", type=Path, required=True, help="测试规范 .xlsx")
    p.add_argument("--evidence", type=Path, required=True, help="pipeline 产物目录")
    p.add_argument("--slots", type=Path, required=True, help="slots.yaml 槽位规格")
    p.add_argument("--doc-alias", default=DEFAULT_DOC_ALIAS)
    p.add_argument("--out", type=Path, default=None, help="输出到副本（默认原地写回 --cases）")
    p.add_argument("--dry-run", action="store_true", help="只打印写入计划，不落盘")
    p.add_argument("--force", action="store_true", help="目标单元格已有不同内容时强制覆盖")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases_path = Path(args.cases).expanduser()
    evidence_dir = Path(args.evidence).expanduser()
    slots_path = Path(args.slots).expanduser()
    for pth, name in ((cases_path, "--cases"), (slots_path, "--slots")):
        if not pth.is_file():
            print(f"[ERROR] 找不到 {name}：{pth}", file=sys.stderr)
            return 2
    if not evidence_dir.is_dir():
        print(f"[ERROR] 找不到 --evidence：{evidence_dir}", file=sys.stderr)
        return 2

    try:
        spec = load_slots(slots_path, args.doc_alias)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    try:
        written, errors = render(cases_path, evidence_dir, spec, args.doc_alias,
                                 args.out, args.dry_run, args.force)
    except (ValueError, OSError) as exc:
        print(f"[ERROR] 渲染失败：{exc}", file=sys.stderr)
        return 2

    mode = "DRY-RUN " if args.dry_run else ""
    print(f"===== evidence_render {mode}结果 =====")
    print(f"写入单元格：{written}" + ("（未落盘）" if args.dry_run else ""))
    for e in errors:
        print(f"  [ERROR] {e}")
    if errors:
        print("结论：FAIL ❌（fail-closed）")
        return 1
    print("结论：PASS ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
