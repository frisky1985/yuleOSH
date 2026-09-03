"use client";

import { useEffect, useState } from "react";
import { api, type UserInfo } from "@/lib/api";
import { type AppRole, isEngineerRole } from "@/lib/role-view";
// 角色 → 视图判定集中到 @/lib/role-view（单一事实来源），本模块 re-export
// 以兼容既有引用（layout.tsx、role-view.test.ts 等）。
export { isEngineerRole, type AppRole } from "@/lib/role-view";

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

/**
 * 失效会话缓存 —— 登出、以及重新登录（可能换了账号）时必须调用。
 *
 * 关键：`_sessionPromise` 是**模块级**缓存，而 router.push("/login") 属客户端
 * 跳转、不会重载页面，模块状态原样保留。若不主动失效，用另一个账号重新登录后
 * loadSession() 会直接返回上一次账号的会话，骨架/邮箱/组织全部停留在旧身份，
 * 表现为「换了账号但视图没变」。localStorage 的角色缓存同理，一并清除。
 */
export function resetSessionCache() {
  _sessionPromise = null;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(LS_ROLE_KEY);
    } catch {
      /* 忽略隐私模式写入失败 */
    }
  }
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

// 角色 → 应用骨架分流逻辑已移至 @/lib/role-view（见该模块注释）；
// 本模块仅 re-export（顶部 export ... from "@/lib/role-view"），不再本地定义，
// 避免分流逻辑漂移。
//   admin / owner / 未登录(null) → 决策视角（顶栏 dashboard，横向）
//   developer / reviewer / auditor / member / 未知角色 → 工程视角（v5 左侧栏，纵向）
//   （分类以 @/lib/role-view 为准，对齐后端 rbac/model.py 权限映射）


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
