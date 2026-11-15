"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { FolderPlus, Play, Search, UploadCloud } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { GOVERNANCE_GROUPS } from "@/components/desktop/governance-menu";
import type { GovernanceKey } from "@/components/desktop/governance-menu";

// ─── Types ────────────────────────────────────────────────────────────────

export type CommandActionKey = "new-project" | "run-pipeline" | "sync";

export interface PaletteProject {
  id: string;
  name: string;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  projects: PaletteProject[];
  activeId: string | null;
  onSelectProject: (id: string) => void;
  onGovernance: (key: GovernanceKey) => void;
  onAction: (action: CommandActionKey) => void;
}

interface PaletteItem {
  id: string;
  label: string;
  hint: string;
  group: string;
  icon: LucideIcon;
  run: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────

/**
 * 桌面端命令面板（Ctrl/Cmd+K）：头部「治理工具」收进下拉后，
 * 用可搜索的键盘入口统一承载工程切换、治理面板与常用操作。
 */
export function CommandPalette({
  open,
  onClose,
  projects,
  activeId,
  onSelectProject,
  onGovernance,
  onAction,
}: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const items = useMemo<PaletteItem[]>(() => {
    const actions: PaletteItem[] = [
      {
        id: "action-new-project",
        label: "新建工程",
        hint: "从模板创建工程并导入初始产物",
        group: "操作",
        icon: FolderPlus,
        run: () => onAction("new-project"),
      },
      {
        id: "action-run-pipeline",
        label: "运行流水线",
        hint: "对当前工程执行需求 → 设计 → 代码 → 测试流水线",
        group: "操作",
        icon: Play,
        run: () => onAction("run-pipeline"),
      },
      {
        id: "action-sync",
        label: "同步云端",
        hint: "把当前工程产物上传到云端工作区",
        group: "操作",
        icon: UploadCloud,
        run: () => onAction("sync"),
      },
    ];

    const projectItems: PaletteItem[] = projects.map((p) => ({
      id: `project-${p.id}`,
      label: p.name,
      hint: p.id === activeId ? "当前工程" : "切换到此工程",
      group: "工程",
      icon: Search,
      run: () => onSelectProject(p.id),
    }));

    const governance: PaletteItem[] = GOVERNANCE_GROUPS.flatMap((g) =>
      g.items.map((item) => ({
        id: `gov-${item.key}`,
        label: item.label,
        hint: item.hint,
        group: g.label,
        icon: item.icon,
        run: () => onGovernance(item.key),
      })),
    );

    return [...actions, ...projectItems, ...governance];
  }, [projects, activeId, onAction, onSelectProject, onGovernance]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (i) =>
        i.label.toLowerCase().includes(q) || i.hint.toLowerCase().includes(q),
    );
  }, [items, query]);

  // 每次打开重置查询与光标
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCursor(0);
    const t = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    setCursor(0);
  }, [query]);

  // 保持选中项可见
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(
      `[data-testid="cmd-item-${filtered[cursor]?.id}"]`,
    );
    el?.scrollIntoView?.({ block: "nearest" });
  }, [cursor, filtered]);

  if (!open) return null;

  const execute = (item: PaletteItem | undefined) => {
    if (!item) return;
    onClose();
    item.run();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => (filtered.length ? (c + 1) % filtered.length : 0));
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) =>
        filtered.length ? (c - 1 + filtered.length) % filtered.length : 0,
      );
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      execute(filtered[cursor]);
    }
  };

  let lastGroup = "";

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/60 px-4 pt-[12vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="命令面板"
        data-testid="cmd-palette"
        className="w-full max-w-xl overflow-hidden rounded-xl border border-[#1e293b] bg-[#111827] shadow-2xl"
      >
        <div className="flex items-center gap-2 border-b border-[#1e293b] px-3 py-2.5">
          <Search className="h-4 w-4 shrink-0 text-[#64748b]" />
          <input
            ref={inputRef}
            data-testid="cmd-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="搜索工程、治理工具或操作…"
            className="w-full bg-transparent text-sm text-[#e2e8f0] placeholder:text-[#475569] focus:outline-none"
          />
          <kbd className="shrink-0 rounded border border-[#1e293b] px-1.5 py-0.5 text-[10px] text-[#64748b]">
            Esc
          </kbd>
        </div>

        <div ref={listRef} className="max-h-[52vh] overflow-y-auto p-1.5">
          {filtered.length === 0 && (
            <div className="px-3 py-8 text-center text-xs text-[#64748b]">
              没有匹配的命令
            </div>
          )}
          {filtered.map((item, index) => {
            const Icon = item.icon;
            const showGroup = item.group !== lastGroup;
            lastGroup = item.group;
            return (
              <div key={item.id}>
                {showGroup && (
                  <div className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-[#475569]">
                    {item.group}
                  </div>
                )}
                <button
                  type="button"
                  data-testid={`cmd-item-${item.id}`}
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => execute(item)}
                  className={`flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors ${
                    index === cursor ? "bg-[#1e293b]" : "hover:bg-[#1e293b]/60"
                  }`}
                >
                  <Icon className="h-4 w-4 shrink-0 text-[#64748b]" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-[#e2e8f0]">
                      {item.label}
                    </span>
                    <span className="block truncate text-[10px] text-[#64748b]">
                      {item.hint}
                    </span>
                  </span>
                </button>
              </div>
            );
          })}
        </div>

        <div className="flex items-center justify-between border-t border-[#1e293b] px-3 py-1.5 text-[10px] text-[#475569]">
          <span>↑↓ 选择 · Enter 执行 · Esc 关闭</span>
          <span>{filtered.length} 项</span>
        </div>
      </div>
    </div>
  );
}
