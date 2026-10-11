"use client";

/** useRealtimeFeed: 订阅 /api/v1/events/stream SSE 多 topic 实时事件。
 *
 * 与 ``subscribeSSE``（lib/sse.ts）的差异：
 *  - subscribeSSE 面向单条 run 的「终态驱动」场景，固定一个 event 名。
 *  - useRealtimeFeed 面向「仪表盘全局订阅」场景，多 topic 同时分发，所有
 *    事件一律推 handler（handler 自己做 topic 路由 / 业务分发）。
 *  - since_id 单调累积: 同一页面多次 re-mount 会从已累积最大 id 继续（不会
 *    重复推送历史）。
 *  - 不提供轮询兜底: 实时层是「加速」而非「必备」，常规 polling 仍按原
 *    节奏跑。
 *
 * 卸载 / 切换 topics 自动关闭 EventSource（cleanup）。
 */
import { useEffect, useRef } from "react";

export interface RealtimeFrame {
  id: number;
  ts: number;
  topic: string;
  payload: Record<string, unknown>;
}

export interface UseRealtimeFeedOptions {
  /** 订阅的 topic 列表（白名单）；未传则订阅所有 topic。 */
  topics?: string[];
  /** 每收到一帧 SSE 业务事件时回调（首帧 hello 不触发）。 */
  onEvent: (frame: RealtimeFrame) => void;
  /** SSE 连接错误回调（可选，主要用于埋点 / 标记「实时降级」）。 */
  onError?: (err: unknown) => void;
  /** 连接成功时回调（首次连接 + 每次重连成功后）。 */
  onConnect?: () => void;
  /** 连接断开时回调（用于显示降级横幅）。 */
  onDisconnect?: () => void;
  /** 显式禁用；用于 SSR / 单测。 */
  enabled?: boolean;
  /** 自定义基础 URL（默认用 `/api/v1`）。 */
  basePath?: string;
}

export function useRealtimeFeed(opts: UseRealtimeFeedOptions): void {
  const { topics, onEvent, onError, onConnect, onDisconnect, enabled = true, basePath = "/api/v1" } = opts;
  // 用 ref 让回调读到最新函数（避免 effect 频繁重启 EventSource）
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const onConnectRef = useRef(onConnect);
  onConnectRef.current = onConnect;
  const onDisconnectRef = useRef(onDisconnect);
  onDisconnectRef.current = onDisconnect;

  // since_id 在组件生命周期内单调累积（用 ref，避免渲染期间变化）
  const sinceIdRef = useRef<number>(0);
  // 重连退避计数（每次断线 +1，成功连接后归零）
  const retryCountRef = useRef<number>(0);
  // 重连定时器 ID（cleanup 时 clearTimeout）
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled) return;
    if (typeof EventSource === "undefined") {
      // SSR 期间或浏览器不支持 EventSource —— 静默跳过，业务层继续走轮询。
      return;
    }

    let cancelled = false;
    let es: EventSource | null = null;

    const connect = () => {
      if (cancelled) return;
      const qs = new URLSearchParams();
      if (topics && topics.length > 0) qs.set("topics", topics.join(","));
      // 每次重连都带 since_id，保证 at-least-once 语义（前端按 id 去重）
      if (sinceIdRef.current > 0) qs.set("since_id", String(sinceIdRef.current));
      const url = `${basePath}/events/stream${qs.toString() ? `?${qs}` : ""}`;

      try {
        es = new EventSource(url);
      } catch (e) {
        onErrorRef.current?.(e);
        scheduleReconnect();
        return;
      }

      // 通用 onmessage 兜底抓未被事件名命中的帧。SSE 帧本身在 data 字段里
      // 既带 topic 也带 id —— 前端按 topic 自行分发即可。
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as RealtimeFrame;
          if (typeof data.id === "number" && data.id > sinceIdRef.current) {
            sinceIdRef.current = data.id;
          }
          onEventRef.current(data);
        } catch {
          /* ignore malformed frame */
        }
      };

      // 显式事件名: topic=pipeline → 监听 "pipeline" 类型帧
      if (topics && topics.length > 0) {
        for (const t of topics) {
          es.addEventListener(t, (ev: Event) => {
            try {
              const data = JSON.parse((ev as MessageEvent).data) as RealtimeFrame;
              if (typeof data.id === "number" && data.id > sinceIdRef.current) {
                sinceIdRef.current = data.id;
              }
              onEventRef.current(data);
            } catch {
              /* ignore */
            }
          });
        }
      }

      // open 事件 = 连接成功（首次 or 重连后）
      es.onopen = () => {
        if (retryCountRef.current > 0) {
          // 重连成功，重置退避计数
          retryCountRef.current = 0;
        }
        onConnectRef.current?.();
      };

      // 禁用 EventSource 原生重连（默认 3s 固定间隔，不带 since_id）。
      // 改用手动指数退避重连，保证 since_id 补齐 + 避免雪崩。
      es.onerror = () => {
        // 立即关闭当前连接，阻止原生重连
        try {
          es?.close();
        } catch {
          /* ignore */
        }
        es = null;
        onDisconnectRef.current?.();
        onErrorRef.current?.(new Error("SSE connection lost"));
        if (!cancelled) scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (cancelled) return;
      // 指数退避：1s → 2s → 4s → 8s → 16s → 30s（封顶）
      const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000);
      retryCountRef.current += 1;
      reconnectTimerRef.current = setTimeout(connect, delay);
    };

    connect();

    return () => {
      cancelled = true;
      try {
        es?.close();
      } catch {
        /* ignore */
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
    // topics / basePath 变化时重启 EventSource
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, topics?.join(","), basePath]);
}
