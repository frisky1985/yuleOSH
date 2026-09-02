// 角色 → 视图 单一事实来源（single source of truth）。
//
// dashboard/layout.tsx 按 isEngineerRole(role) 在「决策视角（TopNav 横向）」与
// 「工程视角（EngineerSidebar 纵向）」之间分流；user-menu.tsx 用 viewOf 渲染
// 视图徽标。两处共用本模块，避免分流逻辑漂移导致两视图趋同——即「决策者 /
// 工程师演示账号视图不同」不变量被破坏。
//
// 角色清单与后端 rbac/model.py / auth_extended.ensure_view_test_accounts 对齐：
//   admin                          → 决策视角
//   developer / reviewer / auditor → 工程视角
//   member / 其它 / 未登录(null)    → 决策视角（默认顶栏）

export type AppRole =
  | "admin"
  | "developer"
  | "reviewer"
  | "auditor"
  | "member"
  | null;

/** 是否工程视角（左侧纵向导航）。决策 / 成员 / 未知 → 决策视角。 */
export function isEngineerRole(role: AppRole): boolean {
  return role === "developer" || role === "reviewer" || role === "auditor";
}

export type ViewTone = "decision" | "engineer" | "member";

export interface RoleView {
  label: string;
  tone: ViewTone;
}

/** 角色 → 视图标签 + 色调（与 layout.tsx 的 isEngineerRole 分流一致）。 */
export function viewOf(role?: string | null): RoleView {
  if (role === "developer" || role === "reviewer" || role === "auditor") {
    return { label: "工程视角", tone: "engineer" };
  }
  if (role === "admin") {
    return { label: "决策视角", tone: "decision" };
  }
  return { label: "成员视角", tone: "member" };
}

export const VIEW_BADGE_CLS: Record<ViewTone, string> = {
  decision: "border-[#722ed1]/40 text-[#a78bfa] bg-[#722ed1]/10",
  engineer: "border-[#1677ff]/40 text-[#60a5fa] bg-[#1677ff]/10",
  member: "border-[#334155] text-[#94a3b8] bg-[#1e293b]",
};
