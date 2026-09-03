// 角色 → 视图 分流（单一事实来源消费端）。
//
// dashboard/layout.tsx 按 isEngineerRole(role) 在「决策视角（TopNav 横向）」与
// 「工程视角（EngineerSidebar 纵向）」之间分流；user-menu.tsx 用 viewOf 渲染
// 视图徽标。两处共用本模块，避免分流逻辑漂移导致两视图趋同——即「决策者 /
// 工程师演示账号视图不同」不变量被破坏。
//
// 本模块不再自行定义角色语义，而是消费 codegen 生成的 role-contract.generated.ts
// （其唯一事实来源是后端 src/yuleosh/rbac/role_contract.py）。改角色映射请改后端
// 契约并重跑 scripts/gen_role_contract.py，否则 CI 的契约一致性测试会挂。
//   admin / owner                  → 决策视角（TopNav，对应后端 ROLE_ADMIN）
//   developer / reviewer / auditor / member / architect / quality_manager / viewer
//                                 → 工程视角（EngineerSidebar，对应各自权限档）
//   null（未登录兜底）             → 决策视角（默认顶栏）

import { type OrgRole, type UiView, ROLE_UI_VIEW } from "./role-contract.generated";

export type AppRole = OrgRole | null;

/** 是否工程视角（左侧纵向导航）。决策视角 = admin / owner / null；其余（含 member 与未知/遗留角色）均为工程视角，对齐后端权限映射。 */
export function isEngineerRole(role: string | null): boolean {
  if (role === null) return false; // 未登录兜底 → 决策视角
  if (role === "admin" || role === "owner") return false; // 决策视角
  // 其余角色以契约 ROLE_UI_VIEW 为准；未知/遗留角色下沉为工程视角（与后端默认 developer 一致）。
  return (ROLE_UI_VIEW[role] ?? "engineer") === "engineer";
}

export type ViewTone = "decision" | "engineer";

export interface RoleView {
  label: string;
  tone: ViewTone;
}

/** 角色 → 视图标签 + 色调（与 layout.tsx 的 isEngineerRole 分流一致，并对齐后端契约）。 */
export function viewOf(role?: string | null): RoleView {
  if (role === null) return { label: "决策视角", tone: "decision" }; // 未登录兜底
  if (role === "admin" || role === "owner") {
    return { label: "决策视角", tone: "decision" };
  }
  // 其余角色以契约 ROLE_UI_VIEW 为准；未知/遗留角色（含 undefined 兜底）下沉为工程视角。
  const tone: UiView = (role ? ROLE_UI_VIEW[role] : undefined) ?? "engineer";
  return { label: tone === "decision" ? "决策视角" : "工程视角", tone };
}

export const VIEW_BADGE_CLS: Record<ViewTone, string> = {
  decision: "border-[#722ed1]/40 text-[#a78bfa] bg-[#722ed1]/10",
  engineer: "border-[#1677ff]/40 text-[#60a5fa] bg-[#1677ff]/10",
};
