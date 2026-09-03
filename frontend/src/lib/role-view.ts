// 角色 → 视图 单一事实来源（single source of truth）。
//
// dashboard/layout.tsx 按 isEngineerRole(role) 在「决策视角（TopNav 横向）」与
// 「工程视角（EngineerSidebar 纵向）」之间分流；user-menu.tsx 用 viewOf 渲染
// 视图徽标。两处共用本模块，避免分流逻辑漂移导致两视图趋同——即「决策者 /
// 工程师演示账号视图不同」不变量被破坏。
//
// 本模块的权威分类必须与后端 rbac/model.py::get_role_from_user_info 对齐
// （该函数是权限校验的唯一事实来源，本模块不可自行发明角色语义）：
//   admin / owner                  → 决策视角（TopNav，对应后端 ROLE_ADMIN）
//   developer / reviewer / auditor → 工程视角（EngineerSidebar）
//   member                         → 工程视角（后端把 member 映射为 ROLE_DEVELOPER，
//                                    故成员拥有开发者级权限；UI 必须展示工程视图，
//                                    否则成员看不到其被授权使用的工程功能）
//   其它 / 未知 / 遗留角色          → 工程视角（后端对未知角色默认 ROLE_DEVELOPER）
//   null（未登录兜底）             → 决策视角（默认顶栏）

export type AppRole =
  | "admin"
  | "owner"
  | "developer"
  | "reviewer"
  | "auditor"
  | "member"
  | "viewer"
  | "architect"
  | "quality_manager"
  | null;

/** 是否工程视角（左侧纵向导航）。决策视角 = admin / owner / null；其余（含 member 与未知/遗留角色）均为工程视角，对齐后端权限映射。 */
export function isEngineerRole(role: string | null): boolean {
  if (role === null) return false; // 未登录兜底 → 决策视角
  if (role === "admin" || role === "owner") return false; // 决策视角
  return true; // developer/reviewer/auditor/member + 任何未知/遗留角色 → 工程视角
}

export type ViewTone = "decision" | "engineer";

export interface RoleView {
  label: string;
  tone: ViewTone;
}

/** 角色 → 视图标签 + 色调（与 layout.tsx 的 isEngineerRole 分流一致，并对齐后端权限模型）。 */
export function viewOf(role?: string | null): RoleView {
  if (role === null) return { label: "决策视角", tone: "decision" }; // 未登录兜底
  if (role === "admin" || role === "owner") {
    return { label: "决策视角", tone: "decision" };
  }
  // developer / reviewer / auditor / member 及任何未知/遗留角色 → 工程视角
  // （member 与后端 rbac/model.py 的 member→ROLE_DEVELOPER 对齐；
  //  未知角色与后端对未知角色默认 ROLE_DEVELOPER 对齐）
  return { label: "工程视角", tone: "engineer" };
}

export const VIEW_BADGE_CLS: Record<ViewTone, string> = {
  decision: "border-[#722ed1]/40 text-[#a78bfa] bg-[#722ed1]/10",
  engineer: "border-[#1677ff]/40 text-[#60a5fa] bg-[#1677ff]/10",
};
