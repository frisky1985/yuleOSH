"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AlertCircle, Loader2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { AccountInfo } from "@/lib/api";

interface AccountInfoDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fallback email used before the request completes (e.g. from session). */
  fallbackEmail?: string;
  /** Fallback org name shown while /me/account is loading. */
  fallbackOrgName?: string;
}

/** 决策者顶栏 → 个人信息：展示账户的完整资料。
 *
 * 数据源 GET /api/v1/me/account（@require_auth，cookie 鉴权）。
 * 失败回落到上层传来的 session 字段，不阻塞 UI。 */
export function AccountInfoDialog({
  open,
  onOpenChange,
  fallbackEmail,
  fallbackOrgName,
}: AccountInfoDialogProps) {
  const [info, setInfo] = useState<AccountInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchInfo = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.v1.me.account();
      setInfo(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "获取账户信息失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && !info) {
      void fetchInfo();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const role = info?.user.role ?? "—";
  const email = info?.user.email ?? fallbackEmail ?? "—";
  const orgName = info?.org.name ?? fallbackOrgName ?? "—";
  const status = info?.user.status ?? "—";
  const createdAt = info?.user.created_at ?? null;
  const activeSessions = info?.active_sessions;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md" data-testid="account-info-dialog">
        <DialogHeader>
          <DialogTitle>账户信息</DialogTitle>
          <DialogDescription>
            当前登录账户的完整资料。涉及身份与权限的关键字段均在此处可视。
          </DialogDescription>
        </DialogHeader>

        {loading && !info && (
          <div className="flex items-center gap-2 text-sm text-[#94a3b8] py-6 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" />
            加载中…
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-[#ff4d4f]/30 bg-[#ff4d4f]/5 p-3 text-xs text-[#ff4d4f]">
            <AlertCircle className="w-4 h-4 mt-px shrink-0" />
            <div className="flex-1">
              <div>{error}</div>
              <Button
                variant="ghost"
                size="xs"
                className="mt-2 text-xs"
                onClick={() => void fetchInfo()}
              >
                <RefreshCw className="w-3 h-3" />
                重试
              </Button>
            </div>
          </div>
        )}

        {info && (
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <Field label="邮箱" value={email} />
            <Field label="角色" value={roleLabel(role)} />
            <Field label="账户状态" value={statusLabel(status)} highlight={status === "deleted"} />
            <Field
              label="所属组织"
              value={
                <span className="truncate flex items-center gap-2">
                  <span>{orgName}</span>
                  {info?.org.slug && (
                    <span className="text-[10px] text-[#94a3b8] border border-[#1e293b] rounded px-1.5">
                      /{info.org.slug}
                    </span>
                  )}
                </span>
              }
            />
            <Field
              label="注册时间"
              value={createdAt ? formatDate(createdAt) : "—"}
            />
            <Field
              label="活跃会话"
              value={
                activeSessions === null || activeSessions === undefined
                  ? "—"
                  : `${activeSessions} 个`
              }
            />
          </div>
        )}

        <div className="flex justify-end pt-2">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, value, highlight }: { label: string; value: React.ReactNode; highlight?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] text-[#94a3b8] uppercase tracking-wider">{label}</span>
      <span
        className={
          highlight
            ? "text-[#ff4d4f] font-medium"
            : "text-[#e2e8f0] font-medium truncate"
        }
      >
        {value}
      </span>
    </div>
  );
}

function roleLabel(role: string): string {
  switch (role) {
    case "admin":
      return "决策者（Admin）";
    case "developer":
      return "工程师（Developer）";
    case "reviewer":
      return "审核员（Reviewer）";
    case "auditor":
      return "审计员（Auditor）";
    case "owner":
      return "组织所有者（Owner）";
    default:
      return role || "—";
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "active":
      return "已激活";
    case "pending":
      return "邀请待生效";
    case "deleted":
      return "已注销";
    default:
      return status || "—";
  }
}

function formatDate(iso: string): string {
  // 简单格式化（无需 date-fns / dayjs）；只显示年月日时分
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
