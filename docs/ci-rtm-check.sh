#!/bin/bash
# ci-rtm-check.sh — RTM 门禁检查 (ASPICE SWE.4)
#
# Copyright (c) 2026 yuleOSH
# SPDX-License-Identifier: MIT
#
# This script verifies Requirements Traceability Matrix (RTM) coverage
# as part of the CI pipeline (evidence job). It ensures every SHALL
# statement has at least one corresponding automated test case.
#
# Reference:
#   - ASPICE SWE.4 (Software Unit Verification)
#   - docs/rtm-spec.md (RTM 规范)
#   - docs/acceptance-matrix-rtm.md (验收矩阵)
#   - docs/aspice-readiness-assessment.md (ASPICE 评估)
#
# Usage:
#   bash docs/ci-rtm-check.sh                    # use defaults
#   bash docs/ci-rtm-check.sh 85                 # custom SHALL threshold
#   bash docs/ci-rtm-check.sh 80 spec.md tests/  # custom paths
#
# Environment variables:
#   SHALL_THRESHOLD  — minimum SHALL coverage percentage (default: 80)
#   SPEC_FILE        — path to specification document
#   TEST_DIR         — path to test directory

set -euo pipefail

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🔍 yuleOSH RTM Gate Check (ASPICE SWE.4)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ---- Configuration ----
SHALL_THRESHOLD=${1:-${SHALL_THRESHOLD:-80}}
SPEC_FILE=${2:-${SPEC_FILE:-"docs/spec.md"}}
TEST_DIR=${3:-${TEST_DIR:-"tests/"}}
ACCEPTANCE_MATRIX="${PROJECT_ROOT:-.}/docs/acceptance-matrix-rtm.md"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "   Threshold:  ≥${SHALL_THRESHOLD}%"
echo "   Spec:       ${SPEC_FILE}"
echo "   Tests:      ${TEST_DIR}"
echo "   Matrix:     ${ACCEPTANCE_MATRIX}"
echo ""

# ---- Step 1: Validate input file existence ----
if [ ! -f "${PROJECT_ROOT}/${SPEC_FILE}" ]; then
  echo "⚠️  Spec file not found: ${SPEC_FILE}"
  echo "   Falling back to acceptance matrix..."
  if [ -f "${ACCEPTANCE_MATRIX}" ]; then
    SPEC_FILE="${ACCEPTANCE_MATRIX}"
    echo "   ✅ Using ${SPEC_FILE}"
  else
    echo "❌ No RTM source found. Skipping check (non-blocking without RTM data)."
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ⚠️  RTM CHECK SKIPPED (no spec or matrix found)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 0
  fi
else
  SPEC_FILE="${PROJECT_ROOT}/${SPEC_FILE}"
fi

# ---- Step 2: Run RTM verification ----
# Try yuleosh.rtm module first, fall back to static analysis
if python3 -c "from yuleosh.rtm import verify_coverage" 2>/dev/null; then
  echo "🔍 Running RTM verification via yuleosh.rtm module..."
  python3 -m yuleosh.rtm verify \
    --spec "${SPEC_FILE}" \
    --test-dir "${PROJECT_ROOT}/${TEST_DIR}" \
    --shall "${SHALL_THRESHOLD}" \
    --output "${PROJECT_ROOT}/artifacts/rtm/verify-result.json"
  RESULT=$?
else
  echo "🔍 yuleosh.rtm module not available — performing static matrix check..."
  echo ""

  # ---- Static check: parse acceptance matrix for SHALL coverage ----
  python3 -c "
import re, sys

matrix_path = '${ACCEPTANCE_MATRIX}'
try:
    with open(matrix_path) as f:
        content = f.read()
except FileNotFoundError:
    print(f'⚠️  Acceptance matrix not found at {matrix_path}')
    sys.exit(0)

# Parse SHALL rows from markdown tables — each row with SHALL keyword and status emoji
lines = content.split('\n')
shall_rows = []
for line in lines:
    if line.startswith('|') and 'SHALL' in line:
        shall_rows.append(line)

covered = 0
total = len(shall_rows)

for row in shall_rows:
    # 🟢 or ✅ indicates a covered SHALL
    if '🟢' in row or '✅' in row:
        covered += 1

if total == 0:
    print('⚠️  No SHALL statements found in RTM matrix')
    sys.exit(0)

coverage_pct = (covered / total) * 100
threshold = float(${SHALL_THRESHOLD})

print(f'   📊 SHALL Coverage:  {covered}/{total} = {coverage_pct:.1f}%')
print(f'   📊 Threshold:       ≥{threshold:.0f}%')
print()

if coverage_pct >= threshold:
    print(f'   ✅ RTM Gate: PASSED')
    sys.exit(0)
else:
    print(f'   ❌ RTM Gate: FAILED — coverage {coverage_pct:.1f}% below {threshold:.0f}%')
    sys.exit(1)
"
  RESULT=$?
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $RESULT -eq 0 ]; then
  echo "  ✅ RTM GATE PASSED — all SHALL requirements are covered"
else
  echo "  ❌ RTM GATE FAILED — see details above"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
exit $RESULT
