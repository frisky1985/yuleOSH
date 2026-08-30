"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Clock,
  FileText,
  Link2,
  ListChecks,
  Loader2,
  Play,
  Target,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  getGapDetail,
  getGapRunStatus,
  runGap,
  type GapDetailResponse,
  type GapRunStatus,
} from "@/lib/api";

const SEVERITY_META: Record<
  string,
  { label: string; color: string; bg: string }
> = {
  critical: { label: "Critical", color: "#ff4d4f", bg: "#ff4d4f14" },
  major: { label: "Major", color: "#faad14", bg: "#faad1414" },
  minor: { label: "Minor", color: "#10b981", bg: "#10b98114" },
};

const STATUS_META: Record<string, { label: string; color: string }> = {
  open: { label: "未处理", color: "#ff4d4f" },
  in_progress: { label: "修复中", color: "#faad14" },
  completed: { label: "已完成", color: "#10b981" },
  failed: { label: "失败", color: "#ff4d4f" },
};

export function GapDetailModal({
  open,
  gapId,
  onClose,
  onRunComplete,
}: {
  open: boolean;
  gapId: string | null;
  onClose: () => void;
  onRunComplete?: () => void;
}) {
  const [detail, setDetail] = useState<GapDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");

  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<GapRunStatus | null>(null);
  const [runError, setRunError] = useState("");

  // ── Load detail whenever gapId changes ────────────────────────────────
  useEffect(() => {
    if (!open || !gapId) {
      // Reset state when closed
      setDetail(null);
      setRunId(null);
      setRunStatus(null);
      setDetailError("");
      setRunError("");
      return;
    }
    setDetailLoading(true);
    setDetailError("");
    setRunId(null);
    setRunStatus(null);
    setRunError("");
    getGapDetail(gapId)
      .then((d) => setDetail(d))
      .catch((e) => setDetailError(typeof e === "string" ? e : e?.message || "加载失败"))
      .finally(() => setDetailLoading(false));
  }, [open, gapId]);

  // ── Poll run status while running ────────────────────────────────────
  useEffect(() => {
    if (!runId || !gapId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const s = await getGapRunStatus(gapId, runId);
        if (cancelled) return;
        setRunStatus(s);
        if (s.status === "completed") {
          onRunComplete?.();
        }
      } catch (e) {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : typeof e === "string" ? e : "轮询失败";
        setRunError(msg);
      }
    };
    void poll();
    const t = setInterval(poll, 700);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [runId, gapId, onRunComplete]);

  const handleRun = useCallback(async () => {
    if (!gapId) return;
    setRunError("");
    try {
      const r = await runGap(gapId);
      setRunId(r.run_id);
      setRunStatus({
        run_id: r.run_id,
        gap_id: r.gap_id,
        status: r.status,
        progress_pct: 0,
        started_at: new Date().toISOString(),
        finished_at: null,
        log: [],
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : typeof e === "string" ? e : "运行失败";
      setRunError(msg);
    }
  }, [gapId]);

  if (!open) return null;

  const item = detail?.item;
  const sev = item ? SEVERITY_META[item.severity] || SEVERITY_META.minor : null;
  const status = item ? STATUS_META[item.status] || STATUS_META.open : null;
  const isRunning = runStatus?.status === "running" || runStatus?.status === "queued";
  const isCompleted = runStatus?.status === "completed";
  const isFailed = runStatus?.status === "failed";
  const progress = runStatus?.progress_pct ?? 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <Card
        className="w-full max-w-2xl max-h-[88vh] flex flex-col border-[#1e293b] bg-[#111827] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <CardHeader className="pb-3 border-b border-[#1e293b]">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <CardTitle className="text-base font-bold text-[#e2e8f0] flex items-center gap-2 flex-wrap">
                <Target className="w-4 h-4 text-[#faad14] shrink-0" />
                <span>差距分析详情</span>
                {item && (
                  <span
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded-md"
                    style={{ color: sev?.color, background: sev?.bg }}
                  >
                    {item.id}
                  </span>
                )}
                {item && (
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded-md font-medium"
                    style={{ color: sev?.color, background: sev?.bg }}
                  >
                    {sev?.label}
                  </span>
                )}
                {item && status && (
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded-md"
                    style={{ color: status.color, background: `${status.color}14` }}
                  >
                    {status.label}
                  </span>
                )}
              </CardTitle>
              {detail && (
                <p className="text-[11px] text-[#64748b] mt-1">
                  {item?.swe_area}
                  {detail.swe_label ? ` · ${detail.swe_label}` : ""}
                </p>
              )}
            </div>
            <button
              onClick={onClose}
              className="text-[#64748b] hover:text-white text-lg leading-none"
              aria-label="关闭"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </CardHeader>

        <CardContent className="flex-1 overflow-y-auto py-4 px-5 space-y-4">
          {detailLoading ? (
            <div className="flex items-center justify-center py-12 text-[#64748b]">
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              加载详情中…
            </div>
          ) : detailError ? (
            <div className="text-xs text-[#ff4d4f] flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" />
              {detailError}
            </div>
          ) : !detail || !item ? (
            <div className="text-center py-12 text-[#64748b] text-sm">暂无数据</div>
          ) : (
            <>
              {/* Description */}
              <div>
                <div className="text-[11px] text-[#64748b] mb-1.5 flex items-center gap-1">
                  <FileText className="w-3 h-3" />
                  差距描述
                </div>
                <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 px-3 py-2 text-xs text-[#cbd5e1] leading-relaxed">
                  {item.description}
                </div>
                {item.suggestion && (
                  <div className="mt-2 text-[11px] text-[#94a3b8]">
                    <span className="text-[#64748b]">建议：</span>
                    {item.suggestion}
                  </div>
                )}
              </div>

              {/* Fix steps */}
              <div>
                <div className="text-[11px] text-[#64748b] mb-1.5 flex items-center gap-1">
                  <ListChecks className="w-3 h-3" />
                  推荐修复步骤（按过程域）
                </div>
                <ol className="space-y-1.5">
                  {detail.fix_steps.map((step, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 text-xs text-[#cbd5e1] rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 px-3 py-2"
                    >
                      <span className="text-[#10b981] font-mono shrink-0">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className="leading-relaxed">{step}</span>
                    </li>
                  ))}
                </ol>
              </div>

              {/* Related requirements */}
              {detail.related_requirements.length > 0 && (
                <div>
                  <div className="text-[11px] text-[#64748b] mb-1.5 flex items-center gap-1">
                    <Link2 className="w-3 h-3" />
                    关联需求条目
                    <span className="text-[#475569]">
                      {detail.related_requirements.length} 条
                    </span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                    {detail.related_requirements.map((r) => (
                      <div
                        key={r.req_id}
                        className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 px-2.5 py-1.5 text-[11px] flex items-center gap-2"
                      >
                        <span className="text-[#722ed1] font-mono shrink-0">
                          {r.req_id}
                        </span>
                        <span className="text-[#64748b] truncate font-mono">
                          {r.source}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Run section */}
              <div>
                <div className="text-[11px] text-[#64748b] mb-1.5 flex items-center gap-1">
                  <Play className="w-3 h-3" />
                  修复执行
                </div>
                <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 p-3">
                  {!runId && !runStatus && (
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-[#94a3b8]">
                        点击运行触发相关制品的重跑（设计扫描 / 代码 / 测试 / 证据补齐）
                      </span>
                      <Button
                        onClick={handleRun}
                        disabled={isRunning}
                        size="sm"
                        className="bg-gradient-to-r from-[#10b981] to-[#1677ff] text-white h-8 text-xs gap-1.5 shadow-lg shadow-[#10b981]/20"
                      >
                        <Play className="w-3.5 h-3.5" />
                        运行
                      </Button>
                    </div>
                  )}

                  {runError && (
                    <div className="text-xs text-[#ff4d4f] flex items-center gap-1">
                      <AlertCircle className="w-3.5 h-3.5" />
                      {runError}
                    </div>
                  )}

                  {runStatus && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="flex items-center gap-1.5 text-[#cbd5e1]">
                          {isRunning && <Loader2 className="w-3.5 h-3.5 animate-spin text-[#722ed1]" />}
                          {isCompleted && <CheckCircle2 className="w-3.5 h-3.5 text-[#10b981]" />}
                          {isFailed && <AlertCircle className="w-3.5 h-3.5 text-[#ff4d4f]" />}
                          {isRunning && "正在执行…"}
                          {isCompleted && "执行完成"}
                          {isFailed && "执行失败"}
                        </span>
                        <span className="text-[#64748b] font-mono">
                          {progress}%
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${progress}%`,
                            background: isFailed
                              ? "#ff4d4f"
                              : isCompleted
                              ? "#10b981"
                              : "linear-gradient(90deg, #10b981, #1677ff)",
                          }}
                        />
                      </div>
                      {runStatus.log.length > 0 && (
                        <div className="mt-2 max-h-32 overflow-y-auto rounded border border-[#1e293b] bg-black/30 px-2 py-1.5 font-mono text-[10px] text-[#94a3b8] space-y-0.5">
                          {runStatus.log.map((line, i) => (
                            <div key={i} className="leading-relaxed">
                              {line}
                            </div>
                          ))}
                        </div>
                      )}
                      {isCompleted && (
                        <div className="text-[10px] text-[#64748b] flex items-center gap-1 mt-1">
                          <ChevronRight className="w-3 h-3" />
                          关闭此弹窗后，列表中该差距项状态会显示为「已完成」
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Run history */}
              {detail.run_history.length > 0 && (
                <div>
                  <div className="text-[11px] text-[#64748b] mb-1.5 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    历史执行
                    <span className="text-[#475569]">
                      {detail.run_history.length} 次
                    </span>
                  </div>
                  <div className="space-y-1">
                    {detail.run_history.map((r) => (
                      <div
                        key={r.run_id}
                        className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 px-2.5 py-1.5 text-[11px] flex items-center gap-2"
                      >
                        <span className="text-[#94a3b8] font-mono">{r.run_id}</span>
                        <span
                          className="text-[10px] px-1.5 rounded"
                          style={{
                            color:
                              r.status === "completed"
                                ? "#10b981"
                                : r.status === "failed"
                                ? "#ff4d4f"
                                : "#faad14",
                          }}
                        >
                          {r.status}
                        </span>
                        <span className="text-[#64748b] font-mono ml-auto">
                          {r.started_at?.slice(0, 19).replace("T", " ")}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {detail.note && (
                <div className="rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-3 py-2 text-[11px] text-[#faad14]">
                  {detail.note}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
