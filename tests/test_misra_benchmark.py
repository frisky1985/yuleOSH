#!/usr/bin/env python3
"""
MISRA 误报率/漏报率基准测试 (Benchmark).

统计指标:
    TP (True Positive):  正确检测到的违规
    FP (False Positive): 误报（clean code 上检测到违规）
    FN (False Negative): 漏报（known positive 上未检测到预期违规）
    Precision = TP / (TP + FP)
    Recall    = TP / (TP + FN)
    F1        = 2 * Precision * Recall / (Precision + Recall)

用法:
    python3 -m pytest tests/test_misra_benchmark.py -v --tb=short

设计:
    - known-positives/ 中的 C 文件标记了预期的 MISRA 规则（// expected: misra-c2023-XX.X）
    - clean-code/ 中的 C 文件预期无任何 MISRA 违规
    - 通过 cppcheck --addon=misra 实际扫描，与预期结果比对
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# ── 路径 ──────────────────────────────────────────────────────────────
BENCH_DIR = Path(__file__).resolve().parent / "benchmarks" / "misra-false-positive"
KNOWN_POSITIVES_DIR = BENCH_DIR / "known-positives"
CLEAN_CODE_DIR = BENCH_DIR / "clean-code"
EXPECTED_RESULTS_PATH = BENCH_DIR / "expected-results.yaml"

# cppcheck MISRA 规则匹配 — 输出格式 example:
#   src/main.c:42:5: style: misra violation (use --rule-texts=...) [misra-c2012-17.7]
_RULE_PATTERN = re.compile(r"\[misra-c(\d{4})-(\d+\.\d+)\]")

# 用于统一版本号：将所有检测结果归一到 misra-c2023-* 命名空间
_MISRA_YEAR_MAP = {"2012": "2023"}

# ── 全局统计累加器 ──────────────────────────────────────────────────────
# 用模块级 dict 让所有 test 函数能写入，pytest 结束后打印汇总报告
_bench_stats = {"tp": 0, "fp": 0, "fn": 0, "total_scenarios": 0}


def _normalize_rule_id(rule_id: str) -> str:
    """将 misra-c2012-XX.X 归一化为 misra-c2023-XX.X。

    cppcheck 2.17 的 misra addon 仍输出 misra-c2012-* 格式，
    而预期结果使用 misra-c2023-*（当前标准）。此函数做归一化。
    """
    m = re.match(r"misra-c(\d{4})-(\d+\.\d+)", rule_id)
    if not m:
        return rule_id
    year = _MISRA_YEAR_MAP.get(m.group(1), m.group(1))
    return f"misra-c{year}-{m.group(2)}"


def _run_cppcheck(c_file: Path) -> set[str]:
    """在给定 C 文件上运行 cppcheck --addon=misra，返回检测到的归一化规则 ID 集合。"""
    cmd = [
        "cppcheck",
        "--addon=misra",
        "--language=c",
        "--std=c11",
        "--enable=all",
        "--suppress=missingIncludeSystem",
        "-q",
        str(c_file),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
    except FileNotFoundError:
        pytest.fail("cppcheck 未安装 — 请先安装 cppcheck")
    except subprocess.TimeoutExpired:
        pytest.fail(f"cppcheck 超时: {c_file.name}")

    output = result.stderr or result.stdout or ""
    detected: set[str] = set()
    for m in _RULE_PATTERN.finditer(output):
        raw_rule = f"misra-c{m.group(1)}-{m.group(2)}"
        detected.add(_normalize_rule_id(raw_rule))
    return detected


def _load_expected() -> dict:
    """加载 expected-results.yaml。"""
    with open(EXPECTED_RESULTS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Known-Positive 测试（检查 Recall — 漏报） ──────────────────────────
# 参数化：每个 .c 文件在 expected-results.yaml 中查找预期规则列表，
# 运行 cppcheck 检测，比对预期 vs 实际。

def _list_known_positive_cases():
    """读取 known-positives/ 目录文件并构建 (file, expected_rules) 对。"""
    expected_data = _load_expected().get("known_positives", {})
    cases = []
    for c_file in sorted(KNOWN_POSITIVES_DIR.glob("*.c")):
        exp_rules = expected_data.get(c_file.name, [])
        cases.append(pytest.param(c_file, exp_rules, id=c_file.stem))
    return cases


@pytest.mark.parametrize("c_file,expected_rules", _list_known_positive_cases())
def test_known_positive(c_file, expected_rules):
    """已知违规场景 — 检查所有预期规则是否被 cppcheck 检测到。"""
    detected = _run_cppcheck(c_file)
    expected_set = set(expected_rules)

    # TP: 预期且检测到的规则
    tp_rules = expected_set & detected
    # FN: 预期但未检测到的规则
    fn_rules = expected_set - detected

    _bench_stats["tp"] += len(tp_rules)
    _bench_stats["fn"] += len(fn_rules)
    _bench_stats["total_scenarios"] += len(expected_rules) if expected_rules else 1

    # 如果存在漏报，打印详细信息
    if fn_rules:
        extra = detected - expected_set
        detail = (
            f"\n  {'='*50}\n"
            f"  File: {c_file.name}\n"
            f"  Expected rules: {sorted(expected_set)}\n"
            f"  Detected rules: {sorted(detected)}\n"
            f"  Missed (FN):    {sorted(fn_rules)}\n"
            f"  Extra:          {sorted(extra)}\n"
            f"  {'='*50}"
        )
        pytest.fail(
            f"漏报 (FN): cppcheck 未检测到预期规则 {sorted(fn_rules)}{detail}"
        )


# ── Clean-Code 测试（检查 FP — 误报） ──────────────────────────────────

def _list_clean_code_cases():
    """读取 clean-code/ 目录文件。"""
    expected_data = _load_expected().get("clean_code", {})
    cases = []
    for c_file in sorted(CLEAN_CODE_DIR.glob("*.c")):
        cases.append(pytest.param(c_file, id=c_file.stem))
    return cases


@pytest.mark.parametrize("c_file", _list_clean_code_cases())
def test_clean_code(c_file):
    """干净代码场景 — 预期无任何 MISRA 违规。"""
    detected = _run_cppcheck(c_file)

    if detected:
        _bench_stats["fp"] += len(detected)
        pytest.fail(
            f"误报 (FP) — 干净代码 '{c_file.name}' 中检测到违规:\n"
            f"  Detected: {sorted(detected)}"
        )

    _bench_stats["total_scenarios"] += 1


# ── 汇总报告 ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def _print_benchmark_report(request):
    """所有测试执行完毕后打印 benchmark 汇总报告。"""
    yield
    # 仅在主动运行 benchmark 时才打印报告，而非被 import 时
    _print_report()


def _print_report():
    """计算并打印 MISRA Benchmark Report。"""
    tp = _bench_stats["tp"]
    fp = _bench_stats["fp"]
    fn = _bench_stats["fn"]
    total = _bench_stats["total_scenarios"]

    if total == 0:
        return

    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    report = f"""
{'='*46}
   MISRA Benchmark Report
{'='*46}
  Scenarios: {total}
  TP: {tp} | FP: {fp} | FN: {fn}
  Precision: {precision:.1f}%
  Recall:    {recall:.1f}%
  F1 Score:  {f1:.1f}%
{'='*46}
    """
    print(report)


# ── 独立运行入口 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    """直接运行时执行完整 benchmark 并打印报告。"""
    print("Running MISRA false-positive benchmark...\n")

    expected = _load_expected()
    tp = fp = fn = total = 0

    # 1) Known positives
    for c_file in sorted(KNOWN_POSITIVES_DIR.glob("*.c")):
        detected = _run_cppcheck(c_file)
        expected_rules = set(expected.get("known_positives", {}).get(c_file.name, []))
        tp += len(expected_rules & detected)
        fn += len(expected_rules - detected)
        total += len(expected_rules) if expected_rules else 1

        missed = expected_rules - detected
        if missed:
            print(f"  ⚠ FN [{c_file.stem}]: missed {sorted(missed)}")

    # 2) Clean code
    for c_file in sorted(CLEAN_CODE_DIR.glob("*.c")):
        detected = _run_cppcheck(c_file)
        fp += len(detected)
        total += 1
        if detected:
            print(f"  ⚠ FP [{c_file.stem}]: false positive {sorted(detected)}")

    # 3) Report
    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    print(f"\n{'='*46}")
    print(f"   MISRA Benchmark Report")
    print(f"{'='*46}")
    print(f"  Scenarios: {total}")
    print(f"  TP: {tp} | FP: {fp} | FN: {fn}")
    print(f"  Precision: {precision:.1f}%")
    print(f"  Recall:    {recall:.1f}%")
    print(f"  F1 Score:  {f1:.1f}%")
    print(f"{'='*46}")
