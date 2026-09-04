# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""``GET /api/v1/events/stream`` —— SSE 实时事件订阅端点。

设计要点：
  * 单进程内存总线（``yuleosh.realtime.EVENT_BUS``），进程内多线程扇出，
    无外部 broker。SSE handler 在 ``BaseHTTPRequestHandler`` 流式响应上
    阻塞读取订阅 queue，逐帧 ``data: ...\\n\\n`` 写到 ``wfile``，并按
    15s 间隔发心跳帧（``: keep-alive\\n\\n``）防代理掐断。
  * 客户端重连可带 ``?since_id=N`` 重放缓存历史（at-least-once in-proc）。
  * 订阅 topic 通过 ``?topics=pipeline,evidence,gap`` 过滤；不传默认订阅
    所有 topic。事件渲染见 ``RealtimeEvent.to_sse_frame``。
  * 响应生命周期独立于 ``api_v1_dispatch`` 的 ``_respond`` JSON 包装：
    本 handler 直接写 ``wfile`` 后 ``return None``（dispatch 注释里已说明
    "if handler returned None, it already sent the response"）。

线程模型：
  * ThreadingHTTPServer 每连接一个线程；本 handler 占一个线程直到客户端
    断开。每个连接开新订阅、关流自动 unsubscribe。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import parse_qs

from yuleosh.realtime import EVENT_BUS, _Subscription

log = logging.getLogger("yuleosh.api.events")


# 心跳 / idle 超时（秒）—— 低于常见代理 / LB 的 idle timeout。
_HEARTBEAT_INTERVAL_S = 15.0
# 单帧最大 idle：客户端断开后 publisher 还要把 sentinel 推入 queue 才能跳出。
_POLL_INTERVAL_S = 1.0
# 单连接上限（防被恶意占线程）—— 30 分钟。
_MAX_CONNECTION_S = 30 * 60.0


def _parse_topics(raw: Any) -> set[str] | None:
    """``?topics=a,b,c`` → ``{'a','b','c'}``；空或缺省 → 所有 topic。"""
    if raw is None:
        return None
    if isinstance(raw, list):
        # parse_qs 把 ``?topics=...&topics=...`` 拍成 list
        joined = ",".join(raw)
    else:
        joined = str(raw)
    parts = [p.strip() for p in joined.split(",") if p.strip()]
    return set(parts) if parts else None


def _write_sse(handler, payload_text: str) -> bool:
    """写一帧 SSE，捕获客户端断开（BrokenPipeError / ConnectionResetError）。

    Returns:
        True if write succeeded, False if client went away.
    """
    try:
        handler.wfile.write(payload_text.encode("utf-8"))
        handler.wfile.flush()
        return True
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        log.debug("SSE client disconnected: %s", e)
        return False


def handle_events(method: str, path_tail: str, body, query, handler) -> None:
    """``GET /api/v1/events/stream`` —— SSE 订阅入口。

    Query args:
        topics     — 逗号分隔的 topic 白名单（缺省 = 全部）
        since_id   — 历史重放起点（默认 0），重连补齐用
    """
    if method != "GET":
        # SSE 仅 GET。其它方法走 dispatch 主流程 4xx 即可，这里直接拒绝。
        try:
            handler.send_response(405)
            handler.send_header("Allow", "GET")
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(b'{"ok":false,"error":"method not allowed"}')
        except Exception:  # noqa: BLE001 — bare mock 测试无 wfile 时静默
            pass
        return

    topics = _parse_topics(query.get("topics"))
    since_raw = query.get("since_id", ["0"])
    try:
        since_id = int(since_raw[0] if isinstance(since_raw, list) else since_raw)
    except (TypeError, ValueError):
        since_id = 0

    # ── 流式响应头（不走 _json_response / 走 wfile 原生通道） ──
    try:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache, no-transform")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("X-Accel-Buffering", "no")  # 防 nginx 缓冲
        # CORS 由 dispatcher 主导；SSE 流需要明确 allow-origin 给 frontend。
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
    except Exception as e:  # noqa: BLE001 — 无 wfile 时静默（单元测试裸 mock）
        log.debug("SSE handshake failed: %s", e)
        return

    # ── 订阅 + 重放历史（best-effort） ──
    sub: _Subscription = EVENT_BUS.subscribe(topics)
    replayed = EVENT_BUS.replay_history(sub, since_id=since_id)
    if replayed:
        log.info("SSE replayed %d events (since_id=%d topics=%s)",
                 replayed, since_id, sorted(topics) if topics else "*")

    # ── 首帧 hello（让前端 EventSource 立刻 onopen 触发 onmessage 周期） ──
    hello_frame = (
        f"event: hello\n"
        f"data: {json.dumps({'topics': sorted(topics) if topics else '*', 'since_id': since_id})}\n\n"
    )
    if not _write_sse(handler, hello_frame):
        EVENT_BUS.unsubscribe(sub)
        return

    started = time.time()
    last_hb = started
    queue = sub.queue
    try:
        while True:
            # 连接时长 / 心跳节流
            now = time.time()
            if now - started > _MAX_CONNECTION_S:
                log.debug("SSE connection reached MAX_CONNECTION_S, closing")
                break
            if now - last_hb >= _HEARTBEAT_INTERVAL_S:
                if not _write_sse(handler, ": keep-alive\n\n"):
                    break
                last_hb = now

            try:
                evt = queue.get(timeout=_POLL_INTERVAL_S)
            except Exception:  # noqa: BLE001 — queue.Empty 之外的意外也兜底
                continue

            # sentinel = unsubscribe
            if evt is None:
                break
            if not _write_sse(handler, evt.to_sse_frame()):
                break
    finally:
        EVENT_BUS.unsubscribe(sub)


__all__ = ["handle_events"]
