#!/usr/bin/env python3
"""metrics_collect.py — MAN.1 度量采集/判定/渲染（fail-closed，单文件，依赖 openpyxl + pyyaml）

真源：<root>/metrics.yaml（度量定义）+ <root>/metrics_history.jsonl（时间序列，活文档）。
视图：横切_过程度量与目标定义_座椅控制器示例_V1.0.xlsx。

  --collect  运行校验器组（复用 gate_sync.checker_commands），按 metrics.yaml 采值，
             追加 history，对 target 判定；任一 FAIL 退出码 1
  --verify   不重跑校验器，对最近一次 collect 快照判定，供 gate_sync 作为第六校验器
  --render   渲染度量模板（度量项清单/采集记录/超限措施/汇总）
  --selftest 自包含测试
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

import yaml
from openpyxl import load_workbook
from openpyxl.styles import Font

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from gate_sync import checker_commands  # noqa: E402

TEMPLATE = TOOLS_DIR.parent / "templates_new" / "横切_过程度量与目标定义_V1.0.xlsx"
RENDER_NAME = "横切_过程度量与目标定义_座椅控制器示例_V1.0.xlsx"
DEMO_BANNER = "示例数据 · 不得作为项目证据"
HISTORY = "metrics_history.jsonl"

_SEG = re.compile(r"^(\w+)(?:\[(\w+)=([^\]]+)\])?$")
RULES = {"eq", "gte", "lte", "info"}
STREAK_LIMIT = 2  # 同一度量连续 ≥2 次采集 FAIL → E-METRIC-STREAK 升级


def load_spec(root: Path) -> tuple[list[dict], list[dict]]:
    """加载 metrics.yaml 并做定义级 schema 校验（E-METRIC-DEF）。"""
    data = yaml.safe_load((root / "metrics.yaml").read_text(encoding="utf-8"))
    metrics = data.get("metrics") or []
    errors, ids = [], set()
    for m in metrics:
        mid = m.get("id", "<missing>")
        if mid in ids:
            errors.append({"rule": "E-METRIC-DEF", "msg": f"度量 ID 重复：{mid}"})
        ids.add(mid)
        rule = m.get("rule")
        if rule not in RULES:
            errors.append({"rule": "E-METRIC-DEF", "msg": f"{mid} 非法 rule：{rule!r}（须 ∈ {sorted(RULES)}）"})
        elif rule != "info" and m.get("target") is None:
            errors.append({"rule": "E-METRIC-DEF", "msg": f"{mid} rule={rule} 但缺 target"})
        if ("extract" in m) == ("expr" in m):
            errors.append({"rule": "E-METRIC-DEF", "msg": f"{mid} extract 与 expr 必须且仅能有其一"})
        if not m.get("source"):
            errors.append({"rule": "E-METRIC-DEF", "msg": f"{mid} 缺 source"})
    return metrics, errors


def extract(data, path: str):
    """点路径取值：`a.b[k=v].count`；段尾 count 对列表取长度。"""
    cur = data
    for seg in path.split("."):
        if seg == "count":
            cur = len(cur)
            continue
        m = _SEG.match(seg)
        if not m:
            raise ValueError(f"非法路径段: {seg}")
        key, fk, fv = m.group(1), m.group(2), m.group(3)
        cur = cur[key]
        if fk:
            cur = [x for x in cur if str(x.get(fk)) == fv]
    return cur


def evaluate(value, rule: str, target) -> str:
    if rule == "info":
        return "INFO"
    ok = {"eq": value == target, "gte": value >= target, "lte": value <= target}[rule]
    return "PASS" if ok else "FAIL"


def collect(root: Path) -> list[dict]:
    spec, def_errors = load_spec(root)
    if def_errors:
        for e in def_errors:
            print(f"[ERROR][{e['rule']}] {e['msg']}", file=sys.stderr)
        raise SystemExit(1)
    outputs: dict[str, dict] = {}
    for name, cmd in checker_commands(root):
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        outputs[name] = json.loads(proc.stdout)
    today = date.today().isoformat()
    period = date.today().strftime("%Y-%m")
    records = []
    for m in spec:
        src = m["source"]
        if src.startswith("file:"):
            data = yaml.safe_load((root / src[5:]).read_text(encoding="utf-8"))
        else:
            data = outputs[src]
        if "expr" in m:
            vars_ = {k: v for k, v in data.items() if isinstance(v, (int, float))}
            value = eval(m["expr"], {"__builtins__": {}}, vars_)  # 本地可信 yaml
        else:
            value = extract(data, m["extract"])
        status = evaluate(value, m["rule"], m["target"])
        records.append({"date": today, "period": period, "id": m["id"], "name": m["name"],
                        "value": value, "rule": m["rule"], "target": m["target"],
                        "status": status})
    with open(root / HISTORY, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return records


def latest_snapshot(root: Path) -> dict[str, dict]:
    """每个度量项取最近一条记录。"""
    snap: dict[str, dict] = {}
    hp = root / HISTORY
    if hp.exists():
        for line in hp.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            snap[r["id"]] = r
    return snap


def verify_result(root: Path) -> dict:
    _, def_errors = load_spec(root)
    snap = latest_snapshot(root)
    errors = list(def_errors)
    errors += [{"rule": "E-METRIC-OUT",
                "msg": f"{r['id']} {r['name']} = {r['value']}，"
                       f"违反 {r['rule']} {r['target']}（{r['date']} 采集）"}
               for r in snap.values() if r["status"] == "FAIL"]
    # 趋势升级：同一度量连续 ≥STREAK_LIMIT 次采集 FAIL → 持续恶化，区别于单次抖动
    hist: list[dict] = []
    hp = root / HISTORY
    if hp.exists():
        hist = [json.loads(x) for x in hp.read_text(encoding="utf-8").splitlines()]
    for mid in dict.fromkeys(r["id"] for r in hist):
        streak = 0
        for r in reversed([x for x in hist if x["id"] == mid]):
            if r["status"] == "FAIL":
                streak += 1
            else:
                break
        if streak >= STREAK_LIMIT:
            name = next((x["name"] for x in reversed(hist) if x["id"] == mid), mid)
            errors.append({"rule": "E-METRIC-STREAK",
                           "msg": f"{mid} {name} 连续 {streak} 次采集超限（趋势恶化，须升级纠正措施）"})
    return {"metrics": list(snap.values()), "errors": errors, "passed": not errors}


def cmd_render(root: Path) -> int:
    spec = yaml.safe_load((root / "metrics.yaml").read_text(encoding="utf-8"))["metrics"]
    snap = latest_snapshot(root)
    out = root / RENDER_NAME
    shutil.copy(TEMPLATE, out)
    wb = load_workbook(out)
    wb["封面"]["B1"] = DEMO_BANNER
    wb["封面"]["B1"].font = Font(bold=True, color="CC0000", size=14)

    # 1.度量项清单（表头 row 1，数据 row 2 起）
    ws = wb["1.度量项清单"]
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    for i, m in enumerate(spec):
        r = i + 2
        ws.cell(row=r, column=1, value=m["id"])
        ws.cell(row=r, column=2, value=m["pa"])
        ws.cell(row=r, column=3, value=m["name"])
        ws.cell(row=r, column=4, value=m["formula"])
        ws.cell(row=r, column=5, value=f"{m['source']} → {m.get('extract') or m.get('expr')}")
        ws.cell(row=r, column=6, value="每次门禁运行")
        ws.cell(row=r, column=7, value=m["target_text"])
        ws.cell(row=r, column=8, value=m["warn_text"])
        ws.cell(row=r, column=9, value=m["action"])
        ws.cell(row=r, column=10, value=m["owner"])
        ws.cell(row=r, column=11, value="PA3.1")
        ws.cell(row=r, column=12, value=m["direction"])

    # 2.度量采集记录（全量历史）
    ws = wb["2.度量采集记录"]
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    rows = []
    hp = root / HISTORY
    if hp.exists():
        rows = [json.loads(x) for x in hp.read_text(encoding="utf-8").splitlines()]
    for i, rec in enumerate(rows):
        r = i + 2
        ws.cell(row=r, column=1, value=rec["id"])
        ws.cell(row=r, column=2, value=rec["period"])
        v = rec["value"]
        ws.cell(row=r, column=3, value=round(v, 4) if isinstance(v, float) else v)
        ws.cell(row=r, column=4, value=str(rec["target"]) if rec["target"] is not None else "—")
        ws.cell(row=r, column=5, value="是" if rec["status"] == "FAIL" else "否")
        ws.cell(row=r, column=6, value=f"{rec['source'] if 'source' in rec else rec['id']} 门禁输出")
        ws.cell(row=r, column=7, value="metrics_collect（自动）")
        ws.cell(row=r, column=8, value="数值")

    # 3.超限与纠正措施
    ws = wb["3.超限与纠正措施"]
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    n = 0
    for rec in rows:
        if rec["status"] != "FAIL":
            continue
        n += 1
        r = n + 1
        m = next(x for x in spec if x["id"] == rec["id"])
        ws.cell(row=r, column=1, value=f"MA-{n:03d}")
        ws.cell(row=r, column=2, value=rec["id"])
        ws.cell(row=r, column=3, value=rec["period"])
        ws.cell(row=r, column=4, value=f"{rec['name']} = {rec['value']}（目标 {m['target_text']}）")
        ws.cell(row=r, column=5, value="见 gate_registry 对应问题单")
        ws.cell(row=r, column=6, value=m["action"])
        ws.cell(row=r, column=7, value=m["owner"])
        ws.cell(row=r, column=8, value=rec["date"])
        ws.cell(row=r, column=9, value=rec["date"])
        ws.cell(row=r, column=10, value="门禁自动复测")
        ws.cell(row=r, column=11, value="已关闭" if rec["id"] in snap and snap[rec["id"]]["status"] != "FAIL" else "打开")

    # 4.度量汇总（写值不写字段公式）
    ws = wb["4.度量汇总"]
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    for i, m in enumerate(spec):
        r = i + 2
        hist = [x for x in rows if x["id"] == m["id"]]
        fails = sum(1 for x in hist if x["status"] == "FAIL")
        ws.cell(row=r, column=1, value=m["id"])
        ws.cell(row=r, column=2, value=m["name"])
        ws.cell(row=r, column=3, value=m["pa"])
        ws.cell(row=r, column=4, value=m["direction"])
        ws.cell(row=r, column=5, value=m["target_text"])
        ws.cell(row=r, column=6, value=m["warn_text"])
        last = hist[-1]["value"] if hist else "—"
        ws.cell(row=r, column=7, value=round(last, 4) if isinstance(last, float) else last)
        ws.cell(row=r, column=8, value=fails)
        ws.cell(row=r, column=9, value=len(hist))
        ws.cell(row=r, column=10,
                value=f"{(1 - fails / len(hist)) * 100:.0f}%" if hist else "—")
    wb.save(out)
    print(f"[RENDER] {RENDER_NAME}：{len(spec)} 度量项，{len(rows)} 条采集记录")
    return 0


def selftest() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="metrics_selftest_"))
    (tmp / "metrics.yaml").write_text(yaml.safe_dump({"metrics": [
        {"id": "M-1", "name": "t", "source": "s", "extract": "x", "rule": "lte", "target": 0}]},
        allow_unicode=True), encoding="utf-8")
    # extract / evaluate 单元断言
    d = {"a": {"b": 3}, "problems": [{"status": "打开"}, {"status": "已关闭"}, {"status": "打开"}]}
    assert extract(d, "a.b") == 3
    assert extract(d, "problems[status=打开].count") == 2
    assert extract(d, "problems.count") == 3
    assert evaluate(5, "lte", 5) == "PASS" and evaluate(6, "lte", 5) == "FAIL"
    assert evaluate(1.0, "gte", 1.0) == "PASS" and evaluate(0, "info", None) == "INFO"
    # verify_result：FAIL 快照 → errors
    (tmp / HISTORY).write_text(
        json.dumps({"date": "2026-11-06", "period": "2026-11", "id": "M-1", "name": "t",
                    "value": 5, "rule": "lte", "target": 0, "status": "FAIL"},
                   ensure_ascii=False) + "\n", encoding="utf-8")
    r = verify_result(tmp)
    assert not r["passed"] and r["errors"][0]["rule"] == "E-METRIC-OUT"
    # ① 定义 schema 校验
    (tmp / "metrics.yaml").write_text(yaml.safe_dump({"metrics": [
        {"id": "M-1", "name": "a", "source": "s", "extract": "x", "rule": "bad", "target": 0},
        {"id": "M-1", "name": "b", "source": "s", "extract": "x", "rule": "gte"},
        {"id": "M-2", "name": "c", "source": "s", "rule": "info"},
    ]}, allow_unicode=True), encoding="utf-8")
    _, def_errors = load_spec(tmp)
    msgs = " ".join(e["msg"] for e in def_errors)
    assert "重复" in msgs and "非法 rule" in msgs and "缺 target" in msgs and "仅能有其一" in msgs, msgs
    # 恢复合法定义（verify_result 会带 def_errors）
    (tmp / "metrics.yaml").write_text(yaml.safe_dump({"metrics": [
        {"id": "M-9", "name": "t", "source": "s", "extract": "x", "rule": "lte", "target": 0}]},
        allow_unicode=True), encoding="utf-8")
    # ② 连续超限升级：尾部两次 FAIL → E-METRIC-STREAK
    (tmp / HISTORY).write_text(
        "\n".join(json.dumps({"date": "d", "period": "p", "id": "M-9", "name": "t",
                              "value": v, "rule": "lte", "target": 0, "status": s},
                             ensure_ascii=False)
                  for v, s in [(1, "FAIL"), (0, "PASS"), (2, "FAIL"), (3, "FAIL")]) + "\n",
        encoding="utf-8")
    r = verify_result(tmp)
    assert any(e["rule"] == "E-METRIC-STREAK" and "连续 2 次" in e["msg"] for e in r["errors"]), r
    # 最新一条 PASS → 无升级
    (tmp / HISTORY).write_text(
        json.dumps({"date": "d", "period": "p", "id": "M-9", "name": "t",
                    "value": 0, "rule": "lte", "target": 0, "status": "PASS"},
                   ensure_ascii=False) + "\n", encoding="utf-8")
    assert verify_result(tmp)["passed"]
    print("[SELFTEST PASS] 12 组断言全部通过（路径/过滤/计数/判定/info/快照/定义校验/趋势升级）")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="MAN.1 度量采集/判定/渲染（fail-closed）")
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--json", action="store_true")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--collect", action="store_true")
    g.add_argument("--verify", action="store_true")
    g.add_argument("--render", action="store_true")
    g.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    root = args.root.resolve()
    if args.render:
        return cmd_render(root)
    if args.verify:
        result = verify_result(root)
    else:
        records = collect(root)
        fails = [r for r in records if r["status"] == "FAIL"]
        for r in records:
            v = round(r["value"], 4) if isinstance(r["value"], float) else r["value"]
            print(f"  {r['id']} {r['name']}: {v} [{r['status']}]")
        result = verify_result(root)
        print(f"[COLLECT] {len(records)} 项，FAIL {len(fails)} → history 追加")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for e in result["errors"]:
            print(f"[ERROR][{e['rule']}] {e['msg']}")
        print("结论：" + ("FAIL ❌" if not result["passed"] else "PASS ✅"))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
