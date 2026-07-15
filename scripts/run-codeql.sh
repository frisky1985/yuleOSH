#!/usr/bin/env bash
# =============================================================================
# run-codeql.sh — yuleOSH 本地 CodeQL 深度安全分析
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

EXIT_CODE=0

echo "🔍 yuleOSH CodeQL — 深度安全 + 数据流分析"
echo "============================================"
echo

# Check codeql installed
if ! command -v codeql &>/dev/null; then
  echo "❌ codeql CLI not found. Install:"
  echo "   brew install github/codeql-cli/codeql"
  echo "   or download from: https://github.com/github/codeql-cli-binaries"
  exit 1
fi

echo "📦 CodeQL version: $(codeql version 2>/dev/null | head -1)"
echo

# Ensure CodeQL pack is initialized
if [ ! -d ".codeql" ]; then
  echo "📦 Initializing CodeQL pack..."
  # We use the CodeQL standard library, no pack init needed for simple queries
fi

# Determine database dir
DB_DIR=".codeql-db"

# ---------- Python Analysis ----------
if [ -d "src/" ]; then
  echo "━━━ CodeQL: Python 分析 ━━━"

  # Create CodeQL database from source
  echo "→ 创建数据库..."
  rm -rf "$DB_DIR"
  codeql database create "$DB_DIR" \
    --language=python \
    --source-root=. \
    --overwrite 2>&1 || { echo "⚠️  CodeQL database creation failed"; exit 1; }

  # Run standard queries
  echo "→ 运行安全查询 (security-extended)..."
  codeql database analyze "$DB_DIR" \
    --format=sarif-latest \
    --output=codeql-python-security.sarif \
    --sarif-category=python-security \
    codeql/python-queries:codeql-suites/python-security-extended.qls \
    2>&1 || EXIT_CODE=$?

  # Run custom queries
  echo "→ 运行自定义查询 (taint-tracking)..."
  codeql database analyze "$DB_DIR" \
    --format=sarif-latest \
    --output=codeql-python-taint.sarif \
    --sarif-category=python-taint \
    .github/codeql-queries/python/ \
    2>&1 || EXIT_CODE=$?

  # Run sensitive data leak
  echo "→ 运行自定义查询 (sensitive-leak)..."
  codeql database analyze "$DB_DIR" \
    --format=sarif-latest \
    --output=codeql-python-leak.sarif \
    --sarif-category=python-leak \
    .github/codeql-queries/python/sensitive-leak.ql \
    2>&1 || EXIT_CODE=$?

  # Clean up database
  rm -rf "$DB_DIR"
fi

echo
echo "============================================"
if [ $EXIT_CODE -ne 0 ]; then
  echo "⚠️  CodeQL found issues (exit code: $EXIT_CODE)"
else
  echo "✅ CodeQL passed — no blocking issues"
fi
echo "📄 Reports: codeql-python-security.sarif, codeql-python-taint.sarif"
exit $EXIT_CODE
