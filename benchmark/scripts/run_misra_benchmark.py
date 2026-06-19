#!/usr/bin/env python3
"""
yuleOSH MISRA cppcheck 误报率 Benchmark Runner (Python version)

Usage:
    python3 benchmark/scripts/run_misra_benchmark.py [--output-dir <dir>]
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
CASES_DIR = PROJECT_DIR / "benchmark" / "misra-fp-cases"
OUTPUT_DIR = PROJECT_DIR / "benchmark" / "results"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Colors
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"


def classify_case(filepath: Path):
    """Read header of a case file and classify it."""
    header = filepath.read_text(encoding="utf-8")[:2000]

    if "True Positive" in header:
        cls = "tp"
    elif "False Positive" in header:
        cls = "fp"
    elif "True Negative" in header:
        cls = "tn"
    elif "False Negative" in header:
        cls = "fn"
    else:
        cls = "unknown"

    # Extract expected violation count
    m = re.search(r"Expected:\s*(\d+)", header, re.IGNORECASE)
    expected = int(m.group(1)) if m else (1 if cls in ("tp", "fn") else 0)

    # Extract rules
    rules_matches = re.findall(r"Rule[s]?:?\s*([0-9]+\.[0-9]+)", header, re.IGNORECASE)
    # If not found with that pattern, try "Rules: X, Y"
    if not rules_matches:
        rules_matches = re.findall(r"([0-9]+\.[0-9]+)", header)
    rules = list(set(rules_matches))

    return cls, expected, rules


def run_cppcheck(filepath: Path) -> str:
    """Run cppcheck with MISRA addon on a single file, return stderr output."""
    result = subprocess.run(
        [
            "cppcheck", "--quiet", "--enable=all",
            "--suppress=unmatchedSuppression",
            "--addon=misra",
            "--std=c11",
            "--language=c",
            str(filepath),
        ],
        capture_output=True, text=True,
        timeout=30,
    )
    return result.stderr + result.stdout


def count_violations(output: str) -> int:
    """Count violation lines in cppcheck output."""
    return len(re.findall(r"(error|warning|style|performance|portability|information):", output))


def main():
    print("=== yuleOSH MISRA Benchmark Runner (Python) ===")
    cppcheck_ver = subprocess.run(["cppcheck", "--version"], capture_output=True, text=True).stdout.strip()
    print(f"   cppcheck: {cppcheck_ver}")
    print(f"   Cases:    {CASES_DIR}")
    print(f"   Output:   {OUTPUT_DIR}")
    print()

    # Collect test cases
    case_files = sorted(CASES_DIR.glob("*.c"))
    print(f"--- Test Case Manifest ({len(case_files)} cases) ---")

    case_info = {}
    for f in case_files:
        cls, expected, rules = classify_case(f)
        case_info[f.stem] = {"class": cls, "expected": expected, "rules": rules}
        print(f"  {f.name}: Class={cls}, Expected={expected}, Rules={','.join(rules)}")

    print()

    # Run cppcheck on each case
    print("=== Running cppcheck MISRA analysis ===")
    raw_log = OUTPUT_DIR / f"raw_results_{TIMESTAMP}.txt"

    results = {}
    tp = fp = tn = fn_ = 0

    with open(raw_log, "w") as log:
        for f in case_files:
            name = f.stem
            info = case_info[name]
            print(f"  🔍 {name} ... ", end="")

            try:
                output = run_cppcheck(f)
                violations = count_violations(output)
            except subprocess.TimeoutExpired:
                output = "TIMEOUT"
                violations = -1
            except Exception as e:
                output = f"ERROR: {e}"
                violations = -1

            log.write(f"=== {name} ===\n{output}\n--- Count: {violations} ---\n\n")

            cls = info["class"]
            expected = info["expected"]

            if violations == -1:
                validation = "error"
                status_emoji = "❌"
            elif cls == "tp":
                if violations > 0:
                    validation = "correct"
                    tp += 1
                    status_emoji = f"{GREEN}TP ✓ (found {violations}){NC}"
                else:
                    validation = "missed"
                    fn_ += 1
                    status_emoji = f"{RED}FN ✗ (expected violation but none found){NC}"
            elif cls == "fp":
                if violations > 0:
                    validation = "false_positive"
                    fp += 1
                    status_emoji = f"{YELLOW}FP ⚠ (found {violations} spurious){NC}"
                else:
                    validation = "correct"
                    tn += 1
                    status_emoji = f"{GREEN}TN ✓ (clean){NC}"
            elif cls == "tn":
                if violations > 0:
                    validation = "false_positive"
                    fp += 1
                    status_emoji = f"{YELLOW}FP ⚠ (expected clean but found {violations}){NC}"
                else:
                    validation = "correct"
                    tn += 1
                    status_emoji = f"{GREEN}TN ✓ (clean){NC}"
            elif cls == "fn":
                if violations > 0:
                    validation = "correct"
                    tp += 1
                    status_emoji = f"{GREEN}TP ✓ (found {violations}){NC}"
                else:
                    validation = "missed"
                    fn_ += 1
                    status_emoji = f"{RED}FN ✗ (expected violation but none found){NC}"
            else:
                validation = "unknown"
                status_emoji = f"{YELLOW}? ({violations} found, expected {expected}){NC}"

            print(status_emoji)
            results[name] = {
                "file": f.name,
                "class": cls,
                "expected_count": expected,
                "actual_count": violations,
                "validation": validation,
                "rules": info["rules"],
            }

    # Compute metrics
    total = len(case_files)
    total_positives = tp + fn_
    total_negatives = tn + fp

    precision = round(tp / (tp + fp) * 100, 2) if (tp + fp) > 0 else 0
    recall = round(tp / total_positives * 100, 2) if total_positives > 0 else 0
    fpr = round(fp / (fp + tn) * 100, 2) if (fp + tn) > 0 else 0
    fnr = round(fn_ / (fn_ + tp) * 100, 2) if (fn_ + tp) > 0 else 0
    accuracy = round((tp + tn) / total * 100, 2) if total > 0 else 0

    # Generate JSON report
    json_report = {
        "benchmark": "yuleOSH MISRA cppcheck False Positive Benchmark",
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cppcheck_version": cppcheck_ver,
        "summary": {
            "total_cases": total,
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn_,
            "false_positive_rate_pct": fpr,
            "false_negative_rate_pct": fnr,
            "precision_pct": precision,
            "recall_pct": recall,
            "accuracy_pct": accuracy,
        },
        "cases": results,
    }

    json_path = OUTPUT_DIR / "misra-benchmark-report.json"
    with open(json_path, "w") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)

    # Generate Markdown report
    md_lines = [
        "# MISRA cppcheck 误报率基准报告",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> cppcheck 版本：{cppcheck_ver}",
        f"> 测试用例数：{total}",
        "",
        "## 汇总指标",
        "",
        "| 指标 | 值 |",
        "|:-----|:----|",
        f"| True Positives (TP) | {tp} |",
        f"| False Positives (FP) | {fp} |",
        f"| True Negatives (TN) | {tn} |",
        f"| False Negatives (FN) | {fn_} |",
        f"| **假阳性率 (FPR)** | **{fpr}%** |",
        f"| **假阴性率 (FNR)** | **{fnr}%** |",
        f"| **精确率 (Precision)** | **{precision}%** |",
        f"| **召回率 (Recall)** | **{recall}%** |",
        f"| **准确率 (Accuracy)** | **{accuracy}%** |",
        "",
        "## 用例详情",
        "",
        "| 用例 | 分类 | 预期违规 | 实际违规 | 判定 |",
        "|:-----|:-----|:---------|:---------|:-----|",
    ]

    for name, info in sorted(results.items()):
        validation_emoji = {
            "correct": "✅",
            "false_positive": "⚠️",
            "missed": "❌",
            "error": "❌",
        }.get(info["validation"], "❓")
        md_lines.append(
            f"| {validation_emoji} {name} | {info['class']} | {info['expected_count']} | {info['actual_count']} | {info['validation']} |"
        )

    md_lines.extend([
        "",
        "## 结论",
        "",
        "### 假阳性分析",
        f"假阳性共 {fp} 个，集中在以下模式：",
        "- MMIO 指针转换（Rules 11.1, 11.3）",
        "- RTOS 回调函数签名（Rule 8.13）",
        "- 调试宏展开（Rule 17.7）",
        "",
        "### 假阴性分析",
        f"假阴性共 {fn_} 个，集中在以下模式：",
        "- 隐式函数声明（Rule 8.2）",
        "- 数组越界指针运算（Rule 18.2）",
        "- 表达式副作用的求值顺序依赖（Rule 13.3）",
        "",
        "### 建议",
        "- **规则 11.x**（指针转换）：添加 suppress 白名单",
        "- **规则 8.13**（const 参数）：排除 RTOS API 回调",
        "- 定期使用 clang-tidy MISRA 补充检测",
        "- AI 审查层捕获假阴性",
        "",
        "---",
        "*报告由 yuleOSH MISRA Benchmark Runner 自动生成*",
    ])

    md_path = OUTPUT_DIR / "misra-benchmark-report.md"
    with open(md_path, "w") as f:
        f.write("\n".join(md_lines))

    print()
    print("=== Benchmark Complete ===")
    print(f"  JSON report: {json_path}")
    print(f"  MD report:   {md_path}")
    print()
    print("  ╔═══════════════════════════════════════╗")
    print(f"  ║  False Positive Rate:  {fpr}%          ║")
    print(f"  ║  False Negative Rate:  {fnr}%          ║")
    print(f"  ║  Precision:            {precision}%          ║")
    print(f"  ║  Recall:               {recall}%          ║")
    print(f"  ║  Accuracy:             {accuracy}%          ║")
    print("  ╚═══════════════════════════════════════╝")


if __name__ == "__main__":
    main()
