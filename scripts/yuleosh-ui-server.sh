#!/bin/bash
# yuleOSH UI 常驻运行器（由 setsid 拉起, 脱离 agent 进程树）
# - 崩溃后 2s 自动重启（看门狗）
# - 真正"只由用户停": 需 kill 本进程或 launchctl unload(若有)
set -u

REPO="/Users/ingeek/workspace/yuleOSH"
VENV_PY="$REPO/.venv/bin/python"
OUT_LOG="/tmp/yuleosh-ui.out.log"
ERR_LOG="/tmp/yuleosh-ui.err.log"

# 加载演示用 LLM key（若存在）
if [ -f "$HOME/.hermes/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$HOME/.hermes/.env"
  set +a
fi

export YULEOSH_AUTH_DISABLED="${YULEOSH_AUTH_DISABLED:-1}"
export OSH_HOME="$REPO"
export YULEOSH_HOST="${YULEOSH_HOST:-127.0.0.1}"
export YULEOSH_PORT="${YULEOSH_PORT:-8080}"
export PATH="$REPO/.venv/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

cd "$REPO" || exit 1

echo "[$(date)] yuleosh-ui-server watchdog start ($$)" >> "$OUT_LOG"
while true; do
  echo "[$(date)] launching: $VENV_PY -m yuleosh ui" >> "$OUT_LOG"
  "$VENV_PY" -m yuleosh ui >> "$OUT_LOG" 2>> "$ERR_LOG"
  RC=$?
  echo "[$(date)] yuleosh ui exited rc=$RC, restart in 2s" >> "$OUT_LOG"
  sleep 2
done
