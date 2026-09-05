#!/usr/bin/env bash
# =============================================================================
# yuleOSH — 本地部署脚本（开发 / 演示）
#
# 用法:
#   bash scripts/local-deploy.sh            # 前台运行（Ctrl+C 停止），适合自己终端
#   bash scripts/local-deploy.sh install    # 注册为 macOS launchd 守护进程（免登录、会话回收/重启都在）
#   bash scripts/local-deploy.sh uninstall  # 卸载守护进程（彻底停止）
#   bash scripts/local-deploy.sh stop       # 停掉「前台/nohup」方式起的服务
#
# 浏览器访问: http://localhost:8080
#
# 说明:
#   - 单进程同时提供 API 与前端静态资源（frontend/out/），无需单独起前端。
#   - 默认 YULEOSH_AUTH_DISABLED=1（免登录体验模式）。
#   - install 模式把服务交给系统 launchd 托管：只有 `uninstall` 才真正结束，
#     会话回收、关终端、甚至重启机器都不影响（RunAtLoad + KeepAlive）。
#   - 注意：launchctl 需要用户 GUI 登录会话，必须在你自己 Terminal 里跑 install，
#     不能由 agent / 非登录会话执行（会被 macOS 拒绝）。
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

PLIST="$HOME/Library/LaunchAgents/com.yuleosh.ui.plist"

# 选择解释器
if [ -x .venv/bin/python ]; then
  INTERP=(.venv/bin/python -m yuleosh)
elif command -v yuleosh >/dev/null 2>&1; then
  INTERP=(yuleosh)
else
  INTERP=(python3 -m yuleosh)
fi

ensure_frontend() {
  if [ ! -f frontend/out/index.html ]; then
    echo "▶ 前端未构建，执行 npm run build ..."
    (cd frontend && CODEBUDDY_SAFE_DELETE_ENABLED=0 npm run build)
  fi
}

write_plist() {
  local py="${INTERP[0]}"
  [ "${INTERP[1]:-}" = "-m" ] && py="${INTERP[0]}"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.yuleosh.ui</string>
  <key>ProgramArguments</key>
  <array>
    <string>$REPO/.venv/bin/python</string>
    <string>-m</string>
    <string>yuleosh</string>
    <string>ui</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$REPO</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>YULEOSH_AUTH_DISABLED</key>
    <string>1</string>
    <key>OSH_HOME</key>
    <string>$REPO</string>
    <key>YULEOSH_HOST</key>
    <string>127.0.0.1</string>
    <key>YULEOSH_PORT</key>
    <string>8080</string>
    <key>PATH</key>
    <string>$REPO/.venv/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/yuleosh-ui.out.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/yuleosh-ui.err.log</string>
</dict>
</plist>
EOF
}

CMD="${1:-run}"
case "$CMD" in
  run)
    ensure_frontend
    export YULEOSH_AUTH_DISABLED=1
    export OSH_HOME="${OSH_HOME:-$REPO}"
    export YULEOSH_HOST="${YULEOSH_HOST:-127.0.0.1}"
    export YULEOSH_PORT="${YULEOSH_PORT:-8080}"
    if [ -f "$HOME/.hermes/.env" ]; then
      set -a; source "$HOME/.hermes/.env"; set +a
      echo "▶ 已加载 ~/.hermes/.env（LLM Key 就绪）"
    fi
    echo "▶ 启动 yuleOSH UI @ http://${YULEOSH_HOST}:${YULEOSH_PORT}（Ctrl+C 停止）"
    echo "  OSH_HOME=${OSH_HOME}"
    exec "${INTERP[@]}" ui
    ;;
  install)
    ensure_frontend
    write_plist
    echo "▶ 注册 launchd 守护进程 ..."
    if launchctl load "$PLIST" 2>/dev/null; then
      echo "  launchctl load 成功"
    else
      launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null \
        && echo "  launchctl bootstrap 成功" \
        || { echo "✗ launchctl 失败：请在你自己的 Terminal（GUI 登录会话）里执行"; exit 1; }
    fi
    sleep 2
    curl -s --noproxy 127.0.0.1 -m 5 -o /dev/null -w "  健康检查: HTTP %{http_code}\n" http://127.0.0.1:8080/health || true
    echo "✅ 已常驻：浏览器开 http://localhost:8080；停止用 bash $0 uninstall"
    ;;
  uninstall)
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "✅ 已卸载并停止守护进程"
    ;;
  stop)
    PIDS="$(lsof -tiTCP:8080 -sTCP:LISTEN -P -n 2>/dev/null || true)"
    if [ -n "$PIDS" ]; then kill $PIDS && echo "✅ 已停止: $PIDS"; else echo "无运行中的服务"; fi
    ;;
  *)
    echo "用法: $0 [run|install|uninstall|stop]"; exit 1;;
esac
