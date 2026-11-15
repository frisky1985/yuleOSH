"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  UserCheck,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api-fetch";

// ─── Types ────────────────────────────────────────────────────────────────

export type AuditStatus = "open" | "pending_approval" | "closed";
export type FindingStatus = "open" | "acknowledged" | "resolved" | "closed";
export type QaSeverity = "low" | "medium" | "high" | "critical";

export interface QaAuditRow {
  id: string;
  title: string;
  auditor: string;
  auditor_role: string;
  scope: string;
  date: string;
  status: AuditStatus;
  approved_by: string;
  finding_count: number;
  open_findings: number;
}

export interface QaFinding {
  id: string;
  description: string;
  severity: QaSeverity;
  status: FindingStatus;
  assigned_to: string;
  resolution?: string;
  verifier?: string;
  created_at: string;
  updated_at: string;
  resolved_at?: string;
  closed_at?: string;
}

export interface QaApproval {
  approved_by: string;
  role: string;
  note: string;
  approved_at: string;
}

export interface QaAudit {
  id: string;
  title: string;
  auditor: string;
  auditor_role: string;
  scope: string;
  date: string;
  status: AuditStatus;
  approval: QaApproval | null;
  findings: QaFinding[];
  created_at: string;
  updated_at: string;
}

interface QaAuditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
}

// ─── Metadata ─────────────────────────────────────────────────────────────

const AUDIT_STATUS_META: Record<AuditStatus, { label: string; cls: string }> = {
  open: { label: "进行中", cls: "border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fbbf24]" },
  pending_approval: {
    label: "待批准",
    cls: "border-[#1677ff]/40 bg-[#1677ff]/10 text-[#60a5fa]",
  },
  closed: { label: "已关闭", cls: "border-[#10b981]/40 bg-[#10b981]/10 text-[#34d399]" },
};

const FINDING_STATUS_META: Record<FindingStatus, { label: string; cls: string }> = {
  open: { label: "待处理", cls: "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#f87171]" },
  acknowledged: {
    label: "已确认",
    cls: "border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fbbf24]",
  },
  resolved: { label: "已解决", cls: "border-[#1677ff]/40 bg-[#1677ff]/10 text-[#60a5fa]" },
  closed: { label: "已关闭", cls: "border-[#10b981]/40 bg-[#10b981]/10 text-[#34d399]" },
};

const SEVERITY_META: Record<QaSeverity, { label: string; cls: string }> = {
  low: { label: "低", cls: "border-[#475569]/40 bg-[#475569]/10 text-[#94a3b8]" },
  medium: { label: "中", cls: "border-[#1677ff]/40 bg-[#1677ff]/10 text-[#60a5fa]" },
  high: { label: "高", cls: "border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fbbf24]" },
  critical: { label: "严重", cls: "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#f87171]" },
};

export const FINDING_TRANSITIONS: Record<FindingStatus, FindingStatus[]> = {
  open: ["acknowledged", "resolved", "closed"],
  acknowledged: ["resolved", "closed"],
  resolved: ["closed"],
  closed: [],
};

const TRANSITION_LABEL: Record<FindingStatus, string> = {
  open: "重新打开",
  acknowledged: "确认问题",
  resolved: "标记解决",
  closed: "关闭",
};

const SEVERITIES: QaSeverity[] = ["critical", "high", "medium", "low"];

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

/** Mirrors yuleosh.desktop.qa._audit_status (fail-closed). */
export function deriveAuditStatus(audit: Pick<QaAudit, "findings" | "approval">): AuditStatus {
  const findings = audit.findings || [];
  const allClosed = findings.every((f) => f.status === "closed");
  if (audit.approval?.approved_by && allClosed) return "closed";
  if (findings.length > 0 && allClosed) return "pending_approval";
  return "open";
}

function StatusBadge({ status }: { status: AuditStatus }) {
  const meta = AUDIT_STATUS_META[status] ?? AUDIT_STATUS_META.open;
  return (
    <span
      data-testid={`qa-status-${status}`}
      className={`rounded-full border px-2 py-0.5 text-[10px] ${meta.cls}`}
    >
      {meta.label}
    </span>
  );
}

function FindingStatusBadge({ status }: { status: FindingStatus }) {
  const meta = FINDING_STATUS_META[status] ?? FINDING_STATUS_META.open;
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

// ─── Dialog ───────────────────────────────────────────────────────────────

/** 桌面端 QA 审计（SUP.1）：审计计划、不符合项登记与流转、管理批准与导出。 */
export function QaAuditDialog({ open, onOpenChange, projectId }: QaAuditDialogProps) {
  const [audits, setAudits] = useState<QaAuditRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [audit, setAudit] = useState<QaAudit | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [title, setTitle] = useState("");
  const [auditor, setAuditor] = useState("");
  const [scope, setScope] = useState("");

  const [findingDesc, setFindingDesc] = useState("");
  const [findingSeverity, setFindingSeverity] = useState<QaSeverity>("medium");
  const [findingAssignee, setFindingAssignee] = useState("");
  const [findingNote, setFindingNote] = useState("");
  const [approver, setApprover] = useState("");
  // Creation returns the full audit — skip the redundant detail fetch.
  const skipDetailRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{ audits: QaAuditRow[] }>(
        `/api/v1/desktop/projects/${projectId}/qa`,
      );
      const list = data.audits || [];
      setAudits(list);
      setSelectedId((cur) => (list.some((a) => a.id === cur) ? cur : list[0]?.id ?? null));
    } catch (e) {
      setError((e as Error).message || "加载 QA 审计失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    setAudits([]);
    setSelectedId(null);
    setAudit(null);
    setTitle("");
    setAuditor("");
    setScope("");
    setFindingDesc("");
    setFindingSeverity("medium");
    setFindingAssignee("");
    setFindingNote("");
    setApprover("");
    skipDetailRef.current = null;
    setError("");
    setNotice("");
    load();
  }, [open, projectId, load]);

  // The list endpoint returns summaries only; findings live in the detail.
  useEffect(() => {
    if (!open || !projectId || !selectedId) {
      setAudit(null);
      return;
    }
    if (skipDetailRef.current === selectedId) {
      skipDetailRef.current = null;
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    apiFetch<{ audit: QaAudit }>(`/api/v1/desktop/projects/${projectId}/qa/${selectedId}`)
      .then((data) => {
        if (!cancelled) setAudit(data.audit);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message || "加载审计详情失败");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, projectId, selectedId]);

  const syncRow = useCallback((next: QaAudit) => {
    setAudits((prev) =>
      prev.map((a) =>
        a.id === next.id
          ? {
              ...a,
              title: next.title,
              status: next.status,
              approved_by: next.approval?.approved_by ?? "",
              finding_count: next.findings.length,
              open_findings: next.findings.filter((f) => f.status !== "closed").length,
            }
          : a,
      ),
    );
  }, []);

  const stats = useMemo(() => {
    const findings = audit?.findings ?? [];
    return {
      total: audits.length,
      openAudits: audits.filter((a) => a.status !== "closed").length,
      findings: findings.length,
      openFindings: findings.filter((f) => f.status !== "closed").length,
    };
  }, [audits, audit]);

  const create = async () => {
    if (!projectId || working) return;
    const trimmed = title.trim();
    if (!trimmed) {
      setError("审计标题不能为空");
      return;
    }
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ audit: QaAudit }>(
        `/api/v1/desktop/projects/${projectId}/qa`,
        {
          method: "POST",
          body: JSON.stringify({
            title: trimmed,
            auditor: auditor.trim() || "local",
            scope: scope.trim(),
          }),
        },
      );
      setAudits((prev) => [
        {
          id: data.audit.id,
          title: data.audit.title,
          auditor: data.audit.auditor,
          auditor_role: data.audit.auditor_role,
          scope: data.audit.scope,
          date: data.audit.date,
          status: data.audit.status,
          approved_by: "",
          finding_count: data.audit.findings?.length ?? 0,
          open_findings: (data.audit.findings ?? []).filter((f) => f.status !== "closed").length,
        },
        ...prev,
      ]);
      skipDetailRef.current = data.audit.id;
      setSelectedId(data.audit.id);
      setAudit(data.audit);
      setTitle("");
      setAuditor("");
      setScope("");
      setNotice(`已创建审计 ${data.audit.id}`);
    } catch (e) {
      setError((e as Error).message || "创建审计失败");
    } finally {
      setWorking(false);
    }
  };

  const addFinding = async () => {
    if (!projectId || !audit || working) return;
    const desc = findingDesc.trim();
    if (!desc) {
      setError("不符合项描述不能为空");
      return;
    }
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ finding: QaFinding }>(
        `/api/v1/desktop/projects/${projectId}/qa/${audit.id}/findings`,
        {
          method: "POST",
          body: JSON.stringify({
            description: desc,
            severity: findingSeverity,
            assigned_to: findingAssignee.trim() || "unassigned",
          }),
        },
      );
      const next: QaAudit = {
        ...audit,
        findings: [...audit.findings, data.finding],
      };
      next.status = deriveAuditStatus(next);
      setAudit(next);
      syncRow(next);
      setFindingDesc("");
      setFindingAssignee("");
      setFindingSeverity("medium");
      setNotice(`已登记不符合项 ${data.finding.id}`);
    } catch (e) {
      setError((e as Error).message || "登记不符合项失败");
    } finally {
      setWorking(false);
    }
  };

  const moveFinding = async (finding: QaFinding, target: FindingStatus) => {
    if (!projectId || !audit || working) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const body: Record<string, string> = { status: target };
      if (findingNote.trim()) body.resolution = findingNote.trim();
      const data = await apiFetch<{ finding: QaFinding }>(
        `/api/v1/desktop/projects/${projectId}/qa/${audit.id}/findings/${finding.id}/transition`,
        { method: "POST", body: JSON.stringify(body) },
      );
      const next: QaAudit = {
        ...audit,
        findings: audit.findings.map((f) => (f.id === data.finding.id ? data.finding : f)),
      };
      next.status = deriveAuditStatus(next);
      setAudit(next);
      syncRow(next);
      setFindingNote("");
      setNotice(`${finding.id} 状态已更新为${FINDING_STATUS_META[target].label}`);
    } catch (e) {
      setError((e as Error).message || "不符合项流转失败");
    } finally {
      setWorking(false);
    }
  };

  const approve = async () => {
    if (!projectId || !audit || working) return;
    const who = approver.trim();
    if (!who) {
      setError("批准人不能为空");
      return;
    }
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ audit: QaAudit }>(
        `/api/v1/desktop/projects/${projectId}/qa/${audit.id}/approve`,
        { method: "POST", body: JSON.stringify({ approver: who }) },
      );
      setAudit(data.audit);
      syncRow(data.audit);
      setApprover("");
      setNotice(`审计 ${data.audit.id} 已由 ${who} 批准关闭`);
    } catch (e) {
      setError((e as Error).message || "批准审计失败");
    } finally {
      setWorking(false);
    }
  };

  const exportReport = async () => {
    if (!projectId || working) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ path: string }>(
        `/api/v1/desktop/projects/${projectId}/qa/export`,
      );
      setNotice(`已导出 QA 报告：${data.path}`);
    } catch (e) {
      setError((e as Error).message || "导出 QA 报告失败");
    } finally {
      setWorking(false);
    }
  };

  const findings = audit?.findings ?? [];
  const allClosed = findings.every((f) => f.status === "closed");
  const canApprove = Boolean(audit) && allClosed && !audit?.approval?.approved_by;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="w-[min(95vw,1080px)] max-h-[88vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ClipboardCheck className="w-5 h-5 text-[#1677ff]" /> QA 审计
          </DialogTitle>
          <DialogDescription className="text-[#64748b]">
            SUP.1 质量保证：审计计划 → 不符合项登记 → 确认/解决/关闭 → 管理批准（全部关闭后才可关闭审计）。
          </DialogDescription>
        </DialogHeader>

        <div
          className="grid min-h-0 gap-3 overflow-hidden md:grid-cols-[320px_1fr]"
          data-testid="qa-dialog"
        >
          {/* ── 左：新建审计 + 列表 ────────────────────────────────── */}
          <div className="flex min-h-0 flex-col gap-2">
            <section className="rounded-md border border-[#1e293b] bg-[#0b1020] p-2.5">
              <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold text-[#94a3b8]">
                <Plus className="w-3 h-3" /> 新建审计
              </div>
              <div className="space-y-1.5">
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="审计标题（必填）"
                  data-testid="qa-audit-title"
                  className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                />
                <Input
                  value={auditor}
                  onChange={(e) => setAuditor(e.target.value)}
                  placeholder="审计员（默认 local）"
                  data-testid="qa-auditor"
                  className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                />
                <Input
                  value={scope}
                  onChange={(e) => setScope(e.target.value)}
                  placeholder="审计范围（可选）"
                  data-testid="qa-scope"
                  className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                />
                <Button
                  size="sm"
                  onClick={create}
                  disabled={!projectId || working}
                  data-testid="qa-create"
                  className="h-8 w-full bg-[#1677ff] text-white hover:bg-[#1677ff]/90"
                >
                  {working ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "创建审计"}
                </Button>
              </div>
            </section>

            <div className="flex items-center justify-between px-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                审计记录（{audits.length}）
              </span>
              <button
                type="button"
                onClick={load}
                disabled={!projectId || loading}
                title="刷新"
                data-testid="qa-reload"
                className="text-[#64748b] hover:text-white disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5" />
                )}
              </button>
            </div>

            <div
              className="min-h-0 flex-1 space-y-1 overflow-y-auto scrollbar-dark pr-1"
              data-testid="qa-list"
            >
              {!loading && audits.length === 0 && (
                <div
                  className="rounded-md border border-[#1e293b] px-3 py-6 text-center text-[11px] text-[#64748b]"
                  data-testid="qa-empty"
                >
                  还没有 QA 审计记录。
                </div>
              )}
              {audits.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => {
                    setSelectedId(a.id);
                    setFindingNote("");
                    setApprover("");
                    setError("");
                    setNotice("");
                  }}
                  data-testid={`qa-row-${a.id}`}
                  className={`w-full rounded-md border px-2 py-1.5 text-left transition-colors ${
                    a.id === selectedId
                      ? "border-[#1677ff]/50 bg-[#1677ff]/10"
                      : "border-[#1e293b] hover:bg-[#111827]"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[11px] text-[#e2e8f0]">{a.title}</span>
                    <span className="ml-auto shrink-0"><StatusBadge status={a.status} /></span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[10px] text-[#475569]">
                    <span className="font-mono">{a.id}</span>
                    <span>
                      不符合项 {a.finding_count}（未关闭 {a.open_findings}）
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* ── 右：统计 + 详情 + 不符合项 ─────────────────────────── */}
          <div className="min-h-0 space-y-2 overflow-y-auto scrollbar-dark pr-1">
            <div className="grid grid-cols-4 gap-2" data-testid="qa-stats">
              <Stat label="审计数" value={stats.total} />
              <Stat label="未关闭审计" value={stats.openAudits} />
              <Stat label="不符合项" value={stats.findings} />
              <Stat label="未关闭项" value={stats.openFindings} warn={stats.openFindings > 0} />
            </div>

            {error && (
              <div
                className="rounded-md border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 text-xs text-[#f87171]"
                data-testid="qa-error"
              >
                {error}
              </div>
            )}
            {notice && (
              <div
                className="rounded-md border border-[#10b981]/30 bg-[#10b981]/10 px-3 py-2 text-xs text-[#34d399]"
                data-testid="qa-notice"
              >
                {notice}
              </div>
            )}

            {!audit && !detailLoading && (
              <div className="rounded-md border border-[#1e293b] px-3 py-10 text-center text-xs text-[#64748b]">
                选择左侧的审计记录查看详情。
              </div>
            )}
            {detailLoading && !audit && (
              <div className="flex items-center gap-2 px-3 py-6 text-xs text-[#64748b]">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> 加载审计详情…
              </div>
            )}

            {audit && (
              <div className="space-y-2" data-testid="qa-detail">
                <section className="rounded-md border border-[#1e293b] p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-[#e2e8f0]">{audit.id}</span>
                    <StatusBadge status={audit.status} />
                    <span className="text-[11px] text-[#64748b]">
                      {fmtTime(audit.date)}
                    </span>
                  </div>
                  <div className="mt-1 text-sm font-semibold text-[#e2e8f0]">{audit.title}</div>
                  <div className="mt-2 grid gap-1 text-[10px] text-[#64748b] sm:grid-cols-2">
                    <div>审计员：{audit.auditor || "local"}（{audit.auditor_role || "qa_engineer"}）</div>
                    <div>范围：{audit.scope || "—"}</div>
                    <div>创建：{fmtTime(audit.created_at)}</div>
                    <div>更新：{fmtTime(audit.updated_at)}</div>
                  </div>

                  {audit.approval?.approved_by ? (
                    <div className="mt-2 rounded border border-[#10b981]/30 bg-[#10b981]/10 px-2 py-1.5 text-[11px] text-[#34d399]">
                      已由 {audit.approval.approved_by}（{audit.approval.role || "qa_lead"}）批准于{" "}
                      {fmtTime(audit.approval.approved_at)}
                      {audit.approval.note ? ` · ${audit.approval.note}` : ""}
                    </div>
                  ) : (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <Input
                        value={approver}
                        onChange={(e) => setApprover(e.target.value)}
                        placeholder="批准人（qa lead）"
                        data-testid="qa-approver"
                        className="h-8 max-w-[200px] border-[#1e293b] bg-[#111827] text-xs"
                      />
                      <Button
                        size="sm"
                        onClick={approve}
                        disabled={!canApprove || working}
                        data-testid="qa-approve"
                        title={
                          canApprove
                            ? "记录管理批准并关闭审计"
                            : "所有不符合项关闭后才能批准关闭"
                        }
                        className="h-8 bg-[#10b981] text-white hover:bg-[#10b981]/90 disabled:opacity-40"
                      >
                        <UserCheck className="w-3.5 h-3.5 mr-1" />批准关闭
                      </Button>
                      {!allClosed && (
                        <span className="text-[10px] text-[#f59e0b]">
                          <AlertTriangle className="mr-1 inline w-3 h-3" />
                          仍有未关闭的不符合项
                        </span>
                      )}
                    </div>
                  )}

                  <div className="mt-2 flex justify-end">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={exportReport}
                      disabled={working || audits.length === 0}
                      data-testid="qa-export"
                      className="h-7 border-[#1e293b] text-[11px] text-[#94a3b8] hover:text-white"
                    >
                      <FileText className="w-3 h-3 mr-1" />导出 QA 报告
                    </Button>
                  </div>
                </section>

                <section className="rounded-md border border-[#1e293b] p-3">
                  <div className="mb-2 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                    <Plus className="w-3.5 h-3.5" /> 登记不符合项
                  </div>
                  <div className="space-y-1.5">
                    <Input
                      value={findingDesc}
                      onChange={(e) => setFindingDesc(e.target.value)}
                      placeholder="不符合项描述（必填）"
                      data-testid="qa-finding-desc"
                      className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                    />
                    <div className="flex flex-wrap gap-1.5">
                      <select
                        value={findingSeverity}
                        onChange={(e) => setFindingSeverity(e.target.value as QaSeverity)}
                        data-testid="qa-finding-severity"
                        className="h-8 flex-1 rounded-md border border-[#1e293b] bg-[#111827] px-2 text-xs text-[#e2e8f0]"
                      >
                        {SEVERITIES.map((s) => (
                          <option key={s} value={s}>{`严重度：${SEVERITY_META[s].label}`}</option>
                        ))}
                      </select>
                      <Input
                        value={findingAssignee}
                        onChange={(e) => setFindingAssignee(e.target.value)}
                        placeholder="责任人"
                        data-testid="qa-finding-assignee"
                        className="h-8 w-[120px] border-[#1e293b] bg-[#111827] text-xs"
                      />
                      <Button
                        size="sm"
                        onClick={addFinding}
                        disabled={working}
                        data-testid="qa-add-finding"
                        className="h-8 bg-[#1677ff] text-white hover:bg-[#1677ff]/90"
                      >
                        登记
                      </Button>
                    </div>
                  </div>
                </section>

                <section className="rounded-md border border-[#1e293b] p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                      不符合项（{findings.length}）
                    </span>
                    <Input
                      value={findingNote}
                      onChange={(e) => setFindingNote(e.target.value)}
                      placeholder="处理说明（解决/关闭时归档）"
                      data-testid="qa-finding-note"
                      className="h-7 max-w-[240px] border-[#1e293b] bg-[#111827] text-[11px]"
                    />
                  </div>

                  {findings.length === 0 ? (
                    <div className="rounded border border-[#1e293b] px-3 py-5 text-center text-[11px] text-[#64748b]">
                      暂无不符合项。空审计不构成质量证据，仍需管理批准后才能关闭。
                    </div>
                  ) : (
                    <div className="space-y-1.5" data-testid="qa-findings">
                      {findings.map((f) => (
                        <div
                          key={f.id}
                          data-testid={`qa-finding-${f.id}`}
                          className="rounded border border-[#1e293b] px-2 py-1.5"
                        >
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span
                              className={`rounded border px-1.5 py-0.5 text-[10px] ${
                                SEVERITY_META[f.severity]?.cls ?? SEVERITY_META.medium.cls
                              }`}
                            >
                              {SEVERITY_META[f.severity]?.label ?? f.severity}
                            </span>
                            <FindingStatusBadge status={f.status} />
                            <span className="font-mono text-[10px] text-[#64748b]">{f.id}</span>
                            <span className="ml-auto text-[10px] text-[#475569]">
                              责任人 {f.assigned_to || "unassigned"}
                            </span>
                          </div>
                          <div className="mt-1 text-[11px] text-[#e2e8f0]">{f.description}</div>
                          {(f.resolution || f.verifier) && (
                            <div className="mt-0.5 text-[10px] text-[#64748b]">
                              {f.resolution ? `处理：${f.resolution}` : ""}
                              {f.verifier ? ` · 验证：${f.verifier}` : ""}
                            </div>
                          )}
                          {FINDING_TRANSITIONS[f.status]?.length > 0 && (
                            <div className="mt-1.5 flex flex-wrap gap-1">
                              {FINDING_TRANSITIONS[f.status].map((target) => (
                                <Button
                                  key={target}
                                  size="sm"
                                  variant="outline"
                                  onClick={() => moveFinding(f, target)}
                                  disabled={working}
                                  data-testid={`qa-finding-${f.id}-to-${target}`}
                                  className="h-6 px-2 text-[10px] border-[#1e293b] text-[#94a3b8] hover:text-white"
                                >
                                  {target === "closed" ? (
                                    <CheckCircle2 className="w-3 h-3 mr-1" />
                                  ) : (
                                    <ArrowRight className="w-3 h-3 mr-1" />
                                  )}
                                  {TRANSITION_LABEL[target]}
                                </Button>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Stat({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div className="rounded-md border border-[#1e293b] bg-[#0b1020] px-2 py-1.5">
      <div className="text-[10px] text-[#64748b]">{label}</div>
      <div
        className={`text-sm font-semibold tabular-nums ${
          warn ? "text-[#f87171]" : "text-[#e2e8f0]"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
