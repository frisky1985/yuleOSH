"use client";

import { useEffect, useState } from "react";
import { api, type UserInfo } from "@/lib/api";

// ── 模块级缓存：所有消费方共享同一次会话请求 ───────────────────────────────
let _sessionPromise: Promise<UserInfo | null> | null = null;

async function loadSession(): Promise<UserInfo | null> {
  if (!_sessionPromise) {
    _sessionPromise = api.auth
      .session()
      .then((s) => s ?? null)
      .catch(() => null);
  }
  return _sessionPromise;
}

export type AppRole = "admin" | "developer" | "reviewer" | "auditor" | null;

// 角色 → 应用骨架分流：
//   admin / 未登录(null)        → 决策视角（顶栏 dashboard，即当前界面）
//   developer / reviewer / auditor → 工程视角（v5 左侧栏：流水线优先）
export function isEngineerRole(role: AppRole): boolean {
  return role === "developer" || role === "reviewer" || role === "auditor";
}

export function useSessionRole() {
  const [state, setState] = useState<{ role: AppRole; session: UserInfo | null }>({
    role: null,
    session: null,
  });

  useEffect(() => {
    let alive = true;
    loadSession().then((s) => {
      if (alive) setState({ role: (s?.role as AppRole) ?? null, session: s });
    });
    return () => {
      alive = false;
    };
  }, []);

  return state;
}
