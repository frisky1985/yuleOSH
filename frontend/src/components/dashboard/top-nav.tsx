"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertTriangle,
  BookOpen,
  ChevronDown,
  Cpu,
  FlaskConical,
  GitBranch,
  Layers,
  ListChecks,
  ScrollText,
  TrendingUp,
  Users,
  type LucideIcon,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

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
  | { kind: "link"; href: string; label: string; icon: LucideIcon };

type NavGroup = { id: string; label: string; items: NavItem[] };

// Navigation grouped by decision-maker workflow (2026-09-02).
// Logo points at /dashboard. Tab items render in both modes:
//   - "tabs" mode (/dashboard): click → in-page tab switch
//   - "links" mode (sub-pages): click → router.push("/dashboard?tab=<tab>"),
//     dashboard reads the query and activates that tab. This keeps the
//     decision-maker able to jump straight to any tab from any sub-page,
//     rather than losing tab entries (gap-analysis / misra-trends) once
//     they leave /dashboard.
//
// 2026-09-02 (rev 2): groups are now **click-to-open dropdowns** instead of a
// flat 11-item row. Each group label is the DropdownMenu trigger; its items
// appear in the menu. A group with a single visible item in the current mode
// is rendered inline (no pointless one-option dropdown).
//
// Groups are designed as 4 concerns:
//   概览        — landing anchor (1 item; inline)
//   合规与交付  — compliance output axis (4 items, what decision-makers act on)
//   工程执行    — operations / live signal (5 items)
//   管理        — resource & policy control (3 items, includes 知识库)
const NAV_GROUPS: NavGroup[] = [
  {
    id: "overview",
    label: "概览",
    items: [
      { kind: "tab", tab: "overview", label: "概览", icon: Layers },
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

// Inline pill (single-item groups + active state)
const PILL_ACTIVE =
  "px-3 py-1.5 text-xs font-medium rounded-lg transition-all whitespace-nowrap bg-[#722ed1]/15 text-[#722ed1] border border-[#722ed1]/30";
const PILL_IDLE =
  "px-3 py-1.5 text-xs font-medium rounded-lg transition-all whitespace-nowrap text-[#94a3b8] hover:text-white hover:bg-[#1e293b]";
// Dropdown trigger (multi-item groups)
const TRIGGER_ACTIVE =
  "px-3 py-1.5 text-xs font-semibold rounded-lg transition-all whitespace-nowrap bg-[#722ed1]/15 text-[#722ed1] border border-[#722ed1]/30 flex items-center gap-1 cursor-pointer";
const TRIGGER_IDLE =
  "px-3 py-1.5 text-xs font-medium rounded-lg transition-all whitespace-nowrap text-[#94a3b8] hover:text-white hover:bg-[#1e293b] flex items-center gap-1 cursor-pointer";
// Dropdown item
const ITEM_ACTIVE = "text-[#722ed1] bg-[#722ed1]/10";
const ITEM_IDLE = "text-[#cbd5e1] hover:text-white hover:bg-[#1e293b]";

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
  const router = useRouter();

  // Tab items render in BOTH modes (so the decision-maker keeps gap-analysis /
  // misra-trends / overview entries reachable from any sub-page). Their click
  // behaviour switches by mode — see handlers below.
  const groups = NAV_GROUPS;

  // Click handler for a "tab" item. In tabs mode it switches the in-page tab;
  // in links mode (sub-pages) it routes back to /dashboard?tab=<tab> so the
  // landing page can activate the requested tab on mount.
  const handleTabClick = (tab: DashboardTab) => {
    if (mode === "tabs") {
      onTabChange?.(tab);
    } else {
      router.push(`/dashboard?tab=${tab}`);
    }
  };

  const isItemActive = (item: NavItem): boolean =>
    item.kind === "tab"
      ? mode === "tabs" && activeTab === item.tab
      : pathname === item.href;

  const renderInlineItem = (item: NavItem) => {
    const active = isItemActive(item);
    if (item.kind === "tab") {
      return (
        <button
          key={item.tab}
          onClick={() => handleTabClick(item.tab)}
          className={active ? PILL_ACTIVE : PILL_IDLE}
        >
          <item.icon className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
          {item.label}
        </button>
      );
    }
    return (
      <Link
        key={item.href}
        href={item.href}
        className={active ? PILL_ACTIVE : PILL_IDLE}
      >
        <item.icon className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
        {item.label}
      </Link>
    );
  };

  return (
    <nav
      data-testid="top-nav"
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
            {groups.map((group) => {
              // 单 item 组直接平铺，不套无意义的单选项下拉
              if (group.items.length === 1) {
                return (
                  <div key={group.id} className="flex items-center">
                    {renderInlineItem(group.items[0])}
                  </div>
                );
              }
              const groupActive = group.items.some(isItemActive);
              return (
                <DropdownMenu key={group.id}>
                  <DropdownMenuTrigger
                    className={groupActive ? TRIGGER_ACTIVE : TRIGGER_IDLE}
                  >
                    {group.label}
                    <ChevronDown className="w-3.5 h-3.5" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="start"
                    className="w-48 border-[#1e293b] bg-[#111827] text-[#e2e8f0] mt-1"
                  >
                    {group.items.map((item) => {
                      const active = isItemActive(item);
                      const cls = `text-sm gap-2 ${active ? ITEM_ACTIVE : ITEM_IDLE}`;
                      if (item.kind === "tab") {
                      return (
                        <DropdownMenuItem
                          key={item.tab}
                          onClick={() => handleTabClick(item.tab)}
                          className={cls}
                        >
                          <item.icon className="w-3.5 h-3.5" />
                          {item.label}
                        </DropdownMenuItem>
                      );
                      }
                      return (
                        <DropdownMenuItem
                          key={item.href}
                          onClick={() => router.push(item.href)}
                          className={cls}
                        >
                          <item.icon className="w-3.5 h-3.5" />
                          {item.label}
                        </DropdownMenuItem>
                      );
                    })}
                  </DropdownMenuContent>
                </DropdownMenu>
              );
            })}
          </div>

          {children ?? <div className="shrink-0" />}
        </div>
      </div>
    </nav>
  );
}
