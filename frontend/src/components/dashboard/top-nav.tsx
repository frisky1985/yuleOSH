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

export type DashboardTab =
  | "overview"
  | "gap-analysis"
  | "knowledge-base"
  | "misra-trends";

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

// Navigation grouped by concern (2026-08-30).  The logo now points at
// /dashboard (it used to go to the marketing home page).  "tab" items only
// exist on the /dashboard landing page — sub-pages render link items only,
// which keeps their previous behaviour byte-for-byte identical.
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
    label: "合规分析",
    items: [
      { kind: "tab", tab: "gap-analysis", label: "差距分析", icon: AlertTriangle },
      { kind: "tab", tab: "misra-trends", label: "MISRA 趋势", icon: TrendingUp },
    ],
  },
  {
    id: "engineering",
    label: "工程内容",
    items: [
      { kind: "tab", tab: "knowledge-base", label: "知识库", icon: BookOpen },
    ],
  },
  {
    id: "pipeline",
    label: "流水线与执行",
    items: [
      { kind: "link", href: "/dashboard/pipeline", label: "流水线", icon: GitBranch },
      { kind: "link", href: "/dashboard/devices", label: "设备", icon: Cpu },
      { kind: "link", href: "/dashboard/tests", label: "测试", icon: FlaskConical },
      { kind: "link", href: "/dashboard/logs", label: "日志", icon: ScrollText },
    ],
  },
  {
    id: "admin",
    label: "管理",
    items: [
      { kind: "link", href: "/dashboard/roles", label: "角色", icon: Users },
      { kind: "link", href: "/dashboard/requirements", label: "需求", icon: ListChecks },
    ],
  },
];

const ACTIVE_CLS =
  "px-3 py-1.5 text-xs font-medium rounded-lg transition-all whitespace-nowrap bg-[#722ed1]/15 text-[#722ed1] border border-[#722ed1]/30";
const IDLE_CLS =
  "px-3 py-1.5 text-xs font-medium rounded-lg transition-all whitespace-nowrap text-[#94a3b8] hover:text-white hover:bg-[#1e293b]";

interface TopNavProps {
  /** "tabs" on /dashboard (renders in-page tab items), "links" on sub-pages. */
  mode: "tabs" | "links";
  /** Current tab — required in "tabs" mode. */
  activeTab?: DashboardTab;
  /** Tab switch handler — required in "tabs" mode. */
  onTabChange?: (tab: DashboardTab) => void;
  /** Right-hand slot (user menu).  Only the landing page provides one. */
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
                className="flex items-center gap-1"
                title={group.label}
              >
                {groupIndex > 0 && (
                  <div className="w-px h-4 bg-[#1e293b] mx-1.5 shrink-0" />
                )}
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
