"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  GitBranch,
  ListChecks,
  FlaskConical,
  Layers,
  ScrollText,
  LogOut,
} from "lucide-react";
import { api } from "@/lib/api";
import { useSessionRole } from "@/lib/use-session-role";

// v5 风格左侧栏导航 — 工程视角优先展示流水线相关内容。
const NAV: {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  exact?: boolean;
}[] = [
  { href: "/dashboard", label: "概览", icon: LayoutDashboard, exact: true },
  { href: "/dashboard/pipeline", label: "流水线", icon: GitBranch },
  { href: "/dashboard/requirements", label: "项目需求", icon: ListChecks },
  { href: "/dashboard/tests", label: "测试用例", icon: FlaskConical },
  { href: "/dashboard/test-layers", label: "阶段看板", icon: Layers },
  { href: "/dashboard/evidence", label: "证据包", icon: ScrollText },
];

export function EngineerSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { session } = useSessionRole();

  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname === href || pathname.startsWith(href + "/");

  const handleLogout = async () => {
    try {
      await api.auth.logout();
    } catch {
      /* 忽略登出失败，直接跳转 */
    }
    router.push("/login");
  };

  return (
    <aside className="fixed left-0 top-0 z-40 hidden h-screen w-60 flex-col border-r border-[#1e293b] bg-[#0b0f1a] md:flex">
      {/* Logo */}
      <div className="flex h-14 items-center border-b border-[#1e293b] px-5">
        <Link href="/dashboard" className="text-lg font-black tracking-tight">
          <span className="text-[#10b981]">yule</span>
          <span className="text-[#1677ff]">OSH</span>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {NAV.map((item) => {
          const active = isActive(item.href, item.exact);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={
                "flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-all " +
                (active
                  ? "border-[#722ed1]/30 bg-[#722ed1]/15 text-[#722ed1]"
                  : "border-transparent text-[#94a3b8] hover:bg-[#1e293b] hover:text-white")
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* User */}
      <div className="border-t border-[#1e293b] p-3">
        <div className="flex items-center gap-2 rounded-lg px-2 py-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#722ed1]/20 text-xs font-bold text-[#722ed1]">
            {session?.email?.[0]?.toUpperCase() ?? "U"}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-xs text-[#e2e8f0]">{session?.email ?? "未登录"}</div>
            <div className="truncate text-[10px] text-[#64748b]">{session?.org_name ?? ""}</div>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="mt-2 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-[#94a3b8] transition-all hover:bg-[#ff4d4f]/10 hover:text-[#ff4d4f]"
        >
          <LogOut className="h-3.5 w-3.5" /> 退出登录
        </button>
      </div>
    </aside>
  );
}
