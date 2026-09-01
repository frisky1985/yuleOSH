"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AlertCircle, Loader2, LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { resetSessionCache } from "@/lib/use-session-role";

interface LogoutConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 用于确认消息中显示"哪位用户在退出"。 */
  emailLabel?: string;
}

const REDIRECT_DELAY_MS = 600;

/** 决策者顶栏 → 退出登录：二次确认 Dialog。
 * 避免误触当前页面右上角菜单时直接掉登出。 */
export function LogoutConfirmDialog({
  open,
  onOpenChange,
  emailLabel,
}: LogoutConfirmDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onConfirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.auth.logout();
    } catch (e) {
      // 即便后端失败也继续跳转（避免会话卡死）。
      console.warn("logout request failed:", e);
    }
    resetSessionCache();
    // 跳登录页（与 layout.handleLogout 行为一致）
    if (typeof window !== "undefined") {
      window.location.assign("/login");
    } else {
      setBusy(false);
    }
    // 视觉上略等再假装完成，避免组件在此期间被卸载但 isLoading 闪烁
    window.setTimeout(() => onOpenChange(false), REDIRECT_DELAY_MS);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm" data-testid="logout-confirm-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <LogOut className="w-4 h-4 text-[#f59e0b]" />
            确认退出登录
          </DialogTitle>
          <DialogDescription>
            {emailLabel ? (
              <span>
                将退出当前会话，<span className="text-[#e2e8f0] font-medium">{emailLabel}</span>
                需要重新登录才能继续操作。
              </span>
            ) : (
              <span>将退出当前会话，需要重新登录才能继续操作。</span>
            )}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-[#ff4d4f]/30 bg-[#ff4d4f]/5 p-3 text-xs text-[#ff4d4f]">
            <AlertCircle className="w-4 h-4 mt-px shrink-0" />
            {error}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={busy}>
            取消
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => void onConfirm()}
            disabled={busy}
          >
            {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            退出登录
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
