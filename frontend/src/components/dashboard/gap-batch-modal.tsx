"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Layers,
  Link2,
  Loader2,
  Play,
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
  batchRunGap,
  getGapBatchStatus,
  getGapDetail,
  type GapBatchStatus,
  type GapDetailResponse,
} from "@/lib/api";
import { startExponentialPoll, type PollHandle } from "@/lib/poll";

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
  queued: { label: "排队中", color: "#64748b" },
  running: { label: "执行中", color: "#722ed1" },
};

export function GapBatchModal({
  open,
  mode,
  gapIds,
  onClose,
  onComplete,
}: {
  open: boolean;
  mode: "analyze" | "remediate";
  gapIds: string[];
  onClose: () => void;
  onComplete?: () => void;
}) {
  const [details, setDetails] = useState<GapDetailResponse[]>([]);
  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [analyzeError, setAnalyzeError] = useState("");

  const [batch, setBatch] = useState<GapBatchStatus | null>(null);
  const [batchError, setBatchError] = useState("");

  const pollRef = useRef<PollHandle | null>(null);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  const idsKey = gapIds.join(",");

  // 把裸后端错误翻成可读中文（后端 *兜底* 文案太裸，对运营用户意义不大）。
  const humanizeError = (e: unknown, fallback: string) => {
    const raw = e instanceof Error ? e.message : String(e);
    if (/Unknown dashboard sub-path or method/i.test(raw)) {
      return "后端服务版本过旧，未识别此接口；请刷新页面或在终端重启 yuleosh 服务（批量修复需要 dashboard.py ≥ v4.0.7）。";
    }
    if (/Batch not found/i.test(raw)) {
      return "批量任务不存在或已结束；可关闭弹窗重新触发。";
    }
    if (/Non-JSON response/i.test(raw)) {
      return "服务未响应（可能被回收）；请刷新页面或重启服务后重试。";
    }
    return raw || fallback;
  };

  // ── Analyze mode: fetch all selected gap details in parallel ────────
  useEffect(() => {
    if (!open) {
      setDetails([]);
      setAnalyzeLoading(false);
      setAnalyzeError("");
      return;
    }
    if (mode !== "analyze") return;
    if (!gapIds.length) return;
    setAnalyzeLoading(true);
    setAnalyzeError("");
    Promise.all(gapIds.map((id) => getGapDetail(id)))
      .then((ds) => setDetails(ds))
      .catch((e) =>
        setAnalyzeError(humanizeError(e, "批量分析失败"))
      )
      .finally(() => setAnalyzeLoading(false));
  }, [open, mode, idsKey]);

  // ── Remediate mode: start batch + poll progress ─────────────────────
  useEffect(() => {
    if (!open || mode !== "remediate") return;
    if (!gapIds.length) return;
    let cancelled = false;
    setBatchError("");
    setBatch(null);

    const stopPoll = () => {
      pollRef.current?.stop();
      pollRef.current = null;
    };

    batchRunGap(gapIds)
      .then((r) => {
        if (cancelled) return;
        const bid = r.batch_id;
        pollRef.current = startExponentialPoll(
          async () => {
            if (cancelled) return true;
            const s = await getGapBatchStatus(bid);
            if (cancelled) return true;
            setBatch(s);
            if (s.status === "completed") {
              onCompleteRef.current?.();
              return true;
            }
            return false;
          },
          { onError: (e) => setBatchError(humanizeError(e, "轮询批量进度失败")) },
        );
      })
      .catch((e) => {
        if (!cancelled)
          setBatchError(humanizeError(e, "批量修复启动失败"));
      });

    return () => {
      cancelled = true;
      stopPoll();
    };
  }, [open, mode, idsKey]);

  if (!open) return null;

  const isRemediate = mode === "remediate";
  const totalPct =
    batch && batch.total ? Math.round((batch.done / batch.total) * 100) : 0;

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
              <CardTitle className="text-base font-bold text-[#e2e8f0] flex items-center gap-2">
                {isRemediate ? (
                  <Play className="w-4 h-4 text-[#10b981] shrink-0" />
                ) : (
                  <Layers className="w-4 h-4 text-[#722ed1] shrink-0" />
                )}
                <span>{isRemediate ? "批量修复" : "批量分析"}</span>
                <span className="text-[11px] font-normal text-[#64748b]">
                  {gapIds.length} 项差距
                </span>
              </CardTitle>
              <p className="text-[11px] text-[#64748b] mt-1">
                {isRemediate
                  ? "已自动依次触发修复，完成后列表状态会同步更新"
                  : "已自动汇总所选差距项的分析结论与修复步骤"}
              </p>
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

        <CardContent className="flex-1 overflow-y-auto py-4 px-5 space-y-3">
          {isRemediate ? (
            <>
              {/* Overall progress */}
              <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 p-3">
                <div className="flex items-center justify-between text-[11px] mb-2">
                  <span className="flex items-center gap-1.5 text-[#cbd5e1]">
                    {batch?.status === "completed" ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#10b981]" />
                    ) : (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-[#722ed1]" />
                    )}
                    {batch?.status === "completed"
                      ? "全部执行完成"
                      : `执行中（${batch?.done ?? 0}/${batch?.total ?? gapIds.length}）`}
                  </span>
                  <span className="text-[#64748b] font-mono">{totalPct}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${totalPct}%`,
                      background:
                        batch?.status === "completed"
                          ? "#10b981"
                          : "linear-gradient(90deg, #10b981, #1677ff)",
                    }}
                  />
                </div>
                {batchError && (
                  <div className="text-xs text-[#ff4d4f] flex items-center gap-1 mt-2">
                    <AlertCircle className="w-3.5 h-3.5" />
                    {batchError}
                  </div>
                )}
              </div>

              {/* Per-item progress */}
              {batch?.items.map((it) => {
                const meta = STATUS_META[it.status] || STATUS_META.open;
                return (
                  <div
                    key={it.gap_id}
                    className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-mono text-[#94a3b8]">
                        {it.gap_id}
                      </span>
                      <span
                        className="text-[10px] px-1.5 rounded"
                        style={{ color: meta.color, background: `${meta.color}14` }}
                      >
                        {meta.label}
                      </span>
                    </div>
                    <div className="h-1 rounded-full bg-[#1e293b] overflow-hidden mt-1.5">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${it.progress_pct}%`,
                          background:
                            it.status === "failed"
                              ? "#ff4d4f"
                              : it.status === "completed"
                                ? "#10b981"
                                : "linear-gradient(90deg, #10b981, #1677ff)",
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </>
          ) : (
            <>
              {analyzeLoading ? (
                <div className="flex items-center justify-center py-12 text-[#64748b]">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  正在分析 {gapIds.length} 项差距…
                </div>
              ) : analyzeError ? (
                <div className="text-xs text-[#ff4d4f] flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5" />
                  {analyzeError}
                </div>
              ) : details.length === 0 ? (
                <div className="text-center py-12 text-[#64748b] text-sm">
                  暂无数据
                </div>
              ) : (
                details.map((d) => {
                  const item = d.item;
                  const sev = item
                    ? SEVERITY_META[item.severity] || SEVERITY_META.minor
                    : null;
                  return (
                    <div
                      key={item?.id}
                      className="rounded-lg border border-[#1e293b] bg-[#0a0e17]/60 px-3 py-2.5 space-y-2"
                    >
                      <div className="flex items-center gap-2 flex-wrap">
                        <span
                          className="text-[11px] font-mono px-1.5 py-0.5 rounded-md"
                          style={{ color: sev?.color, background: sev?.bg }}
                        >
                          {item?.id}
                        </span>
                        <span className="text-[11px] font-mono text-[#94a3b8]">
                          {item?.swe_area}
                        </span>
                        {sev && (
                          <span
                            className="text-[10px] px-1.5 py-0.5 rounded-md"
                            style={{ color: sev.color, background: sev.bg }}
                          >
                            {sev.label}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-[#cbd5e1] leading-relaxed">
                        {item?.description}
                      </div>
                      {item?.suggestion && (
                        <div className="text-[11px] text-[#94a3b8]">
                          <span className="text-[#64748b]">建议：</span>
                          {item.suggestion}
                        </div>
                      )}
                      {d.fix_steps.length > 0 && (
                        <ol className="space-y-1">
                          {d.fix_steps.map((step, i) => (
                            <li
                              key={i}
                              className="flex items-start gap-2 text-[11px] text-[#cbd5e1]"
                            >
                              <span className="text-[#10b981] font-mono shrink-0">
                                {String(i + 1).padStart(2, "0")}
                              </span>
                              <span className="leading-relaxed">{step}</span>
                            </li>
                          ))}
                        </ol>
                      )}
                      {d.related_requirements.length > 0 && (
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <Link2 className="w-3 h-3 text-[#64748b]" />
                          {d.related_requirements
                            .slice(0, 4)
                            .map((r) => (
                              <span
                                key={r.req_id}
                                className="text-[10px] font-mono text-[#722ed1]"
                              >
                                {r.req_id}
                              </span>
                            ))}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
