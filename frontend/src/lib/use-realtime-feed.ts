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
  /** 显式禁用；用于 SSR / 单测。 */
  enabled?: boolean;
  /** 自定义基础 URL（默认用 `/api/v1`）。 */
  basePath?: string;
}

export function useRealtimeFeed(opts: UseRealtimeFeedOptions): void {
  const { topics, onEvent, onError, enabled = true, basePath = "/api/v1" } = opts;
  // 用 ref 让回调读到最新函数（避免 effect 频繁重启 EventSource）
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  // since_id 在组件生命周期内单调累积（用 ref，避免渲染期间变化）
  const sinceIdRef = useRef<number>(0);

  useEffect(() => {
    if (!enabled) return;
    if (typeof EventSource === "undefined") {
      // SSR 期间或浏览器不支持 EventSource —— 静默跳过，业务层继续走轮询。
      return;
    }
    const qs = new URLSearchParams();
    if (topics && topics.length > 0) qs.set("topics", topics.join(","));
    if (sinceIdRef.current > 0) qs.set("since_id", String(sinceIdRef.current));
    const url = `${basePath}/events/stream${qs.toString() ? `?${qs}` : ""}`;

    let es: EventSource;
    try {
      es = new EventSource(url);
    } catch (e) {
      onErrorRef.current?.(e);
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

    es.onerror = (ev) => {
      onErrorRef.current?.(ev);
      // EventSource 在断线时会自动尝试重连（默认 ~3s），不需要手动重连；
      // 但因服务端心跳很密，长时间静默才触发 error。这里仅记录，不主动关闭。
    };

    return () => {
      try {
        es.close();
      } catch {
        /* ignore */
      }
    };
    // topics / basePath 变化时重启 EventSource
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, topics?.join(","), basePath]);
}
