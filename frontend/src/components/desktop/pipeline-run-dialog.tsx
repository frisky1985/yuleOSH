"use client";

import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api-fetch";
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clock,
  Loader2,
  RotateCw,
  XCircle,
} from "lucide-react";

export interface PipelineStage {
  key: string;
  name?: string;
  status: string;
}

export interface PipelineRunDetail {
  job_id: string;
  status: string;
  progress?: number;
  current_stage?: string | null;
  stages?: PipelineStage[];
  logs?: string[];
  logs_total?: number;
  started_at?: string | null;
  completed_at?: string | null;
  result?: { error?: string; summary?: string } | null;
  source?: string;
}

interface PipelineRunDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
  jobId: string | null;
  running?: boolean;
  onRerun?: () => void;
}

const STATUS_META: Record<string, { label: string; className: string }> = {
  passed: { label: "已通过", className: "bg-[#10b981]/15 text-[#34d399] border-[#10b981]/30" },
  failed: { label: "失败", className: "bg-[#ef4444]/15 text-[#f87171] border-[#ef4444]/30" },
  running: { label: "运行中", className: "bg-[#f59e0b]/15 text-[#fbbf24] border-[#f59e0b]/30" },
  queued: { label: "排队中", className: "bg-[#64748b]/15 text-[#94a3b8] border-[#64748b]/30" },
};

function isActiveStatus(status?: string): boolean {
  return status === "queued" || status === "running";
}

function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", { hour12: false });
}

function duration(detail: PipelineRunDetail): string {
  if (!detail.started_at) return "—";
  const start = new Date(detail.started_at).getTime();
  const end = detail.completed_at ? new Date(detail.completed_at).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "—";
  const sec = Math.round((end - start) / 1000);
  if (sec < 60) return `${sec} 秒`;
  return `${Math.floor(sec / 60)} 分 ${sec % 60} 秒`;
}

function StageIcon({ status }: { status: string }) {
  if (status === "passed") return <CheckCircle2 className="w-4 h-4 text-[#10b981] shrink-0" />;
  if (status === "failed") return <XCircle className="w-4 h-4 text-[#ef4444] shrink-0" />;
  if (status === "running") return <Loader2 className="w-4 h-4 text-[#f59e0b] animate-spin shrink-0" />;
  if (status === "skipped") return <Circle className="w-4 h-4 text-[#475569] shrink-0" />;
  return <Clock className="w-4 h-4 text-[#475569] shrink-0" />;
}

/** 单次流水线运行详情：步骤状态、实时日志、失败原因与重跑入口。 */
export function PipelineRunDialog({
  open,
  onOpenChange,
  projectId,
  jobId,
  running,
  onRerun,
}: PipelineRunDialogProps) {
  const [detail, setDetail] = useState<PipelineRunDetail | null>(null);
  const [error, setError] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open || !projectId || !jobId) return;
    let alive = true;
    let timer: number | undefined;

    const load = async () => {
      try {
        const data = await apiFetch<PipelineRunDetail>(
          `/api/v1/desktop/projects/${projectId}/pipeline/status/${jobId}`,
        );
        if (!alive) return;
        setDetail(data);
        setError("");
        if (isActiveStatus(data.status)) timer = window.setTimeout(load, 1500);
      } catch (e) {
        if (!alive) return;
        setError((e as Error).message || "加载运行详情失败");
      }
    };

    load();
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [open, projectId, jobId]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [detail?.logs?.length]);

  const logs = detail?.logs ?? [];
  const statusMeta = STATUS_META[detail?.status ?? ""] ?? {
    label: detail?.status ?? "未知",
    className: "bg-[#64748b]/15 text-[#94a3b8] border-[#64748b]/30",
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="max-h-[86vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            流水线运行详情
            <span className={`rounded-full border px-2 py-0.5 text-[11px] font-normal ${statusMeta.className}`}>
              {statusMeta.label}
            </span>
          </DialogTitle>
          <DialogDescription className="font-mono text-xs">
            {jobId ?? "—"}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="rounded-md border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 text-xs text-[#f87171]">
            {error}
          </div>
        )}

        {!detail && !error && (
          <div className="flex items-center justify-center gap-2 py-10 text-xs text-[#64748b]">
            <Loader2 className="w-4 h-4 animate-spin" /> 正在加载运行详情…
          </div>
        )}

        {detail && (
          <div className="flex min-h-0 flex-col gap-4 overflow-y-auto pr-1">
            {/* 概要 */}
            <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              <div>
                <div className="text-[#64748b]">开始时间</div>
                <div className="text-[#e2e8f0]">{formatTime(detail.started_at)}</div>
              </div>
              <div>
                <div className="text-[#64748b]">结束时间</div>
                <div className="text-[#e2e8f0]">{formatTime(detail.completed_at)}</div>
              </div>
              <div>
                <div className="text-[#64748b]">耗时</div>
                <div className="text-[#e2e8f0]">{duration(detail)}</div>
              </div>
              <div>
                <div className="text-[#64748b]">进度</div>
                <div className="text-[#e2e8f0]">{Math.round(detail.progress ?? 0)}%</div>
              </div>
            </div>

            <div className="h-1.5 overflow-hidden rounded-full bg-[#1e293b]">
              <div
                className={`h-full rounded-full transition-all ${
                  detail.status === "failed" ? "bg-[#ef4444]" : "bg-[#10b981]"
                }`}
                style={{ width: `${Math.min(100, Math.max(0, detail.progress ?? 0))}%` }}
              />
            </div>

            {/* 步骤 */}
            {detail.stages && detail.stages.length > 0 && (
              <div>
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                  执行步骤
                </div>
                <ul className="space-y-1.5">
                  {detail.stages.map((stage) => (
                    <li key={stage.key} className="flex items-center gap-2 text-xs">
                      <StageIcon status={stage.status} />
                      <span className={stage.status === "pending" ? "text-[#64748b]" : "text-[#cbd5e1]"}>
                        {stage.name || stage.key}
                      </span>
                      <span className="ml-auto text-[10px] text-[#64748b]">{stage.status}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 结果 / 失败原因 */}
            {detail.result?.error && (
              <div className="flex items-start gap-2 rounded-md border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 text-xs text-[#f87171]">
                <AlertTriangle className="mt-0.5 w-4 h-4 shrink-0" />
                <span className="whitespace-pre-wrap break-words">{detail.result.error}</span>
              </div>
            )}
            {!detail.result?.error && detail.result?.summary && (
              <div className="rounded-md border border-[#10b981]/30 bg-[#10b981]/10 px-3 py-2 text-xs text-[#34d399]">
                {detail.result.summary}
              </div>
            )}

            {/* 日志 */}
            <div>
              <div className="mb-2 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                <span>运行日志</span>
                <span className="font-normal normal-case tracking-normal">
                  {detail.logs_total ?? logs.length} 条
                  {isActiveStatus(detail.status) ? " · 实时刷新中" : ""}
                </span>
              </div>
              <div
                ref={logRef}
                data-testid="pipeline-run-logs"
                className="max-h-64 overflow-y-auto rounded-md border border-[#1e293b] bg-[#0b1020] p-3 font-mono text-[11px] leading-relaxed text-[#94a3b8]"
              >
                {logs.length === 0 ? (
                  <div className="text-[#475569]">暂无日志（该记录可能来自历史快照）。</div>
                ) : (
                  logs.map((line, i) => (
                    <div key={i} className="whitespace-pre-wrap break-words">
                      {line}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        <DialogFooter>
          {onRerun && (
            <Button
              size="sm"
              variant="outline"
              onClick={onRerun}
              disabled={running || !projectId || isActiveStatus(detail?.status)}
              className="border-[#1e293b] text-[#94a3b8]"
            >
              <RotateCw className="mr-1 w-3.5 h-3.5" /> 重新运行
            </Button>
          )}
          <Button
            size="sm"
            onClick={() => onOpenChange(false)}
            className="bg-gradient-to-r from-[#10b981] to-[#059669] text-white"
          >
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
