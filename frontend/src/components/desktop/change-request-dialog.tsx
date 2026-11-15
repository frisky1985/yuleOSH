"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  GitPullRequest,
  Loader2,
  Plus,
  RefreshCw,
  ShieldAlert,
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

export type CrStatus = "draft" | "analyzed" | "approved" | "rejected" | "closed";

export interface CrHistoryEntry {
  from: string | null;
  to: string;
  author: string;
  comment: string;
  at: string;
}

export interface CrRequirementImpact {
  id: string;
  code: string[];
  tests: string[];
  design: string[];
}

export interface CrImpact {
  change_request: string;
  generated_at: string;
  author: string;
  requirements: CrRequirementImpact[];
  affected_artifacts: string[];
  summary: {
    requirements: number;
    code_files: number;
    test_files: number;
    design_files: number;
  };
}

export interface ChangeRequest {
  id: string;
  title: string;
  reason: string;
  author: string;
  affected_requirements: string[];
  affected_artifacts: string[];
  status: CrStatus;
  impact: CrImpact | null;
  history: CrHistoryEntry[];
  created_at: string;
  updated_at: string;
}

interface ChangeRequestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────

const STATUS_META: Record<CrStatus, { label: string; cls: string }> = {
  draft: { label: "草稿", cls: "border-[#64748b]/40 bg-[#64748b]/10 text-[#94a3b8]" },
  analyzed: { label: "已分析", cls: "border-[#1677ff]/40 bg-[#1677ff]/10 text-[#60a5fa]" },
  approved: { label: "已批准", cls: "border-[#10b981]/40 bg-[#10b981]/10 text-[#34d399]" },
  rejected: { label: "已驳回", cls: "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#f87171]" },
  closed: { label: "已关闭", cls: "border-[#475569]/40 bg-[#475569]/10 text-[#64748b]" },
};

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

function StatusBadge({ status }: { status: CrStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.draft;
  return (
    <span
      data-testid={`cr-status-${status}`}
      className={`rounded-full border px-2 py-0.5 text-[10px] ${meta.cls}`}
    >
      {meta.label}
    </span>
  );
}

function parseList(value: string): string[] {
  return value
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

// ─── Dialog ───────────────────────────────────────────────────────────────

/** 桌面端变更请求：列表、状态流转、影响分析结果展示。 */
export function ChangeRequestDialog({ open, onOpenChange, projectId }: ChangeRequestDialogProps) {
  const [items, setItems] = useState<ChangeRequest[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("");
  const [reqInput, setReqInput] = useState("");
  const [comment, setComment] = useState("");

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{ change_requests: ChangeRequest[] }>(
        `/api/v1/desktop/projects/${projectId}/change-requests`,
      );
      const list = data.change_requests || [];
      setItems(list);
      setSelectedId((cur) => (list.some((c) => c.id === cur) ? cur : list[0]?.id ?? null));
    } catch (e) {
      setError((e as Error).message || "加载变更请求失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    setItems([]);
    setSelectedId(null);
    setTitle("");
    setReason("");
    setReqInput("");
    setComment("");
    setError("");
    setNotice("");
    load();
  }, [open, projectId, load]);

  const selected = useMemo(
    () => items.find((c) => c.id === selectedId) ?? null,
    [items, selectedId],
  );

  const upsert = (cr: ChangeRequest) => {
    setItems((prev) => {
      const idx = prev.findIndex((c) => c.id === cr.id);
      if (idx === -1) return [cr, ...prev];
      const next = [...prev];
      next[idx] = cr;
      return next;
    });
    setSelectedId(cr.id);
  };

  const create = async () => {
    if (!projectId || working) return;
    const trimmed = title.trim();
    if (!trimmed) {
      setError("变更请求标题不能为空");
      return;
    }
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ change_request: ChangeRequest }>(
        `/api/v1/desktop/projects/${projectId}/change-requests`,
        {
          method: "POST",
          body: JSON.stringify({
            title: trimmed,
            reason: reason.trim(),
            requirements: parseList(reqInput),
          }),
        },
      );
      upsert(data.change_request);
      setTitle("");
      setReason("");
      setReqInput("");
      setNotice(`已创建 ${data.change_request.id}（草稿）`);
    } catch (e) {
      setError((e as Error).message || "创建变更请求失败");
    } finally {
      setWorking(false);
    }
  };

  const analyze = async () => {
    if (!projectId || !selected || working) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ impact: CrImpact; change_request: ChangeRequest }>(
        `/api/v1/desktop/projects/${projectId}/change-requests/${selected.id}/analyze`,
        { method: "POST", body: JSON.stringify({ comment: comment.trim() }) },
      );
      upsert(data.change_request);
      setComment("");
      setNotice(
        `影响分析完成：${data.impact.summary.requirements} 个需求、` +
          `${data.impact.summary.code_files} 个代码 / ${data.impact.summary.test_files} 个测试文件`,
      );
    } catch (e) {
      setError((e as Error).message || "影响分析失败");
    } finally {
      setWorking(false);
    }
  };

  const move = async (status: CrStatus) => {
    if (!projectId || !selected || working) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch<{ change_request: ChangeRequest }>(
        `/api/v1/desktop/projects/${projectId}/change-requests/${selected.id}/transition`,
        {
          method: "POST",
          body: JSON.stringify({ status, comment: comment.trim() }),
        },
      );
      upsert(data.change_request);
      setComment("");
      setNotice(`${selected.id} 状态已更新为${STATUS_META[status].label}`);
    } catch (e) {
      setError((e as Error).message || "状态流转失败");
    } finally {
      setWorking(false);
    }
  };

  const actions = selected ? renderActions(selected.status, working, analyze, move) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="w-[min(95vw,1080px)] max-h-[88vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitPullRequest className="w-5 h-5 text-[#1677ff]" /> 变更请求
          </DialogTitle>
          <DialogDescription className="text-[#64748b]">
            变更请求的创建、状态流转，以及受影响需求 / 设计 / 代码 / 测试的影响分析结果。
          </DialogDescription>
        </DialogHeader>

        <div
          className="grid min-h-0 gap-3 overflow-hidden md:grid-cols-[320px_1fr]"
          data-testid="change-request-dialog"
        >
          {/* ── 左：新建 + 列表 ─────────────────────────────────────── */}
          <div className="flex min-h-0 flex-col gap-2">
            <section className="rounded-md border border-[#1e293b] bg-[#0b1020] p-2.5">
              <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold text-[#94a3b8]">
                <Plus className="w-3 h-3" /> 新建变更请求
              </div>
              <div className="space-y-1.5">
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="标题（必填）"
                  data-testid="cr-title"
                  className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                />
                <Input
                  value={reqInput}
                  onChange={(e) => setReqInput(e.target.value)}
                  placeholder="受影响需求，如 REQ-001, REQ-002"
                  data-testid="cr-requirements"
                  className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                />
                <Input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="变更原因（可选）"
                  data-testid="cr-reason"
                  className="h-8 border-[#1e293b] bg-[#111827] text-xs"
                />
                <Button
                  size="sm"
                  onClick={create}
                  disabled={!projectId || working}
                  data-testid="cr-create"
                  className="h-8 w-full bg-[#1677ff] text-white hover:bg-[#1677ff]/90"
                >
                  {working ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "创建"}
                </Button>
              </div>
            </section>

            <div className="flex items-center justify-between px-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                列表（{items.length}）
              </span>
              <button
                type="button"
                onClick={load}
                disabled={!projectId || loading}
                title="刷新"
                data-testid="cr-reload"
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
              data-testid="cr-list"
            >
              {!loading && items.length === 0 && (
                <div
                  className="rounded-md border border-[#1e293b] px-3 py-6 text-center text-[11px] text-[#64748b]"
                  data-testid="cr-empty"
                >
                  还没有变更请求。
                </div>
              )}
              {items.map((cr) => (
                <button
                  key={cr.id}
                  type="button"
                  onClick={() => {
                    setSelectedId(cr.id);
                    setComment("");
                    setError("");
                    setNotice("");
                  }}
                  data-testid={`cr-row-${cr.id}`}
                  className={`w-full rounded-md border px-2 py-1.5 text-left transition-colors ${
                    cr.id === selectedId
                      ? "border-[#1677ff]/50 bg-[#1677ff]/10"
                      : "border-[#1e293b] hover:bg-[#111827]"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] text-[#e2e8f0]">{cr.id}</span>
                    <span className="ml-auto"><StatusBadge status={cr.status} /></span>
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-[#94a3b8]">{cr.title}</div>
                  <div className="mt-0.5 text-[10px] text-[#475569]">
                    {cr.affected_requirements.length} 个需求 · {fmtTime(cr.updated_at)}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* ── 右：详情 + 影响分析 ─────────────────────────────────── */}
          <div className="min-h-0 space-y-2 overflow-y-auto scrollbar-dark pr-1">
            {error && (
              <div
                className="rounded-md border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 text-xs text-[#f87171]"
                data-testid="cr-error"
              >
                {error}
              </div>
            )}
            {notice && (
              <div
                className="rounded-md border border-[#10b981]/30 bg-[#10b981]/10 px-3 py-2 text-xs text-[#34d399]"
                data-testid="cr-notice"
              >
                {notice}
              </div>
            )}

            {!selected && !loading && (
              <div className="rounded-md border border-[#1e293b] px-3 py-10 text-center text-xs text-[#64748b]">
                选择左侧的变更请求查看详情。
              </div>
            )}

            {selected && (
              <div className="space-y-2" data-testid="cr-detail">
                <section className="rounded-md border border-[#1e293b] p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-[#e2e8f0]">{selected.id}</span>
                    <StatusBadge status={selected.status} />
                    <span className="text-[11px] text-[#64748b]">
                      更新于 {fmtTime(selected.updated_at)}
                    </span>
                  </div>
                  <div className="mt-1 text-sm font-semibold text-[#e2e8f0]">{selected.title}</div>
                  {selected.reason && (
                    <div className="mt-1 text-[11px] leading-relaxed text-[#94a3b8]">
                      {selected.reason}
                    </div>
                  )}
                  {selected.affected_requirements.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {selected.affected_requirements.map((r) => (
                        <span
                          key={r}
                          className="rounded bg-[#1e293b] px-1.5 py-0.5 font-mono text-[10px] text-[#94a3b8]"
                        >
                          {r}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Input
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      placeholder="流转备注（可选）"
                      data-testid="cr-comment"
                      className="h-8 max-w-[220px] border-[#1e293b] bg-[#111827] text-xs"
                    />
                    {actions}
                  </div>
                </section>

                <section className="rounded-md border border-[#1e293b] p-3">
                  <div className="mb-2 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                    <ClipboardList className="w-3.5 h-3.5" /> 影响分析
                  </div>
                  {selected.impact ? (
                    <ImpactView impact={selected.impact} />
                  ) : (
                    <div className="text-[11px] text-[#475569]">
                      尚未执行影响分析。草稿状态下点「执行影响分析」即可扫描受影响的需求、设计、代码与测试。
                    </div>
                  )}
                </section>

                <section className="rounded-md border border-[#1e293b] p-3">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                    流转历史
                  </div>
                  <div className="space-y-1.5" data-testid="cr-history">
                    {selected.history.map((h, i) => (
                      <div key={`${h.at}-${i}`} className="flex items-start gap-2 text-[11px]">
                        <ArrowRight className="mt-0.5 w-3 h-3 shrink-0 text-[#475569]" />
                        <div className="min-w-0">
                          <div className="text-[#94a3b8]">
                            {h.from ? `${STATUS_META[h.from as CrStatus]?.label ?? h.from} → ` : ""}
                            {STATUS_META[h.to as CrStatus]?.label ?? h.to}
                            <span className="ml-2 text-[#475569]">{h.author}</span>
                            <span className="ml-2 text-[#475569]">{fmtTime(h.at)}</span>
                          </div>
                          {h.comment && (
                            <div className="truncate text-[#64748b]">{h.comment}</div>
                          )}
                        </div>
                      </div>
                    ))}
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

function renderActions(
  status: CrStatus,
  working: boolean,
  analyze: () => void,
  move: (s: CrStatus) => void,
) {
  const disabled = working;
  const spinner = working ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : null;
  switch (status) {
    case "draft":
      return (
        <Button
          size="sm"
          onClick={analyze}
          disabled={disabled}
          data-testid="cr-analyze"
          className="h-8 bg-[#1677ff] text-white hover:bg-[#1677ff]/90"
        >
          {spinner}执行影响分析
        </Button>
      );
    case "analyzed":
      return (
        <>
          <Button
            size="sm"
            onClick={() => move("approved")}
            disabled={disabled}
            data-testid="cr-approve"
            className="h-8 bg-[#10b981] text-white hover:bg-[#10b981]/90"
          >
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" />批准
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => move("rejected")}
            disabled={disabled}
            data-testid="cr-reject"
            className="h-8 border-[#ef4444]/40 text-[#f87171] hover:bg-[#ef4444]/10"
          >
            <XCircle className="w-3.5 h-3.5 mr-1" />驳回
          </Button>
        </>
      );
    case "approved":
      return (
        <Button
          size="sm"
          variant="outline"
          onClick={() => move("closed")}
          disabled={disabled}
          data-testid="cr-close"
          className="h-8 border-[#1e293b] text-[#94a3b8] hover:text-white"
        >
          <ShieldAlert className="w-3.5 h-3.5 mr-1" />关闭
        </Button>
      );
    case "rejected":
      return (
        <Button
          size="sm"
          variant="outline"
          onClick={() => move("draft")}
          disabled={disabled}
          data-testid="cr-reopen"
          className="h-8 border-[#1e293b] text-[#94a3b8] hover:text-white"
        >
          <AlertTriangle className="w-3.5 h-3.5 mr-1" />重新打开
        </Button>
      );
    default:
      return null;
  }
}

function ImpactView({ impact }: { impact: CrImpact }) {
  return (
    <div className="space-y-2" data-testid="cr-impact">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="cr-impact-summary">
        <ImpactStat label="受影响需求" value={impact.summary.requirements} />
        <ImpactStat label="设计文件" value={impact.summary.design_files} />
        <ImpactStat label="代码文件" value={impact.summary.code_files} />
        <ImpactStat label="测试文件" value={impact.summary.test_files} />
      </div>

      {impact.requirements.length === 0 ? (
        <div className="text-[11px] text-[#fbbf24]">
          未定位到受影响需求。请先填写需求编号，或在受影响文件中加入 @req 注解。
        </div>
      ) : (
        <div className="space-y-1">
          {impact.requirements.map((r) => (
            <div key={r.id} className="rounded border border-[#1e293b] px-2 py-1.5">
              <div className="font-mono text-[11px] text-[#e2e8f0]">{r.id}</div>
              <div className="mt-0.5 space-y-0.5 text-[10px]">
                <FileLine label="设计" files={r.design} />
                <FileLine label="代码" files={r.code} />
                <FileLine label="测试" files={r.tests} />
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="text-[10px] text-[#475569]">
        生成于 {fmtTime(impact.generated_at)} · 证据：
        {`.osh/evidence/impact-analysis-${impact.change_request}.json`}
      </div>
    </div>
  );
}

function FileLine({ label, files }: { label: string; files: string[] }) {
  return (
    <div className="flex gap-2">
      <span className="w-8 shrink-0 text-[#64748b]">{label}</span>
      <span className="font-mono text-[#94a3b8]">{files.length ? files.join("、") : "—"}</span>
    </div>
  );
}

function ImpactStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-[#1e293b] bg-[#0b1020] px-2 py-1.5">
      <div className="text-[10px] text-[#64748b]">{label}</div>
      <div className="text-sm font-semibold tabular-nums text-[#e2e8f0]">{value}</div>
    </div>
  );
}
