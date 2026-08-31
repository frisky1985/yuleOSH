"use client";

import { useEffect, useState, type ReactNode } from "react";
import { TopNav, type DashboardTab } from "@/components/dashboard/top-nav";
import { EngineerSidebar } from "@/components/dashboard/engineer-sidebar";
import { useSessionRole, isEngineerRole } from "@/lib/use-session-role";

interface DashboardChromeProps {
  /** "tabs" 落地页（渲染页内 tab 导航）；"links" 子页面（仅链接导航）。 */
  mode: "tabs" | "links";
  /** 当前 tab — mode="tabs" 必填。 */
  activeTab?: DashboardTab;
  onTabChange?: (tab: DashboardTab) => void;
  /** 顶栏右侧用户菜单（仅 mode="tabs" 决策视角使用）。 */
  userMenu?: ReactNode;
  children: ReactNode;
}

/**
 * 角色感知应用外壳：
 *  - 工程师角色（developer/reviewer/auditor）→ v5 左侧栏布局
 *  - 决策者（admin）/ 未登录 → 维持当前顶栏 dashboard
 * 登录后由 useSessionRole 自动分流，无需手动切换。
 *
 * 预览开关：URL 携带 ?view=engineer 强制工程左栏、?view=manage 强制决策顶栏，
 * 便于未持工程师账号时直接预览（不影响真实角色判定）。
 */
export function DashboardChrome({
  mode,
  activeTab,
  onTabChange,
  userMenu,
  children,
}: DashboardChromeProps) {
  const { role } = useSessionRole();
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setPreview(new URLSearchParams(window.location.search).get("view"));
  }, []);

  const engineer =
    preview === "engineer" || (preview !== "manage" && isEngineerRole(role));

  if (engineer) {
    return (
      <>
        <EngineerSidebar />
        <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0] md:pl-60">
          {children}
        </div>
      </>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      <TopNav mode={mode} activeTab={activeTab} onTabChange={onTabChange}>
        {userMenu}
      </TopNav>
      {children}
    </div>
  );
}
