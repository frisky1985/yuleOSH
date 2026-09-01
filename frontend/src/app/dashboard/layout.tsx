"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Settings, User as UserIcon } from "lucide-react";

import { TopNav, type DashboardTab } from "@/components/dashboard/top-nav";
import { EngineerSidebar } from "@/components/dashboard/engineer-sidebar";
import { isEngineerRole, useSessionRole } from "@/lib/use-session-role";
import { api } from "@/lib/api";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

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

function initialOf(email?: string) {
  return email?.[0]?.toUpperCase() ?? "YU";
}

function nameOf(email?: string) {
  return email?.split("@")[0] ?? "用户";
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

  const [activeTab, setActiveTab] = useState<DashboardTab>("overview");
  // mounted 门控：服务端/静态 HTML 无法预知角色，未确定前不渲染导航，
  // 既避免 hydration mismatch，也避免闪出错误骨架。
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isLanding = pathname === "/dashboard";
  // 视图完全由登录用户的角色决定：admin -> 横向决策顶栏（TopNav）；
  // developer / reviewer / auditor -> 纵向工程左栏（EngineerSidebar）。
  // 不再依赖 ?view 预览参数 / localStorage，避免同一浏览器下预览状态跨账号
  // 污染，使两个角色的视图趋同（即"显示没区别"的根因）。
  const engineer = isEngineerRole(role);

  const handleLogout = async () => {
    try {
      await api.auth.logout();
    } catch {
      /* 忽略登出失败，直接跳转 */
    }
    router.push("/login");
  };

  const userMenu = (
    <div className="flex items-center gap-2">
      {session ? (
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-2 rounded-lg border border-[#1e293b] hover:border-[#722ed1]/40 px-2 py-1 transition-all cursor-pointer">
            <Avatar className="w-7 h-7 border border-[#1e293b]">
              <AvatarFallback className="bg-[#722ed1]/20 text-[#722ed1] text-[10px]">
                {initialOf(session.email)}
              </AvatarFallback>
            </Avatar>
            <span className="text-xs text-[#94a3b8] hidden sm:inline max-w-[120px] truncate">
              {nameOf(session.email)}
            </span>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="w-56 border-[#1e293b] bg-[#111827] text-[#e2e8f0]"
          >
            <DropdownMenuLabel className="text-xs text-[#94a3b8]">
              {session.org_name || "账号"}
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-[#1e293b]" />
            <DropdownMenuItem className="text-sm text-[#94a3b8] hover:text-white hover:bg-[#1e293b] cursor-pointer gap-2">
              <UserIcon className="w-3.5 h-3.5" />
              个人信息
            </DropdownMenuItem>
            <DropdownMenuItem className="text-sm text-[#94a3b8] hover:text-white hover:bg-[#1e293b] cursor-pointer gap-2">
              <Settings className="w-3.5 h-3.5" />
              项目设置
            </DropdownMenuItem>
            <DropdownMenuSeparator className="bg-[#1e293b]" />
            <DropdownMenuItem
              onClick={handleLogout}
              className="text-sm text-[#ff4d4f] hover:text-[#ff4d4f] hover:bg-[#ff4d4f]/10 cursor-pointer gap-2"
            >
              <LogOut className="w-3.5 h-3.5" />
              退出登录
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        <Link
          href="/login"
          className="text-sm px-3 py-1.5 rounded-lg border border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40 transition-all"
        >
          登录
        </Link>
      )}
    </div>
  );

  let shell: ReactNode = children;

  if (mounted) {
    shell = engineer ? (
      <>
        <EngineerSidebar />
        {/* pt-14 让出窄屏顶栏（<768px 侧栏隐藏、改由顶栏承载导航），
            md 及以上由侧栏占位 md:pl-60，无需顶部内边距。 */}
        <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0] pt-14 md:pt-0 md:pl-60">
          {children}
        </div>
      </>
    ) : (
      <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
        <TopNav
          mode={isLanding ? "tabs" : "links"}
          activeTab={activeTab}
          onTabChange={setActiveTab}
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
