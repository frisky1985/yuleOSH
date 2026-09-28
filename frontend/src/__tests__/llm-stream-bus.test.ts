// llm-stream-bus 单元测试：覆盖 applyDelta 纯 reducer 的拼接/去重/reset/
// attempt 切换/done 粘滞/字符上限/LRU 淘汰，以及模块级 store 的订阅通知。

import {
  applyDelta,
  clearDeltas,
  getDeltaSnapshot,
  MAX_CHARS_PER_STEP,
  MAX_STEPS,
  pushDelta,
  subscribeDelta,
  type LlmDeltaPayload,
  type LlmStreamSnapshot,
} from "@/lib/llm-stream-bus";

const empty: LlmStreamSnapshot = { steps: new Map(), order: [], version: 0 };

function frame(over: Partial<LlmDeltaPayload> = {}): LlmDeltaPayload {
  return {
    run_id: "r1",
    project_dir: "/p",
    step_key: "prd",
    step_index: 2,
    text: "",
    seq: null,
    total_chars: 0,
    attempt: 1,
    reset: false,
    done: false,
    model: "deepseek-chat",
    provider: "deepseek",
    ...over,
  };
}

describe("applyDelta", () => {
  it("非法 payload 原样返回（null / 缺 run_id / 缺 step_key）", () => {
    expect(applyDelta(empty, null as never)).toBe(empty);
    expect(applyDelta(empty, frame({ run_id: "" }))).toBe(empty);
    expect(applyDelta(empty, frame({ step_key: "" }))).toBe(empty);
  });

  it("reset 帧建立流（text 清空，attempt 生效）", () => {
    const s1 = applyDelta(empty, frame({ reset: true }));
    const st = s1.steps.get("r1::prd")!;
    expect(st).toBeDefined();
    expect(st.text).toBe("");
    expect(st.attempt).toBe(1);
    expect(st.done).toBe(false);
    expect(s1.order).toEqual(["r1::prd"]);
    expect(s1.version).toBe(1);
  });

  it("chunk 帧按 seq 拼接并累计 totalChars", () => {
    let s = applyDelta(empty, frame({ reset: true }));
    s = applyDelta(s, frame({ text: "Hel", seq: 1, total_chars: 3 }));
    s = applyDelta(s, frame({ text: "lo", seq: 2, total_chars: 5 }));
    const st = s.steps.get("r1::prd")!;
    expect(st.text).toBe("Hello");
    expect(st.totalChars).toBe(5);
    expect(st.lastSeq).toBe(2);
    expect(st.done).toBe(false);
  });

  it("乱序/重复 chunk 帧被丢弃（同 attempt 内 seq 必须递增）", () => {
    let s = applyDelta(empty, frame({ reset: true }));
    s = applyDelta(s, frame({ text: "ab", seq: 2, total_chars: 2 }));
    const before = s;
    // seq 相同与 seq 更小 → 原样返回（无版本递增）
    expect(applyDelta(s, frame({ text: "xx", seq: 2 }))).toBe(before);
    expect(applyDelta(s, frame({ text: "xx", seq: 1 }))).toBe(before);
    const st = s.steps.get("r1::prd")!;
    expect(st.text).toBe("ab");
    expect(st.lastSeq).toBe(2);
  });

  it("seq 为 null 的 chunk 帧不去重（直接追加）", () => {
    let s = applyDelta(empty, frame({ reset: true }));
    s = applyDelta(s, frame({ text: "a", seq: null }));
    s = applyDelta(s, frame({ text: "b", seq: null }));
    const st = s.steps.get("r1::prd")!;
    expect(st.text).toBe("ab");
    expect(st.lastSeq).toBe(0);
  });

  it("attempt 变化 → 重建 base，旧文本作废", () => {
    let s = applyDelta(empty, frame({ reset: true }));
    s = applyDelta(s, frame({ text: "stale", seq: 1, total_chars: 5 }));
    s = applyDelta(s, frame({ reset: true, attempt: 2 }));
    const st = s.steps.get("r1::prd")!;
    expect(st.text).toBe("");
    expect(st.attempt).toBe(2);
    expect(st.lastSeq).toBe(0);
    expect(st.totalChars).toBe(0);
    // 新 attempt 的 chunk 正常累计
    s = applyDelta(s, frame({ text: "fresh", seq: 1, total_chars: 5, attempt: 2 }));
    expect(s.steps.get("r1::prd")!.text).toBe("fresh");
  });

  it("reset 帧即使同 attempt 也清屏（seq 重置）", () => {
    let s = applyDelta(empty, frame({ reset: true }));
    s = applyDelta(s, frame({ text: "abc", seq: 3, total_chars: 3 }));
    s = applyDelta(s, frame({ reset: true }));
    const st = s.steps.get("r1::prd")!;
    expect(st.text).toBe("");
    expect(st.lastSeq).toBe(0);
  });

  it("done 帧粘滞：后续 chunk 不再翻动 done", () => {
    let s = applyDelta(empty, frame({ reset: true }));
    s = applyDelta(s, frame({ done: true }));
    expect(s.steps.get("r1::prd")!.done).toBe(true);
    s = applyDelta(s, frame({ text: "late", seq: 1 }));
    // 迟到帧仍拼接（不丢内容），但 done 保持 true
    const st = s.steps.get("r1::prd")!;
    expect(st.text).toBe("late");
    expect(st.done).toBe(true);
  });

  it("单步文本截断到 MAX_CHARS_PER_STEP", () => {
    const big = "x".repeat(MAX_CHARS_PER_STEP + 100);
    let s = applyDelta(empty, frame({ reset: true }));
    s = applyDelta(
      s,
      frame({ text: big, seq: 1, total_chars: MAX_CHARS_PER_STEP + 100 }),
    );
    const st = s.steps.get("r1::prd")!;
    expect(st.text.length).toBe(MAX_CHARS_PER_STEP);
    // total_chars 用服务端累计值（可大于截断后长度）
    expect(st.totalChars).toBe(MAX_CHARS_PER_STEP + 100);
  });

  it(`超过 ${MAX_STEPS} 步时按 LRU 淘汰最旧`, () => {
    let s = empty;
    for (let i = 0; i < MAX_STEPS + 3; i++) {
      s = applyDelta(
        s,
        frame({ run_id: "r", step_key: `k${i}`, reset: true }),
      );
    }
    expect(s.order.length).toBe(MAX_STEPS);
    // 最旧的三步被淘汰
    expect(s.steps.has("r::k0")).toBe(false);
    expect(s.steps.has("r::k1")).toBe(false);
    expect(s.steps.has("r::k2")).toBe(false);
    expect(s.steps.has(`r::k${MAX_STEPS + 2}`)).toBe(true);
    // 被淘汰的 key 从 steps map 一并清除
    expect(s.steps.size).toBe(MAX_STEPS);
  });

  it("更新既有 step 时 order 置顶且不产生重复项", () => {
    let s = applyDelta(empty, frame({ step_key: "a", reset: true }));
    s = applyDelta(s, frame({ step_key: "b", reset: true }));
    s = applyDelta(s, frame({ step_key: "a", text: "x", seq: 1 }));
    expect(s.order).toEqual(["r1::a", "r1::b"]);
  });
});

describe("llm-stream-bus store", () => {
  beforeEach(() => clearDeltas());
  afterEach(() => clearDeltas());

  it("pushDelta 通知订阅者且快照可读到", () => {
    let notified = 0;
    const unsub = subscribeDelta(() => {
      notified++;
    });
    pushDelta(frame({ reset: true }));
    pushDelta(frame({ text: "hi", seq: 1, total_chars: 2 }));
    expect(notified).toBe(2);
    const st = getDeltaSnapshot().steps.get("r1::prd")!;
    expect(st.text).toBe("hi");
    unsub();
    pushDelta(frame({ text: "!", seq: 2, total_chars: 3 }));
    expect(notified).toBe(2); // 退订后不再通知
  });

  it("无效 push 不通知（快照无变化）", () => {
    let notified = 0;
    subscribeDelta(() => {
      notified++;
    });
    pushDelta(null as never);
    pushDelta(frame({ run_id: "" }));
    expect(notified).toBe(0);
    expect(getDeltaSnapshot().version).toBe(0);
  });

  it("clearDeltas 清空并通知", () => {
    let notified = 0;
    subscribeDelta(() => {
      notified++;
    });
    pushDelta(frame({ reset: true }));
    expect(getDeltaSnapshot().steps.size).toBe(1);
    clearDeltas();
    expect(getDeltaSnapshot().steps.size).toBe(0);
    expect(notified).toBe(2);
    // 已是空时再 clear 为 no-op
    clearDeltas();
    expect(notified).toBe(2);
  });
});
