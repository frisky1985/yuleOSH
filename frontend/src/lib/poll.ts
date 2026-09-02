// 任务型进度轮询工具：首次立即执行，之后按指数退避（默认 1s 起步，
// 封顶 5s）重试，直到 pollFn 返回 true（任务结束）或调用 stop()。
//
// 相比固定 setInterval，指数退避在长任务（差距批量修复、证据包生成、
// 运行状态轮询）下能显著降低无谓的请求频率，同时首轮仍即时给出反馈。
//
// pollFn 约定：返回 true 表示可以停止轮询；抛错时通过 onError 回调上报，
// 轮询自身不会因此中断（除非明确返回 true）。调用方负责在卸载/关闭时
// 调用返回的 handle.stop() 释放定时器。

export interface PollHandle {
  stop: () => void;
}

export interface ExponentialPollOptions {
  /** 首次轮询后的初始间隔（ms），默认 1000。 */
  initialMs?: number;
  /** 间隔上限（ms），默认 5000，超出不再翻倍。 */
  maxMs?: number;
  /** 轮询抛错时的回调，常用于 setError。 */
  onError?: (e: unknown) => void;
}

export function startExponentialPoll(
  pollFn: () => boolean | Promise<boolean>,
  opts: ExponentialPollOptions = {},
): PollHandle {
  const initialMs = opts.initialMs ?? 1000;
  const maxMs = opts.maxMs ?? 5000;

  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let delay = initialMs;

  const tick = async () => {
    if (stopped) return;
    let done = false;
    try {
      done = !!(await pollFn());
    } catch (e) {
      if (stopped) return;
      opts.onError?.(e);
    }
    if (stopped || done) {
      timer = null;
      return;
    }
    const next = Math.min(delay, maxMs);
    delay = Math.min(delay * 2, maxMs);
    timer = setTimeout(tick, next);
  };

  // 首轮立即执行，不空等 initialMs
  void tick();

  return {
    stop: () => {
      stopped = true;
      if (timer != null) clearTimeout(timer);
      timer = null;
    },
  };
}
