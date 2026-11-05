#!/usr/bin/env python3
"""gate_sync.py — SUP.9/10 自动闭环（fail-closed，单文件，依赖 openpyxl + pyyaml）

把「校验器组的红灯」接到「问题管理/变更管理流程」：
  --sync-problems  运行四个校验器（trace/evidence×2/consistency/cm_registry），
                   每条 ERROR 自动开立问题单（PR-SEAT-xxx，按内容哈希去重）；
                   本轮不再出现的 ERROR 自动关闭（复测通过）。
  --sync-changes   从 cm_registry.yaml 的 changelog 生成变更请求（CR-SEAT-xxx，去重）。
  --render         渲染 SUP.9_缺陷问题管理表 与 SUP.10_项目变更跟踪表（模板 → seat 实例）。
  --selftest       自包含测试。

真源：<root>/gate_registry.yaml；SUP.9/SUP.10 xlsx 是渲染视图。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import yaml
from openpyxl import load_workbook
from openpyxl.styles import Font

TOOLS_DIR = Path(__file__).resolve().parent
ASPICE = TOOLS_DIR.parent
REGISTRY_NAME = "gate_registry.yaml"
SUP9_TEMPLATE = ASPICE / "templates_clean" / "SUP.9_缺陷问题管理表_V1.0.xlsx"
SUP10_TEMPLATE = ASPICE / "templates_clean" / "SUP.10_项目变更跟踪表_V1.0.xlsx"
SUP9_NAME = "SUP.9_缺陷问题管理表_座椅控制器示例_V1.0.xlsx"
SUP10_NAME = "SUP.10_项目变更跟踪表_座椅控制器示例_V1.0.xlsx"
DEMO_BANNER = "示例数据 · 不得作为项目证据"

# seat demo 的校验器组（cwd=root 执行，stdout 须为纯 JSON）
def checker_commands(root: Path) -> list[tuple[str, list[str]]]:
    py = sys.executable
    return [
        ("trace_check", [py, str(TOOLS_DIR / "trace_check.py"),
                         "--trace", "ENG_需求追踪表_座椅控制器示例_V1.0.xlsx",
                         "--cases", "ENG_测试规范_座椅控制器示例_V1.0.xlsx",
                         "--bidirectional", "--json"]),
        ("evidence_check(测试规范)", [py, str(TOOLS_DIR / "evidence_check.py"),
                         "--cases", "ENG_测试规范_座椅控制器示例_V1.0.xlsx",
                         "--evidence", "evidence", "--slots", "slots.yaml", "--json"]),
        ("evidence_check(SUP.1)", [py, str(TOOLS_DIR / "evidence_check.py"),
                         "--cases", "SUP.1_评审记录_座椅控制器示例_V1.0.xlsx",
                         "--evidence", "evidence_stage", "--slots", "slots.yaml",
                         "--doc-alias", "SUP.1_评审记录", "--json"]),
        ("consistency_check", [py, str(TOOLS_DIR / "consistency_check.py"),
                         "--spec", "consistency.yaml", "--json"]),
        ("cm_registry", [py, str(TOOLS_DIR / "cm_registry.py"),
                         "--root", ".", "--verify", "--json"]),
    ]


def norm_issues(source: str, data: dict) -> list[dict]:
    """把各校验器的 JSON 统一成 [{rule, msg}]（仅 ERROR 级）。"""
    out: list[dict] = []
    if source == "trace_check":
        for issue in data.get("issues", []):
            if str(issue.get("severity", "")).upper() == "ERROR":
                out.append({"rule": issue.get("rule") or "TRACE",
                            "msg": issue.get("msg") or issue.get("message") or str(issue)})
    else:
        for e in data.get("errors", []):
            out.append({"rule": e.get("rule", "UNKNOWN"), "msg": e.get("msg", "")})
    return out


def issue_key(source: str, rule: str, msg: str) -> str:
    return hashlib.sha1(f"{source}|{rule}|{msg}".encode()).hexdigest()[:12]


def load_reg(root: Path) -> dict:
    p = root / REGISTRY_NAME
    if p.exists():
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    return {"problems": [], "changes": []}


def save_reg(root: Path, reg: dict) -> None:
    (root / REGISTRY_NAME).write_text(yaml.safe_dump(reg, allow_unicode=True, sort_keys=False),
                                      encoding="utf-8")


def harvest_problems(root: Path, outputs: dict[str, dict]) -> tuple[int, int, int]:
    """outputs: {checker_name: parsed_json}。返回 (新开, 仍开, 关闭)。"""
    reg = load_reg(root)
    today = date.today().isoformat()
    seen: dict[str, dict] = {}
    for source, data in outputs.items():
        for e in norm_issues(source, data):
            key = issue_key(source, e["rule"], e["msg"])
            seen[key] = {"source": source, **e}
    opened = still = closed = 0
    by_key = {p["key"]: p for p in reg["problems"]}
    next_id = max((int(p["id"].rsplit("-", 1)[1]) for p in reg["problems"]), default=0) + 1
    for key, e in seen.items():
        if key in by_key:
            p = by_key[key]
            if p["status"] == "打开":
                still += 1
            else:  # 曾关闭又复现 → 重新打开
                p["status"], p["closed"] = "打开", None
                opened += 1
            p["last_seen"] = today
        else:
            reg["problems"].append({
                "id": f"PR-SEAT-{next_id:03d}", "key": key, "source": e["source"],
                "rule": e["rule"], "summary": e["msg"][:200],
                "first_seen": today, "last_seen": today, "status": "打开", "closed": None})
            next_id += 1
            opened += 1
    for p in reg["problems"]:
        if p["status"] == "打开" and p["key"] not in seen:
            p["status"], p["closed"] = "已关闭", today
            closed += 1
    save_reg(root, reg)
    return opened, still, closed


def harvest_changes(root: Path) -> int:
    reg = load_reg(root)
    cm = yaml.safe_load((root / "cm_registry.yaml").read_text(encoding="utf-8"))
    live = {it["path"] for it in cm.get("items", []) if it.get("live")}
    have = {c["key"] for c in reg["changes"]}
    next_id = max((int(c["id"].rsplit("-", 1)[1]) for c in reg["changes"]), default=0) + 1
    added = 0
    for entry in cm.get("changelog", []):
        if entry["path"] in live:
            continue  # 活文档登记自身不是变更请求
        if entry.get("added"):
            key = f"added|{entry['path']}"
            desc = f"新增配置项 {entry['path']}"
        else:
            key = f"{entry['path']}|{entry['old']}|{entry['new']}"
            desc = f"{entry['path']} 内容变更（{entry['old']}… → {entry['new']}…）"
        if key in have:
            continue
        reg["changes"].append({
            "id": f"CR-SEAT-{next_id:03d}", "key": key, "date": entry["date"],
            "object": entry["path"], "request": desc,
            "baseline": entry["baseline"], "status": "已实施（自动登记）"})
        next_id += 1
        added += 1
    save_reg(root, reg)
    return added


def cmd_sync_problems(root: Path) -> int:
    outputs: dict[str, dict] = {}
    checkers = checker_commands(root)
    # 第六校验器：MAN.1 度量（对最近一次 collect 快照判定，不重跑校验器组，避免递归）
    metrics_json = root / "metrics.yaml"
    if metrics_json.exists():
        checkers = checkers + [("metrics", [sys.executable, str(TOOLS_DIR / "metrics_collect.py"),
                                            "--root", ".", "--verify", "--json"])]
    if (root / "risk_registry.yaml").exists():
        checkers = checkers + [("man_check", [sys.executable, str(TOOLS_DIR / "man_check.py"),
                                              "--root", ".", "--verify", "--json"])]
    for name, cmd in checkers:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        try:
            outputs[name] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print(f"ERROR: {name} 未输出合法 JSON：{proc.stdout[:200]}{proc.stderr[:200]}",
                  file=sys.stderr)
            return 2
    opened, still, closed = harvest_problems(root, outputs)
    total_open = sum(1 for p in load_reg(root)["problems"] if p["status"] == "打开")
    print(f"[SYNC-PROBLEMS] 新开 {opened}，仍开 {still}，自动关闭 {closed}；当前打开 {total_open}")
    return 0


def cmd_sync_changes(root: Path) -> int:
    added = harvest_changes(root)
    total = len(load_reg(root)["changes"])
    print(f"[SYNC-CHANGES] 新登记 {added}，累计变更 {total}")
    return 0


def unmerge_below(ws, first_data_row: int) -> None:
    """解除数据区的合并单元格（模板示例行的纵向合并在 delete_rows 后仍残留，
    会吞掉写入值）。"""
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= first_data_row:
            ws.unmerge_cells(str(rng))


def cmd_render(root: Path) -> int:
    reg = load_reg(root)
    today = date.today().isoformat()

    # SUP.9：问题单
    out9 = root / SUP9_NAME
    shutil.copy(SUP9_TEMPLATE, out9)
    wb = load_workbook(out9)
    wb["封面"]["B1"] = DEMO_BANNER
    wb["封面"]["B1"].font = Font(bold=True, color="CC0000", size=14)
    ws = wb["缺陷问题管理表"]
    unmerge_below(ws, 5)
    if ws.max_row > 4:
        ws.delete_rows(5, ws.max_row - 4)
    for i, p in enumerate(sorted(reg["problems"], key=lambda x: x["id"])):
        r = i + 5
        ws.cell(row=r, column=2, value=p["id"])                       # 缺陷ID
        ws.cell(row=r, column=3, value=p["first_seen"])               # 日期
        ws.cell(row=r, column=4, value=f"gate_sync({p['source']})")   # 发现者
        ws.cell(row=r, column=5, value=f"[{p['rule']}] {p['summary']}")  # 描述
        ws.cell(row=r, column=6, value="SEAT-DEMO")                   # 发现版本
        ws.cell(row=r, column=7, value="自动门禁校验")                 # 发现阶段
        ws.cell(row=r, column=8, value=p["source"])                   # 原因（来源校验器）
        ws.cell(row=r, column=11, value="中")                          # 缺陷等级
        ws.cell(row=r, column=12, value="否")                          # 是否紧急
        if p["status"] == "已关闭":
            ws.cell(row=r, column=13, value="问题已消除")              # 修正措施
            ws.cell(row=r, column=16, value=p["closed"])               # 实际日期
            ws.cell(row=r, column=18, value="gate_sync（自动）")       # 验证责任人
            ws.cell(row=r, column=19, value=p["closed"])               # 验证日期
            ws.cell(row=r, column=20, value="门禁自动复测")            # 验证方法
            ws.cell(row=r, column=22, value="已关闭（复测通过）")      # 结果
    wb.save(out9)

    # SUP.10：变更请求
    out10 = root / SUP10_NAME
    shutil.copy(SUP10_TEMPLATE, out10)
    wb = load_workbook(out10)
    wb["封面"]["B1"] = DEMO_BANNER
    wb["封面"]["B1"].font = Font(bold=True, color="CC0000", size=14)
    ws = wb["项目变更跟踪表"]
    unmerge_below(ws, 5)                 # 表头占 row 2-4（B2:B4 等纵向合并），数据从 row 5 起
    if ws.max_row > 4:
        ws.delete_rows(5, ws.max_row - 4)
    for i, c in enumerate(sorted(reg["changes"], key=lambda x: x["id"])):
        r = i + 5
        ws.cell(row=r, column=2, value=c["id"])                        # 变更ID
        ws.cell(row=r, column=3, value=c["status"])                    # 状态
        ws.cell(row=r, column=4, value="cm_registry（自动）")          # 提出者
        ws.cell(row=r, column=5, value=c["date"])                      # 提出日期
        ws.cell(row=r, column=7, value=c["object"])                    # 变更对象
        ws.cell(row=r, column=8, value="文档变更")                      # 变更分类
        ws.cell(row=r, column=9, value="配置项基线更新")               # 变更来源
        ws.cell(row=r, column=10, value=c["request"])                  # 变更原因
        ws.cell(row=r, column=11, value=c["request"])                  # 变更具体要求
        ws.cell(row=r, column=13, value=c["object"])                   # 输出的工作产品
        ws.cell(row=r, column=14, value="示例")                        # 责任人
        ws.cell(row=r, column=15, value=c["date"])
        ws.cell(row=r, column=16, value=c["date"])
        ws.cell(row=r, column=17, value=f"通过（基线 {c['baseline']} verify PASS）")
        ws.cell(row=r, column=18, value="cm_registry（自动）")
        ws.cell(row=r, column=19, value=c["date"])
    wb.save(out10)
    print(f"[RENDER] {SUP9_NAME}（{len(reg['problems'])} 问题）+ "
          f"{SUP10_NAME}（{len(reg['changes'])} 变更）")
    return 0


def selftest() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="gate_selftest_"))
    outputs = {"consistency_check": {"errors": [
        {"rule": "E-FACT-MISMATCH", "msg": "欠压保护阈值不一致：期望 8.5V，a.xlsx W6 出现 8.0V"}]}}
    o, s, c = harvest_problems(tmp, outputs)
    assert (o, s, c) == (1, 0, 0), (o, s, c)
    o, s, c = harvest_problems(tmp, outputs)          # 同样错误 → 去重，仍开
    assert (o, s, c) == (0, 1, 0), (o, s, c)
    o, s, c = harvest_problems(tmp, {"consistency_check": {"errors": []}})  # 消失 → 自动关闭
    assert (o, s, c) == (0, 0, 1), (o, s, c)
    o, s, c = harvest_problems(tmp, outputs)          # 复现 → 重新打开（不换 ID）
    reg = load_reg(tmp)
    assert o == 1 and reg["problems"][0]["id"] == "PR-SEAT-001" and reg["problems"][0]["status"] == "打开"
    # 变更登记：新增 + 修改各一，重复同步去重
    (tmp / "cm_registry.yaml").write_text(yaml.safe_dump({"changelog": [
        {"date": "2026-11-06", "path": "README.md", "added": True, "baseline": "BL2"},
        {"date": "2026-11-06", "path": "a.xlsx", "old": "aaa", "new": "bbb", "baseline": "BL2"},
    ]}), encoding="utf-8")
    assert harvest_changes(tmp) == 2
    assert harvest_changes(tmp) == 0
    print("[SELFTEST PASS] 6 组断言全部通过（开立/去重/自动关闭/复现重开/变更登记/变更去重）")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="SUP.9/10 自动闭环（fail-closed）")
    ap.add_argument("--root", type=Path, required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sync-problems", action="store_true")
    g.add_argument("--sync-changes", action="store_true")
    g.add_argument("--render", action="store_true")
    g.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    root = args.root.resolve()
    if args.sync_problems:
        return cmd_sync_problems(root)
    if args.sync_changes:
        return cmd_sync_changes(root)
    return cmd_render(root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
