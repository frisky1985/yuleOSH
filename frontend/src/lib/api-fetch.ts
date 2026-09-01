/**
 * yuleOSH 共享 API 取数工具
 *
 * 将原先散落在 9 个 dashboard 页中、逐字一致的本地 `apiFetch` 收敛到此处，
 * 消除重复定义。行为与原实现保持一致：
 *  - 携带 same-origin cookie（与后端 httpOnly 鉴权模型一致）；
 *  - 解包 `{ ok, data? }` 信封；
 *  - 非 JSON 响应抛错，避免 JSON.parse 崩溃。
 *
 * 新增修复（原 9 处共同缺陷）：**401 → 失效会话缓存并跳登录页**。
 * 之前会话过期时页面只会显示通用报错文本、不会送回登录页。
 *
 * 注意：本机 8080 运行在 AUTH_ENABLED=False 免登录模式，不会返回 401，
 * 该分支仅在真实鉴权部署（AUTH_ENABLED=True）下生效。
 */

import { resetSessionCache } from "@/lib/use-session-role";

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  // 401：会话过期 / 未登录。失效模块级会话缓存（防跨账号串身份），送回登录页。
  if (res.status === 401) {
    resetSessionCache();
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
    throw new Error("未授权，请重新登录");
  }

  const contentType = res.headers.get("content-type") || "";
  let body: unknown = null;
  if (contentType.includes("application/json")) {
    body = await res.json();
  } else {
    const text = await res.text();
    throw new Error(`Non-JSON response (${res.status}): ${text.slice(0, 200)}`);
  }
  const record = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
  if (record.ok === false) {
    throw new Error(typeof record.error === "string" ? record.error : `API error (${res.status})`);
  }
  const payload = record.data !== undefined ? record.data : body;
  return payload as T;
}
