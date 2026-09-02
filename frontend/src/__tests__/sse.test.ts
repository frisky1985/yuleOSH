// subscribeSSE 单元测试：覆盖「SSE 成功推送终态」「环境无 EventSource 直接走轮询」
// 「连接错误自动降级轮询」三条路径。EventSource 在 jsdom 中默认未实现，这里
// 用 FakeES 模拟并按需挂载到 global。

import { subscribeSSE } from "@/lib/sse";

class FakeES {
  static instances: FakeES[] = [];
  url: string;
  listeners: Record<string, (ev: { data: string }) => void> = {};
  onerror: (() => void) | null = null;
  closed = false;
  constructor(url: string) {
    this.url = url;
    FakeES.instances.push(this);
  }
  addEventListener(type: string, cb: (ev: { data: string }) => void) {
    this.listeners[type] = cb;
  }
  close() {
    this.closed = true;
  }
  emit(type: string, data: string) {
    this.listeners[type]?.({ data });
  }
  triggerError() {
    this.onerror?.();
  }
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("subscribeSSE", () => {
  afterEach(() => {
    FakeES.instances = [];
    delete (global as any).EventSource;
  });

  it("SSE 推送终态时调用 onStatus 并关闭连接", () => {
    (global as any).EventSource = FakeES;
    const onStatus = jest.fn((d: any) => d.status === "completed");
    const handle = subscribeSSE({
      url: "/api/v1/x/stream?task_id=t1",
      onStatus,
    });

    const es = FakeES.instances[0];
    es.emit("status", JSON.stringify({ status: "running", progress_pct: 10 }));
    es.emit("status", JSON.stringify({ status: "completed", progress_pct: 100 }));

    expect(onStatus).toHaveBeenCalledTimes(2);
    expect(onStatus.mock.calls[0][0]).toEqual({
      status: "running",
      progress_pct: 10,
    });
    expect(es.closed).toBe(true); // 终态后 stop() 关闭
    handle.stop();
  });

  it("环境无 EventSource 时直接走 fallbackPoll", () => {
    const fallbackPoll = jest.fn(() => false);
    const onStatus = jest.fn();
    const handle = subscribeSSE({
      url: "/api/v1/x/stream?task_id=t1",
      onStatus,
      fallbackPoll,
    });
    expect(fallbackPoll).toHaveBeenCalled();
    expect(onStatus).not.toHaveBeenCalled();
    handle.stop();
  });

  it("SSE 连接错误时自动降级到 fallbackPoll 并关闭原连接", async () => {
    (global as any).EventSource = FakeES;
    FakeES.instances = [];
    const fallbackPoll = jest.fn().mockResolvedValue(false);
    const onStatus = jest.fn(() => false);
    const handle = subscribeSSE({
      url: "/api/v1/x/stream?task_id=t1",
      onStatus,
      fallbackPoll,
    });

    const es = FakeES.instances[0];
    es.triggerError();

    await flush();
    expect(es.closed).toBe(true);
    expect(fallbackPoll).toHaveBeenCalled();
    handle.stop();
  });

  it("gone 事件停止全部且不盲目轮询", () => {
    (global as any).EventSource = FakeES;
    const fallbackPoll = jest.fn(() => false);
    const onGone = jest.fn();
    const handle = subscribeSSE({
      url: "/api/v1/x/stream?task_id=t1",
      onStatus: () => false,
      fallbackPoll,
      onGone,
    });
    const es = FakeES.instances[0];
    es.emit("gone", "{}");
    expect(onGone).toHaveBeenCalled();
    expect(es.closed).toBe(true);
    expect(fallbackPoll).not.toHaveBeenCalled();
    handle.stop();
  });
});
