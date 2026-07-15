#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph — Git Hook Check / Install / Update / Uninstall.

Provides:
  - ``check_installed()`` — 检测 KG post-commit hook 是否已安装
  - ``is_version_current()`` — 检查安装是否最新
  - ``install_hook()`` — 安装/更新 post-commit hook
  - ``uninstall_hook()`` — 卸载 post-commit hook
  - ``get_status()`` — 返回完整状态 dict

CLI:
    python -m yuleosh.knowledge_graph.git_hook_check --install
    python -m yuleosh.knowledge_graph.git_hook_check --check
    python -m yuleosh.knowledge_graph.git_hook_check --uninstall
"""

import argparse
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("yuleosh.knowledge_graph.git_hook_check")

# ── 版本号（与 scripts/install-kg-hooks.sh 同步） ──────────────────────
KG_HOOK_VERSION = "1.0.0"

# ── 生成 post-commit hook 脚本内容 ─────────────────────────────────────
POST_COMMIT_TEMPLATE = r"""#!/usr/bin/env bash
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT
# KG post-commit hook v{HOOK_VERSION} — 异步更新知识图谱

set -euo pipefail

HOOK_VERSION="{HOOK_VERSION}"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/.yuleosh"
LOG_FILE="$LOG_DIR/kg-hooks.log"
PYTHON="${{YULEOSH_PYTHON:-python3}}"

mkdir -p "$LOG_DIR"

START_TS="$(date '+%Y-%m-%d %H:%M:%S')"
CHANGED_FILES=$(git diff-tree --no-commit-id -r --name-only HEAD 2>/dev/null || true)
TARGET_FILES=""

if [ -z "$CHANGED_FILES" ]; then
    echo "[${{START_TS}}] INFO: no changed files detected (empty commit?)" >> "$LOG_FILE"
    exit 0
fi

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
    echo "[${{START_TS}}] INFO: no yuleOSH/tests Python files changed, skipping KG update" >> "$LOG_FILE"
    exit 0
fi

echo "[${{START_TS}}] INFO: changed files: $TARGET_FILES" >> "$LOG_FILE"

nohup "$PYTHON" -m yuleosh.knowledge_graph.ci_hook \
    --changed-files "$TARGET_FILES" \
    >> "$LOG_FILE" 2>&1 &

KG_PID=$!
echo "[${{START_TS}}] INFO: KG update spawned (pid=$KG_PID, files=$TARGET_FILES)" >> "$LOG_FILE"
disown "$KG_PID" 2>/dev/null || true
exit 0
"""


# ── 工具函数 ─────────────────────────────────────────────────────────────

def _get_git_root() -> Optional[Path]:
    """返回 git 仓库根目录，如果不在 git 仓库中则返回 None。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _get_hooks_dir() -> Optional[Path]:
    """返回 .git/hooks 目录，如果不在 git 仓库中则返回 None。"""
    root = _get_git_root()
    if root is None:
        return None
    hooks_dir = root / ".git" / "hooks"
    if hooks_dir.is_dir():
        return hooks_dir
    return None


def _get_hook_path() -> Optional[Path]:
    """返回 post-commit hook 路径，如果不在 git 仓库中则返回 None。"""
    hooks_dir = _get_hooks_dir()
    if hooks_dir is None:
        return None
    return hooks_dir / "post-commit"


def _get_installed_version(hook_path: Path) -> Optional[str]:
    """读取已安装 hook 的版本号。"""
    try:
        content = hook_path.read_text()
        for line in content.splitlines():
            if line.startswith("HOOK_VERSION="):
                return line.split('"')[1] if '"' in line else line.split("=", 1)[1].strip()
        return None
    except (OSError, IndexError):
        return None


# ── 公开 API ─────────────────────────────────────────────────────────────

def check_installed() -> bool:
    """检查 KG post-commit hook 是否已安装且可执行。"""
    hook_path = _get_hook_path()
    if hook_path is None:
        return False
    if not hook_path.exists():
        return False
    # 检查是否为可执行文件（非 sample）
    mode = hook_path.stat().st_mode
    return bool(mode & stat.S_IXUSR) and "sample" not in hook_path.name


def is_version_current() -> tuple[bool, Optional[str]]:
    """检查已安装 hook 版本是否最新。

    Returns:
        (is_current, installed_version) — 如果未安装则 is_current=False, installed_version=None
    """
    hook_path = _get_hook_path()
    if hook_path is None or not hook_path.exists():
        return False, None
    installed = _get_installed_version(hook_path)
    if installed is None:
        return False, None
    return installed == KG_HOOK_VERSION, installed


def get_status() -> dict:
    """返回 hook 安装状态的完整信息。"""
    hook_path = _get_hook_path()
    git_root = _get_git_root()

    if git_root is None:
        return {
            "installed": False,
            "current_version": None,
            "installed_version": None,
            "hook_path": None,
            "git_root": None,
            "message": "不在 Git 仓库中",
        }

    installed = hook_path is not None and hook_path.exists()
    installed_version = _get_installed_version(hook_path) if installed else None
    is_current = installed_version == KG_HOOK_VERSION if installed_version else False

    message = "KG post-commit hook 已安装且为最新" if installed and is_current else \
              (f"KG post-commit hook 已安装 (v{installed_version})，最新版本 v{KG_HOOK_VERSION}" if installed else
               "KG post-commit hook 未安装")

    return {
        "installed": installed,
        "current_version": KG_HOOK_VERSION,
        "installed_version": installed_version,
        "hook_path": str(hook_path) if hook_path else None,
        "git_root": str(git_root),
        "is_current": is_current,
        "message": message,
    }


def install_hook(force: bool = False) -> bool:
    """安装或更新 KG post-commit hook。

    Args:
        force: 即使已安装最新版本也重新写入

    Returns:
        True 表示安装/更新成功
    """
    hook_path = _get_hook_path()
    if hook_path is None:
        log.error("❌ 不在 Git 仓库中，无法安装 hook")
        return False

    if hook_path.exists() and not force:
        installed = _get_installed_version(hook_path)
        if installed == KG_HOOK_VERSION:
            log.info("✅ KG post-commit hook 已安装且为最新版本 (v%s)", KG_HOOK_VERSION)
            return True
        elif installed:
            log.info("更新 KG post-commit hook (v%s → v%s)", installed, KG_HOOK_VERSION)
        else:
            log.info("更新 KG post-commit hook")

    # 生成 hook 内容
    content = POST_COMMIT_TEMPLATE.format(HOOK_VERSION=KG_HOOK_VERSION)

    # 写入文件
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(content)
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    log.info("✅ KG post-commit hook 已安装到 %s (v%s)", hook_path, KG_HOOK_VERSION)

    # 确保日志目录存在
    git_root = _get_git_root()
    if git_root:
        log_dir = git_root / ".yuleosh"
        log_dir.mkdir(parents=True, exist_ok=True)
        log.info("📝 日志目录: %s", log_dir / "kg-hooks.log")

    return True


def uninstall_hook() -> bool:
    """卸载 KG post-commit hook。

    Returns:
        True 表示卸载成功（或本来就没安装）
    """
    hook_path = _get_hook_path()
    if hook_path is None:
        log.warning("⚠️  不在 Git 仓库中，无法卸载")
        return False

    if not hook_path.exists():
        log.info("ℹ️  KG post-commit hook 尚未安装，无需卸载")
        return True

    # 验证是 KG hook（避免误删用户自己的 hook）
    content = hook_path.read_text()
    if "KG post-commit hook" not in content or "yuleosh.knowledge_graph.ci_hook" not in content:
        log.warning("⚠️  %s 不是 KG hook，跳过卸载（如需手动删除请直接操作）", hook_path)
        return False

    hook_path.unlink()
    log.info("✅ KG post-commit hook 已卸载")

    # 清理空 hooks 目录（不会真的删除 .git/hooks）
    return True


def _describe_changed_files(files: list[str]) -> str:
    """过滤出 src/yuleosh/ 和 tests/ 下的 Python 文件。"""
    matched = []
    for f in files:
        if f.startswith("src/yuleosh/") and f.endswith(".py"):
            matched.append(f)
        elif f.startswith("tests/") and f.endswith(".py"):
            matched.append(f)
    return ",".join(matched)


def get_changed_files_from_commit() -> list[str]:
    """获取最近一次 commit 的变更文件列表。

    Returns:
        str 列表，每条为一个文件路径
    """
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", "HEAD"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
        return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="yuleOSH 知识图谱 Git hook 管理工具",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--install", action="store_true",
        help="安装或更新 KG post-commit hook",
    )
    group.add_argument(
        "--uninstall", action="store_true",
        help="卸载 KG post-commit hook",
    )
    group.add_argument(
        "--check", action="store_true",
        help="检查 hook 安装状态（默认）",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="强制重新安装（覆盖已存在的 hook）",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    if args.install:
        success = install_hook(force=args.force)
        return 0 if success else 1

    elif args.uninstall:
        success = uninstall_hook()
        return 0 if success else 1

    else:  # --check (default)
        status = get_status()
        print(f"📊 KG post-commit hook 状态")
        print(f"   ├─ Git 仓库:  {status['git_root'] or '❌ 不在 Git 仓库中'}")
        print(f"   ├─ 安装路径:  {status['hook_path'] or 'N/A'}")
        print(f"   ├─ 安装状态:  {'✅ 已安装' if status['installed'] else '❌ 未安装'}")
        if status['installed']:
            print(f"   ├─ 已安装版本: v{status['installed_version']}")
            print(f"   ├─ 最新版本:   v{status['current_version']}")
            print(f"   └─ 版本匹配:   {'✅ 是' if status['is_current'] else '⚠️  需要更新'}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
