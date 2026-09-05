#!/usr/bin/env bash
# =============================================================================
# yuleOSH — 本地一键部署（开发 / 演示）
#
# 用法:
#   bash scripts/local-deploy.sh
# 浏览器访问: http://localhost:8080
#
# 说明:
#   - 单进程同时提供 API 与前端静态资源（frontend/out/），无需单独起前端。
#   - 默认 YULEOSH_AUTH_DISABLED=1（免登录体验模式）。
#   - 如需演示真实 pipeline（走 LLM），会自动 source ~/.hermes/.env 取 API Key。
#   - OSH_HOME 默认仓库根；数据落在 <repo>/.osh 与本地 store。
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

# 1) 前端未构建则先构建（Next.js 静态导出）
if [ ! -f frontend/out/index.html ]; then
  echo "▶ 前端未构建，执行 npm run build ..."
  (cd frontend && CODEBUDDY_SAFE_DELETE_ENABLED=0 npm run build)
fi

# 2) 环境变量
export YULEOSH_AUTH_DISABLED="${YULEOSH_AUTH_DISABLED:-1}"
export OSH_HOME="${OSH_HOME:-$REPO}"
export YULEOSH_HOST="${YULEOSH_HOST:-127.0.0.1}"
export YULEOSH_PORT="${YULEOSH_PORT:-8080}"

# 可选：真实 LLM Key（演示 pipeline 时需要；不存在则跳过，UI 仍可浏览）
if [ -f "$HOME/.hermes/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$HOME/.hermes/.env"
  set +a
  echo "▶ 已加载 ~/.hermes/.env（LLM Key 就绪）"
fi

# 3) 选择解释器：优先项目 .venv，其次 yuleosh CLI，再次 python3 -m yuleosh
if [ -x .venv/bin/python ]; then
  PY=(.venv/bin/python -m yuleosh)
elif command -v yuleosh >/dev/null 2>&1; then
  PY=(yuleosh)
else
  PY=(python3 -m yuleosh)
fi

echo "▶ 启动 yuleOSH UI @ http://${YULEOSH_HOST}:${YULEOSH_PORT}"
echo "  OSH_HOME=${OSH_HOME}"
echo "  按 Ctrl+C 停止"
exec "${PY[@]}" ui
