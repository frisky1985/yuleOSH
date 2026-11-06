#!/usr/bin/env python3
"""cm_registry.py — SUP.8 配置项注册表与配置清单生成（fail-closed，单文件，依赖 openpyxl + pyyaml）

真源：<root>/cm_registry.yaml（CI-ID ↔ 路径 ↔ sha256 ↔ 基线）。
文档 SUP.8_项目配置项清单及状态报告 是从注册表渲染的视图。

模式：
  --init     扫描 root 建立注册表（已存在则报错，防误覆盖）
  --update   重扫：保留既有 CI-ID，新文件分配新 ID，登记新哈希
  --verify   校验：E-HASH-MISMATCH（篡改）/ E-ITEM-MISSING（丢失）/ E-FILE-UNREGISTERED（未受控文件）
  --render   从注册表渲染 SUP.8 配置项清单 xlsx（模板 → seat 实例）
  --selftest 自包含测试
退出码：0=PASS，1=ERROR，2=用法错误
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

import yaml
from openpyxl import load_workbook

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = TOOLS_DIR.parent / "templates_clean" / "SUP.8_项目配置项清单及状态报告_V1.0.xlsx"
REGISTRY_NAME = "cm_registry.yaml"
RENDER_NAME = "SUP.8_项目配置项清单及状态报告_座椅控制器示例_V1.0.xlsx"
DEMO_BANNER = "示例数据 · 不得作为项目证据"

# 活文档：内容随流程演进的登记表（问题/变更登记册及其渲染视图）。
# 它们必须注册受控（存在性强制），但哈希仅作信息记录，不做基线比对，
# 其变更也不产生变更请求——登记表记录自身不是「变更」。
def is_live(rel: str) -> bool:
    return rel in ("gate_registry.yaml", "metrics_history.jsonl") or \
        rel.startswith(("SUP.9_", "SUP.10_", "横切_过程度量与目标定义_座椅",
                        "MAN.5_风险登记册_座椅", "MAN.3_项目进度计划_座椅", "证据链总览_"))

DEFAULT_SCOPE = {
    "include": ["**/*.xlsx", "**/*.yaml", "**/*.md", "**/*.json", "**/*.docx", "**/*.py",
                "**/*.html"],
    "exclude": [REGISTRY_NAME, "**/__pycache__/**"],
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_files(root: Path, scope: dict) -> list[str]:
    """返回受控范围内的相对路径（排序、确定序）。"""
    found: set[str] = set()
    for pattern in scope["include"]:
        for p in root.glob(pattern):
            if p.is_file():
                found.add(p.relative_to(root).as_posix())
    out = []
    for rel in sorted(found):
        if any(fnmatch.fnmatch(rel, ex) for ex in scope["exclude"]):
            continue
        out.append(rel)
    return out


def load_registry(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def save_registry(path: Path, reg: dict) -> None:
    path.write_text(yaml.safe_dump(reg, allow_unicode=True, sort_keys=False), encoding="utf-8")


def make_item(cid: str, rel: str, root: Path, baseline: str) -> dict:
    p = root / rel
    live = is_live(rel)
    item = {"id": cid, "path": rel, "name": Path(rel).stem,
            "management": "版本管理（活文档）" if live else
                          ("版本管理" if rel.endswith((".yaml", ".py", ".md")) else "存储管理"),
            "version": "V1.0", "status": "正式发布", "baseline": baseline,
            "sha256": sha256_of(p), "size": p.stat().st_size}
    if live:
        item["live"] = True
    return item


def cmd_init(root: Path, baseline: str) -> int:
    reg_path = root / REGISTRY_NAME
    if reg_path.exists():
        print(f"ERROR: {REGISTRY_NAME} 已存在（用 --update 增量更新）", file=sys.stderr)
        return 2
    reg = {"baseline": baseline, "tool": "cm_registry.py", "scope": DEFAULT_SCOPE, "items": []}
    for i, rel in enumerate(scan_files(root, DEFAULT_SCOPE), 1):
        reg["items"].append(make_item(f"CI-SEAT-{i:03d}", rel, root, baseline))
    save_registry(reg_path, reg)
    print(f"[INIT] {len(reg['items'])} 个配置项已注册（基线 {baseline}）")
    return 0


def cmd_update(root: Path, baseline: str | None) -> int:
    reg_path = root / REGISTRY_NAME
    reg = load_registry(reg_path)
    bl = baseline or reg["baseline"]
    by_path = {it["path"]: it for it in reg["items"]}
    next_id = max((int(it["id"].rsplit("-", 1)[1]) for it in reg["items"]), default=0) + 1
    files = scan_files(root, reg["scope"])
    added = refreshed = 0
    today = date.today().isoformat()
    changelog = reg.setdefault("changelog", [])
    for rel in files:
        if rel in by_path:
            it = by_path[rel]
            digest = sha256_of(root / rel)
            if it["sha256"] != digest:
                if not it.get("live"):
                    changelog.append({"date": today, "path": rel,
                                      "old": it["sha256"][:12], "new": digest[:12], "baseline": bl})
                    refreshed += 1
                it["sha256"], it["size"], it["baseline"] = digest, (root / rel).stat().st_size, bl
        else:
            reg["items"].append(make_item(f"CI-SEAT-{next_id:03d}", rel, root, bl))
            changelog.append({"date": today, "path": rel, "added": True, "baseline": bl})
            next_id += 1
            added += 1
    reg["baseline"] = bl
    save_registry(reg_path, reg)
    print(f"[UPDATE] 新增 {added}，刷新哈希 {refreshed}，共 {len(reg['items'])} 项")
    return 0


def verify(root: Path) -> dict:
    reg = load_registry(root / REGISTRY_NAME)
    errors, warnings = [], []
    seen_ids: set[str] = set()
    for it in reg["items"]:
        if it["id"] in seen_ids:
            errors.append({"rule": "E-ID-DUPLICATE", "msg": f"CI-ID 重复：{it['id']}"})
        seen_ids.add(it["id"])
        p = root / it["path"]
        if not p.exists():
            errors.append({"rule": "E-ITEM-MISSING", "msg": f"{it['id']} 文件丢失：{it['path']}"})
            continue
        if it.get("live"):
            continue  # 活文档：哈希仅信息记录，不做基线比对
        digest = sha256_of(p)
        if digest != it["sha256"]:
            errors.append({"rule": "E-HASH-MISMATCH",
                           "msg": f"{it['id']} {it['path']} 哈希与基线 {it['baseline']} 不符"
                                  f"（注册 {it['sha256'][:12]}… ≠ 实际 {digest[:12]}…）"})
    registered = {it["path"] for it in reg["items"]}
    for rel in scan_files(root, reg["scope"]):
        if rel not in registered:
            errors.append({"rule": "E-FILE-UNREGISTERED",
                           "msg": f"工作产品未纳入配置管理：{rel}（SUP.8 要求 100% 受控）"})
    return {"items": len(reg["items"]), "baseline": reg["baseline"],
            "errors": errors, "warnings": warnings, "passed": not errors}


def cmd_render(root: Path, template: Path) -> int:
    reg = load_registry(root / REGISTRY_NAME)
    result = verify(root)
    if result["errors"]:
        print("ERROR: 注册表校验未过（先 --update 或修复篡改），中止渲染：", file=sys.stderr)
        for e in result["errors"]:
            print(f"  [{e['rule']}] {e['msg']}", file=sys.stderr)
        return 1
    out = root / RENDER_NAME
    shutil.copy(template, out)
    wb = load_workbook(out)

    # 封面：项目名 + 红色示例声明
    cover = wb["封面"]
    for row in cover.iter_rows(min_row=1, max_row=10):
        for c in row:
            if c.value == "项目/产品名称":
                c.value = "项目/产品名称：主驾座椅控制器（SCM）示例"
    cover["B1"] = DEMO_BANNER
    from openpyxl.styles import Font
    cover["B1"].font = Font(bold=True, color="CC0000", size=14)

    # 配置项清单：清示例行，写注册表
    ws = wb["配置项清单"]
    if ws.max_row > 2:
        ws.delete_rows(3, ws.max_row - 2)
    today = date.today().isoformat()
    for i, it in enumerate(reg["items"], 1):
        r = i + 2
        ws.cell(row=r, column=2, value=i)
        ws.cell(row=r, column=3, value=it["name"])
        ws.cell(row=r, column=4, value=it["management"])
        ws.cell(row=r, column=5, value=f"aspice/examples/seat/{it['path']}")
        ws.cell(row=r, column=6, value="配置管理员")
        ws.cell(row=r, column=7, value="示例")
        ws.cell(row=r, column=8, value=today)
        ws.cell(row=r, column=9, value=today)
        ws.cell(row=r, column=10, value=it["version"])
        ws.cell(row=r, column=11, value=it["status"])
        ws.cell(row=r, column=12, value=f"基线 {it['baseline']}；sha256 见 cm_registry.yaml")

    # 变更履历首行
    log = wb["变更履历"]
    log.cell(row=4, column=2, value="V1.0")
    log.cell(row=4, column=3, value=today)
    log.cell(row=4, column=4, value="cm_registry.py")
    log.cell(row=4, column=5, value="示例")
    log.cell(row=4, column=6, value="示例")
    log.cell(row=4, column=7, value=f"首次基线 {reg['baseline']}（{len(reg['items'])} 个配置项）")

    # 状态统计第一行
    stat = wb["配置项状态统计报告"]
    n = len(reg["items"])
    stat.cell(row=4, column=3, value=n)
    stat.cell(row=4, column=4, value=n)
    stat.cell(row=4, column=6, value=n)
    stat.cell(row=4, column=7, value=n)
    stat.cell(row=4, column=9, value=today)
    wb.save(out)
    print(f"[RENDER] {out.name}：{n} 个配置项（基线 {reg['baseline']}）")
    return 0


def selftest() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cm_selftest_"))
    (tmp / "doc_a.xlsx").write_bytes(b"fake-xlsx-a")
    (tmp / "spec.yaml").write_text("k: v\n", encoding="utf-8")
    assert cmd_init(tmp, "BL-TEST") == 0
    r = verify(tmp)
    assert r["passed"] and r["items"] == 2, r
    # 篡改 → E-HASH-MISMATCH
    (tmp / "spec.yaml").write_text("k: tampered\n", encoding="utf-8")
    r = verify(tmp)
    assert not r["passed"] and any(e["rule"] == "E-HASH-MISMATCH" for e in r["errors"])
    # update 刷新后回绿
    assert cmd_update(tmp, None) == 0
    assert verify(tmp)["passed"]
    # 未注册新文件 → E-FILE-UNREGISTERED
    (tmp / "new.md").write_text("# x\n", encoding="utf-8")
    r = verify(tmp)
    assert not r["passed"] and any(e["rule"] == "E-FILE-UNREGISTERED" for e in r["errors"])
    assert cmd_update(tmp, None) == 0
    # 删除已注册文件 → E-ITEM-MISSING
    (tmp / "doc_a.xlsx").unlink()
    r = verify(tmp)
    assert not r["passed"] and any(e["rule"] == "E-ITEM-MISSING" for e in r["errors"])
    print("[SELFTEST PASS] 5 组断言全部通过（注册/篡改/刷新/未注册/丢失）")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="SUP.8 配置项注册表与清单生成（fail-closed）")
    ap.add_argument("--root", type=Path, required=True, help="配置库根目录（含 cm_registry.yaml）")
    ap.add_argument("--baseline", default=None, help="基线标签（init 必填，默认 SEAT-DEMO-BL1）")
    ap.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--init", action="store_true")
    g.add_argument("--update", action="store_true")
    g.add_argument("--verify", action="store_true")
    g.add_argument("--render", action="store_true")
    g.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    root = args.root.resolve()
    if args.init:
        return cmd_init(root, args.baseline or "SEAT-DEMO-BL1")
    if args.update:
        return cmd_update(root, args.baseline)
    if args.render:
        return cmd_render(root, args.template)
    result = verify(root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for e in result["errors"]:
            print(f"[ERROR][{e['rule']}] {e['msg']}")
        for w in result["warnings"]:
            print(f"[WARN ][{w['rule']}] {w['msg']}")
        print("===== cm_registry verify 结果 =====")
        print(f"配置项 : {result['items']}（基线 {result['baseline']}）")
        print(f"ERROR  : {len(result['errors'])}")
        print(f"WARN   : {len(result['warnings'])}")
        failed = bool(result["errors"]) or (args.strict and result["warnings"])
        print("结论：" + ("FAIL ❌" if failed else "PASS ✅"))
    return 1 if result["errors"] or (args.strict and result["warnings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
