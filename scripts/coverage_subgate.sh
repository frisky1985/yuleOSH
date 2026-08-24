#!/usr/bin/env bash
# Coverage sub-gate: per-module minimum coverage for production-critical paths.
# P1-3d: ensures key modules don't regress below their threshold.
set -euo pipefail

VENV_PYTHON="${VENV_PYTHON:-python}"
fail=0

run_subgate() {
  local module="$1"
  local tests="$2"
  local threshold="$3"
  echo "== $module (>= ${threshold}%) =="
  $VENV_PYTHON -m coverage run --source=yuleosh --branch \
    -m pytest $tests -q --no-header -o addopts="" -p no:randomly 2>&1 | tail -5
  $VENV_PYTHON -m coverage report --include="$module" --fail-under="$threshold" || fail=1
  echo ""
}

run_subgate \
  "src/yuleosh/plugins/sandbox.py" \
  "tests/test_sandbox_security_deep.py tests/test_plugins.py tests/test_plugins_smoke.py" \
  85

run_subgate \
  "src/yuleosh/sil/adapter.py" \
  "tests/test_sil_adapter_deep.py tests/test_sil.py" \
  80

if [ $fail -eq 1 ]; then
  echo "❌ Coverage sub-gate FAILED — see thresholds above."
  exit 1
fi

echo "✅ Coverage sub-gates passed."
