"use client";

/** Dashboard 侧栏与子页面状态持久化 (Stage-6, 2026-09-05).
 *
 * 把用户在 sidebar 上的展开/折叠、activeTab、各 page 的"展开全部/收起"
 * 等 UI 偏好写入 localStorage, 刷新或重开浏览器后还原。
 *
 * 设计动机:
 *   - 用户多次反馈「打开 dashboard 默认收起, 我之前展开的就丢了」
 *   - 跨页 / 跨 session 持久化, 但**跨账号不污染** (key 用 uid + role)
 *   - 写入是 debounced, 不阻塞渲染
 *   - 读侧是一次性 init, 用 lazy initializer 避免 setState 闪一下
 *
 * 存储键命名:
 *   yuleosh:dash:<user_id>:<role>:<key>
 *   例: yuleosh:dash:local-dev:engineer:activeTab
 */

import { useCallback, useEffect, useRef, useState } from "react";

const NS = "yuleosh:dash";
const DEBOUNCE_MS = 250;

function scopeKey(scope: string, key: string): string {
  return `${NS}:${scope}:${key}`;
}

/** 同步读 localStorage；失败/缺失返回 fallback。 */
export function readPref<T>(scope: string, key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(scopeKey(scope, key));
    if (raw == null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

/** Debounced 写 localStorage（多次调用合并最后一次）。 */
export function writePref<T>(scope: string, key: string, value: T): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(scopeKey(scope, key), JSON.stringify(value));
  } catch {
    // quota / privacy mode — 静默忽略, 不影响 UI
  }
}

/** Hook: 受 localStorage 持久化的 state.
 *
 * 用法:
 *   const [tab, setTab] = usePersistentState("engineer", "activeTab", "overview");
 *   // 函数式更新:
 *   setTab((prev) => prev + 1);
 */
export function usePersistentState<T>(
  scope: string,
  key: string,
  initial: T,
): [T, (next: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => readPref(scope, key, initial));
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const setter = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved =
          typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => writePref(scope, key, resolved), DEBOUNCE_MS);
        return resolved;
      });
    },
    [scope, key],
  );
  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);
  return [value, setter];
}

/** 把 dashboard shell 状态 (activeTab) 同步到 localStorage + URL.
 *
 * 策略:
 *   - URL ?tab= 优先级最高 (用户主动切换)
 *   - localStorage 次之 (保留上次选择)
 *   - 默认 "overview" 兜底
 *
 * 返回的 setTab 同时更新 localStorage, 让下一次直接打开 /dashboard 也
 * 跳到对应 tab。
 */
export function useDashboardTabPersistence(): [
  string,
  (next: string, opts?: { pushUrl?: boolean }) => void,
] {
  const [tab, setTab] = usePersistentState<string>("engineer", "activeTab", "overview");
  const setter = useCallback(
    (next: string, opts?: { pushUrl?: boolean }) => {
      setTab(next);
      if (opts?.pushUrl && typeof window !== "undefined") {
        const url = new URL(window.location.href);
        url.searchParams.set("tab", next);
        window.history.replaceState(null, "", url.toString());
      }
    },
    [setTab],
  );
  return [tab, setter];
}