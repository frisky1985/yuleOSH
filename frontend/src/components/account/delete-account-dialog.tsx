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
import { Input } from "@/components/ui/input";
import { AlertCircle, Eye, EyeOff, Loader2, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { resetSessionCache } from "@/lib/use-session-role";

interface DeleteAccountDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  emailLabel?: string;
}

/** 后端要求的硬性确认字符串。用户必须逐字照敲，复制粘贴不算。*/
export const DELETE_CONFIRMATION_CODE = "DELETE-MY-ACCOUNT";

/** 决策者顶栏 → 注销账户：必须输入确认串 + 当前登录密码双重验证。
 *
 * 后端 DELETE /api/v1/me/account：
 *   * body = { confirmation_code, password }
 *   * confirmation_code 必须等于 DELETE_CONFIRMATION_CODE（"额外的码"）
 *   * password 必须匹配当前用户 bcrypt
 *   * 软注销：users.status='deleted' + 清空 sessions + 写审计事件
 */
export function DeleteAccountDialog({
  open,
  onOpenChange,
  emailLabel,
}: DeleteAccountDialogProps) {
  const [confirmationCode, setConfirmationCode] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const codeOk = confirmationCode === DELETE_CONFIRMATION_CODE;
  const passwordOk = password.length > 0;
  const canSubmit = codeOk && passwordOk && !busy;

  const reset = () => {
    setConfirmationCode("");
    setPassword("");
    setShowPassword(false);
    setError(null);
    setBusy(false);
  };

  const onCancel = () => {
    if (busy) return;
    reset();
    onOpenChange(false);
  };

  const onConfirm = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await api.v1.me.deleteAccount({
        confirmation_code: confirmationCode,
        password,
      });
      // 注销成功 → 失效会话缓存 + 跳登录页（与登出一致）
      resetSessionCache();
      if (typeof window !== "undefined") {
        window.location.assign("/login");
      }
      return;
    } catch (e) {
      setError(e instanceof Error ? e.message : "注销失败，请稍后再试");
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => (busy ? undefined : onOpenChange(v))}>
      <DialogContent size="md" data-testid="delete-account-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-[#ff4d4f]">
            <Trash2 className="w-4 h-4" />
            注销账户（不可恢复）
          </DialogTitle>
          <DialogDescription>
            {emailLabel ? (
              <span>
                将注销账户 <span className="text-[#e2e8f0] font-medium">{emailLabel}</span>。
                此操作 <span className="text-[#ff4d4f] font-medium">不可恢复</span>，
                所有该账户的会话将被立即吊销。
              </span>
            ) : (
              <span>
                此操作 <span className="text-[#ff4d4f] font-medium">不可恢复</span>，
                所有该账户的会话将被立即吊销。
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-lg border border-[#ff4d4f]/30 bg-[#ff4d4f]/5 p-3 text-xs text-[#ff4d4f]/90 leading-relaxed">
          为防止误操作，请完成下列两项验证：
          <ol className="list-decimal list-inside mt-1 space-y-0.5">
            <li>
              在下方「确认串」框中输入{" "}
              <code className="font-mono text-[#ff4d4f] font-semibold">{DELETE_CONFIRMATION_CODE}</code>
              （区分大小写）。
            </li>
            <li>
              在下方输入当前账户的登录密码。
            </li>
          </ol>
        </div>

        <div className="flex flex-col gap-4 mt-1">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="delete-confirm-code" className="text-xs text-[#94a3b8]">
              确认串
              <span className="text-[#ff4d4f] ml-1">*</span>
            </label>
            <Input
              id="delete-confirm-code"
              type="text"
              autoComplete="off"
              value={confirmationCode}
              onChange={(e) => setConfirmationCode(e.target.value)}
              placeholder={DELETE_CONFIRMATION_CODE}
              className="font-mono"
              disabled={busy}
              aria-invalid={confirmationCode !== "" && !codeOk}
            />
            {confirmationCode !== "" && !codeOk && (
              <span className="text-[10px] text-[#ff4d4f]">
                必须等于 <code className="font-mono">{DELETE_CONFIRMATION_CODE}</code>
              </span>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="delete-password" className="text-xs text-[#94a3b8]">
              当前登录密码
              <span className="text-[#ff4d4f] ml-1">*</span>
            </label>
            <div className="relative">
              <Input
                id="delete-password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                disabled={busy}
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[#94a3b8] hover:text-white"
                tabIndex={-1}
                aria-label={showPassword ? "隐藏密码" : "显示密码"}
                disabled={busy}
              >
                {showPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-[#ff4d4f]/30 bg-[#ff4d4f]/5 p-3 text-xs text-[#ff4d4f]">
            <AlertCircle className="w-4 h-4 mt-px shrink-0" />
            {error}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={busy}>
            取消
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => void onConfirm()}
            disabled={!canSubmit}
          >
            {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            我已了解风险，永久注销
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
