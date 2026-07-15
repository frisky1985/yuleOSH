#!/usr/bin/env bash
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT
#
# install-kg-hooks.sh — 安装知识图谱 Git post-commit hook
#
# 用法:
#   ./scripts/install-kg-hooks.sh              # 安装
#   ./scripts/install-kg-hooks.sh --uninstall  # 卸载
#   ./scripts/install-kg-hooks.sh --check      # 检查状态
#
# 说明:
#   post-commit hook 在每次 git commit 后异步运行 KG CI hook，
#   将变更文件的 traceability 信息更新到知识图谱。
#   hook 本身非常轻量，不阻塞 git commit 流程。
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
HOOK_NAME="post-commit"
HOOK_PATH="$HOOKS_DIR/$HOOK_NAME"
KG_HOOK_VERSION="1.0.0"

# ── 日志 ────────────────────────────────────────────────────────────────
log_info()  { echo "[KG-HOOKS] ℹ️  $*"; }
log_ok()    { echo "[KG-HOOKS] ✅ $*"; }
log_warn()  { echo "[KG-HOOKS] ⚠️  $*"; }
log_error() { echo "[KG-HOOKS] ❌ $*" >&2; }

# ── post-commit hook 内容 ───────────────────────────────────────────────
read -r -d '' HOOK_CONTENT <<'HOOK_BODY' || true
#!/usr/bin/env bash
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT
# KG post-commit hook v1.0.0 — 异步更新知识图谱

set -euo pipefail

HOOK_VERSION="1.0.0"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/.yuleosh"
LOG_FILE="$LOG_DIR/kg-hooks.log"
PYTHON="${YULEOSH_PYTHON:-python3}"

# 确保日志目录存在
mkdir -p "$LOG_DIR"

# 标记开始时间
START_TS="$(date '+%Y-%m-%d %H:%M:%S')"

# 获取本次 commit 变更的 Python 文件列表（轻量）
CHANGED_FILES=$(git diff-tree --no-commit-id -r --name-only HEAD 2>/dev/null || true)
TARGET_FILES=""

if [ -z "$CHANGED_FILES" ]; then
    # 有些 git 版本下 HEAD 刚创建，fallback 到空
    echo "[${START_TS}] INFO: no changed files detected (empty commit?)" >> "$LOG_FILE"
    exit 0
fi

# 过滤出 src/yuleosh/ 和 tests/ 下的 Python 文件
while IFS= read -r file; do
    [ -z "$file" ] && continue
    case "$file" in
        src/yuleosh/*.py|tests/*.py)
            if [ -z "$TARGET_FILES" ]; then
                TARGET_FILES="$file"
            else
                TARGET_FILES="$TARGET_FILES,$file"
            fi
            ;;
    esac
done <<< "$CHANGED_FILES"

if [ -z "$TARGET_FILES" ]; then
    echo "[${START_TS}] INFO: no yuleOSH/tests Python files changed, skipping KG update" >> "$LOG_FILE"
    exit 0
fi

echo "[${START_TS}] INFO: changed files: $TARGET_FILES" >> "$LOG_FILE"

# 在后台异步调用 CI hook（nohup 防止 SIGHUP 中断）
nohup "$PYTHON" -m yuleosh.knowledge_graph.ci_hook \
    --changed-files "$TARGET_FILES" \
    >> "$LOG_FILE" 2>&1 &

KG_PID=$!
echo "[${START_TS}] INFO: KG update spawned (pid=$KG_PID, files=$TARGET_FILES)" >> "$LOG_FILE"
# 不 wait — 完全异步，不阻塞 git
disown "$KG_PID" 2>/dev/null || true
exit 0
HOOK_BODY

# ── 函数 ─────────────────────────────────────────────────────────────────

check_git_repo() {
    if [ ! -d "$PROJECT_ROOT/.git" ]; then
        log_error "不是 Git 仓库: $PROJECT_ROOT"
        log_error "请确保在 yuleOSH 项目根目录运行"
        exit 1
    fi
}

check_hook_installed() {
    if [ -f "$HOOK_PATH" ] && [ -x "$HOOK_PATH" ]; then
        return 0
    fi
    return 1
}

check_hook_version() {
    if ! check_hook_installed; then
        return 1
    fi
    local installed_version
    installed_version=$(grep -E "^HOOK_VERSION=" "$HOOK_PATH" 2>/dev/null | cut -d'"' -f2 || echo "")
    if [ "$installed_version" = "$KG_HOOK_VERSION" ]; then
        return 0
    fi
    return 2  # 版本不匹配
}

print_status() {
    if ! check_hook_installed; then
        log_info "KG post-commit hook: ❌ 未安装"
        return 1
    fi
    local installed_version
    installed_version=$(grep -E "^HOOK_VERSION=" "$HOOK_PATH" 2>/dev/null | cut -d'"' -f2 || echo "?")
    if [ "$installed_version" = "$KG_HOOK_VERSION" ]; then
        log_ok "KG post-commit hook: ✅ 已安装 (v$installed_version, 最新)"
    else
        log_warn "KG post-commit hook: ⚠️  已安装 (v$installed_version, 最新版本 v$KG_HOOK_VERSION)"
    fi
    return 0
}

do_install() {
    check_git_repo

    if check_hook_installed; then
        local installed_version
        installed_version=$(grep -E "^HOOK_VERSION=" "$HOOK_PATH" 2>/dev/null | cut -d'"' -f2 || echo "?")
        if [ "$installed_version" = "$KG_HOOK_VERSION" ]; then
            log_ok "KG post-commit hook 已安装且为最新版本 (v$KG_HOOK_VERSION)"
            return 0
        fi
        log_info "更新 KG post-commit hook (v$installed_version → v$KG_HOOK_VERSION)"
    else
        log_info "安装 KG post-commit hook (v$KG_HOOK_VERSION)"
    fi

    # 写入 hook 文件
    echo "$HOOK_CONTENT" > "$HOOK_PATH"
    chmod +x "$HOOK_PATH"

    log_ok "KG post-commit hook 已安装到 $HOOK_PATH"

    # 创建日志目录
    mkdir -p "$PROJECT_ROOT/.yuleosh"
    log_ok "日志将写入 $PROJECT_ROOT/.yuleosh/kg-hooks.log"
}

do_uninstall() {
    if check_hook_installed; then
        rm -f "$HOOK_PATH"
        log_ok "KG post-commit hook 已卸载"
    else
        log_info "KG post-commit hook 尚未安装，无需卸载"
    fi
}

# ── 主流程 ──────────────────────────────────────────────────────────────

case "${1:-install}" in
    install|--install)
        do_install
        ;;
    uninstall|--uninstall)
        do_uninstall
        ;;
    check|--check|status|--status)
        print_status
        ;;
    *)
        echo "用法: $0 [install|uninstall|check]"
        echo ""
        echo "   install    安装/更新 KG post-commit hook (默认)"
        echo "   uninstall  卸载 KG post-commit hook"
        echo "   check      检查 hook 安装状态"
        exit 1
        ;;
esac
