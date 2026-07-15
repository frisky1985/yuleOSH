#!/usr/bin/env bash
# =============================================================================
# yuleOSH — 个人开发者一键快速开始
# =============================================================================
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/frisky1985/yuleOSH/main/scripts/dev-quickstart.sh | bash
#   或: bash scripts/dev-quickstart.sh
#
# 本脚本会:
#   1. 检查本地环境（Python / Docker）
#   2. 安装依赖
#   3. 启动服务器
#   4. 打印快速入门指引
# =============================================================================

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║      yuleOSH — 个人开发者快速开始     ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: 检查环境 ──────────────────────────────────────────────
echo -e "${BOLD}[1/5] 检查环境...${NC}"

USE_DOCKER=false
HAS_PYTHON=false
HAS_DOCKER=false

if command -v python3 &>/dev/null; then
  PY_VER=$(python3 --version 2>&1)
  HAS_PYTHON=true
  echo -e "  ${GREEN}✅${NC} $PY_VER"
else
  echo -e "  ${YELLOW}⚠️  未找到 Python 3${NC}"
fi

if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
  HAS_DOCKER=true
  echo -e "  ${GREEN}✅${NC} Docker Compose $(docker compose version --short 2>/dev/null || echo '已安装')"
else
  echo -e "  ${YELLOW}⚠️  未找到 Docker Compose${NC}"
fi

# ── Step 2: 确定启动方式 ──────────────────────────────────────────
echo ""
echo -e "${BOLD}[2/5] 确定启动方式...${NC}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ "$HAS_DOCKER" = true ]; then
  USE_DOCKER=true
  echo -e "  ${GREEN}→ 使用 Docker Compose 启动${NC}"
elif [ "$HAS_PYTHON" = true ]; then
  echo -e "  ${GREEN}→ 使用 Python 直接启动${NC}"
else
  echo -e "  ${RED}❌ 需要 Python 3 或 Docker${NC}"
  echo "  安装: brew install python3 或 Docker Desktop"
  exit 1
fi

# ── Step 3: 安装/构建 ─────────────────────────────────────────────
echo ""
echo -e "${BOLD}[3/5] 安装依赖...${NC}"

if [ "$USE_DOCKER" = true ]; then
  echo "  构建 Docker 镜像（第一次会比较慢）..."
  (cd "$PROJECT_DIR" && docker compose build 2>&1) | sed 's/^/  /'
  echo -e "  ${GREEN}✅ Docker 镜像构建完成${NC}"
else
  echo "  安装 Python 依赖..."
  (cd "$PROJECT_DIR" && pip install -e . 2>&1) | tail -3 | sed 's/^/  /'
  echo -e "  ${GREEN}✅ Python 依赖安装完成${NC}"
fi

# ── Step 4: 启动 ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[4/5] 启动服务器...${NC}"

if [ "$USE_DOCKER" = true ]; then
  (cd "$PROJECT_DIR" && docker compose up -d 2>&1) | sed 's/^/  /'
  echo -e "  ${GREEN}✅ yuleOSH 正在 Docker 中运行${NC}"
  STOP_CMD="docker compose down"
else
  echo "  启动中..."
  # Start in background
  (cd "$PROJECT_DIR" && YULEOSH_AUTH_DISABLED=1 python3 -m yuleosh.ui.server &
    SERVER_PID=$!
    echo $SERVER_PID > /tmp/yuleosh.pid
  )
  sleep 2
  echo -e "  ${GREEN}✅ yuleOSH 已启动 (PID: $(cat /tmp/yuleosh.pid))${NC}"
  STOP_CMD="kill \$(cat /tmp/yuleosh.pid)"
fi

# ── Step 5: 验证 + 打印指南 ──────────────────────────────────────
echo ""
echo -e "${BOLD}[5/5] 验证启动...${NC}"
sleep 1

if command -v curl &>/dev/null; then
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>/dev/null || echo "failed")
  if [ "$HTTP_CODE" = "200" ]; then
    echo -e "  ${GREEN}✅ 服务器响应正常 (HTTP 200)${NC}"
  else
    echo -e "  ${YELLOW}⚠️  服务器返回状态码: $HTTP_CODE${NC}"
  fi
fi

echo ""
echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       🎉 yuleOSH 可以开始使用了！      ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Dashboard:${NC}     http://localhost:8080/dashboard"
echo -e "  ${BOLD}Demo:${NC}          http://localhost:8080/demo"
echo -e "  ${BOLD}Pricing:${NC}       http://localhost:8080/pricing"
echo -e "  ${BOLD}Docs:${NC}          http://localhost:8080/docs"
echo ""
echo -e "  ${BOLD}停止服务:${NC}      $STOP_CMD"
echo ""
echo -e "  ${BOLD}快速体验:${NC}"
echo -e "  1. 打开 http://localhost:8080/demo"
echo -e "  2. 点击 'Run Mock Pipeline' 看全流程"
echo -e "  3. 去 /dashboard 创建第一个项目"
echo ""
echo -e "  ${BOLD}详细文档:${NC}      ${PROJECT_DIR}/docs/quick-start.md"
echo ""
