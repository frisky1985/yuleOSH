"use client";

import { useEffect, useState } from "react";
import { api, type UserInfo } from "@/lib/api";

// ── 模块级缓存：所有消费方共享同一次会话请求 ───────────────────────────────
let _sessionPromise: Promise<UserInfo | null> | null = null;

// 角色缓存到 localStorage：会话请求是异步的，若首帧无法判定角色就会先渲染
// 决策顶栏再切到工程左栏（可见闪烁）。缓存后首帧即可确定骨架。
const LS_ROLE_KEY = "yuleosh_role";

async function loadSession(): Promise<UserInfo | null> {
  if (!_sessionPromise) {
    _sessionPromise = api.auth
      .session()
      .then((s) => s ?? null)
      .catch(() => null);
  }
  const s = await _sessionPromise;
  if (s?.role && typeof window !== "undefined") {
    try {
      window.localStorage.setItem(LS_ROLE_KEY, s.role);
    } catch {
      /* 忽略隐私模式写入失败 */
    }
  }
  return s;
}

/** 同步读取上次缓存的角色（仅用于首帧骨架判定）。 */
export function getCachedRole(): AppRole {
  if (typeof window === "undefined") return null;
  try {
    return (window.localStorage.getItem(LS_ROLE_KEY) as AppRole) ?? null;
  } catch {
    return null;
  }
}

export type AppRole = "admin" | "developer" | "reviewer" | "auditor" | "member" | null;

// 骨架预览开关（?view=engineer|manage）。必须持久化：左栏链接若不携带该参数，
// 一旦发生整页加载（硬导航 / 刷新子页），layout 会重新挂载并重新读取 URL，
// 参数丢失就会回落到决策顶栏 —— 表现为"点左栏后左栏消失"。
// 用 localStorage 持久化（而非 sessionStorage / 纯 URL），刷新与硬导航后仍能恢复。
const VIEW_PREVIEW_KEY = "yuleosh_view_preview";

/**
 * 读取当前骨架预览模式：URL 参数优先（并写入 localStorage 持久化），
 * 否则回落到 localStorage（刷新 / 硬导航后保留，解决"点左栏后左栏消失"）。
 */
export function readViewPreview(): "engineer" | "manage" | null {
  if (typeof window === "undefined") return null;
  const fromUrl = new URLSearchParams(window.location.search).get("view");
  if (fromUrl === "engineer" || fromUrl === "manage") {
    try {
      window.localStorage.setItem(VIEW_PREVIEW_KEY, fromUrl);
    } catch {
      /* 忽略隐私模式写入失败 */
    }
    return fromUrl;
  }
  try {
    const stored = window.localStorage.getItem(VIEW_PREVIEW_KEY);
    return stored === "engineer" || stored === "manage" ? stored : null;
  } catch {
    return null;
  }
}

// 角色 → 应用骨架分流：
//   admin / 未登录(null)        → 决策视角（顶栏 dashboard，即当前界面）
//   developer / reviewer / auditor → 工程视角（v5 左侧栏：流水线优先）
export function isEngineerRole(role: AppRole): boolean {
  return role === "developer" || role === "reviewer" || role === "auditor";
}

export function useSessionRole() {
  const [state, setState] = useState<{ role: AppRole; session: UserInfo | null }>({
    // 首帧直接用缓存角色，避免"先顶栏后左栏"的骨架闪烁。
    role: getCachedRole(),
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
