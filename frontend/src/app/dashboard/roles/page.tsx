"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  BookMarked,
  ChevronDown,
  ChevronRight,
  Cpu,
  FlaskConical,
  LayoutDashboard,
  Loader2,
  Mail,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  UserPlus,
  Workflow,
} from "lucide-react";
import { TopNav } from "@/components/dashboard/top-nav";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// ─── Types ───────────────────────────────────────────────────────────────────

type PermLevel = "full" | "read" | "none";

interface Member {
  id: number | string;
  email: string;
  role: string;
  created_at?: string | null;
}

interface MembersResponse {
  members: Member[];
  count: number;
  note?: string | null;
}

interface RolePerms {
  role: string;
  permissions: Record<string, PermLevel>;
}

interface RolesResponse {
  roles: RolePerms[];
  modules?: string[];
}

interface MemberResponse {
  member: Member;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: "owner", label: "所有者" },
  { value: "admin", label: "管理员" },
  { value: "quality_manager", label: "质量经理" },
  { value: "architect", label: "架构师" },
  { value: "developer", label: "开发者" },
  { value: "viewer", label: "访客" },
];

const ROLE_META: Record<string, { label: string; color: string }> = {
  owner: { label: "所有者", color: "#722ed1" },
  admin: { label: "管理员", color: "#ff4d4f" },
  quality_manager: { label: "质量经理", color: "#10b981" },
  architect: { label: "架构师", color: "#1677ff" },
  developer: { label: "开发者", color: "#faad14" },
  viewer: { label: "访客", color: "#64748b" },
};

const PERM_META: Record<PermLevel, { label: string; color: string; symbol: string }> = {
  full: { label: "完全权限", color: "#10b981", symbol: "●" },
  read: { label: "只读", color: "#1677ff", symbol: "◐" },
  none: { label: "无权限", color: "#475569", symbol: "○" },
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Fetch an API v1 endpoint and unwrap the {ok, data?} envelope. */
async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const contentType = res.headers.get("content-type") || "";
  let body: unknown = null;
  if (contentType.includes("application/json")) {
    body = await res.json();
  } else {
    const text = await res.text();
    throw new Error(`Non-JSON response (${res.status}): ${text.slice(0, 200)}`);
  }
  const record = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
  if (record.ok === false) {
    throw new Error(typeof record.error === "string" ? record.error : `API error (${res.status})`);
  }
  const payload = record.data !== undefined ? record.data : body;
  return payload as T;
}

function errMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function formatDate(dateStr?: string | null): string {
  if (!dateStr || dateStr === "-") return "-";
  try {
    const d = new Date(dateStr);
    if (Number.isNaN(d.getTime())) return dateStr;
    return d.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function roleMeta(role: string): { label: string; color: string } {
  return ROLE_META[role] || { label: role || "未知", color: "#64748b" };
}

// ─── Nav ─────────────────────────────────────────────────────────────────────

// Navigation is rendered by the shared TopNav component
// (see src/components/dashboard/top-nav.tsx).

// ─── Page ────────────────────────────────────────────────────────────────────

export default function RolesPage() {

  // Member list
  const [members, setMembers] = useState<Member[]>([]);
  const [listNote, setListNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAllMembers, setShowAllMembers] = useState(false);

  // Invite form
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("developer");
  const [inviting, setInviting] = useState(false);
  const [inviteMsg, setInviteMsg] = useState("");

  // Role change (per row)
  const [savingId, setSavingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");

  // Permission matrix
  const [matrix, setMatrix] = useState<RolesResponse | null>(null);
  const [matrixLoading, setMatrixLoading] = useState(true);
  const [matrixError, setMatrixError] = useState("");

  // ── Load members ─────────────────────────────────────────────────────────
  const loadMembers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch<MembersResponse>("/api/v1/members");
      setMembers(res.members || []);
      setListNote(res.note ?? null);
    } catch (err) {
      setError(errMessage(err));
      setMembers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Load permission matrix ───────────────────────────────────────────────
  const loadMatrix = useCallback(async () => {
    setMatrixLoading(true);
    setMatrixError("");
    try {
      const res = await apiFetch<RolesResponse>("/api/v1/members/roles");
      setMatrix(res);
    } catch (err) {
      setMatrixError(errMessage(err));
      setMatrix(null);
    } finally {
      setMatrixLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMembers();
    void loadMatrix();
  }, [loadMembers, loadMatrix]);

  // ── Invite a member ──────────────────────────────────────────────────────
  const handleInvite = useCallback(async () => {
    const email = inviteEmail.trim();
    if (!email) {
      setInviteMsg("请输入邮箱地址");
      return;
    }
    setInviting(true);
    setInviteMsg("");
    setError("");
    try {
      await apiFetch<MemberResponse>("/api/v1/members/invite", {
        method: "POST",
        body: JSON.stringify({ email, role: inviteRole }),
      });
      setInviteEmail("");
      setInviteMsg(`已发送邀请：${email}（${roleMeta(inviteRole).label}）`);
      await loadMembers();
    } catch (err) {
      setInviteMsg(`邀请失败：${errMessage(err)}`);
    } finally {
      setInviting(false);
    }
  }, [inviteEmail, inviteRole, loadMembers]);

  // ── Change a member's role ───────────────────────────────────────────────
  const handleRoleChange = useCallback(
    async (member: Member, newRole: string) => {
      if (!newRole || newRole === member.role || savingId !== null) return;
      setSavingId(String(member.id));
      setActionError("");
      try {
        await apiFetch<MemberResponse>(`/api/v1/members/${String(member.id)}`, {
          method: "PATCH",
          body: JSON.stringify({ role: newRole }),
        });
        await loadMembers();
      } catch (err) {
        setActionError(`更新 ${member.email} 的角色失败：${errMessage(err)}`);
      } finally {
        setSavingId(null);
      }
    },
    [savingId, loadMembers]
  );

  const isEmpty = !loading && members.length === 0;

  // Matrix derived state
  const matrixRoles = matrix?.roles || [];
  const matrixModules = matrix?.modules?.length
    ? matrix.modules
    : matrixRoles.length > 0
      ? Object.keys(matrixRoles[0].permissions || {})
      : [];

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      <TopNav mode="links" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
              <ShieldCheck className="w-4.5 h-4.5 text-[#722ed1]" />
              角色管理
            </h1>
            <p className="text-xs text-[#94a3b8] mt-0.5">
              组织成员与角色权限矩阵（邀请成员、调整角色、查看 6 角色 × 8 模块权限）
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void loadMembers();
              void loadMatrix();
            }}
            disabled={loading || matrixLoading}
            className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading || matrixLoading ? "animate-spin" : ""}`} />
            刷新
          </Button>
        </div>

        {/* Data note */}
        {listNote && (
          <div className="mb-4 rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-4 py-2 text-xs text-[#faad14] flex items-center gap-2">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>{listNote}</span>
          </div>
        )}

        {/* Error banner */}
        {(error || actionError) && (
          <div className="mb-4 rounded-lg bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-4 py-2 text-xs text-[#ff4d4f] flex items-center justify-between">
            <span className="flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" />
              {error || actionError}
            </span>
            <button
              onClick={() => {
                setError("");
                setActionError("");
              }}
              className="ml-2 hover:text-white text-sm"
            >
              &times;
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 items-start">
          {/* ── Left: member list ── */}
          <Card className="border-[#1e293b] bg-[#111827]">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                <UserPlus className="w-4 h-4 text-[#722ed1]" />
                成员列表
                {!loading && (
                  <span className="text-xs font-normal text-[#64748b]">共 {members.length} 人</span>
                )}
              </CardTitle>
              <CardDescription className="text-xs text-[#64748b]">
                点击行内角色下拉可调整成员角色（仅 Owner/Admin 可操作）
              </CardDescription>
            </CardHeader>
            <CardContent className="px-0">
              {loading ? (
                <div className="flex items-center justify-center py-14 text-[#64748b]">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  加载中…
                </div>
              ) : isEmpty ? (
                <div className="py-14 text-center text-[#64748b] text-sm">
                  <div className="text-2xl mb-2">👥</div>
                  暂无成员
                  <div className="text-xs mt-1 text-[#475569]">
                    使用右侧表单邀请第一个成员
                  </div>
                </div>
              ) : (
                <div>
                  {/* Table header */}
                  <div className="grid grid-cols-[1fr_auto_auto] gap-3 px-4 py-2 text-xs text-[#64748b] border-b border-[#1e293b]">
                    <span>邮箱</span>
                    <span className="w-44">角色</span>
                    <span className="w-32 text-right">加入时间</span>
                  </div>

                  {(() => {
                    const MEMBER_PREVIEW = 3;
                    const visible = showAllMembers ? members : members.slice(0, MEMBER_PREVIEW);
                    const hidden = members.length - visible.length;
                    return (
                      <>
                        {visible.map((m) => {
                          const meta = roleMeta(m.role);
                          const saving = savingId === String(m.id);
                          return (
                            <div
                              key={String(m.id)}
                              className="grid grid-cols-[1fr_auto_auto] gap-3 px-4 py-3 items-center border-b border-[#1e293b] last:border-b-0 hover:bg-[#1e293b]/40 transition-all"
                            >
                              <div className="flex items-center gap-2 min-w-0">
                                <Mail className="w-4 h-4 text-[#722ed1] shrink-0" />
                                <span className="text-sm text-[#e2e8f0] truncate">{m.email}</span>
                              </div>
                              <div className="w-44 flex items-center gap-2">
                                <Badge
                                  variant="outline"
                                  className="border-transparent shrink-0"
                                  style={{
                                    color: meta.color,
                                    background: `${meta.color}1f`,
                                    borderColor: `${meta.color}4d`,
                                  }}
                                >
                                  {meta.label}
                                </Badge>
                                {saving ? (
                                  <span className="flex items-center gap-1 text-xs text-[#64748b]">
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                    保存中…
                                  </span>
                                ) : (
                                  <Select
                                    value={m.role}
                                    onValueChange={(v) => void handleRoleChange(m, v ?? "")}
                                  >
                                    <SelectTrigger size="sm" className="w-full">
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent align="start">
                                      {ROLE_OPTIONS.map((opt) => (
                                        <SelectItem key={opt.value} value={opt.value}>
                                          {opt.label}
                                        </SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                )}
                              </div>
                              <div className="w-32 text-right text-xs text-[#94a3b8]">
                                {formatDate(m.created_at)}
                              </div>
                            </div>
                          );
                        })}
                        {hidden > 0 && (
                          <button
                            type="button"
                            onClick={() => setShowAllMembers(true)}
                            className="w-full px-4 py-2.5 text-xs text-[#722ed1] hover:text-white hover:bg-[#722ed1]/10 transition-colors flex items-center justify-center gap-1.5 border-b border-[#1e293b] last:border-b-0"
                          >
                            <ChevronDown className="w-3.5 h-3.5" />
                            显示更多（还有 {hidden} 位成员）
                          </button>
                        )}
                        {showAllMembers && members.length > MEMBER_PREVIEW && (
                          <button
                            type="button"
                            onClick={() => setShowAllMembers(false)}
                            className="w-full px-4 py-2.5 text-xs text-[#64748b] hover:text-white hover:bg-[#1e293b]/50 transition-colors flex items-center justify-center gap-1.5 border-b border-[#1e293b] last:border-b-0"
                          >
                            收起
                          </button>
                        )}
                      </>
                    );
                  })()}
                </div>
              )}
            </CardContent>
          </Card>

          {/* ── Right: invite form ── */}
          <Card className="border-[#1e293b] bg-[#111827] lg:sticky lg:top-20">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                <Mail className="w-4 h-4 text-[#722ed1]" />
                邀请成员
              </CardTitle>
              <CardDescription className="text-xs text-[#64748b]">
                输入邮箱并选择角色，邀请加入当前组织
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="block text-xs text-[#94a3b8] mb-1.5">邮箱</label>
                <Input
                  type="email"
                  placeholder="name@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  disabled={inviting}
                  className="border-[#1e293b] bg-[#0a0e17] text-[#e2e8f0] placeholder:text-[#475569]"
                />
              </div>
              <div>
                <label className="block text-xs text-[#94a3b8] mb-1.5">角色</label>
                <Select value={inviteRole} onValueChange={(v) => setInviteRole(v ?? "developer")}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent align="start">
                    {ROLE_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button
                size="sm"
                className="w-full bg-[#722ed1] hover:bg-[#722ed1]/80 text-white"
                onClick={() => void handleInvite()}
                disabled={inviting || !inviteEmail.trim()}
              >
                {inviting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    邀请中…
                  </>
                ) : (
                  <>
                    <UserPlus className="w-3.5 h-3.5" />
                    发送邀请
                  </>
                )}
              </Button>
              {inviteMsg && (
                <div
                  className={`rounded-lg border px-3 py-2 text-xs flex items-center gap-1 ${
                    inviteMsg.startsWith("邀请失败") || inviteMsg.startsWith("请")
                      ? "bg-[#ff4d4f]/10 border-[#ff4d4f]/20 text-[#ff4d4f]"
                      : "bg-[#10b981]/10 border-[#10b981]/20 text-[#10b981]"
                  }`}
                >
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  {inviteMsg}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── Permission matrix ── */}
        <Card className="border-[#1e293b] bg-[#111827] mt-6">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-[#722ed1]" />
              权限矩阵
              {!matrixLoading && matrixRoles.length > 0 && (
                <span className="text-xs font-normal text-[#64748b]">
                  {matrixRoles.length} 角色 × {matrixModules.length} 模块
                </span>
              )}
            </CardTitle>
            <CardDescription className="text-xs text-[#64748b]">
              <span className="inline-flex items-center gap-3">
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full inline-block" style={{ background: PERM_META.full.color }} />
                  完全权限
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full inline-block" style={{ background: PERM_META.read.color }} />
                  只读
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full inline-block" style={{ background: PERM_META.none.color }} />
                  无权限
                </span>
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            {matrixLoading ? (
              <div className="flex items-center justify-center py-14 text-[#64748b]">
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                加载中…
              </div>
            ) : matrixError ? (
              <div className="py-10 text-center text-[#ff4d4f] text-xs flex items-center justify-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" />
                {matrixError}
              </div>
            ) : matrixRoles.length === 0 ? (
              <div className="py-14 text-center text-[#64748b] text-sm">暂无权限数据</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[#1e293b] text-[#64748b]">
                      <th className="px-4 py-2 text-left font-medium w-32">模块 \\ 角色</th>
                      {matrixRoles.map((r) => {
                        const meta = roleMeta(r.role);
                        return (
                          <th key={r.role} className="px-2 py-2 text-center font-medium whitespace-nowrap">
                            <span style={{ color: meta.color }}>{meta.label}</span>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {matrixModules.map((mod) => (
                      <tr key={mod} className="border-b border-[#1e293b]/60 last:border-b-0 hover:bg-[#1e293b]/30">
                        <td className="px-4 py-2 text-[#e2e8f0] whitespace-nowrap">{mod}</td>
                        {matrixRoles.map((r) => {
                          const level = (r.permissions || {})[mod] || "none";
                          const meta = PERM_META[level];
                          return (
                            <td key={r.role} className="px-2 py-2 text-center">
                              <span
                                title={`${roleMeta(r.role).label} · ${mod} · ${meta.label}`}
                                className="inline-flex items-center justify-center w-6 h-6 rounded-full cursor-default transition-transform hover:scale-125"
                                style={{
                                  color: meta.color,
                                  background: `${meta.color}1f`,
                                  border: `1px solid ${meta.color}4d`,
                                }}
                              >
                                {meta.symbol}
                              </span>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Footer hint */}
        <div className="mt-6 flex items-center gap-1 text-xs text-[#475569]">
          <ChevronRight className="w-3 h-3" />
          角色权限依据设计文档第 4 章矩阵静态渲染；成员数据来自当前组织。
        </div>
      </div>
    </div>
  );
}
