"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Bug,
  CheckCircle2,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
  XCircle,
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

export type IssueStatus = "open" | "analyzed" | "resolved" | "verified" | "closed" | "rejected";
export type IssueSeverity = "low" | "medium" | "high" | "critical";

export interface IssueRow {
  id: string;
  title: string;
  severity: IssueSeverity;
  status: IssueStatus;
  owner: string;
  created_at: string;
  closed_at: string | null;
}

export interface IssueDetail extends IssueRow {
  description: string;
  reported_by: string;
  verified_by: string;
  root_cause: string;
  resolution: string;
  verification: string;
  updated_at: string;
}

interface IssueTrackerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
}

// ─── Metadata ─────────────────────────────────────────────────────────────

const STATUS_META: Record<IssueStatus, { label: string; cls: string }> = {
  open: { label: "新建", cls: "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#f87171]" },
  analyzed: { label: "已分析", cls: "border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fbbf24]" },
  resolved: { label: "已修复", cls: "border-[#1677ff]/40 bg-[#1677ff]/10 text-[#60a5fa]" },
  verified: { label: "已验证", cls: "border-[#10b981]/40 bg-[#10b981]/10 text-[#34d399]" },
  closed: { label: "已关闭", cls: "border-[#475569]/40 bg-[#475569]/10 text-[#64748b]" },
  rejected: { label: "已拒绝", cls: "border-[#64748b]/40 bg-[#64748b]/10 text-[#94a3b8]" },
};

const SEVERITY_META: Record<IssueSeverity, { label: string; cls: string }> = {
  low: { label: "低", cls: "border-[#475569]/40 bg-[#475569]/10 text-[#94a3b8]" },
  medium: { label: "中", cls: "border-[#1677ff]/40 bg-[#1677ff]/10 text-[#60a5fa]" },
  high: { label: "高", cls: "border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fbbf24]" },
  critical: { label: "严重", cls: "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#f87171]" },
};

/** Mirrors the backend state machine (yuleosh.desktop.issues). */
export const ALLOWED_TRANSITIONS: Record<IssueStatus, IssueStatus[]> = {
  open: ["analyzed", "rejected"],
  analyzed: ["resolved", "rejected"],
  resolved: ["verified", "analyzed"],
  verified: ["closed"],
  closed: [],
  rejected: [],
};

const TRANSITION_META: Record<IssueStatus, { label: string; cls: string; icon: "ok" | "no" | "next" }> = {
  analyzed: {
    label: "开始分析",
    cls: "border-[#f59e0b]/40 text-[#fbbf24] hover:bg-[#f59e0b]/10",
    icon: "next",
  },
  resolved: {
    label: "提交修复",
    cls: "border-[#1677ff]/40 text-[#60a5fa] hover:bg-[#1677ff]/10",
    icon: "next",
  },
  verified: {
    label: "验证通过",
    cls: "border-[#10b981]/40 text-[#34d399] hover:bg-[#10b981]/10",
    icon: "ok",
  },
  closed: {
    label: "关闭",
    cls: "border-[#1e293b] text-[#94a3b8] hover:text-white",
    icon: "ok",
  },
  rejected: {
    label: "拒绝（不修复）",
    cls: "border-[#ef4444]/40 text-[#f87171] hover:bg-[#ef4444]/10",
    icon: "no",
  },
  open: { label: "", cls: "", icon: "next" },
};

/** Target status → payload field that the backend archives. */
const NOTE_FIELD: Partial<Record<IssueStatus, "root_cause" | "resolution" | "verification">> = {
  analyzed: "root_cause",
  resolved: "resolution",
  verified: "verification",
};

const NOTE_HINT: Partial<Record<IssueStatus, string>> = {
  analyzed: "根因分析（写入 root_cause）",
  resolved: "修复说明（写入 resolution）",
  verified: "验证结论（写入 verification）",
};

const SEVERITIES: IssueSeverity[] = ["critical", "high", "medium", "low"];
const STATUSES: IssueStatus[] = ["open", "analyzed", "resolved", "verified", "closed", "rejected"];

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

function StatusBadge({ status }: { status: IssueStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.open;
  return (
    <span
      data-testid={`issue-status-${status}`}
      className={`rounded-full border px-2 py-0.5 text-[10px] ${meta.cls}`}
    >
      {meta.label}
    </span>
  );
}

function SeverityBadge({ severity }: { severity: IssueSeverity }) {
  const meta = SEVERITY_META[severity] ?? SEVERITY_META.medium;
  return (
    <span
      data-testid={`issue-severity-badge-${severity}`}
      className={`rounded border px-1.5 py-0.5 text-[10px] ${meta.cls}`}
    >
      {meta.label}
    </span>
  );
}

// ─── Dialog ───────────────────────────────────────────────────────────────

/** 桌面端问题追踪（ASPICE SUP.9）：列表、筛选、状态流转与导出。 */
export function IssueTrackerDialog({ open, onOpenChange, projectId }: IssueTrackerDialogProps) {
  const [items, setItems] = useState<IssueRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<IssueDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState<IssueSeverity>("medium");
  const [owner, setOwner] = useState("");
  const [note, setNote] = useState("");

  const [severityFilter, setSeverityFilter] = useState<"all" | IssueSeverity>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | IssueStatus>("all");
  // Creation already returns the full issue — skip the redundant detail fetch.
  const skipDetailRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{ issues: IssueRow[] }>(
        `/api/v1/desktop/projects/${projectId}/issues`,
      );
      const list = data.issues || [];
      setItems(list);
      setSelectedId((cur) => (list.some((i) => i.id === cur) ? cur : list[0]?.id ?? null));
    } catch (e) {
      setError((e as Error).message || "加载问题列表失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    setItems([]);
    setSelectedId(null);
    setDetail(null);
    skipDetailRef.current = null;
    setTitle("");
    setDescription("");
    setSeverity("medium");
    setOwner("");
    setNote("");
    setSeverityFilter("all");
    setStatusFilter("all");
    setError("");
    setNotice("");
    load();
  }, [open, projectId, load]);

  // Detail carries the root-cause / resolution / verification fields, which the
  // list endpoint intentionally omits.
  useEffect(() => {
    if (!open || !projectId || !selectedId) {
      setDetail(null);
      return;
    }
    if (skipDetailRef.current === selectedId) {
      skipDetailRef.current = null;
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    apiFetch<{ issue: IssueDetail }>(
      `/api/v1/desktop/projects/${projectId}/issues/${selectedId}`,
    )
      .then((data) => {
        if (!cancelled) setDetail(data.issue);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message || "加载问题详情失败");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, projectId, selectedId]);

  const filtered = useMemo(
    () =>
      items.filter(
        (i) =>
          (severityFilter === "all" || i.severity === severityFilter) &&
          (statusFilter === "all" || i.status === statusFilter),
      ),
    [items, severityFilter, statusFilter],
  );

  const stats = useMemo(() => {
    const open = items.filter((i) =>
      ["open", "analyzed", "resolved"].includes(i.status),
    ).length;
    const done = items.filter((i) => i.status === "closed").length;
    const critical = items.filter(
      (i) => i.severity === "critical" && i.status !== "closed" && i.status !== "rejected",
    ).length;
    return { total: items.length, open, done, critical };
  }, [items]);

  const applyRow = (row: IssueRow) => {
    setItems((prev) => {
      const idx = prev.findIndex((i) => i.id === row.id);
      if (idx === -1) return [row, ...prev];
      const next = [...prev];
      next[idx] = { ...next[idx], ...row };
      return next;
    });
    setSelectedId(row.id);
  };

  const create = async () => {
    if (!projectId || working) return;
    const trimmed = title.trim();
    if (!trimmed) {
      setError("问题标题不能为空");
      return;
    }
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ issue: IssueDetail }>(
        `/api/v1/desktop/projects/${projectId}/issues`,
        {
          method: "POST",
          body: JSON.stringify({
            title: trimmed,
            description: description.trim(),
            severity,
            owner: owner.trim() || "unassigned",
          }),
        },
      );
      setItems((prev) => [data.issue, ...prev]);
      skipDetailRef.current = data.issue.id;
      setSelectedId(data.issue.id);
      setDetail(data.issue);
      setTitle("");
      setDescription("");
      setOwner("");
      setSeverity("medium");
      setNotice(`已创建 ${data.issue.id}（新建）`);
    } catch (e) {
      setError((e as Error).message || "创建问题失败");
    } finally {
      setWorking(false);
    }
  };

  const move = async (target: IssueStatus) => {
    if (!projectId || !selected || working) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const body: Record<string, string> = { status: target };
      const field = NOTE_FIELD[target];
      if (field && note.trim()) body[field] = note.trim();
      const data = await apiFetch<{ issue: IssueDetail }>(
        `/api/v1/desktop/projects/${projectId}/issues/${selected.id}/transition`,
        { method: "POST", body: JSON.stringify(body) },
      );
      applyRow(data.issue);
      setDetail(data.issue);
      setNote("");
      setNotice(`${selected.id} 状态已更新为${STATUS_META[target].label}`);
    } catch (e) {
      setError((e as Error).message || "状态流转失败");
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
        `/api/v1/desktop/projects/${projectId}/issues/export`,
      );
      setNotice(`已导出问题报告：${data.path}`);
    } catch (e) {
      setError((e as Error).message || "导出问题报告失败");
    } finally {
      setWorking(false);
    }
  };

  const selected = detail && detail.id === selectedId ? detail : null;
  const allowed = selected ? ALLOWED_TRANSITIONS[selected.status] ?? [] : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="w-[min(95vw,1080px)] max-h-[88vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bug className="w-5 h-5 text-[#ef4444]" /> 问题追踪
          </DialogTitle>
          <DialogDescription className="text-[#64748b]">
            SUP.9 问题解决闭环：登记 → 根因分析 → 修复 → 验证 → 关闭（关闭前必须已验证）。
          </DialogDescription>
        </DialogHeader>

        <div
          className="grid min-h-0 gap-3 overflow-hidden md:grid-cols-[320px_1fr]"
          data-testid="issue-dialog"
        >
          {/* ── 左：新建 + 筛选 + 列表 ─────────────────────────────── */}
          <div className="flex min-h-0 flex-col gap-2">
            <section className="rounded-md border border-[#1e293b] bg-[#0b1020] p-2.5">
              <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold text-[#94a3b8]">
                <Plus className="w-3 h-3" /> 新建问题
              </div>
              <div className="space-y-1.5">
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="标题（必填）"
                  data-testid="issue-title"
                  className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                />
                <Input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="问题描述（可选）"
                  data-testid="issue-description"
                  className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                />
                <div className="flex gap-1.5">
                  <select
                    value={severity}
                    onChange={(e) => setSeverity(e.target.value as IssueSeverity)}
                    data-testid="issue-severity"
                    className="h-8 flex-1 rounded-md border border-[#1e293b] bg-[#111827] px-2 text-xs text-[#e2e8f0]"
                  >
                    {SEVERITIES.map((s) => (
                      <option key={s} value={s}>{`严重度：${SEVERITY_META[s].label}`}</option>
                    ))}
                  </select>
                  <Input
                    value={owner}
                    onChange={(e) => setOwner(e.target.value)}
                    placeholder="责任人"
                    data-testid="issue-owner"
                    className="h-8 w-[110px] border-[#1e293b] bg-[#111827] text-xs"
                  />
                </div>
                <Button
                  size="sm"
                  onClick={create}
                  disabled={!projectId || working}
                  data-testid="issue-create"
                  className="h-8 w-full bg-[#1677ff] text-white hover:bg-[#1677ff]/90"
                >
                  {working ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "登记问题"}
                </Button>
              </div>
            </section>

            <div className="flex items-center gap-1.5" data-testid="issue-filters">
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value as "all" | IssueSeverity)}
                data-testid="issue-severity-filter"
                className="h-7 flex-1 rounded border border-[#1e293b] bg-[#111827] px-1 text-[11px] text-[#94a3b8]"
              >
                <option value="all">全部严重度</option>
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>{SEVERITY_META[s].label}</option>
                ))}
              </select>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as "all" | IssueStatus)}
                data-testid="issue-status-filter"
                className="h-7 flex-1 rounded border border-[#1e293b] bg-[#111827] px-1 text-[11px] text-[#94a3b8]"
              >
                <option value="all">全部状态</option>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>{STATUS_META[s].label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={load}
                disabled={!projectId || loading}
                title="刷新"
                data-testid="issue-reload"
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
              data-testid="issue-list"
            >
              {!loading && filtered.length === 0 && (
                <div
                  className="rounded-md border border-[#1e293b] px-3 py-6 text-center text-[11px] text-[#64748b]"
                  data-testid="issue-empty"
                >
                  {items.length === 0 ? "还没有问题记录。" : "当前筛选条件下没有问题。"}
                </div>
              )}
              {filtered.map((issue) => (
                <button
                  key={issue.id}
                  type="button"
                  onClick={() => {
                    setSelectedId(issue.id);
                    setNote("");
                    setError("");
                    setNotice("");
                  }}
                  data-testid={`issue-row-${issue.id}`}
                  className={`w-full rounded-md border px-2 py-1.5 text-left transition-colors ${
                    issue.id === selectedId
                      ? "border-[#1677ff]/50 bg-[#1677ff]/10"
                      : "border-[#1e293b] hover:bg-[#111827]"
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <SeverityBadge severity={issue.severity} />
                    <span className="ml-auto"><StatusBadge status={issue.status} /></span>
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-[#e2e8f0]">{issue.title}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-[10px] text-[#475569]">
                    <span className="font-mono">{issue.id}</span>
                    <span className="truncate">负责人 {issue.owner || "unassigned"}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* ── 右：统计 + 详情 + 流转 ─────────────────────────────── */}
          <div className="min-h-0 space-y-2 overflow-y-auto scrollbar-dark pr-1">
            <div className="grid grid-cols-4 gap-2" data-testid="issue-stats">
              <Stat label="总计" value={stats.total} />
              <Stat label="未关闭" value={stats.open} />
              <Stat label="已关闭" value={stats.done} />
              <Stat label="未关闭严重" value={stats.critical} warn={stats.critical > 0} />
            </div>

            {error && (
              <div
                className="rounded-md border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 text-xs text-[#f87171]"
                data-testid="issue-error"
              >
                {error}
              </div>
            )}
            {notice && (
              <div
                className="rounded-md border border-[#10b981]/30 bg-[#10b981]/10 px-3 py-2 text-xs text-[#34d399]"
                data-testid="issue-notice"
              >
                {notice}
              </div>
            )}

            {!selected && !detailLoading && (
              <div className="rounded-md border border-[#1e293b] px-3 py-10 text-center text-xs text-[#64748b]">
                选择左侧的问题查看详情。
              </div>
            )}
            {detailLoading && !selected && (
              <div className="flex items-center gap-2 px-3 py-6 text-xs text-[#64748b]">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> 加载详情…
              </div>
            )}

            {selected && (
              <div className="space-y-2" data-testid="issue-detail">
                <section className="rounded-md border border-[#1e293b] p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-[#e2e8f0]">{selected.id}</span>
                    <SeverityBadge severity={selected.severity} />
                    <StatusBadge status={selected.status} />
                    <span className="text-[11px] text-[#64748b]">
                      更新于 {fmtTime(selected.updated_at)}
                    </span>
                  </div>
                  <div className="mt-1 text-sm font-semibold text-[#e2e8f0]">{selected.title}</div>
                  {selected.description && (
                    <div className="mt-1 text-[11px] leading-relaxed text-[#94a3b8]">
                      {selected.description}
                    </div>
                  )}
                  <div className="mt-2 grid gap-1 text-[10px] text-[#64748b] sm:grid-cols-2">
                    <div>负责人：{selected.owner || "unassigned"}</div>
                    <div>报告人：{selected.reported_by || "—"}</div>
                    <div>创建：{fmtTime(selected.created_at)}</div>
                    <div>关闭：{fmtTime(selected.closed_at)}</div>
                  </div>

                  <div className="mt-3 space-y-1.5">
                    <Input
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder={NOTE_HINT[allowed[0]] || "流转说明（可选）"}
                      data-testid="issue-note"
                      className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                    />
                    <div className="flex flex-wrap items-center gap-1.5">
                      {allowed.length === 0 ? (
                        <span className="text-[11px] text-[#475569]">
                          {selected.status === "closed" ? "问题已关闭，流程结束。" : "问题已拒绝，流程结束。"}
                        </span>
                      ) : (
                        allowed.map((target) => (
                          <Button
                            key={target}
                            size="sm"
                            variant="outline"
                            onClick={() => move(target)}
                            disabled={working}
                            data-testid={`issue-move-${target}`}
                            className={`h-7 text-[11px] ${TRANSITION_META[target].cls}`}
                          >
                            {TRANSITION_META[target].icon === "ok" && (
                              <CheckCircle2 className="w-3 h-3 mr-1" />
                            )}
                            {TRANSITION_META[target].icon === "no" && (
                              <XCircle className="w-3 h-3 mr-1" />
                            )}
                            {TRANSITION_META[target].icon === "next" && (
                              <ArrowRight className="w-3 h-3 mr-1" />
                            )}
                            {TRANSITION_META[target].label}
                          </Button>
                        ))
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={exportReport}
                        disabled={working || items.length === 0}
                        data-testid="issue-export"
                        className="ml-auto h-7 border-[#1e293b] text-[11px] text-[#94a3b8] hover:text-white"
                      >
                        <FileText className="w-3 h-3 mr-1" />导出报告
                      </Button>
                    </div>
                  </div>
                </section>

                <section className="rounded-md border border-[#1e293b] p-3">
                  <div className="mb-2 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                    <ShieldCheck className="w-3.5 h-3.5" /> 分析与处置记录
                  </div>
                  <div className="space-y-2" data-testid="issue-analysis">
                    <Field label="根因分析" value={selected.root_cause} testId="issue-root-cause" />
                    <Field label="修复说明" value={selected.resolution} testId="issue-resolution" />
                    <Field
                      label="验证结论"
                      value={
                        selected.verification
                          ? `${selected.verification}${selected.verified_by ? `（${selected.verified_by}）` : ""}`
                          : ""
                      }
                      testId="issue-verification"
                    />
                  </div>
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

function Field({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <div className="text-[11px]" data-testid={testId}>
      <span className="text-[#64748b]">{label}：</span>
      <span className={value ? "text-[#e2e8f0]" : "text-[#475569]"}>
        {value || "未填写"}
      </span>
    </div>
  );
}
