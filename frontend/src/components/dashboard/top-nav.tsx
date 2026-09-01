"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AlertTriangle,
  BookOpen,
  Cpu,
  FlaskConical,
  GitBranch,
  Layers,
  LayoutDashboard,
  ListChecks,
  ScrollText,
  TrendingUp,
  Users,
  type LucideIcon,
} from "lucide-react";

// Note: "knowledge-base" stays in the union because the landing page
// (/dashboard) still keeps inner tab state for backwards compatibility.
// The top-nav does NOT expose a tab for it anymore (now a link to a
// dedicated /dashboard/knowledge-base page in the 「管理」group).
export type DashboardTab =
  | "overview"
  | "gap-analysis"
  | "misra-trends"
  | "knowledge-base";

type NavItem =
  | { kind: "tab"; tab: DashboardTab; label: string; icon: LucideIcon }
  | {
      kind: "link";
      href: string;
      label: string;
      icon: LucideIcon;
      /** Rendered on sub-pages only — e.g. the "座舱" back-to-dashboard link. */
      subPagesOnly?: boolean;
    };

type NavGroup = { id: string; label: string; items: NavItem[] };

// Navigation grouped by decision-maker workflow (2026-09-02).
// Logo points at /dashboard. "tab" items render only on /dashboard;
// sub-pages render link items only (previous behaviour preserved).
// Group label is rendered before each group so the structure is visible
// at a glance — this fixes the previous "looks like a single 11-item row"
// issue caused by 1px-only dividers being invisible on the dark surface.
//
// Groups are designed as 4 concerns (1-5 items each, no orphan single-item
// groups):
//   概览        — landing anchor (1 item)
//   合规与交付  — compliance output axis (4 items, what decision-makers act on)
//   工程执行    — operations / live signal (5 items)
//   管理        — resource & policy control (3 items, includes 知识库)
const NAV_GROUPS: NavGroup[] = [
  {
    id: "overview",
    label: "概览",
    items: [
      { kind: "tab", tab: "overview", label: "概览", icon: Layers },
      {
        kind: "link",
        href: "/dashboard",
        label: "座舱",
        icon: LayoutDashboard,
        subPagesOnly: true,
      },
    ],
  },
  {
    id: "compliance",
    label: "合规与交付",
    items: [
      { kind: "tab", tab: "gap-analysis", label: "差距分析", icon: AlertTriangle },
      { kind: "tab", tab: "misra-trends", label: "MISRA 趋势", icon: TrendingUp },
      {
        kind: "link",
        href: "/dashboard/evidence",
        label: "证据包",
        icon: ScrollText,
      },
      {
        kind: "link",
        href: "/dashboard/traceability",
        label: "追溯矩阵",
        icon: ListChecks,
      },
    ],
  },
  {
    id: "pipeline",
    label: "工程执行",
    items: [
      { kind: "link", href: "/dashboard/pipeline", label: "流水线", icon: GitBranch },
      { kind: "link", href: "/dashboard/devices", label: "设备", icon: Cpu },
      { kind: "link", href: "/dashboard/tests", label: "测试", icon: FlaskConical },
      { kind: "link", href: "/dashboard/test-layers", label: "测试分层", icon: Layers },
      { kind: "link", href: "/dashboard/logs", label: "日志", icon: ScrollText },
    ],
  },
  {
    id: "admin",
    label: "管理",
    items: [
      { kind: "link", href: "/dashboard/knowledge-base", label: "知识库", icon: BookOpen },
      { kind: "link", href: "/dashboard/roles", label: "角色", icon: Users },
      { kind: "link", href: "/dashboard/requirements", label: "需求", icon: ListChecks },
    ],
  },
];

const ACTIVE_CLS =
  "px-3 py-1.5 text-xs font-medium rounded-lg transition-all whitespace-nowrap bg-[#722ed1]/15 text-[#722ed1] border border-[#722ed1]/30";
const IDLE_CLS =
  "px-3 py-1.5 text-xs font-medium rounded-lg transition-all whitespace-nowrap text-[#94a3b8] hover:text-white hover:bg-[#1e293b]";
// Group label: 10px 灰全大写紧凑字,让分组"看得见"但不喧宾夺主.
// 用 uppercase + tracking 在中文下相当于零作用,因此 group.label 仍展示中文,
// letter-spacing 依然让字与字之间松一口气。

interface TopNavProps {
  /** "tabs" on /dashboard (renders in-page tab items), "links" on sub-pages. */
  mode: "tabs" | "links";
  /** Current tab — required in "tabs" mode. */
  activeTab?: DashboardTab;
  /** Tab switch handler — required in "tabs" mode. */
  onTabChange?: (tab: DashboardTab) => void;
  /**
   * Right-hand slot (user menu with logout).  Rendered on **both** the landing
   * page and sub-pages — gating it to the landing page removed the only logout
   * entry point for decision-maker (admin) accounts on every sub-page.
   */
  children?: ReactNode;
}

export function TopNav({ mode, activeTab, onTabChange, children }: TopNavProps) {
  const pathname = usePathname();

  // Sub-pages must not show the landing-page tabs — they have no tab state.
  const groups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => {
      if (item.kind === "tab") return mode === "tabs";
      if (item.subPagesOnly) return mode === "links";
      return true;
    }),
  })).filter((group) => group.items.length > 0);

  return (
    <nav
      className="sticky top-0 z-50 border-b border-[#1e293b]/60 nav-blur"
      style={{ background: "rgba(10,14,23,.85)" }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14 gap-4">
          <Link
            href="/dashboard"
            className="text-lg font-black tracking-tight shrink-0"
          >
            <span className="text-[#10b981]">yule</span>
            <span className="text-[#1677ff]">OSH</span>
          </Link>

          <div className="flex items-center gap-1 overflow-x-auto">
            {groups.map((group, groupIndex) => (
              <div
                key={group.id}
                className="flex items-center gap-0.5"
                title={group.label}
              >
                {groupIndex > 0 && (
                  <div className="w-px h-6 bg-[#1e293b] mx-2 shrink-0" />
                )}
                <span
                  className="hidden md:inline-block text-[10px] font-medium uppercase tracking-[0.3px] text-[#475569] mr-1.5 select-none shrink-0"
                  aria-hidden="true"
                >
                  {group.label}
                </span>
                {group.items.map((item) =>
                  item.kind === "tab" ? (
                    <button
                      key={item.tab}
                      onClick={() => onTabChange?.(item.tab)}
                      className={activeTab === item.tab ? ACTIVE_CLS : IDLE_CLS}
                    >
                      <item.icon className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
                      {item.label}
                    </button>
                  ) : (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={pathname === item.href ? ACTIVE_CLS : IDLE_CLS}
                    >
                      <item.icon className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
                      {item.label}
                    </Link>
                  ),
                )}
              </div>
            ))}
          </div>

          {children ?? <div className="shrink-0" />}
        </div>
      </div>
    </nav>
  );
}
