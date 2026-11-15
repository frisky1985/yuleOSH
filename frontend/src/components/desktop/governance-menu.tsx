"use client";

import { useEffect, useRef, useState } from "react";
import {
  Bug,
  ChevronDown,
  ClipboardCheck,
  Flag,
  Gauge,
  GitBranch,
  GitPullRequest,
  Layers,
  LayoutGrid,
  ShieldCheck,
  Tags,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────

export type GovernanceKey =
  | "traceability"
  | "baselines"
  | "change-requests"
  | "quality-gates"
  | "compliance"
  | "reviews"
  | "issues"
  | "qa"
  | "project-mgmt";

export interface GovernanceItem {
  key: GovernanceKey;
  label: string;
  hint: string;
  icon: LucideIcon;
}

export interface GovernanceGroup {
  label: string;
  items: GovernanceItem[];
}

interface GovernanceMenuProps {
  disabled?: boolean;
  onSelect: (key: GovernanceKey) => void;
}

// ─── Metadata ─────────────────────────────────────────────────────────────

/** 头部原先平铺的 9 个入口，按 ASPICE 关注点归组，避免工具栏溢出。 */
export const GOVERNANCE_GROUPS: GovernanceGroup[] = [
  {
    label: "追溯与变更",
    items: [
      {
        key: "traceability",
        label: "追溯矩阵",
        hint: "需求 → 设计 → 代码 → 测试的 RTM 与审计链校验",
        icon: GitBranch,
      },
      {
        key: "baselines",
        label: "基线",
        hint: "配置基线的创建、文件清单与差异比对",
        icon: Layers,
      },
      {
        key: "change-requests",
        label: "变更请求",
        hint: "变更列表、状态流转与影响分析",
        icon: GitPullRequest,
      },
    ],
  },
  {
    label: "质量与合规",
    items: [
      {
        key: "quality-gates",
        label: "质量门禁",
        hint: "追溯 / 评审 / CI / 测试门禁汇总",
        icon: Gauge,
      },
      {
        key: "compliance",
        label: "合规检查",
        hint: "ASPICE 过程域红黄绿与缺失证据清单",
        icon: ShieldCheck,
      },
      {
        key: "reviews",
        label: "评审中心",
        hint: "跨产物评审列表与批量打标",
        icon: Tags,
      },
    ],
  },
  {
    label: "问题与审计",
    items: [
      {
        key: "issues",
        label: "问题追踪",
        hint: "缺陷登记、根因分析、修复验证与关闭",
        icon: Bug,
      },
      {
        key: "qa",
        label: "QA 审计",
        hint: "审计计划、不符合项与 QA 报告导出",
        icon: ClipboardCheck,
      },
    ],
  },
  {
    label: "项目管理",
    items: [
      {
        key: "project-mgmt",
        label: "风险与里程碑",
        hint: "风险矩阵、缓解闭环与里程碑完成度",
        icon: Flag,
      },
    ],
  },
];

// ─── Component ────────────────────────────────────────────────────────────

/** 「治理工具」下拉：把追溯/合规/评审等板块收进分组菜单。 */
export function GovernanceMenu({ disabled, onSelect }: GovernanceMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown, true);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const pick = (key: GovernanceKey) => {
    setOpen(false);
    onSelect(key);
  };

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        data-testid="gov-trigger"
        title="追溯、基线、变更、门禁、合规、评审、问题、审计与项目管理"
        className="flex items-center gap-1 rounded-md border border-[#1e293b] px-3 py-1.5 text-sm text-[#94a3b8] transition-colors hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        <LayoutGrid className="h-4 w-4" />
        治理工具
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          role="menu"
          data-testid="gov-menu"
          className="absolute right-0 top-full z-50 mt-1 w-72 rounded-lg border border-[#1e293b] bg-[#111827] p-1.5 shadow-xl"
        >
          {GOVERNANCE_GROUPS.map((group) => (
            <div key={group.label} className="mb-1 last:mb-0">
              <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[#475569]">
                {group.label}
              </div>
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.key}
                    type="button"
                    role="menuitem"
                    onClick={() => pick(item.key)}
                    data-testid={`gov-item-${item.key}`}
                    title={item.hint}
                    className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[#1e293b]/60"
                  >
                    <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#64748b]" />
                    <span className="min-w-0">
                      <span className="block text-xs text-[#e2e8f0]">{item.label}</span>
                      <span className="block truncate text-[10px] text-[#64748b]">{item.hint}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
