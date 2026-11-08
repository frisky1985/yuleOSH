#!/usr/bin/env bash
# =============================================================================
# yuleOSH — 持久化 venv 引导脚本
# =============================================================================
# 背景:
#   容器/沙箱每次重建时只有工作区（仓库目录）持久，容器 rootfs 中的
#   /root/.pyenv/.../site-packages 会被重置，手动 pip install 的依赖因此丢失。
#   本脚本把虚拟环境固定在仓库内的 .venv，使依赖随工作区一起保留。
#
# 用法:
#   bash scripts/bootstrap-venv.sh                      # 仅确保环境就绪
#   bash scripts/bootstrap-venv.sh <命令> [参数...]     # 在 venv 中执行命令
#   例:
#   bash scripts/bootstrap-venv.sh python -m yuleosh.cli.main evidence chain --check
#
# 环境变量:
#   VENV_DIR     虚拟环境目录（默认 <repo>/.venv）
#   PYTHON_BIN   用于创建 venv 的解释器（默认自动选择 3.12/3.13/3）
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
STAMP="$VENV_DIR/.deps-installed"

# ── 选择解释器（pyproject 要求 >=3.12,<3.14）────────────────────────────
if [ -z "${PYTHON_BIN:-}" ]; then
  for candidate in python3.12 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [ -z "${PYTHON_BIN:-}" ]; then
  echo "❌ 未找到 Python 3，请先安装 Python 3.12 或 3.13" >&2
  exit 1
fi

# ── 创建/复用 venv ──────────────────────────────────────────────────────
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "→ 创建虚拟环境: $VENV_DIR ($("$PYTHON_BIN" -V 2>&1))"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

PY="$VENV_DIR/bin/python"
echo "→ 使用解释器: $("$PY" -V 2>&1) ($PY)"

# ── 安装依赖（pyproject.toml 更新后自动重装）───────────────────────────
if [ ! -f "$STAMP" ] || [ "$PROJECT_DIR/pyproject.toml" -nt "$STAMP" ]; then
  echo "→ 安装依赖: pip install -e \".[dev]\""
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -e "$PROJECT_DIR[dev]"
  touch "$STAMP"
  echo "✅ 依赖就绪 (marker: $STAMP)"
fi

# ── 执行命令 ────────────────────────────────────────────────────────────
export VIRTUAL_ENV="$VENV_DIR"
export PATH="$VENV_DIR/bin:$PATH"

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

echo ""
echo "环境已就绪。后续可直接使用:"
echo "  source $VENV_DIR/bin/activate"
echo "  python -m yuleosh.cli.main evidence chain --check"
echo ""
echo "或通过本脚本执行单条命令:"
echo "  bash scripts/bootstrap-venv.sh <命令> [参数...]"
