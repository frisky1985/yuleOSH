"use client";

/**
 * 决策者顶栏用户菜单（右上角头像下拉）。
 *
 * 历史根因：
 *   - 早期基于 `@base-ui/react/menu` 的 DropdownMenuTrigger 在某些浏览器
 *     状态/导航场景下会触发整页跳转（Chrome "This page couldn't load"）。
 *   - 49f2be61 修过 onSelect→onClick，但触发链稳定仍依赖 base-ui 内部
 *     状态机；改用纯 DOM 手写实现后彻底与 base-ui Menu 解耦。
 *
 * 设计要点：
 *   - 渲染 `<button type="button">` 作 trigger（杜绝 form 默认 submit 路径，
 *     也杜绝被父级 `<a>` 包裹时意外 navigation）。
 *   - 浮层用纯 CSS `position: absolute` 跟 trigger 对齐，避免 base-ui
 *     Floating UI 计算 hash/anchor。
 *   - outside-click + Esc + 选完即关闭，独立维护 open 状态。
 *   - 菜单项 onClick 直接 `e.stopPropagation()` + 调外部回调（打开 4 个
 *     Dialog 之一） + 关闭菜单。
 *   - a11y：trigger 加 aria-haspopup/aria-expanded；menu role="menu"；
 *     menuitem role="menuitem" + tabIndex。
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { LogOut, Settings, Trash2, User as UserIcon, KeyRound } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { viewOf, VIEW_BADGE_CLS } from "@/lib/role-view";

export interface UserMenuSession {
  email: string;
  org_name?: string | null;
  user_id?: number | string;
  /** 登录用户角色（admin→决策视角；developer/reviewer/auditor→工程视角）。
   *  视图标签/色调由 @/lib/role-view 的 viewOf 统一提供。 */
  role?: string | null;
}

export interface UserMenuActions {
  onOpenAccount: () => void;
  onOpenSettings: () => void;
  onOpenLogout: () => void;
  onOpenDelete: () => void;
  onOpenApiKeys: () => void;
}

interface UserMenuProps {
  session: UserMenuSession;
  actions: UserMenuActions;
}

function initialOf(email?: string) {
  return email?.[0]?.toUpperCase() ?? "YU";
}

function nameOf(email?: string) {
  return email?.split("@")[0] ?? "用户";
}

export function UserMenu({ session, actions }: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const view = viewOf(session.role);
  const [menuStyle, setMenuStyle] = useState<{ right: number; top: number }>({
    right: 16,
    top: 56,
  });

  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const menuId = useId();

  // 计算菜单相对视口的 right/top（trigger 右下角对齐）
  const updatePosition = useCallback(() => {
    const el = triggerRef.current;
    if (typeof window === "undefined" || !el) return;
    const rect = el.getBoundingClientRect();
    setMenuStyle({
      right: Math.max(8, window.innerWidth - rect.right),
      top: rect.bottom + 6,
    });
  }, []);

  // 打开时 + resize/scroll 时同步位置
  useEffect(() => {
    if (!open) return;
    updatePosition();
    const onScrollOrResize = () => updatePosition();
    window.addEventListener("resize", onScrollOrResize);
    window.addEventListener("scroll", onScrollOrResize, true);
    return () => {
      window.removeEventListener("resize", onScrollOrResize);
      window.removeEventListener("scroll", onScrollOrResize, true);
    };
  }, [open, updatePosition]);

  // outside-click 关闭：click 在 menu 外 或 trigger 外 触发关闭
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node | null;
      if (!target) return;
      if (menuRef.current?.contains(target)) return;
      if (triggerRef.current?.contains(target)) return;
      setOpen(false);
    };
    // 用 capture 提前在 React 事件触发前关掉浮层（避免 base-ui / 其它
    // listener 在 propagation 路径里改写 navigation）
    document.addEventListener("mousedown", handler, true);
    return () => document.removeEventListener("mousedown", handler, true);
  }, [open]);

  // Esc 关闭
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const choose = (cb: () => void) => (e: React.MouseEvent) => {
    // 任何一种路径都不允许浮层"自然冒泡"到 React 之外的 navigation：
    // stopPropagation 防父级 Link/router 接走；preventDefault 防 form submit
    // / anchor href 兜底；任何 hashchange / location 变化都不会发生。
    e.preventDefault();
    e.stopPropagation();
    setOpen(false);
    cb();
  };

  return (
    <div className="flex items-center gap-2">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        data-testid="user-menu-trigger"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="flex items-center gap-2 rounded-lg border border-[#1e293b] hover:border-[#722ed1]/40 px-2 py-1 transition-all cursor-pointer bg-transparent text-inherit"
      >
        <Avatar className="w-7 h-7 border border-[#1e293b]">
          <AvatarFallback className="bg-[#722ed1]/20 text-[#722ed1] text-[10px]">
            {initialOf(session.email)}
          </AvatarFallback>
        </Avatar>
        <span className="text-xs text-[#94a3b8] hidden sm:inline max-w-[120px] truncate">
          {nameOf(session.email)}
        </span>
        <span
          className={`hidden md:inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] leading-none ${VIEW_BADGE_CLS[view.tone]}`}
          title={`当前角色：${session.role ?? "未知"}`}
        >
          {view.label}
        </span>
      </button>

      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label="用户菜单"
          data-testid="user-menu-popup"
          // 用 fixed 让浮层不参与文档流，避免 transform/overflow 容器
          // 计算被父层影响导致位置抖动
          style={{
            position: "fixed",
            right: menuStyle.right,
            top: menuStyle.top,
            zIndex: 9999,
          }}
          className="w-56 rounded-lg border border-[#1e293b] bg-[#111827] text-[#e2e8f0] shadow-xl ring-1 ring-black/40 p-1"
          onClick={(e) => {
            // 浮层内部点击不冒泡，杜绝兜底 handler
            e.stopPropagation();
          }}
        >
          <div className="px-2 py-1.5 text-xs text-[#94a3b8] border-b border-[#1e293b] mb-1 flex items-center justify-between gap-2">
            <span className="truncate">{session.org_name || "账号"}</span>
            <span
              className={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] leading-none shrink-0 ${VIEW_BADGE_CLS[view.tone]}`}
              title={`当前角色：${session.role ?? "未知"}`}
            >
              {view.label}
            </span>
          </div>
          <MenuItem
            icon={<UserIcon className="w-3.5 h-3.5" />}
            label="个人信息"
            onClick={choose(actions.onOpenAccount)}
          />
          <MenuItem
            icon={<Settings className="w-3.5 h-3.5" />}
            label="用户设置"
            onClick={choose(actions.onOpenSettings)}
          />
          <MenuItem
            icon={<KeyRound className="w-3.5 h-3.5" />}
            label="API 密钥"
            onClick={choose(actions.onOpenApiKeys)}
          />
          <div className="my-1 h-px bg-[#1e293b]" />
          <MenuItem
            icon={<LogOut className="w-3.5 h-3.5" />}
            label="退出登录"
            tone="warning"
            onClick={choose(actions.onOpenLogout)}
          />
          <MenuItem
            icon={<Trash2 className="w-3.5 h-3.5" />}
            label="注销账户"
            tone="danger"
            onClick={choose(actions.onOpenDelete)}
          />
        </div>
      )}
    </div>
  );
}

interface MenuItemProps {
  icon: React.ReactNode;
  label: string;
  tone?: "default" | "warning" | "danger";
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void;
}

function MenuItem({ icon, label, tone = "default", onClick }: MenuItemProps) {
  const toneCls =
    tone === "danger"
      ? "text-[#ff4d4f] hover:bg-[#ff4d4f]/10"
      : tone === "warning"
        ? "text-[#f59e0b] hover:bg-[#f59e0b]/10"
        : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]";
  return (
    <button
      type="button"
      role="menuitem"
      tabIndex={0}
      onClick={onClick}
      className={`w-full flex items-center gap-2 text-sm rounded-md px-2 py-1.5 cursor-pointer bg-transparent text-left ${toneCls}`}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}
