# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for yuleosh.cli.commands.studio — `yuleosh studio` launcher."""

from unittest.mock import MagicMock, patch

from yuleosh.cli.commands.studio import (
    _ensure_server,
    _open_window,
    _resolve_port,
    cmd_studio,
)


# ── port resolution ─────────────────────────────────────────────────────

def test_resolve_port_explicit():
    assert _resolve_port(9000) == 9000


def test_resolve_port_env(monkeypatch):
    monkeypatch.setenv("OSH_PORT", "8888")
    assert _resolve_port(None) == 8888


def test_resolve_port_default(monkeypatch):
    monkeypatch.delenv("YULEOSH_PORT", raising=False)
    monkeypatch.delenv("OSH_PORT", raising=False)
    assert _resolve_port(None) == 8080


# ── server ensure ───────────────────────────────────────────────────────

def test_ensure_server_reuses_running(monkeypatch):
    monkeypatch.setattr("yuleosh.cli.commands.studio._server_healthy",
                        lambda base, timeout=1.5: True)
    base, proc = _ensure_server(8080)
    assert base == "http://127.0.0.1:8080"
    assert proc is None  # 复用已有服务，不拉起子进程


def test_ensure_server_spawns_when_down(monkeypatch):
    calls = {"n": 0}

    def fake_healthy(base, timeout=1.5):
        calls["n"] += 1
        return calls["n"] >= 2  # 第一次不健康，拉起后健康

    fake_proc = MagicMock()
    fake_proc.poll.return_value = None
    monkeypatch.setattr("yuleosh.cli.commands.studio._server_healthy", fake_healthy)
    monkeypatch.setattr("yuleosh.cli.commands.studio.subprocess.Popen",
                        lambda *a, **kw: fake_proc)
    monkeypatch.setattr("yuleosh.cli.commands.studio.time.sleep", lambda s: None)

    base, proc = _ensure_server(8080)
    assert proc is fake_proc


def test_ensure_server_spawn_dies_early(monkeypatch):
    monkeypatch.setattr("yuleosh.cli.commands.studio._server_healthy",
                        lambda base, timeout=1.5: False)
    fake_proc = MagicMock()
    fake_proc.poll.return_value = 3  # 进程立即退出
    fake_proc.returncode = 3
    monkeypatch.setattr("yuleosh.cli.commands.studio.subprocess.Popen",
                        lambda *a, **kw: fake_proc)

    import pytest
    with pytest.raises(RuntimeError, match="exited immediately"):
        _ensure_server(8080)


# ── window open ─────────────────────────────────────────────────────────

def test_open_window_browser_fallback(monkeypatch):
    """无 pywebview 时回退系统浏览器。"""
    monkeypatch.setitem(__import__("sys").modules, "webview", None)
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    assert _open_window("http://127.0.0.1:8080/studio/") == "browser"
    assert opened == ["http://127.0.0.1:8080/studio/"]


def test_open_window_force_browser(monkeypatch):
    fake_webview = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "webview", fake_webview)
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    assert _open_window("http://x/", force_browser=True) == "browser"
    fake_webview.create_window.assert_not_called()


def test_open_window_native(monkeypatch):
    fake_webview = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "webview", fake_webview)
    assert _open_window("http://x/") == "webview"
    fake_webview.create_window.assert_called_once()
    fake_webview.start.assert_called_once()


# ── cmd_studio ──────────────────────────────────────────────────────────

def test_cmd_studio_no_open(monkeypatch, capsys):
    monkeypatch.setattr("yuleosh.cli.commands.studio._ensure_server",
                        lambda port: ("http://127.0.0.1:8080", None))
    rc = cmd_studio(port=8080, no_open=True)
    assert rc == 0
    assert "/studio/" in capsys.readouterr().out


def test_cmd_studio_server_failure(monkeypatch, capsys):
    def boom(port):
        raise RuntimeError("nope")
    monkeypatch.setattr("yuleosh.cli.commands.studio._ensure_server", boom)
    rc = cmd_studio(port=8080)
    assert rc == 1
    assert "启动失败" in capsys.readouterr().err


def test_cmd_studio_webview_closes_reclaims_child(monkeypatch):
    """pywebview 窗口关闭后回收本命令拉起的服务子进程。"""
    child = MagicMock()
    child.poll.return_value = None
    monkeypatch.setattr("yuleosh.cli.commands.studio._ensure_server",
                        lambda port: ("http://127.0.0.1:8080", child))
    monkeypatch.setattr("yuleosh.cli.commands.studio._open_window",
                        lambda url, force_browser=False: "webview")
    rc = cmd_studio(port=8080)
    assert rc == 0
    child.terminate.assert_called_once()


def test_cmd_studio_browser_keeps_child(monkeypatch):
    """浏览器模式保留服务子进程（杀掉会让刚打开的页面断开）。"""
    child = MagicMock()
    child.poll.return_value = None
    monkeypatch.setattr("yuleosh.cli.commands.studio._ensure_server",
                        lambda port: ("http://127.0.0.1:8080", child))
    monkeypatch.setattr("yuleosh.cli.commands.studio._open_window",
                        lambda url, force_browser=False: "browser")
    rc = cmd_studio(port=8080)
    assert rc == 0
    child.terminate.assert_not_called()
