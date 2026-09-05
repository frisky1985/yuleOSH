"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import { TopNav, type DashboardTab } from "@/components/dashboard/top-nav";
import {
  EngineerSidebar,
  SidebarExtrasContext,
  SidebarExtrasSetterContext,
  type SidebarExtras,
} from "@/components/dashboard/engineer-sidebar";
import { isEngineerRole, useSessionRole } from "@/lib/use-session-role";
import { UserMenu, type UserMenuActions, type UserMenuSession } from "@/components/account/user-menu";
import { AccountInfoDialog } from "@/components/account/account-info-dialog";
import { UserSettingsDialog } from "@/components/account/user-settings-dialog";
import { LogoutConfirmDialog } from "@/components/account/logout-confirm-dialog";
import { DeleteAccountDialog } from "@/components/account/delete-account-dialog";
import { RealtimeProvider } from "@/lib/realtime-store";
import { useDashboardTabPersistence } from "@/lib/sidebar-persistence";

interface DashboardShellContextValue {
  activeTab: DashboardTab;
  setActiveTab: (tab: DashboardTab) => void;
}

const DashboardShellContext = createContext<DashboardShellContextValue>({
  activeTab: "overview",
  setActiveTab: () => {},
});

/** 落地页消费：读取/切换顶部 tab（导航由本 layout 渲染，状态提升到这里）。 */
export function useDashboardShell() {
  return useContext(DashboardShellContext);
}

/**
 * 角色感知应用外壳（提升到 layout）。
 *
 * 关键：App Router 的 layout 在同/下级路由切换时**不会重新挂载**，因此
 * 工程师点击左侧栏时左栏保持常驻，仅右侧 children 替换 —— 既不会整页跳转
 * 重建左栏，也不会因角色异步返回而先闪出决策顶栏。
 *
 *  - admin / 未登录 → 决策视角：顶部 TopNav（落地页 tabs / 子页 links）
 *  - developer / reviewer / auditor → 工程视角：v5 左侧栏 + 右侧内容区
 */
export default function DashboardLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { role, session } = useSessionRole();

  // Active tab is URL-driven: /dashboard?tab=gap-analysis activates gap-analysis
  // on first paint. TopNav pushes ?tab= when a tab is clicked from a sub-page
  // (links mode), so the landing page opens straight onto the requested tab
  // without flashing the default "overview" first.
  //
  // Stage-6 (2026-09-05): 同步持久化到 localStorage —— 用户上次停在
  // gap-analysis, 关闭浏览器重开仍直接进 gap-analysis, 不再回 overview。
  // URL ?tab= 优先级仍高于 localStorage (用户主动切)。
  //
  // NOTE: we deliberately avoid `useSearchParams()` — in `output: "export"`
  // (static) builds Next.js requires it to be wrapped in <Suspense>, which
  // would propagate to every /dashboard/* page and break prerender. Instead
  // we read window.location once at mount (client-only; SSR sees the default).
  // The `mounted` gate below guarantees SSR emits no visible shell, so no
  // hydration mismatch.
  const isValidTab = (t: string | null | undefined): t is DashboardTab =>
    t === "overview" ||
    t === "gap-analysis" ||
    t === "misra-trends" ||
    t === "knowledge-base";
  // Stage-6 (2026-09-05): 子页面徽标上报（device 在线数 / 日志错误数 /
  // 追溯缺口）。合并语义 —— 页面只传自己负责的字段，互不覆盖。
  const [sidebarExtras, setSidebarExtras] = useState<SidebarExtras>({});
  const patchSidebarExtras = useCallback((patch: SidebarExtras) => {
    setSidebarExtras((prev) => ({ ...prev, ...patch }));
  }, []);

  const [persistedTab, setPersistedTab] = useDashboardTabPersistence();
  const [activeTab, setActiveTab] = useState<DashboardTab>("overview");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const urlTab = new URLSearchParams(window.location.search).get("tab");
    if (isValidTab(urlTab)) {
      setActiveTab(urlTab);
    } else if (isValidTab(persistedTab)) {
      // URL 没带时, 还原 localStorage 的上次选择
      setActiveTab(persistedTab);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);
  // setActiveTab 包装: 同时更新 localStorage
  const setActiveTabPersisted = useCallback(
    (tab: DashboardTab) => {
      setActiveTab(tab);
      setPersistedTab(tab, { pushUrl: true });
    },
    [setPersistedTab],
  );
  // mounted 门控：服务端/静态 HTML 无法预知角色，未确定前不渲染导航，
  // 既避免 hydration mismatch，也避免闪出错误骨架。
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // 用户菜单受控 Dialog（决策者专属；工程师视角不挂这套，避免 placeholder 干扰）
  const [accountOpen, setAccountOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const isLanding = pathname === "/dashboard";
  // 视图完全由登录用户的角色决定：admin / owner -> 横向决策顶栏（TopNav）；
  // developer / reviewer / auditor / member 及任何未知/遗留角色 -> 纵向工程左栏
  // （EngineerSidebar）。分类以 @/lib/role-view 为准，与后端 rbac/model.py 权限映射对齐。
  // 不再依赖 ?view 预览参数 / localStorage，避免同一浏览器下预览状态跨账号
  // 污染，使两个角色的视图趋同（即"显示没区别"的根因）。
  const engineer = isEngineerRole(role);

  const userMenu = (
    <div className="flex items-center gap-2">
      {session ? (
        <>
          <UserMenu
            session={session as UserMenuSession}
            actions={
              {
                onOpenAccount: () => setAccountOpen(true),
                onOpenSettings: () => setSettingsOpen(true),
                onOpenApiKeys: () => router.push("/dashboard/settings/api-keys"),
                onOpenLogout: () => setLogoutOpen(true),
                onOpenDelete: () => setDeleteOpen(true),
              } satisfies UserMenuActions
            }
          />

          <AccountInfoDialog
            open={accountOpen}
            onOpenChange={setAccountOpen}
            fallbackEmail={session.email}
            fallbackOrgName={session.org_name}
          />
          <UserSettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} userId={session.user_id} />
          <LogoutConfirmDialog
            open={logoutOpen}
            onOpenChange={setLogoutOpen}
            emailLabel={session.email}
          />
          <DeleteAccountDialog
            open={deleteOpen}
            onOpenChange={setDeleteOpen}
            emailLabel={session.email}
          />
        </>
      ) : (
        // 已登出但仍在 /dashboard/* → layout 显示「登录」入口（不区分角色，按钮跳转通用）
        <a
          href="/login"
          className="text-sm px-3 py-1.5 rounded-lg border border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40 transition-all"
        >
          登录
        </a>
      )}
    </div>
  );

  let shell: ReactNode = children;

  if (mounted) {
    shell = engineer ? (
      <RealtimeProvider topics={["pipeline", "evidence", "gap", "coverage", "misra"]}>
        <SidebarExtrasSetterContext.Provider value={patchSidebarExtras}>
          <SidebarExtrasContext.Provider value={sidebarExtras}>
            <EngineerSidebar />
            {/* pt-14 让出窄屏顶栏（<768px 侧栏隐藏、改由顶栏承载导航），
                md 及以上由侧栏占位 md:pl-60，无需顶部内边距。 */}
            <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0] pt-14 md:pt-0 md:pl-60">
              {children}
            </div>
          </SidebarExtrasContext.Provider>
        </SidebarExtrasSetterContext.Provider>
      </RealtimeProvider>
    ) : (
      <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
        <TopNav
          mode={isLanding ? "tabs" : "links"}
          activeTab={activeTab}
          onTabChange={setActiveTabPersisted}
        >
          {/* 用户菜单（含退出登录）必须在落地页与所有子页常驻：
              此前用 isLanding 门控，导致决策者一旦进入流水线/设备/日志等子页
              右上角菜单整块消失、无法登出（工程师侧栏底部常驻登出，故仅决策者受影响）。 */}
          {userMenu}
        </TopNav>
        {children}
      </div>
    );
  }

  return (
    <DashboardShellContext.Provider value={{ activeTab, setActiveTab }}>
      {shell}
    </DashboardShellContext.Provider>
  );
}
