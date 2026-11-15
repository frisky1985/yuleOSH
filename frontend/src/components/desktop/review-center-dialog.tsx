"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckSquare,
  FileText,
  Filter,
  Loader2,
  RefreshCw,
  Tags,
  Trash2,
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

export type ReviewStatus = "approved" | "rejected" | "needs_revision";
export type ReviewRowStatus = ReviewStatus | "unreviewed";
export type BulkScope = "selected" | "section" | "glob";

export interface ReviewArtifactRow {
  artifact: string;
  section: string;
  status: ReviewRowStatus;
  review_id: string | null;
  comment: string;
  author: string;
  reviewed_at: string | null;
}

export interface ReviewCounts {
  total_files: number;
  approved: number;
  rejected: number;
  needs_revision: number;
  unreviewed: number;
}

export interface ReviewSectionStat {
  section: string;
  total: number;
  approved: number;
  rejected: number;
  needs_revision: number;
  unreviewed: number;
}

interface ReviewCenterDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
}

// ─── Metadata ─────────────────────────────────────────────────────────────

const STATUS_META: Record<ReviewRowStatus, { label: string; cls: string }> = {
  approved: {
    label: "通过",
    cls: "border-[#10b981]/40 bg-[#10b981]/10 text-[#34d399]",
  },
  rejected: {
    label: "退回",
    cls: "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#f87171]",
  },
  needs_revision: {
    label: "需修改",
    cls: "border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fbbf24]",
  },
  unreviewed: {
    label: "未评审",
    cls: "border-[#334155] bg-[#1e293b]/60 text-[#94a3b8]",
  },
};

const BULK_STATUSES: ReviewStatus[] = ["approved", "rejected", "needs_revision"];

const EMPTY_COUNTS: ReviewCounts = {
  total_files: 0,
  approved: 0,
  rejected: 0,
  needs_revision: 0,
  unreviewed: 0,
};

function StatusBadge({ status }: { status: ReviewRowStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.unreviewed;
  return (
    <span className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

function shortTime(iso: string | null): string {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 16);
}

// ─── Dialog ───────────────────────────────────────────────────────────────

/** 桌面端评审中心：跨产物评审列表、按分区/glob 批量打标、导出评审报告。 */
export function ReviewCenterDialog({ open, onOpenChange, projectId }: ReviewCenterDialogProps) {
  const [rows, setRows] = useState<ReviewArtifactRow[]>([]);
  const [counts, setCounts] = useState<ReviewCounts>(EMPTY_COUNTS);
  const [sections, setSections] = useState<ReviewSectionStat[]>([]);
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [statusFilter, setStatusFilter] = useState<"all" | ReviewRowStatus>("all");
  const [sectionFilter, setSectionFilter] = useState("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const [bulkScope, setBulkScope] = useState<BulkScope>("section");
  const [bulkSection, setBulkSection] = useState("");
  const [pattern, setPattern] = useState("code/**/*.c");
  const [bulkStatus, setBulkStatus] = useState<ReviewStatus>("approved");
  const [bulkComment, setBulkComment] = useState("");

  const [reportPath, setReportPath] = useState("");
  const [reportPreview, setReportPreview] = useState("");

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{
        artifacts: ReviewArtifactRow[];
        counts: ReviewCounts;
        sections: ReviewSectionStat[];
      }>(`/api/v1/desktop/projects/${projectId}/review`);
      const list = data.artifacts || [];
      setRows(list);
      setCounts(data.counts ?? EMPTY_COUNTS);
      setSections(data.sections || []);
      setSelected((cur) => {
        const next = new Set<string>();
        for (const p of cur) if (list.some((r) => r.artifact === p)) next.add(p);
        return next;
      });
    } catch (e) {
      setError((e as Error).message || "加载评审列表失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    setStatusFilter("all");
    setSectionFilter("all");
    setSelected(new Set());
    setBulkScope("section");
    setBulkSection("");
    setPattern("code/**/*.c");
    setBulkStatus("approved");
    setBulkComment("");
    setReportPath("");
    setReportPreview("");
    setError("");
    setNotice("");
    load();
  }, [open, projectId, load]);

  // 默认分区跟随列表首项，让「按分区」一开始就是可用状态
  useEffect(() => {
    if (!bulkSection && sections.length) setBulkSection(sections[0].section);
  }, [sections, bulkSection]);

  const visibleRows = useMemo(
    () =>
      rows.filter(
        (r) =>
          (statusFilter === "all" || r.status === statusFilter) &&
          (sectionFilter === "all" || r.section === sectionFilter),
      ),
    [rows, statusFilter, sectionFilter],
  );

  const reviewed = counts.approved + counts.rejected + counts.needs_revision;
  const coveragePct = counts.total_files
    ? Math.round((reviewed / counts.total_files) * 100)
    : 0;

  const toggleRow = (artifact: string) => {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(artifact)) next.delete(artifact);
      else next.add(artifact);
      return next;
    });
  };

  const toggleAllVisible = () => {
    setSelected((cur) => {
      const allSelected =
        visibleRows.length > 0 && visibleRows.every((r) => cur.has(r.artifact));
      const next = new Set(cur);
      for (const r of visibleRows) {
        if (allSelected) next.delete(r.artifact);
        else next.add(r.artifact);
      }
      return next;
    });
  };

  const applyBulk = async () => {
    if (!projectId) return;
    setError("");
    setNotice("");
    const body: Record<string, unknown> = {
      status: bulkStatus,
      comment: bulkComment.trim(),
    };
    if (bulkScope === "selected") {
      if (!selected.size) {
        setError("请先在列表中选择要打标的产物");
        return;
      }
      body.scope = "artifact";
      body.artifacts = Array.from(selected);
    } else if (bulkScope === "section") {
      if (!bulkSection) {
        setError("请选择要批量打标的分区");
        return;
      }
      body.scope = "section";
      body.section = bulkSection;
    } else {
      if (!pattern.trim()) {
        setError("请输入 glob 表达式，例如 code/**/*.c");
        return;
      }
      body.scope = "glob";
      body.pattern = pattern.trim();
    }

    setWorking(true);
    try {
      const res = await apiFetch<{ matched: number; created: number; updated: number }>(
        `/api/v1/desktop/projects/${projectId}/review/bulk`,
        { method: "POST", body: JSON.stringify(body) },
      );
      if (!res.matched) {
        setNotice("没有匹配到产物，未做任何修改");
      } else {
        setNotice(
          `已打标「${STATUS_META[bulkStatus].label}」：匹配 ${res.matched} 个文件，新增 ${res.created} 条，更新 ${res.updated} 条`,
        );
      }
      setSelected(new Set());
      await load();
    } catch (e) {
      setError((e as Error).message || "批量打标失败");
    } finally {
      setWorking(false);
    }
  };

  const deleteReview = async (row: ReviewArtifactRow) => {
    if (!projectId || !row.review_id) return;
    setError("");
    setNotice("");
    setWorking(true);
    try {
      await apiFetch(`/api/v1/desktop/projects/${projectId}/review/${row.review_id}`, {
        method: "DELETE",
      });
      setNotice(`已清除 \`${row.artifact}\` 的评审记录`);
      await load();
    } catch (e) {
      setError((e as Error).message || "删除评审记录失败");
    } finally {
      setWorking(false);
    }
  };

  const exportReport = async () => {
    if (!projectId) return;
    setError("");
    setNotice("");
    setWorking(true);
    try {
      const res = await apiFetch<{
        path: string;
        content: string;
        reviewed_files: number;
        total_files: number;
      }>(`/api/v1/desktop/projects/${projectId}/review/export`);
      setReportPath(res.path);
      setReportPreview(res.content || "");
      setNotice(
        `已导出评审报告：${res.path}（覆盖 ${res.reviewed_files}/${res.total_files} 个产物）`,
      );
    } catch (e) {
      setError((e as Error).message || "导出评审报告失败");
    } finally {
      setWorking(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="w-[min(95vw,1120px)] max-h-[88vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Tags className="w-5 h-5 text-[#1677ff]" /> 评审中心
          </DialogTitle>
          <DialogDescription className="text-[#64748b]">
            跨产物评审列表（含未评审文件）、按分区或 glob 批量打标、导出评审报告到 evidence。
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-1.5" data-testid="review-toolbar">
          <span className="text-[11px] text-[#64748b]">
            覆盖 {reviewed}/{counts.total_files}（{coveragePct}%）
          </span>
          <button
            type="button"
            onClick={load}
            disabled={!projectId || loading}
            title="刷新"
            data-testid="review-reload"
            className="ml-auto text-[#64748b] hover:text-white disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
          </button>
          <Button
            size="sm"
            variant="outline"
            onClick={exportReport}
            disabled={working || !projectId}
            data-testid="review-export"
            className="h-7 border-[#1e293b] text-[11px] text-[#94a3b8] hover:text-white"
          >
            <FileText className="w-3 h-3 mr-1" />导出评审报告
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-2 md:grid-cols-4" data-testid="review-stats">
          {[
            ["产物", counts.total_files, "text-[#e2e8f0]"],
            ["已通过", counts.approved, "text-[#34d399]"],
            ["需处理", counts.rejected + counts.needs_revision, "text-[#f87171]"],
            ["未评审", counts.unreviewed, "text-[#fbbf24]"],
          ].map(([label, value, cls]) => (
            <div
              key={label as string}
              className="rounded-md border border-[#1e293b] bg-[#0b1020] px-2.5 py-1.5"
            >
              <div className="text-[10px] text-[#64748b]">{label}</div>
              <div className={`text-base font-semibold ${cls}`}>{value}</div>
            </div>
          ))}
        </div>

        {error && (
          <div
            className="rounded-md border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 text-xs text-[#f87171]"
            data-testid="review-error"
          >
            {error}
          </div>
        )}
        {notice && (
          <div
            className="rounded-md border border-[#10b981]/30 bg-[#10b981]/10 px-3 py-2 text-xs text-[#34d399]"
            data-testid="review-notice"
          >
            {notice}
          </div>
        )}

        {/* 批量打标 */}
        <section className="rounded-md border border-[#1e293b] bg-[#0b1020] p-2.5" data-testid="review-bulk">
          <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold text-[#94a3b8]">
            <Tags className="w-3 h-3" /> 批量打标
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {(
              [
                ["selected", `已选 ${selected.size}`],
                ["section", "按分区"],
                ["glob", "按 glob"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setBulkScope(key)}
                data-testid={`review-scope-${key}`}
                className={`rounded-md border px-2 py-0.5 text-[11px] ${
                  bulkScope === key
                    ? "border-[#1677ff]/50 bg-[#1677ff]/15 text-[#93c5fd]"
                    : "border-[#1e293b] text-[#94a3b8] hover:text-white"
                }`}
              >
                {label}
              </button>
            ))}
            {bulkScope === "section" && (
              <select
                value={bulkSection}
                onChange={(e) => setBulkSection(e.target.value)}
                data-testid="review-section-select"
                className="h-7 rounded-md border border-[#1e293b] bg-[#111827] px-1 text-[11px] text-[#e2e8f0]"
              >
                {sections.map((s) => (
                  <option key={s.section} value={s.section}>
                    {`${s.section}（${s.total}）`}
                  </option>
                ))}
              </select>
            )}
            {bulkScope === "glob" && (
              <Input
                value={pattern}
                onChange={(e) => setPattern(e.target.value)}
                placeholder="code/**/*.c"
                data-testid="review-pattern"
                className="h-7 w-52 border-[#1e293b] bg-[#111827] font-mono text-[11px]"
              />
            )}
            <select
              value={bulkStatus}
              onChange={(e) => setBulkStatus(e.target.value as ReviewStatus)}
              data-testid="review-bulk-status"
              className="h-7 rounded-md border border-[#1e293b] bg-[#111827] px-1 text-[11px] text-[#e2e8f0]"
            >
              {BULK_STATUSES.map((s) => (
                <option key={s} value={s}>{STATUS_META[s].label}</option>
              ))}
            </select>
            <Input
              value={bulkComment}
              onChange={(e) => setBulkComment(e.target.value)}
              placeholder="批注（可选）"
              data-testid="review-bulk-comment"
              className="h-7 w-48 border-[#1e293b] bg-[#111827] text-[11px]"
            />
            <Button
              size="sm"
              onClick={applyBulk}
              disabled={working || !projectId}
              data-testid="review-bulk-apply"
              className="h-7 bg-[#1677ff] text-[11px] text-white hover:bg-[#0958d9]"
            >
              {working ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <CheckSquare className="w-3 h-3 mr-1" />}
              批量打标
            </Button>
          </div>
        </section>

        {/* 筛选 */}
        <div className="flex flex-wrap items-center gap-1.5" data-testid="review-filters">
          <Filter className="w-3 h-3 text-[#64748b]" />
          {(
            [
              ["all", `全部 ${rows.length}`],
              ["approved", `通过 ${counts.approved}`],
              ["needs_revision", `需修改 ${counts.needs_revision}`],
              ["rejected", `退回 ${counts.rejected}`],
              ["unreviewed", `未评审 ${counts.unreviewed}`],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setStatusFilter(key)}
              data-testid={`review-filter-${key}`}
              className={`rounded-md border px-2 py-0.5 text-[11px] ${
                statusFilter === key
                  ? "border-[#1677ff]/50 bg-[#1677ff]/15 text-[#93c5fd]"
                  : "border-[#1e293b] text-[#94a3b8] hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
          <select
            value={sectionFilter}
            onChange={(e) => setSectionFilter(e.target.value)}
            data-testid="review-filter-section"
            className="ml-auto h-7 rounded-md border border-[#1e293b] bg-[#111827] px-1 text-[11px] text-[#e2e8f0]"
          >
            <option value="all">全部分区</option>
            {sections.map((s) => (
              <option key={s.section} value={s.section}>{s.section}</option>
            ))}
          </select>
        </div>

        {/* 跨产物列表 */}
        <div className="min-h-0 flex-1 overflow-auto rounded-md border border-[#1e293b]" data-testid="review-table">
          <table className="w-full border-collapse text-[11px]">
            <thead className="sticky top-0 bg-[#111827] text-[#64748b]">
              <tr>
                <th className="w-8 px-2 py-1.5">
                  <input
                    type="checkbox"
                    aria-label="全选当前筛选结果"
                    checked={visibleRows.length > 0 && visibleRows.every((r) => selected.has(r.artifact))}
                    onChange={toggleAllVisible}
                    data-testid="review-select-all"
                  />
                </th>
                <th className="px-2 py-1.5 text-left font-medium">产物</th>
                <th className="w-24 px-2 py-1.5 text-left font-medium">分区</th>
                <th className="w-20 px-2 py-1.5 text-left font-medium">状态</th>
                <th className="w-32 px-2 py-1.5 text-left font-medium">评审人 / 时间</th>
                <th className="w-10 px-2 py-1.5" />
              </tr>
            </thead>
            <tbody>
              {visibleRows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-[#64748b]" data-testid="review-empty">
                    {loading ? "加载中…" : "没有符合条件的产物"}
                  </td>
                </tr>
              )}
              {visibleRows.map((row) => (
                <tr
                  key={row.artifact}
                  className="border-t border-[#1e293b]/70 hover:bg-[#111827]/60"
                  data-testid={`review-row-${row.artifact}`}
                >
                  <td className="px-2 py-1">
                    <input
                      type="checkbox"
                      aria-label={`选择 ${row.artifact}`}
                      checked={selected.has(row.artifact)}
                      onChange={() => toggleRow(row.artifact)}
                      data-testid={`review-check-${row.artifact}`}
                    />
                  </td>
                  <td className="px-2 py-1">
                    <div className="font-mono text-[#e2e8f0]">{row.artifact}</div>
                    {row.comment && (
                      <div className="truncate text-[10px] text-[#64748b]" title={row.comment}>
                        {row.comment}
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-1 text-[#94a3b8]">{row.section}</td>
                  <td className="px-2 py-1"><StatusBadge status={row.status} /></td>
                  <td className="px-2 py-1 text-[10px] text-[#94a3b8]">
                    {row.status === "unreviewed" ? "—" : `${row.author || "local"} · ${shortTime(row.reviewed_at)}`}
                  </td>
                  <td className="px-2 py-1">
                    {row.review_id && (
                      <button
                        type="button"
                        onClick={() => deleteReview(row)}
                        disabled={working}
                        title="清除评审记录"
                        data-testid={`review-delete-${row.artifact}`}
                        className="text-[#64748b] hover:text-[#f87171] disabled:opacity-50"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {reportPreview && (
          <div className="rounded-md border border-[#1e293b] bg-[#0b1020]" data-testid="review-report">
            <div className="border-b border-[#1e293b] px-2.5 py-1.5 text-[11px] text-[#94a3b8]">
              报告预览：<span className="font-mono text-[#93c5fd]">{reportPath}</span>
            </div>
            <pre
              className="scrollbar-dark max-h-40 overflow-auto whitespace-pre-wrap px-2.5 py-2 text-[10px] text-[#94a3b8]"
              data-testid="review-report-preview"
            >
              {reportPreview}
            </pre>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
