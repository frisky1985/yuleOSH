// SSE 订阅助手：优先用 EventSource 接收服务端推送（只在状态变化时来包，
// 见后端 _sse_stream），连接失败 / 不支持 / 被代理掐断时自动退回指数退避轮询。
//
// 与 pipeline 页（T10）内联的 SSE 逻辑保持一致：本会话一旦降级到轮询就不再
// 重开 SSE；终态由 onStatus 返回 true 判定，助手随即关闭连接/轮询。
//
// subscribeSSE 返回的 handle.stop() 同时关掉 EventSource 与兜底轮询，组件
// 卸载或任务终态时调用即可。

import { startExponentialPoll, type PollHandle } from "./poll";

export interface SubscribeSSEOptions<T> {
  /** SSE 订阅 URL（相对或绝对均可，建议相对 /api/v1/...）。 */
  url: string;
  /**
   * 收到 `event: status` 帧时回调（data 已 JSON.parse）。
   * 返回 true 表示任务已到终态（completed/failed），助手会立即停止。
   */
  onStatus: (data: T) => boolean;
  /** 可选：收到 `event: gone`（资源已不存在）时回调。默认等同连接中断。 */
  onGone?: () => void;
  /** SSE 事件名，默认 "status"。后端单条差距 run 流用 "run"。 */
  eventName?: string;
  /** SSE 不可用 / 连接中断且未到终态时的轮询兜底。返回 true 表示终态。 */
  fallbackPoll?: () => boolean | Promise<boolean>;
  /** SSE 与轮询各自的错误回调（常用于 setError）。 */
  onError?: (e: unknown) => void;
}

export interface SSEHandle {
  /** 停止全部（EventSource + 兜底轮询）。 */
  stop: () => void;
  /** 主动放弃 SSE 切到轮询兜底。 */
  fallback: () => void;
}

export function subscribeSSE<T = Record<string, unknown>>(
  opts: SubscribeSSEOptions<T>,
): SSEHandle {
  let stopped = false; // 显式停止（卸载 / 已到终态）
  let es: EventSource | null = null;
  let poll: PollHandle | null = null;

  const finishAll = () => {
    if (es) {
      try {
        es.close();
      } catch {
        /* ignore */
      }
      es = null;
    }
    if (poll) {
      poll.stop();
      poll = null;
    }
  };

  const stop = () => {
    stopped = true;
    finishAll();
  };

  const startPoll = () => {
    if (stopped || poll) return;
    if (!opts.fallbackPoll) {
      stopped = true;
      return;
    }
    poll = startExponentialPoll(
      async () => {
        try {
          return !!(await opts.fallbackPoll!());
        } catch (e) {
          opts.onError?.(e);
          return false;
        }
      },
      { onError: opts.onError },
    );
  };

  // 环境不支持 EventSource（如极旧浏览器 / SSR）直接走轮询兜底。
  if (typeof EventSource === "undefined" || !opts.url) {
    startPoll();
    return { stop, fallback: startPoll };
  }

  try {
    es = new EventSource(opts.url);
  } catch {
    startPoll();
    return { stop, fallback: startPoll };
  }

  const eventName = opts.eventName || "status";
  es.addEventListener(eventName, (ev: Event) => {
    if (stopped || !es) return;
    try {
      const data = JSON.parse((ev as MessageEvent).data) as T;
      if (opts.onStatus(data)) stop();
    } catch {
      /* 忽略损坏帧，等下一帧 */
    }
  });

  es.addEventListener("gone", () => {
    if (stopped) return;
    opts.onGone?.();
    // 资源确已不存在：停止全部，不盲目轮询（避免 404 死循环）。
    stop();
  });

  es.onerror = () => {
    // 连接被服务端关闭（含终态后正常关闭）或网络中断。
    // 若 onStatus 已处理终态并 stop()，stopped 为真，此处直接返回。
    if (stopped || !es) return;
    try {
      es.close();
    } catch {
      /* ignore */
    }
    es = null;
    startPoll();
  };

  return { stop, fallback: startPoll };
}
