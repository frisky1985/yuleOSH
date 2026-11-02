# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleosh studio — open the Studio workbench (/studio) in a window.

The Studio page is served by the local UI server (yuleosh ui); this command
ensures a server is running, then opens it in a pywebview native window when
the optional ``studio`` extra is installed, falling back to the system
browser otherwise.
"""

import os
import subprocess
import sys
import time
import urllib.request

DEFAULT_PORT = 8080
_HEALTH_TIMEOUT_S = 15.0


def _resolve_port(port: int | None) -> int:
    if port:
        return port
    for var in ("YULEOSH_PORT", "OSH_PORT"):
        raw = os.environ.get(var, "")
        if raw.isdigit():
            return int(raw)
    return DEFAULT_PORT


def _server_healthy(base: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(f"{base}/api/health", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _ensure_server(port: int) -> tuple[str, subprocess.Popen | None]:
    """Return (base_url, spawned_process). Reuses an already-running server."""
    base = f"http://127.0.0.1:{port}"
    if _server_healthy(base):
        return base, None

    env = dict(os.environ)
    env["OSH_PORT"] = str(port)
    proc = subprocess.Popen(
        [sys.executable, "-m", "yuleosh.ui.server"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + _HEALTH_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"UI server exited immediately (code {proc.returncode}); "
                f"check `yuleosh ui` output for details")
        if _server_healthy(base):
            return base, proc
        time.sleep(0.4)
    proc.terminate()
    raise RuntimeError(f"UI server did not become healthy within {_HEALTH_TIMEOUT_S:.0f}s")


def _open_window(url: str, force_browser: bool = False) -> str:
    """Open the Studio URL. Returns 'webview' or 'browser' (for logging/tests)."""
    if not force_browser:
        try:
            import webview  # pywebview, optional ``studio`` extra
        except ImportError:
            pass
        else:
            webview.create_window("yuleOSH Studio", url, width=1440, height=900)
            webview.start()
            return "webview"
    import webbrowser
    webbrowser.open(url)
    return "browser"


def cmd_studio(port: int | None = None, no_open: bool = False,
               force_browser: bool = False) -> int:
    port = _resolve_port(port)
    try:
        base, proc = _ensure_server(port)
    except RuntimeError as e:
        print(f"❌ Studio 启动失败: {e}", file=sys.stderr)
        return 1

    url = f"{base}/studio/"
    print(f"🚀 yuleOSH Studio: {url}" + (" (复用已运行的服务)" if proc is None else ""))

    if no_open:
        return 0
    try:
        mode = _open_window(url, force_browser=force_browser)
        if mode == "browser":
            print("   已在系统浏览器打开（安装 pywebview 可获得原生窗口: "
                  "pip install 'yuleosh[studio]'）")
            if proc is not None:
                print(f"   UI 服务在后台继续运行 (pid {proc.pid})")
    except Exception as e:  # noqa: BLE001 — 窗口失败不应杀掉刚拉起的本地服务
        print(f"⚠️  打开窗口失败: {e} — 请手动访问 {url}", file=sys.stderr)
        return 0
    # pywebview 是阻塞调用，窗口关闭后才走到这里 —— 回收本命令拉起的服务子进程；
    # 浏览器模式则保留服务（杀掉会让刚打开的页面立刻断开）。
    if mode == "webview" and proc is not None and proc.poll() is None:
        proc.terminate()
    return 0
