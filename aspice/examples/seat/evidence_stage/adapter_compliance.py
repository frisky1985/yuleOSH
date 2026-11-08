#!/usr/bin/env python3
"""adapter_compliance.py — yuleOSH ComplianceChecker 原始输出 → 证据链适配器（示例）

输入：evidence_stage/compliance_raw.json（真实 pipeline 输出，
      由 ComplianceChecker(project_dir='/workspace').run() 生成）
两件事：
  1. 骨架准备：在 SUP.1_评审记录 xlsx 的「2.评审检查单」按 BP 建检查项行
     （CHK-SWE1-BP1 等，幂等：已存在则跳过）——相当于评审计划的落实；
  2. 产物生成：每个 BP 一份 md 产物（frontmatter 自声明 fills 槽位），
     verdict 映射：✅→通过，⚠️/❌→不通过（fail-closed，部分通过不算通过）。

示例数据 · 不得作为项目证据。
"""
import json
import sys
from pathlib import Path

SEAT = Path("/workspace/aspice/examples/seat")
RAW = Path(__file__).parent / "compliance_raw.json"
XLSX = SEAT / "SUP.1_评审记录_座椅控制器示例_V1.0.xlsx"
EVD = Path(__file__).parent
SHEET = "2.评审检查单"
STATUS_MAP = {"✅": "通过", "⚠️": "不通过", "❌": "不通过"}


def bp_to_chk(bp_id: str) -> str:
    # SWE.1.BP1 → CHK-SWE1-BP1
    parts = bp_id.replace(".", "")
    return f"CHK-{parts}"


def main() -> int:
    data = json.loads(RAW.read_text(encoding="utf-8"))
    sections = data.get("swe_sections", {})
    rows = []  # (chk_id, bp_id, title, verdict, detail_summary)
    for sec in sections.values():
        for bp in sec.get("base_practices", []):
            details = bp.get("details", [])
            fails = [d.strip() for d in details if "❌" in d]
            summary = fails[0][:120] if fails else "全部检查项通过"
            rows.append((bp_to_chk(bp["id"]), bp["id"], bp.get("title", ""),
                         STATUS_MAP.get(bp["status"], "不通过"), summary))
    if not rows:
        print("[ERROR] compliance_raw.json 中无 base_practices", file=sys.stderr)
        return 1

    # ---- 1. 骨架准备（幂等） ----
    from openpyxl import load_workbook
    wb = load_workbook(XLSX)
    ws = wb[SHEET]
    existing = set()
    for r in range(2, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if v and str(v).strip() and str(v).strip() != "待填写":
            existing.add(str(v).strip())
    # 清除模板「待填写」占位行
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(row=r, column=1).value or "").strip() == "待填写":
            ws.cell(row=r, column=1).value = None
    next_row = 2
    added = 0
    for chk_id, bp_id, title, _, _ in rows:
        if chk_id in existing:
            continue
        while ws.cell(row=next_row, column=1).value not in (None, ""):
            next_row += 1
        ws.cell(row=next_row, column=1).value = chk_id
        ws.cell(row=next_row, column=2).value = "完整性"
        ws.cell(row=next_row, column=3).value = f"{bp_id} {title}"
        ws.cell(row=next_row, column=6).value = "yuleOSH ComplianceChecker（pipeline）"
        added += 1
    wb.save(XLSX)

    # ---- 2. 产物生成 ----
    for chk_id, bp_id, title, verdict, summary in rows:
        content = f"""---
artifact: {chk_id}__compliance
stage: review
verdict: {verdict}
result: {verdict}
evidence_loc: evidence_stage/compliance_raw.json#{bp_id}
fills:
  - SUP.1_评审记录::{chk_id}::结果(通过·不通过·不适用)
  - SUP.1_评审记录::{chk_id}::证据位置
---

# 示例数据 · 不得作为项目证据

# {chk_id}（{bp_id} {title}）合规评审记录

- 判定：{verdict}
- 依据：{summary}
- 原始报告：evidence_stage/compliance_raw.json 节点 {bp_id}

> 真实 yuleOSH pipeline 输出（ComplianceChecker, ASPICE v3.1, 18 BP），
> 由 adapter_compliance.py 适配为证据链产物。
"""
        (EVD / f"{chk_id}.md").write_text(content, encoding="utf-8")

    passed = sum(1 for r in rows if r[3] == "通过")
    print(f"骨架：新增 {added} 行（已有 {len(existing)} 行）；产物：{len(rows)} 份"
          f"（通过 {passed} / 不通过 {len(rows) - passed}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
