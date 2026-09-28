"use client";

/** LLM 流式输出总线 —— ``llm_delta`` 事件的模块级 pub/sub。
 *
 * 为什么不进 RealtimeStore：llm_delta 是高频 token 增量（后端合并后仍可能
 * 秒级多次），进全局 Context 会让整个 dashboard 跟着重渲染。这里用独立的
 * 模块级 store + ``useSyncExternalStore``，只有 LLMLiveOutputPanel 订阅，
 * 渲染开销隔离在面板内。
 *
 * 后端契约（realtime.emit_pipeline_llm_delta，ephemeral 不入 replay）：
 *   reset 帧 —— attempt+1、text=""，前端据此清屏重放（provider 重试/回退
 *   后 attempt 变化，旧 attempt 的 delta 作废）；
 *   chunk 帧 —— text=合并后的增量，同 attempt 内 seq 单调递增；
 *   done 帧  —— done=true（正常/异常终止都会收到，流生命周期结束）。
 *
 * 去重：SSE at-least-once 可能重发/迟到；chunk 帧按 (attempt, seq) 去重，
 * reset/done 帧总是应用。
 */

export interface LlmDeltaPayload {
  run_id: string;
  project_dir: string;
  step_key: string;
  step_index: number;
  text: string;
  seq: number | null;
  total_chars: number;
  attempt: number;
  reset: boolean;
  done: boolean;
  model: string;
  provider: string;
}

export interface StepStream {
  runId: string;
  projectDir: string;
  stepKey: string;
  stepIndex: number;
  model: string;
  provider: string;
  /** 已接收文本（截断到 MAX_CHARS_PER_STEP） */
  text: string;
  /** 服务端累计字符数（total_chars，可能大于 text.length） */
  totalChars: number;
  done: boolean;
  attempt: number;
  lastSeq: number;
  updatedAt: number;
}

export const MAX_CHARS_PER_STEP = 200_000;
export const MAX_STEPS = 20;

export interface LlmStreamSnapshot {
  steps: ReadonlyMap<string, StepStream>;
  /** 最近更新的 key 在前（LRU 淘汰最旧） */
  order: readonly string[];
  version: number;
}

const emptySnapshot: LlmStreamSnapshot = {
  steps: new Map(),
  order: [],
  version: 0,
};

/** 纯函数：把一帧 delta 应用到快照，返回新快照（无变化时原样返回）。 */
export function applyDelta(
  snap: LlmStreamSnapshot,
  p: LlmDeltaPayload,
  now: number = Date.now(),
): LlmStreamSnapshot {
  if (!p || typeof p !== "object") return snap;
  if (!p.run_id || !p.step_key) return snap;
  const key = `${p.run_id}::${p.step_key}`;

  const existing = snap.steps.get(key);
  const attemptChanged = !existing || existing.attempt !== p.attempt;

  // chunk 帧去重：同 attempt 内 seq 必须递增
  if (!p.done && !p.reset && existing && !attemptChanged) {
    if (p.seq != null && p.seq <= existing.lastSeq) return snap;
  }

  const base: StepStream =
    existing && !attemptChanged && !p.reset
      ? existing
      : {
          runId: p.run_id,
          projectDir: p.project_dir || "",
          stepKey: p.step_key,
          stepIndex: p.step_index ?? -1,
          model: p.model || "",
          provider: p.provider || "",
          text: "",
          totalChars: 0,
          done: false,
          attempt: p.attempt,
          lastSeq: 0,
          updatedAt: now,
        };

  const appended = p.text ? base.text + p.text : base.text;
  const text =
    appended.length > MAX_CHARS_PER_STEP
      ? appended.slice(0, MAX_CHARS_PER_STEP)
      : appended;

  const next: StepStream = {
    ...base,
    text,
    totalChars: Math.max(base.totalChars, p.total_chars || text.length),
    done: p.done ? true : base.done,
    lastSeq:
      p.seq != null && !p.done ? Math.max(base.lastSeq, p.seq) : base.lastSeq,
    model: p.model || base.model,
    provider: p.provider || base.provider,
    updatedAt: now,
  };

  const steps = new Map(snap.steps);
  steps.set(key, next);
  const order = [
    key,
    ...snap.order.filter((k) => k !== key),
  ].slice(0, MAX_STEPS);
  for (const k of snap.order) {
    if (!order.includes(k)) steps.delete(k);
  }
  return { steps, order, version: snap.version + 1 };
}

// ── 模块级 store ────────────────────────────────────────────────────────────

let current: LlmStreamSnapshot = emptySnapshot;
const listeners = new Set<() => void>();

export function pushDelta(p: LlmDeltaPayload): void {
  const next = applyDelta(current, p);
  if (next === current) return;
  current = next;
  listeners.forEach((l) => l());
}

export function subscribeDelta(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getDeltaSnapshot(): LlmStreamSnapshot {
  return current;
}

/** 清空全部流（例如切换 run 时由调用方决定）。 */
export function clearDeltas(): void {
  if (current.steps.size === 0) return;
  current = emptySnapshot;
  listeners.forEach((l) => l());
}
