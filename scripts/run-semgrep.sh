#!/usr/bin/env bash
# =============================================================================
# run-semgrep.sh — yuleOSH 本地 Semgrep SAST + 数据流分析
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

SEMGREP_CONFIGS=(
  ".semgrep/security-python.yml"
  ".semgrep/security-c.yml"
  ".semgrep/dataflow-python.yml"
)
EXIT_CODE=0

echo "🔍 yuleOSH Semgrep — SAST + 数据流分析"
echo "========================================"
echo

# Check semgrep installed
if ! command -v semgrep &>/dev/null; then
  echo "❌ semgrep not found. Install with: pip install semgrep"
  exit 1
fi

# Version
echo "📦 Semgrep version: $(semgrep --version 2>/dev/null || echo 'unknown')"
echo

# Run each config
for CONFIG in "${SEMGREP_CONFIGS[@]}"; do
  if [ ! -f "$CONFIG" ]; then
    echo "⚠️  Config not found: $CONFIG (skipping)"
    continue
  fi

  echo "━━━ Running: $CONFIG ━━━"

  semgrep \
    --config="$CONFIG" \
    --error \
    --metrics=off \
    --output=semgrep-report-$(basename "$CONFIG" .yml).txt \
    src/ 2>&1 | tail -20 || EXIT_CODE=$?

  echo
done

# Run remote rulesets
echo "━━━ Running: Remote Rulesets (OWASP Top 10) ━━━"
semgrep \
  --config=p/python \
  --config=p/owasp-top-ten \
  --config=p/command-injection \
  --config=p/sql-injection \
  --error \
  --metrics=off \
  --output=semgrep-report-remote.txt \
  src/ 2>&1 | tail -20 || true

echo
echo "========================================"
if [ $EXIT_CODE -ne 0 ]; then
  echo "⚠️  Semgrep found issues (exit code: $EXIT_CODE)"
else
  echo "✅ Semgrep passed — no blocking issues"
fi
echo "📄 Reports written to: semgrep-report-*.txt"
exit $EXIT_CODE
