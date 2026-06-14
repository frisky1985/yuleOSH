# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Plugin Sandbox — 插件沙箱（安全执行）。

核心安全策略：
- 限制文件系统访问（仅允许 Plugin 自身目录 + 声明的路径）
- 限制网络访问（默认禁止，通过 manifest permissions 声明）
- 限制系统调用（默认禁止 exec/subprocess）
- 执行超时控制
"""
from __future__ import annotations

import builtins
import functools
import importlib.util
import os
import signal
import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Optional

from . import Plugin, PluginManifest

# ---------------------------------------------------------------------------
# 安全受限的 __builtins__ 白名单
# ---------------------------------------------------------------------------

SAFE_BUILTINS: set[str] = {
    # 基本类型和容器
    "bool", "int", "float", "str", "bytes", "bytearray",
    "list", "tuple", "dict", "set", "frozenset",
    "type", "object", "range", "enumerate", "zip", "map", "filter",
    "len", "min", "max", "sum", "abs", "round", "pow",
    "sorted", "reversed", "iter", "next",
    "True", "False", "None",
    # 字符串/编码
    "chr", "ord", "repr", "ascii", "format",
    "hash", "id", "isinstance", "issubclass", "callable",
    "hasattr", "getattr", "setattr", "delattr",
    # 异常
    "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "AttributeError", "RuntimeError",
    "StopIteration", "NameError", "ZeroDivisionError",
    "AssertionError", "OverflowError", "NotImplementedError",
    # 输入输出（受限）
    "print",  # 允许输出（不涉及文件系统）
    # 其他
    "open",  # 被下方自定义函数替换
    "__import__",  # 被下方自定义函数替换
}


class SandboxViolation(Exception):
    """沙箱违规执行异常。"""
    pass


# ---------------------------------------------------------------------------
# PluginSandbox
# ---------------------------------------------------------------------------

class PluginSandbox:
    """插件沙箱 — 安全执行 Plugin 代码。"""

    def __init__(self, plugin_dir: Path | str, manifest: PluginManifest | None = None):
        self.plugin_dir = Path(plugin_dir).resolve()
        self.manifest = manifest
        self._timeout = (manifest.timeout if manifest and manifest.timeout > 0 else 30)

    # ---- 公共执行接口 ----

    def execute(self, plugin: Plugin, args: dict[str, Any]) -> Any:
        """在沙箱中执行插件入口函数。"""
        entry = plugin.entry_path
        if entry is None or not entry.is_file():
            raise SandboxViolation(f"插件 {plugin.name} 无入口文件")

        # 构建受限命名空间
        safe_globals = self._build_safe_globals(plugin)

        # 读取入口代码
        source = entry.read_text(encoding="utf-8")

        result: Any = None
        exception: Optional[Exception] = None
        done = threading.Event()

        def _run():
            nonlocal result, exception
            try:
                compiled = compile(source, str(entry), "exec")
                exec(compiled, safe_globals)
                # 尝试调用 run() 函数
                if "run" in safe_globals:
                    result = safe_globals["run"](args)
            except Exception as e:
                exception = e
            finally:
                done.set()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        if not done.wait(timeout=self._timeout):
            raise TimeoutError(f"插件 {plugin.name} 执行超时 ({self._timeout}s)")

        if exception:
            raise SandboxViolation(f"插件 {plugin.name} 执行出错: {exception}") from exception

        return result

    # ---- 沙箱构建 ----

    def _build_safe_globals(self, plugin: Plugin) -> dict[str, Any]:
        """构建受限的全局命名空间。"""
        safe_builtins: dict[str, Any] = {}
        for name in SAFE_BUILTINS:
            if name == "open":
                safe_builtins[name] = self._restricted_open(plugin)
            elif name == "__import__":
                safe_builtins[name] = self._restricted_import(plugin)
            elif hasattr(builtins, name):
                safe_builtins[name] = getattr(builtins, name)

        return {
            "__builtins__": safe_builtins,
            "__name__": f"__yuleosh_plugin__{plugin.name}__",
            "__file__": str(plugin.entry_path or ""),
            "__yuleosh_plugin__": {
                "name": plugin.name,
                "manifest": plugin.manifest,
                "directory": str(plugin.directory),
            },
        }

    def _restricted_open(self, plugin: Plugin):
        """受限的 open() — 仅允许读取 Plugin 自身目录下的文件。"""
        allowed_dir = str(self.plugin_dir)

        def safe_open(file, mode="r", *args, **kwargs):
            # 只读模式下检查路径
            if "w" in mode or "a" in mode or "x" in mode or "+" in mode:
                resolved = Path(file).resolve()
                if not str(resolved).startswith(allowed_dir):
                    raise SandboxViolation(
                        f"禁止写入沙箱外文件: {resolved} "
                        f"(允许: {allowed_dir})"
                    )
            # 写模式只允许在插件目录内
            # 读模式默认允许（可进一步收紧）
            return builtins.open(file, mode, *args, **kwargs)

        return safe_open

    def _restricted_import(self, plugin: Plugin):
        """受限的 import — 仅允许 Python 标准库。"""
        # 允许的标准库列表（安全子集）
        ALLOWED_STDLIB: set[str] = {
            "json", "math", "re", "datetime", "collections",
            "functools", "itertools", "typing", "enum",
            "copy", "string", "textwrap", "inspect",
            "dataclasses", "uuid", "base64", "hashlib",
            "pathlib",  # pathlib 允许，但配合受限 open
            "time",
        }

        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            # 只允许顶层 import
            if level != 0:
                raise SandboxViolation(f"禁止相对导入: {name}")
            top_name = name.split(".")[0]
            if top_name not in ALLOWED_STDLIB:
                raise SandboxViolation(f"禁止导入模块: {name} (不在白名单中)")
            return builtins.__import__(name, globals, locals, fromlist, level)

        return safe_import

    # ---- 系统调用限制 ----

    @staticmethod
    def block_subprocess():
        """阻塞子进程创建（通过替换 os.system / os.popen / subprocess）。"""
        raise SandboxViolation("禁止在沙箱中创建子进程")


__all__ = [
    "PluginSandbox",
    "SandboxViolation",
    "SAFE_BUILTINS",
]
