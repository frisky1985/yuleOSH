"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  GitBranch,
  Cpu,
  Terminal,
  ListChecks,
  FlaskConical,
  Layers,
  ScrollText,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { resetSessionCache, useSessionRole } from "@/lib/use-session-role";

// v5 风格左侧栏导航 — 工程视角优先展示流水线相关内容。
const NAV: {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  exact?: boolean;
}[] = [
  { href: "/dashboard", label: "概览", icon: LayoutDashboard, exact: true },
  { href: "/dashboard/pipeline", label: "流水线", icon: GitBranch },
  // 设备（HIL 台架注册）与日志（排查步骤失败，数据源 .osh/sessions/*.log）
  // 都是工程执行向页面，此前入口只在决策顶栏，工程师反而进不去 —— 补在此处。
  { href: "/dashboard/devices", label: "设备", icon: Cpu },
  { href: "/dashboard/logs", label: "日志", icon: Terminal },
  { href: "/dashboard/requirements", label: "项目需求", icon: ListChecks },
  { href: "/dashboard/tests", label: "测试用例", icon: FlaskConical },
  { href: "/dashboard/test-layers", label: "阶段看板", icon: Layers },
  { href: "/dashboard/evidence", label: "证据包", icon: ScrollText },
];

export function EngineerSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { session } = useSessionRole();

  // 桌面侧栏在 <768px 隐藏（hidden md:flex），窄屏改由「顶栏 + 抽屉」承载
  // 导航与登出，否则工程师在窄屏下既无导航也无登出入口。
  const [drawerOpen, setDrawerOpen] = useState(false);

  // 路由变化后自动收起：点导航项跳转后不应残留遮罩/抽屉。
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  // 视图由登录用户角色决定（layout.tsx 中 isEngineerRole 判定），无需 ?view 参数维持。
  const withView = (href: string) => href;

  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname === href || pathname.startsWith(href + "/");

  const handleLogout = async () => {
    try {
      await api.auth.logout();
    } catch {
      /* 忽略登出失败，直接跳转 */
    }
    // 失效模块级会话缓存：否则换账号重新登录后会继续读到上一个账号的身份。
    resetSessionCache();
    router.push("/login");
  };

  // 导航项：桌面侧栏与窄屏抽屉共用，选中态与跳转行为保持一致。
  const navItems = (
    <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
      {NAV.map((item) => {
        const active = isActive(item.href, item.exact);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={withView(item.href)}
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
  );

  // 用户区（含退出登录）：两个外壳共用，确保任何视口都有登出入口。
  const userBlock = (
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
  );

  return (
    <>
      {/* 窄屏顶栏（<768px）：提供 Logo 与抽屉开关 */}
      <div className="fixed inset-x-0 top-0 z-50 flex h-14 items-center justify-between border-b border-[#1e293b] bg-[#0b0f1a] px-4 md:hidden">
        <Link href="/dashboard" className="text-lg font-black tracking-tight">
          <span className="text-[#10b981]">yule</span>
          <span className="text-[#1677ff]">OSH</span>
        </Link>
        <button
          type="button"
          onClick={() => setDrawerOpen((v) => !v)}
          aria-label={drawerOpen ? "关闭导航" : "打开导航"}
          aria-expanded={drawerOpen}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#1e293b] text-[#94a3b8] transition-colors hover:bg-[#1e293b] hover:text-white"
        >
          {drawerOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </button>
      </div>

      {/* 桌面侧栏（>=768px） */}
      <aside className="fixed left-0 top-0 z-40 hidden h-screen w-60 flex-col border-r border-[#1e293b] bg-[#0b0f1a] md:flex">
        {/* Logo */}
        <div className="flex h-14 items-center border-b border-[#1e293b] px-5">
          <Link href="/dashboard" className="text-lg font-black tracking-tight">
            <span className="text-[#10b981]">yule</span>
            <span className="text-[#1677ff]">OSH</span>
          </Link>
        </div>

        {navItems}
        {userBlock}
      </aside>

      {/* 窄屏抽屉（<768px）：桌面侧栏的等价物 */}
      {drawerOpen && (
        <>
          {/* 遮罩：起点下移避开顶栏，保证汉堡按钮始终可点 */}
          <div
            className="fixed inset-x-0 bottom-0 top-14 z-30 bg-black/60 md:hidden"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="fixed bottom-0 left-0 top-14 z-40 flex w-64 flex-col border-r border-[#1e293b] bg-[#0b0f1a] md:hidden">
            {navItems}
            {userBlock}
          </div>
        </>
      )}
    </>
  );
}
