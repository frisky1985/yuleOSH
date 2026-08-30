#!/bin/bash
# 起 yuleosh UI 本地服务（带免登录鉴权，模拟 dashboard 操作）。
# 在 /Users/ingeek/workspace/yuleOSH 目录下执行即可。
export YULEOSH_AUTH_DISABLED=1
export YULEOSH_JWT_SECRET=local-dev-secret
export YULEOSH_HOST=127.0.0.1
export YULEOSH_PORT=8080
export OSH_HOME=/Users/ingeek/workspace/yuleOSH
exec .venv/bin/python -m yuleosh ui
