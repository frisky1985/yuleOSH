"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  Gauge,
  Loader2,
  RefreshCw,
  XCircle,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api-fetch";

// ─── Types ────────────────────────────────────────────────────────────────

export type GateStatus =
  | "passed"
  | "failed"
  | "not-run"
  | "warning"
  | "stale"
  | "retry"
  | "skipped";

export interface GateMetric {
  label: string;
  value: string | number;
}

export interface GateCategory {
  key: string;
  name: string;
  status: GateStatus;
  detail: string;
  metrics: GateMetric[];
  threshold?: number | null;
  job_id?: string | null;
}

export interface RunGate {
  gate: string | null;
  name: string | null;
  status: GateStatus;
  advisory: boolean;
  step_total: number;
}

export interface LatestRunGateDetail {
  job_id: string | null;
  run_status: string | null;
  started_at: string | null;
  completed_at: string | null;
  source: "gate-summary" | "run-record" | "none";
  session: string | null;
  summary_timestamp: string | null;
  summary_path?: string;
  worst_gate_status: GateStatus | null;
  gates: RunGate[];
  not_run_gates: string[];
  stale_gates: string[];
}

export interface QualityGatesReport {
  overall: "green" | "unverified" | "red";
  worst_status: GateStatus;
  generated_at: string;
  categories: GateCategory[];
  latest_run: LatestRunGateDetail;
}

interface QualityGatesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────

/** Visual tone for a gate status — shared by the board and its tests. */
export function gateTone(status: GateStatus): {
  label: string;
  dot: string;
  text: string;
  chip: string;
} {
  switch (status) {
    case "passed":
      return {
        label: "通过",
        dot: "bg-[#10b981]",
        text: "text-[#34d399]",
        chip: "border-[#10b981]/30 bg-[#10b981]/10 text-[#34d399]",
      };
    case "failed":
      return {
        label: "未通过",
        dot: "bg-[#ef4444]",
        text: "text-[#f87171]",
        chip: "border-[#ef4444]/30 bg-[#ef4444]/10 text-[#f87171]",
      };
    case "stale":
      return {
        label: "证据过期",
        dot: "bg-[#f59e0b]",
        text: "text-[#fbbf24]",
        chip: "border-[#f59e0b]/30 bg-[#f59e0b]/10 text-[#fbbf24]",
      };
    case "warning":
      return {
        label: "告警",
        dot: "bg-[#f59e0b]",
        text: "text-[#fbbf24]",
        chip: "border-[#f59e0b]/30 bg-[#f59e0b]/10 text-[#fbbf24]",
      };
    case "retry":
      return {
        label: "待重试",
        dot: "bg-[#f59e0b]",
        text: "text-[#fbbf24]",
        chip: "border-[#f59e0b]/30 bg-[#f59e0b]/10 text-[#fbbf24]",
      };
    case "skipped":
      return {
        label: "不适用",
        dot: "bg-[#64748b]",
        text: "text-[#94a3b8]",
        chip: "border-[#334155] bg-[#1e293b]/50 text-[#94a3b8]",
      };
    default:
      return {
        label: "未执行",
        dot: "bg-[#475569]",
        text: "text-[#94a3b8]",
        chip: "border-[#334155] bg-[#1e293b]/50 text-[#94a3b8]",
      };
  }
}

const OVERALL_META: Record<
  QualityGatesReport["overall"],
  { title: string; hint: string; className: string; icon: typeof CheckCircle2 }
> = {
  green: {
    title: "门禁全部通过",
    hint: "四类门禁均已验证通过，可放行。",
    className: "border-[#10b981]/30 bg-[#10b981]/10 text-[#34d399]",
    icon: CheckCircle2,
  },
  unverified: {
    title: "存在未验证门禁",
    hint: "没有失败门禁，但仍有未执行 / 过期证据，不能当作通过。",
    className: "border-[#f59e0b]/30 bg-[#f59e0b]/10 text-[#fbbf24]",
    icon: AlertTriangle,
  },
  red: {
    title: "存在未通过门禁",
    hint: "至少一类门禁明确失败，应先修复再审阅。",
    className: "border-[#ef4444]/30 bg-[#ef4444]/10 text-[#f87171]",
    icon: XCircle,
  },
};

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

// ─── Dialog ───────────────────────────────────────────────────────────────

/** 桌面端质量门禁看板：追溯 / 评审 / CI / 测试四类门禁 + 最近一次运行的门禁明细。 */
export function QualityGatesDialog({ open, onOpenChange, projectId }: QualityGatesDialogProps) {
  const [report, setReport] = useState<QualityGatesReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!projectId) {
      setReport(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<QualityGatesReport>(
        `/api/v1/desktop/projects/${projectId}/quality-gates`,
      );
      setReport(data);
    } catch (e) {
      setError((e as Error).message || "加载质量门禁失败");
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const overall = report ? OVERALL_META[report.overall] : null;
  const OverallIcon = overall?.icon;
  const latest = report?.latest_run;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="w-[min(94vw,980px)] max-h-[88vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Gauge className="w-5 h-5 text-[#1677ff]" /> 质量门禁看板
          </DialogTitle>
          <DialogDescription className="text-[#64748b]">
            汇总追溯 / 评审 / CI / 测试四类门禁，并展示最近一次流水线的门禁通过情况。
          </DialogDescription>
        </DialogHeader>

        <div
          className="min-h-0 space-y-3 overflow-y-auto scrollbar-dark pr-1"
          data-testid="quality-gates-dialog"
        >
          {loading && !report && (
            <div className="flex items-center gap-2 py-8 text-xs text-[#64748b]">
              <Loader2 className="w-4 h-4 animate-spin" /> 正在汇总门禁结果…
            </div>
          )}

          {error && (
            <div
              className="flex items-center justify-between gap-2 rounded-md border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 text-xs text-[#f87171]"
              data-testid="quality-error"
            >
              <span>{error}</span>
              <button
                type="button"
                onClick={load}
                disabled={loading}
                data-testid="quality-reload"
                className="shrink-0 rounded border border-[#ef4444]/40 px-2 py-0.5 hover:bg-[#ef4444]/10 disabled:opacity-50"
              >
                重新加载
              </button>
            </div>
          )}

          {!projectId && (
            <div className="py-8 text-center text-xs text-[#64748b]">请选择一个工程</div>
          )}

          {report && overall && OverallIcon && (
            <>
              {/* ── 总体状态 ─────────────────────────────────────────── */}
              <section
                data-testid="quality-overall"
                className={`flex items-start gap-3 rounded-md border px-3 py-2.5 ${overall.className}`}
              >
                <OverallIcon className="mt-0.5 w-4 h-4 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                    {overall.title}
                    <span className="rounded border border-current/30 px-1.5 py-0.5 text-[10px] font-normal uppercase">
                      {report.overall}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[11px] opacity-80">{overall.hint}</div>
                  <div className="mt-1 text-[10px] text-[#64748b]">
                    最差状态：{gateTone(report.worst_status).label} · 生成于 {fmtTime(report.generated_at)}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={load}
                  disabled={loading}
                  title="刷新"
                  data-testid="quality-reload"
                  className="text-[#94a3b8] hover:text-white disabled:opacity-50"
                >
                  {loading ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="w-3.5 h-3.5" />
                  )}
                </button>
              </section>

              {/* ── 四类门禁 ─────────────────────────────────────────── */}
              <section className="grid gap-2 sm:grid-cols-2">
                {report.categories.map((cat) => {
                  const tone = gateTone(cat.status);
                  return (
                    <div
                      key={cat.key}
                      data-testid={`quality-category-${cat.key}`}
                      className="rounded-md border border-[#1e293b] bg-[#0b1020] p-2.5"
                    >
                      <div className="flex items-center gap-2">
                        <span className={`h-2 w-2 rounded-full ${tone.dot}`} />
                        <span className="text-xs font-semibold text-[#e2e8f0]">{cat.name}</span>
                        <span
                          className={`ml-auto rounded border px-1.5 py-0.5 text-[10px] ${tone.chip}`}
                        >
                          {tone.label}
                        </span>
                      </div>
                      <div className="mt-1 text-[11px] text-[#94a3b8]">{cat.detail}</div>
                      {cat.metrics.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {cat.metrics.map((m) => (
                            <span
                              key={m.label}
                              className="rounded bg-[#111827] px-1.5 py-0.5 text-[10px] text-[#64748b]"
                            >
                              {m.label} <span className="text-[#cbd5e1]">{m.value}</span>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </section>

              {/* ── 最近一次流水线门禁 ───────────────────────────────── */}
              <section className="rounded-md border border-[#1e293b] bg-[#0b1020] p-2.5">
                <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">
                  最近一次流水线门禁
                  {latest?.source === "gate-summary" && (
                    <span className="rounded border border-[#1677ff]/30 bg-[#1677ff]/10 px-1.5 py-0.5 text-[10px] font-normal normal-case text-[#60a5fa]">
                      门禁汇总
                    </span>
                  )}
                  {latest?.source === "run-record" && (
                    <span className="rounded border border-[#334155] bg-[#1e293b]/50 px-1.5 py-0.5 text-[10px] font-normal normal-case text-[#94a3b8]">
                      仅运行记录
                    </span>
                  )}
                </div>

                {latest?.source === "none" || !latest?.job_id ? (
                  <div className="py-3 text-center text-[11px] text-[#64748b]" data-testid="quality-no-run">
                    尚无流水线运行记录，运行一次流水线后这里会显示门禁结论。
                  </div>
                ) : (
                  <div data-testid="quality-latest-run" className="space-y-2">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[#94a3b8]">
                      <span className="font-mono text-[#e2e8f0]">{latest.job_id}</span>
                      <span className="rounded bg-[#111827] px-1.5 py-0.5">
                        运行 {latest.run_status || "unknown"}
                      </span>
                      <span>开始 {fmtTime(latest.started_at)}</span>
                      <span>结束 {fmtTime(latest.completed_at)}</span>
                      {latest.worst_gate_status && (
                        <span className={gateTone(latest.worst_gate_status).text}>
                          最差门禁 {gateTone(latest.worst_gate_status).label}
                        </span>
                      )}
                      {latest.session && <span className="font-mono">session {latest.session}</span>}
                    </div>

                    {latest.gates.length === 0 ? (
                      <div
                        className="rounded border border-dashed border-[#334155] px-2 py-2 text-[11px] text-[#64748b]"
                        data-testid="quality-no-summary"
                      >
                        该运行未生成 gate-summary.json，无法给出逐门禁结论。
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 gap-1 sm:grid-cols-4 lg:grid-cols-6">
                        {latest.gates.map((g) => {
                          const tone = gateTone(g.status);
                          return (
                            <div
                              key={g.gate}
                              data-testid={`quality-gate-${g.gate}`}
                              title={`${g.name || ""}${g.advisory ? "（咨询性门禁）" : ""}`}
                              className="flex items-center gap-1.5 rounded border border-[#1e293b] px-1.5 py-1 text-[10px]"
                            >
                              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tone.dot}`} />
                              <span className="font-mono text-[#cbd5e1]">{g.gate}</span>
                              {g.advisory && (
                                <span className="ml-auto text-[9px] text-[#475569]">咨询</span>
                              )}
                              <span className={`${g.advisory ? "" : "ml-auto"} ${tone.text}`}>
                                {tone.label}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {latest.not_run_gates.length > 0 && (
                      <div className="text-[10px] text-[#fbbf24]">
                        <CircleSlash className="mr-1 inline w-3 h-3" />
                        未执行门禁：{latest.not_run_gates.join("、")}
                      </div>
                    )}
                    {latest.stale_gates.length > 0 && (
                      <div className="text-[10px] text-[#fbbf24]">
                        <AlertTriangle className="mr-1 inline w-3 h-3" />
                        证据过期门禁：{latest.stale_gates.join("、")}
                      </div>
                    )}
                    {latest.summary_path && (
                      <div className="font-mono text-[10px] text-[#475569]">
                        汇总来源：{latest.summary_path}
                      </div>
                    )}
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
