"use client";

import { apiFetch } from "@/lib/api-fetch";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  BookMarked,
  Check,
  ChevronDown,
  ChevronRight,
  Cpu,
  FlaskConical,
  LayoutDashboard,
  Loader2,
  Lock,
  Mail,
  Pencil,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Trash2,
  UserPlus,
  Workflow,
  X,
} from "lucide-react";
// 导航（顶栏/左栏）由 dashboard/layout 统一渲染，页面只提供内容

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
  status?: string | null;
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
  canEdit?: boolean;
}

interface MemberResponse {
  member: Member;
}

/** 权限矩阵变更审计条目（GET /api/v1/members/roles/audit） */
interface AuditEntry {
  id: number;
  actor: string;
  role: string;
  module: string;
  old_level: string | null;
  new_level: string;
  changed_at: string;
}

interface AuditResponse {
  audit: AuditEntry[];
  count: number;
  note?: string | null;
}

/** 批量设置的作用域：整行（某角色全模块）或整列（某模块全角色）。 */
type BatchScope = "role" | "module";

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
  member: { label: "成员(legacy)", color: "#64748b" }, // join-by-invite 创建的 legacy 角色，仅存量展示
};

const PERM_META: Record<PermLevel, { label: string; color: string; symbol: string }> = {
  full: { label: "完全权限", color: "#10b981", symbol: "●" },
  read: { label: "只读", color: "#1677ff", symbol: "◐" },
  none: { label: "无权限", color: "#475569", symbol: "○" },
};

// Click-to-cycle order for editable matrix cells.
const PERM_CYCLE: PermLevel[] = ["full", "read", "none"];
function nextLevel(level: PermLevel): PermLevel {
  const i = PERM_CYCLE.indexOf(level);
  return PERM_CYCLE[(i + 1) % PERM_CYCLE.length];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────


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

/** 权限级别 → {label, color}；审计日志里的旧值可能为 null/未知级别。 */
function levelMeta(level: string | null): { label: string; color: string } {
  if (!level) return { label: "-", color: "#475569" };
  const m = PERM_META[level as PermLevel];
  return m ? { label: m.label, color: m.color } : { label: level, color: "#64748b" };
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
  const canEdit = matrix?.canEdit ?? false;

  // Matrix edit mode
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<RolesResponse | null>(null);
  const [savingMatrix, setSavingMatrix] = useState(false);
  const [matrixMsg, setMatrixMsg] = useState("");

  // 批量设置（T7）：整行（某角色全模块）/ 整列（某模块全角色）
  const [batchScope, setBatchScope] = useState<BatchScope>("role");
  const [batchTarget, setBatchTarget] = useState("developer");
  const [batchLevel, setBatchLevel] = useState<PermLevel>("read");

  // 权限矩阵审计日志（T7）
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [auditOpen, setAuditOpen] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);

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

  // 移除成员（仅 Owner/Admin；二次确认防误删）
  const handleRemoveMember = useCallback(
    async (member: Member) => {
      if (!canEdit) return;
      if (!window.confirm(`确定移除成员 ${member.email}？此操作不可撤销。`)) return;
      setSavingId(String(member.id));
      setActionError("");
      try {
        await apiFetch(`/api/v1/members/${String(member.id)}`, { method: "DELETE" });
        await loadMembers();
      } catch (err) {
        setActionError(`移除 ${member.email} 失败：${errMessage(err)}`);
      } finally {
        setSavingId(null);
      }
    },
    [canEdit, loadMembers]
  );

  // ── Edit permission matrix ─────────────────────────────────────────────
  const startEdit = useCallback(() => {
    if (!matrix) return;
    setDraft({
      roles: matrix.roles.map((r) => ({ role: r.role, permissions: { ...r.permissions } })),
      modules: matrix.modules,
    });
    setEditing(true);
    setMatrixMsg("");
  }, [matrix]);

  const cancelEdit = useCallback(() => {
    setEditing(false);
    setDraft(null);
    setMatrixMsg("");
  }, []);

  const cycleCell = useCallback((roleIdx: number, module: string) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const roles = prev.roles.map((r, i) =>
        i === roleIdx
          ? { ...r, permissions: { ...r.permissions, [module]: nextLevel(r.permissions[module] || "none") } }
          : r
      );
      return { ...prev, roles };
    });
  }, []);

  // ── 审计日志（T7）：权限矩阵变更记录 ──────────────────────────────────
  const loadAudit = useCallback(async () => {
    setAuditLoading(true);
    try {
      const res = await apiFetch<AuditResponse>("/api/v1/members/roles/audit");
      setAudit(res.audit || []);
    } catch {
      setAudit([]);
    } finally {
      setAuditLoading(false);
    }
  }, []);

  // ── 批量设置（T7）：整行 / 整列一次改到同一级别 ───────────────────────
  const applyBatch = useCallback((scope: BatchScope, target: string, level: PermLevel) => {
    if (!target) return;
    setDraft((prev) => {
      if (!prev) return prev;
      const roles = prev.roles.map((r) => {
        if (scope === "role" && r.role === target) {
          const perms: Record<string, PermLevel> = { ...r.permissions };
          for (const m of Object.keys(perms)) perms[m] = level;
          return { ...r, permissions: perms };
        }
        if (scope === "module") {
          return { ...r, permissions: { ...r.permissions, [target]: level } };
        }
        return r;
      });
      return { ...prev, roles };
    });
  }, []);

  const saveMatrix = useCallback(async () => {
    if (!draft) return;
    const matrixObj: Record<string, Record<string, PermLevel>> = {};
    draft.roles.forEach((r) => {
      matrixObj[r.role] = r.permissions;
    });
    setSavingMatrix(true);
    setMatrixMsg("");
    try {
      const res = await apiFetch<RolesResponse & { updated?: number }>("/api/v1/members/roles", {
        method: "PATCH",
        body: JSON.stringify({ matrix: matrixObj }),
      });
      setMatrix(res);
      setEditing(false);
      setDraft(null);
      setMatrixMsg(`已保存权限矩阵（更新 ${res.updated ?? 0} 项）`);
      if (auditOpen) void loadAudit();
    } catch (err) {
      setMatrixMsg(`保存失败：${errMessage(err)}`);
    } finally {
      setSavingMatrix(false);
    }
  }, [draft, auditOpen, loadAudit]);

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
                              className="grid grid-cols-[1fr_auto_auto_auto] gap-3 px-4 py-3 items-center border-b border-[#1e293b] last:border-b-0 hover:bg-[#1e293b]/40 transition-all"
                            >
                              <div className="flex items-center gap-2 min-w-0">
                                <Mail className="w-4 h-4 text-[#722ed1] shrink-0" />
                                <span className="text-sm text-[#e2e8f0] truncate">{m.email}</span>
                                {m.status === "pending" && (
                                  <span
                                    className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium"
                                    style={{
                                      color: "#faad14",
                                      background: "#faad141f",
                                      border: "1px solid #faad144d",
                                    }}
                                    title="已发送邀请，等待对方首次登录激活"
                                  >
                                    待接受
                                  </span>
                                )}
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
                              {canEdit && (
                                <div className="w-8 flex justify-end">
                                  <button
                                    type="button"
                                    title="移除成员"
                                    disabled={saving}
                                    onClick={() => void handleRemoveMember(m)}
                                    className="p-1.5 rounded-md text-[#64748b] hover:text-[#ff4d4f] hover:bg-[#ff4d4f]/10 transition-colors disabled:opacity-40"
                                  >
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              )}
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
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-[#722ed1]" />
                权限矩阵
                {!matrixLoading && matrixRoles.length > 0 && (
                  <span className="text-xs font-normal text-[#64748b]">
                    {matrixRoles.length} 角色 × {matrixModules.length} 模块
                  </span>
                )}
              </CardTitle>
              <div className="flex items-center gap-2 shrink-0">
                {canEdit && !editing && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void startEdit()}
                    className="border-[#722ed1]/40 text-[#722ed1] hover:text-white hover:bg-[#722ed1]/10"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                    编辑
                  </Button>
                )}
                {editing && (
                  <>
                    <Button
                      size="sm"
                      onClick={() => void saveMatrix()}
                      disabled={savingMatrix}
                      className="bg-[#10b981] hover:bg-[#10b981]/80 text-white"
                    >
                      <Check className="w-3.5 h-3.5" />
                      保存
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void cancelEdit()}
                      disabled={savingMatrix}
                      className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#ff4d4f]/40"
                    >
                      <X className="w-3.5 h-3.5" />
                      取消
                    </Button>
                  </>
                )}
              </div>
            </div>
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
              {editing && (
                <span className="ml-2 text-[#722ed1]">· 点击单元格在 完全 / 只读 / 无 之间切换</span>
              )}
            </CardDescription>
            {!canEdit && !matrixLoading && (
              <p className="text-xs text-[#64748b] mt-1 flex items-center gap-1">
                <Lock className="w-3 h-3" />
                仅 Owner/Admin 可编辑权限矩阵
              </p>
            )}
            {matrixMsg && (
              <p
                className={`text-xs mt-1 flex items-center gap-1 ${
                  matrixMsg.startsWith("保存失败")
                    ? "text-[#ff4d4f]"
                    : "text-[#10b981]"
                }`}
              >
                {matrixMsg.startsWith("保存失败") ? (
                  <AlertCircle className="w-3 h-3" />
                ) : (
                  <Check className="w-3 h-3" />
                )}
                {matrixMsg}
              </p>
            )}
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
              <>
                {/* ── 批量设置（T7）：整行 / 整列一次改到同一级别 ── */}
                {editing && (
                  <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b border-[#1e293b] bg-[#0a0e17]/60">
                    <span className="text-xs text-[#94a3b8]">批量设置</span>
                    <Select
                      value={batchScope}
                      onValueChange={(v) => {
                        const s = (v ?? "role") as BatchScope;
                        setBatchScope(s);
                        setBatchTarget(s === "role" ? "developer" : matrixModules[0] ?? "");
                      }}
                    >
                      <SelectTrigger size="sm" className="w-28">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent align="start">
                        <SelectItem value="role">整行（角色）</SelectItem>
                        <SelectItem value="module">整列（模块）</SelectItem>
                      </SelectContent>
                    </Select>
                    <Select value={batchTarget} onValueChange={(v) => setBatchTarget(v ?? "")}>
                      <SelectTrigger size="sm" className="w-36">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent align="start">
                        {(batchScope === "role"
                          ? ROLE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))
                          : matrixModules.map((m) => ({ value: m, label: m }))
                        ).map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select
                      value={batchLevel}
                      onValueChange={(v) => setBatchLevel((v ?? "read") as PermLevel)}
                    >
                      <SelectTrigger size="sm" className="w-28">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent align="start">
                        {(Object.keys(PERM_META) as PermLevel[]).map((lv) => (
                          <SelectItem key={lv} value={lv}>
                            {PERM_META[lv].label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!batchTarget}
                      onClick={() => applyBatch(batchScope, batchTarget, batchLevel)}
                      className="border-[#722ed1]/40 text-[#722ed1] hover:text-white hover:bg-[#722ed1]/10"
                    >
                      应用到{batchScope === "role" ? "该角色全行" : "该模块全列"}
                    </Button>
                    <span className="text-[11px] text-[#64748b]">
                      批量改动随「保存」一并提交并计入审计日志
                    </span>
                  </div>
                )}
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
                        {matrixRoles.map((r, rIdx) => {
                          const view = editing && draft ? draft.roles[rIdx] : r;
                          const level = (view.permissions || {})[mod] || "none";
                          const meta = PERM_META[level];
                          const cellStyle = {
                            color: meta.color,
                            background: `${meta.color}1f`,
                            border: `1px solid ${meta.color}4d`,
                          };
                          const title = `${roleMeta(r.role).label} · ${mod} · ${meta.label}`;
                          if (editing) {
                            return (
                              <td key={r.role} className="px-2 py-2 text-center">
                                <button
                                  type="button"
                                  onClick={() => void cycleCell(rIdx, mod)}
                                  title={`${title}（点击切换）`}
                                  className="inline-flex items-center justify-center w-6 h-6 rounded-full cursor-pointer transition-transform hover:scale-125"
                                  style={cellStyle}
                                >
                                  {meta.symbol}
                                </button>
                              </td>
                            );
                          }
                          return (
                            <td key={r.role} className="px-2 py-2 text-center">
                              <span
                                title={title}
                                className="inline-flex items-center justify-center w-6 h-6 rounded-full cursor-default transition-transform hover:scale-125"
                                style={cellStyle}
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

                {/* ── 审计日志（T7）：权限矩阵变更记录 ── */}
                <div className="border-t border-[#1e293b]">
                  <button
                    type="button"
                    onClick={() => {
                      const next = !auditOpen;
                      setAuditOpen(next);
                      if (next) void loadAudit();
                    }}
                    className="w-full px-4 py-2.5 text-xs text-[#94a3b8] hover:text-white hover:bg-[#1e293b]/50 transition-colors flex items-center justify-center gap-1.5"
                  >
                    <ScrollText className="w-3.5 h-3.5" />
                    {auditOpen
                      ? "收起审计日志"
                      : `查看审计日志${audit.length ? `（${audit.length}）` : ""}`}
                  </button>
                  {auditOpen && (
                    <div className="px-4 pb-3">
                      {auditLoading ? (
                        <div className="flex items-center justify-center py-6 text-[#64748b]">
                          <Loader2 className="w-3.5 h-3.5 animate-spin mr-2" />
                          加载中…
                        </div>
                      ) : audit.length === 0 ? (
                        <div className="py-6 text-center text-[#64748b] text-xs">
                          暂无权限变更记录
                        </div>
                      ) : (
                        <div className="max-h-64 overflow-y-auto space-y-1">
                          {audit.map((a) => {
                            const oldMeta = levelMeta(a.old_level);
                            const newMeta = levelMeta(a.new_level);
                            const rm = roleMeta(a.role);
                            return (
                              <div
                                key={a.id}
                                className="flex items-center gap-2 text-xs px-2 py-1.5 rounded bg-[#0a0e17] border border-[#1e293b]"
                              >
                                <span className="text-[#64748b] shrink-0 w-28 truncate">
                                  {formatDate(a.changed_at)}
                                </span>
                                <span
                                  className="text-[#e2e8f0] shrink-0 w-32 truncate"
                                  title={a.actor}
                                >
                                  {a.actor}
                                </span>
                                <span className="shrink-0" style={{ color: rm.color }}>
                                  {rm.label}
                                </span>
                                <span className="text-[#475569] shrink-0">·</span>
                                <span className="text-[#94a3b8] shrink-0">{a.module}</span>
                                <span className="ml-auto flex items-center gap-1.5 shrink-0">
                                  <span
                                    className="px-1.5 py-0.5 rounded text-[10px]"
                                    style={{
                                      color: oldMeta.color,
                                      background: `${oldMeta.color}1f`,
                                      border: `1px solid ${oldMeta.color}4d`,
                                    }}
                                  >
                                    {oldMeta.label}
                                  </span>
                                  <span className="text-[#475569]">→</span>
                                  <span
                                    className="px-1.5 py-0.5 rounded text-[10px]"
                                    style={{
                                      color: newMeta.color,
                                      background: `${newMeta.color}1f`,
                                      border: `1px solid ${newMeta.color}4d`,
                                    }}
                                  >
                                    {newMeta.label}
                                  </span>
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Footer hint */}
        <div className="mt-6 flex items-center gap-1 text-xs text-[#475569]">
          <ChevronRight className="w-3 h-3" />
          权限矩阵存储于数据库，可在界面编辑{canEdit ? "（点击「编辑」后逐格调整）" : "；仅 Owner/Admin 拥有编辑权限"}；成员数据来自当前组织。
        </div>
      </div>
  </div>
  );
}
