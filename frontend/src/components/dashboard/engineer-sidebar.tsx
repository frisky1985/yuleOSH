"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  GitBranch,
  Cpu,
  Terminal,
  ListChecks,
  Network,
  FlaskConical,
  Layers,
  ScrollText,
  LogOut,
  Menu,
  X,
  KeyRound,
} from "lucide-react";
import { api } from "@/lib/api";
import { resetSessionCache, useSessionRole } from "@/lib/use-session-role";
import { useRealtimeStore } from "@/lib/realtime-store";

// 「导航项 → 后端 topic」映射: 用于根据 active run 的类型推断侧栏徽标
// 当前阶段只挂 pipeline 徽标; 其它 topic 在阶段 3 接通各页面后挂上。
function getNavBadge(
  href: string,
  state: ReturnType<typeof useRealtimeStore>,
): { count: number; hint?: string } | null {
  if (href === "/dashboard/pipeline") {
    const runs = Object.values(state.activeRuns);
    if (runs.length === 0) return null;
    const running = runs.filter((r) => r.status === "running");
    if (running.length === 0) return null;
    const first = running[0];
    return {
      count: running.length,
      hint: first.current_stage_title || first.current_stage_key,
    };
  }
  if (href === "/dashboard/evidence") {
    if (state.newEvidenceCount === 0) return null;
    return { count: state.newEvidenceCount, hint: "条新证据" };
  }
  return null;
}

// 工程视角侧栏：按 V-model 开发主线分组排序（需求→测试设计→执行→追溯→证据），
// 基础设施（流水线/设备）与可观测性（日志）下沉为辅助区。
const NAV: {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  exact?: boolean;
  section?: string;
}[] = [
  { href: "/dashboard", label: "概览", icon: LayoutDashboard, exact: true, section: "入口" },
  // —— V-model 开发主线：需求驱动、测试设计并行、阶段看板为执行核心 ——
  { href: "/dashboard/requirements", label: "项目需求", icon: ListChecks, section: "V-model 开发主线" },
  { href: "/dashboard/tests", label: "测试用例", icon: FlaskConical },
  { href: "/dashboard/test-layers", label: "阶段看板", icon: Layers },
  // —— 基础设施：编排与 HIL 台架 ——
  { href: "/dashboard/pipeline", label: "流水线", icon: GitBranch, section: "基础设施" },
  { href: "/dashboard/devices", label: "设备", icon: Cpu },
  // —— 可观测性：排查步骤失败 ——
  { href: "/dashboard/logs", label: "日志", icon: Terminal, section: "可观测性" },
  // —— 合规交付：需求↔证据链接，最后打包产出 ——
  { href: "/dashboard/traceability", label: "追溯矩阵", icon: Network, section: "合规交付" },
  { href: "/dashboard/evidence", label: "证据包", icon: ScrollText },
  // —— 安全：加密 API 密钥管理（SEC-PK）——
  { href: "/dashboard/settings/api-keys", label: "API 密钥", icon: KeyRound, section: "安全" },
];

export function EngineerSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { session } = useSessionRole();
  const realtimeState = useRealtimeStore();

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
      {NAV.map((item, idx) => {
        const active = isActive(item.href, item.exact);
        const Icon = item.icon;
        const showSection = item.section && (idx === 0 || NAV[idx - 1].section !== item.section);
        const badge = getNavBadge(item.href, realtimeState);
        return (
          <Fragment key={item.href}>
            {showSection && (
              <div className={idx === 0 ? "pt-0" : "pt-3"}>
                {idx !== 0 && <div className="mx-3 mb-2 h-px bg-[#1e293b]" />}
                <div className="px-3 pb-1 text-[10px] font-medium uppercase tracking-[0.06em] text-[#475569]">
                  {item.section}
                </div>
              </div>
            )}
            <Link
              href={withView(item.href)}
              className={
                "relative flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-all " +
                (active
                  ? "border-[#722ed1]/30 bg-[#722ed1]/15 text-[#722ed1]"
                  : "border-transparent text-[#94a3b8] hover:bg-[#1e293b] hover:text-white")
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1 truncate">{item.label}</span>
              {badge && (
                <span
                  className="ml-auto flex items-center gap-1 rounded-full bg-[#722ed1]/20 px-1.5 py-0.5 text-[10px] font-semibold text-[#c4b5fd] animate-pulse"
                  title={badge.hint ? `当前: ${badge.hint}` : undefined}
                >
                  {badge.count}
                </span>
              )}
            </Link>
          </Fragment>
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
      <aside data-testid="engineer-sidebar" className="fixed left-0 top-0 z-40 hidden h-screen w-60 flex-col border-r border-[#1e293b] bg-[#0b0f1a] md:flex">
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
