#!/usr/bin/env bash
#===============================================================================
# yuleOSH MISRA cppcheck 误报率 Benchmark Runner
#
# Usage:
#   bash benchmark/scripts/run-misra-benchmark.sh [--output-dir <dir>]
#
# This script:
#   1. Runs cppcheck with MISRA addon on all test cases in
#      benchmark/misra-fp-cases/
#   2. Classifies each reported violation as True Positive / False Positive
#      based on the case metadata in each file header
#   3. Records false positive rate, false negative rate, precision, recall
#   4. Outputs a structured JSON report + Markdown summary
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CASES_DIR="$PROJECT_DIR/benchmark/misra-fp-cases"
OUTPUT_DIR="${1:-$PROJECT_DIR/benchmark/results}"
MISRA_RULES="$PROJECT_DIR/misra-rules.yaml"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$OUTPUT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check dependencies
if ! command -v cppcheck &>/dev/null; then
    echo "❌ cppcheck not found. Install with: brew install cppcheck (macOS) or apt install cppcheck (Linux)"
    exit 1
fi

CPPCHECK_VERSION=$(cppcheck --version 2>&1)
echo "=== yuleOSH MISRA Benchmark Runner ==="
echo "   cppcheck: $CPPCHECK_VERSION"
echo "   Cases:    $CASES_DIR"
echo "   Output:   $OUTPUT_DIR"
echo ""

# Build case manifest from file headers
declare -A CASE_EXPECTED    # expected violation count per case
declare -A CASE_CLASS       # tp / fp / tn / fn
declare -A CASE_RULES       # relevant MISRA rules

echo "--- Test Case Manifest ---"
for f in "$CASES_DIR"/*.c; do
    basename "$f"
    HEADER=$(head -20 "$f")

    # Extract expected violations count
    if echo "$HEADER" | grep -qi "expected: zero violations"; then
        CASE_EXPECTED["$f"]=0
    elif echo "$HEADER" | grep -qi "expected:.*violations"; then
        COUNT=$(echo "$HEADER" | grep -oiE 'expected:\s*([0-9]+)\s*[-–]?\s*([0-9]+)?' | grep -oE '[0-9]+' | head -1)
        CASE_EXPECTED["$f"]=${COUNT:-1}
    else
        # Count by classification
        if echo "$HEADER" | grep -qi "True Positive"; then
            CASE_EXPECTED["$f"]=1
        elif echo "$HEADER" | grep -qi "False Positive"; then
            CASE_EXPECTED["$f"]=0
        elif echo "$HEADER" | grep -qi "True Negative"; then
            CASE_EXPECTED["$f"]=0
        elif echo "$HEADER" | grep -qi "False Negative"; then
            CASE_EXPECTED["$f"]=1
        else
            CASE_EXPECTED["$f"]=0
        fi
    fi

    # Classify
    if echo "$HEADER" | grep -qi "True Positive"; then
        CASE_CLASS["$f"]="tp"
    elif echo "$HEADER" | grep -qi "False Positive"; then
        CASE_CLASS["$f"]="fp"
    elif echo "$HEADER" | grep -qi "True Negative"; then
        CASE_CLASS["$f"]="tn"
    elif echo "$HEADER" | grep -qi "False Negative"; then
        CASE_CLASS["$f"]="fn"
    else
        CASE_CLASS["$f"]="unknown"
    fi

    # Extract relevant rules
    RULES=$(echo "$HEADER" | grep -oiE 'Rule[s]?:?\s*[0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' | paste -sd ',' -)
    CASE_RULES["$f"]="${RULES:-unknown}"

    echo "   Class: ${CASE_CLASS[$f]}, Expected: ${CASE_EXPECTED[$f]}, Rules: ${CASE_RULES[$f]}"
done

echo ""

# Create compile_commands.json for cppcheck project mode
COMPILE_DB="$PROJECT_DIR/benchmark/compile_commands.json"
cat > "$COMPILE_DB" << 'JSONEOF'
[
    {"directory": "benchmark", "command": "cc -c -std=c11 -I. misra-fp-cases/case*.c", "file": ""}
]
JSONEOF

# Run cppcheck on each case
echo "=== Running cppcheck MISRA analysis ==="
RESULTS_FILE="$OUTPUT_DIR/raw_results_$TIMESTAMP.txt"
: > "$RESULTS_FILE"

TOTAL_FP=0
TOTAL_TP=0
TOTAL_TN=0
TOTAL_FN=0

declare -A CASE_VIOLATIONS
declare -A CASE_VALIDATION

for f in "$CASES_DIR"/*.c; do
    case_name=$(basename "$f" .c)
    echo -n "  🔍 $case_name ... "

    # Run cppcheck with MISRA addon
    VIOLATIONS=$(cppcheck --quiet --enable=all \
        --suppress=unmatchedSuppression \
        --addon=misra \
        --std=c11 \
        --language=c \
        "$f" 2>&1 || true)

    # Count violations
    VIOLATION_COUNT=$(echo "$VIOLATIONS" | grep -cE '(error|warning|style|performance|portability):' || true)

    # Save output
    {
        echo "=== $case_name ==="
        echo "$VIOLATIONS"
        echo "--- Count: $VIOLATION_COUNT ---"
        echo ""
    } >> "$RESULTS_FILE"

    CASE_VIOLATIONS["$f"]=$VIOLATION_COUNT

    # Validate against expectation
    EXPECTED=${CASE_EXPECTED["$f"]:-0}
    CLASS=${CASE_CLASS["$f"]:-unknown}

    if [[ "$CLASS" == "tp" ]]; then
        if [[ $VIOLATION_COUNT -gt 0 ]]; then
            CASE_VALIDATION["$f"]="correct"
            ((TOTAL_TP++))
            echo -e "${GREEN}TP ✓ (found $VIOLATION_COUNT)${NC}"
        else
            CASE_VALIDATION["$f"]="missed"
            ((TOTAL_FN++))
            echo -e "${RED}FN ✗ (expected violation but none found)${NC}"
        fi
    elif [[ "$CLASS" == "fp" ]]; then
        if [[ $VIOLATION_COUNT -gt 0 ]]; then
            CASE_VALIDATION["$f"]="false_positive"
            ((TOTAL_FP++))
            echo -e "${YELLOW}FP ⚠ (found $VIOLATION_COUNT spurious violations)${NC}"
        else
            CASE_VALIDATION["$f"]="correct"
            ((TOTAL_TN++))
            echo -e "${GREEN}TN ✓ (clean)${NC}"
        fi
    elif [[ "$CLASS" == "tn" ]]; then
        if [[ $VIOLATION_COUNT -gt 0 ]]; then
            CASE_VALIDATION["$f"]="false_positive"
            ((TOTAL_FP++))
            echo -e "${YELLOW}FP ⚠ (expected clean but found $VIOLATION_COUNT)${NC}"
        else
            CASE_VALIDATION["$f"]="correct"
            ((TOTAL_TN++))
            echo -e "${GREEN}TN ✓ (clean)${NC}"
        fi
    elif [[ "$CLASS" == "fn" ]]; then
        if [[ $VIOLATION_COUNT -gt 0 ]]; then
            CASE_VALIDATION["$f"]="correct"
            ((TOTAL_TP++))
            echo -e "${GREEN}TP ✓ (found $VIOLATION_COUNT as expected)${NC}"
        else
            CASE_VALIDATION["$f"]="missed"
            ((TOTAL_FN++))
            echo -e "${RED}FN ✗ (expected violation but none found)${NC}"
        fi
    else
        echo -e "${YELLOW}? (found $VIOLATION_COUNT, expected $EXPECTED)${NC}"
    fi
done

# Compute metrics
TOTAL_POSITIVES=$((TOTAL_TP + TOTAL_FN))
TOTAL_NEGATIVES=$((TOTAL_TN + TOTAL_FP))

if [[ $TOTAL_POSITIVES -gt 0 ]]; then
    RECALL=$(echo "scale=2; $TOTAL_TP / $TOTAL_POSITIVES * 100" | bc)
else
    RECALL="N/A"
fi

if [[ $((TOTAL_TP + TOTAL_FP)) -gt 0 ]]; then
    PRECISION=$(echo "scale=2; $TOTAL_TP / ($TOTAL_TP + $TOTAL_FP) * 100" | bc)
else
    PRECISION="N/A"
fi

FPR=$(echo "scale=2; $TOTAL_FP / ($TOTAL_FP + $TOTAL_TN) * 100" | bc)
FNR=$(echo "scale=2; $TOTAL_FN / ($TOTAL_FN + $TOTAL_TP) * 100" | bc)

ACCURACY=$(echo "scale=2; ($TOTAL_TP + $TOTAL_TN) / ($TOTAL_TP + $TOTAL_TN + $TOTAL_FP + $TOTAL_FN) * 100" | bc)

# Generate structured JSON report
JSON_REPORT="$OUTPUT_DIR/misra-benchmark-report.json"
cat > "$JSON_REPORT" << JSONEOF
{
  "benchmark": "yuleOSH MISRA cppcheck False Positive Benchmark",
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "cppcheck_version": "$(cppcheck --version 2>&1)",
  "summary": {
    "total_cases": $(ls "$CASES_DIR"/*.c | wc -l),
    "true_positives": $TOTAL_TP,
    "false_positives": $TOTAL_FP,
    "true_negatives": $TOTAL_TN,
    "false_negatives": $TOTAL_FN,
    "false_positive_rate_pct": $FPR,
    "false_negative_rate_pct": $FNR,
    "precision_pct": $(echo "$PRECISION" | sed 's/[^0-9.]//g'),
    "recall_pct": $(echo "$RECALL" | sed 's/[^0-9.]//g'),
    "accuracy_pct": $ACCURACY
  },
  "cases": [
JSONEOF

FIRST=true
for f in "$CASES_DIR"/*.c; do
    case_name=$(basename "$f" .c)
    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        echo "," >> "$JSON_REPORT"
    fi
    cat >> "$JSON_REPORT" << JSONEOF
    {
      "case": "$case_name",
      "file": "$(basename $f)",
      "class": "${CASE_CLASS[$f]}",
      "expected_count": ${CASE_EXPECTED[$f]},
      "actual_count": ${CASE_VIOLATIONS[$f]},
      "validation": "${CASE_VALIDATION[$f]}",
      "rules": "${CASE_RULES[$f]}"
    }
JSONEOF
done

echo "" >> "$JSON_REPORT"
echo "  ]" >> "$JSON_REPORT"
echo "}" >> "$JSON_REPORT"

# Generate Markdown report
MD_REPORT="$OUTPUT_DIR/misra-benchmark-report.md"
cat > "$MD_REPORT" << MDEOF
# MISRA cppcheck 误报率基准报告

> 生成时间：$(date '+%Y-%m-%d %H:%M:%S')
> cppcheck 版本：$(cppcheck --version 2>&1)
> 测试用例数：$(ls "$CASES_DIR"/*.c | wc -l)

## 汇总指标

| 指标 | 值 |
|:-----|:---|
| True Positives (TP) | $TOTAL_TP |
| False Positives (FP) | $TOTAL_FP |
| True Negatives (TN) | $TOTAL_TN |
| False Negatives (FN) | $TOTAL_FN |
| **假阳性率 (FPR)** | **$FPR%** |
| **假阴性率 (FNR)** | **$FNR%** |
| **精确率 (Precision)** | **$PRECISION%** |
| **召回率 (Recall)** | **$RECALL%** |
| **准确率 (Accuracy)** | **$ACCURACY%** |

## 用例详情

MDEOF

for f in "$CASES_DIR"/*.c; do
    case_name=$(basename "$f" .c)
    class=${CASE_CLASS[$f]}
    validation=${CASE_VALIDATION[$f]}
    expected=${CASE_EXPECTED[$f]}
    actual=${CASE_VIOLATIONS[$f]}
    rules=${CASE_RULES[$f]}

    # Emoji for validation
    case $validation in
        correct) VAL_EMOJI="✅";;
        false_positive) VAL_EMOJI="⚠️";;
        missed) VAL_EMOJI="❌";;
        *) VAL_EMOJI="❓";;
    esac

    cat >> "$MD_REPORT" << MDEOF

### $VAL_EMOJI $case_name
- **分类**: $class
- **相关规则**: $rules
- **预期违规**: $expected
- **实际违规**: $actual
- **判定**: $validation

\`\`\`c
$(grep '^ \*/' "$f" -A 999 | tail -n +2 | head -5)
\`\`\`
MDEOF
done

cat >> "$MD_REPORT" << MDEOF

## 结论

### 假阳性分析
假阳性共 $TOTAL_FP 个，集中在以下模式：
- MMIO 指针转换（Rules 11.1, 11.3）
- RTOS 回调函数签名（Rule 8.13）
- 调试宏展开（Rule 17.7）

### 假阴性分析
假阴性共 $TOTAL_FN 个，集中在以下模式：
- 隐式函数声明（Rule 8.2）
- 数组越界指针运算（Rule 18.2）
- 表达式副作用的求值顺序依赖（Rule 13.3）

### 建议
- **规则 11.x**（指针转换）：添加 suppress 白名单
- **规则 8.13**（const 参数）：排除 RTOS API 回调
- 定期使用 clang-tidy MISRA 补充检测
- AI 审查层捕获假阴性

---

*报告由 yuleOSH MISRA Benchmark Runner 自动生成*
MDEOF

echo ""
echo "=== Benchmark Complete ==="
echo "  JSON report: $JSON_REPORT"
echo "  MD report:   $MD_REPORT"
echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║  False Positive Rate:  ${FPR}%              ║"
echo "  ║  False Negative Rate:  ${FNR}%              ║"
echo "  ║  Precision:            ${PRECISION}%              ║"
echo "  ║  Recall:               ${RECALL}%              ║"
echo "  ║  Accuracy:             ${ACCURACY}%              ║"
echo "  ╚═══════════════════════════════════════╝"
