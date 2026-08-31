"use client";

// yuleASR BSW project live status widget (engineer perspective).
// Reuses GET /api/v1/pipeline/yuleasr-status.
// Design reference: archived dashboard-v5.html "yuleASR BSW Status" widget.
import { useState, useEffect, useCallback } from "react";
import { Loader2, Cpu } from "lucide-react";

interface YuleASRStatusData {
  ok: boolean;
  available: boolean;
  compile_status?: string | null;
  misra_violations?: number | null;
  coverage?: {
    line_rate?: number;
    branch_rate?: number;
    function_rate?: number;
  } | null;
  qemu_status?: string | null;
  last_run_at?: string | null;
  recent_autosar_runs?: { id?: string; status?: string; created_at?: string }[];
  errors?: string[];
}

function passColor(v?: string | null): string {
  if (v === "passed" || v === "completed") return "#10b981";
  if (v === "running") return "#eab308";
  if (!v) return "#64748b";
  return "#ff4d4f";
}

function StatusIcon({ v }: { v?: string | null }) {
  if (v === "passed" || v === "completed") return <span>✅</span>;
  if (v === "running") return <span>🔄</span>;
  if (!v) return <span>—</span>;
  return <span>❌</span>;
}

export function YuleASRStatus() {
  const [data, setData] = useState<YuleASRStatusData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const resp = await fetch("/api/v1/pipeline/yuleasr-status", {
        credentials: "same-origin",
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body = await resp.json();
      setData(body);
    } catch (e) {
      console.warn("yuleasr load failed", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const compilePassed =
    data?.compile_status === "passed" || data?.compile_status === "completed";
  const coveragePct = data?.coverage?.line_rate != null ? data.coverage.line_rate * 100 : null;
  const misra = data?.misra_violations;

  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-4 sm:p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
          <Cpu className="w-4 h-4 text-[#1677ff]" />
          yuleASR BSW 状态
        </h2>
        <span className="text-[10px] text-[#64748b] flex items-center gap-1.5">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: data?.available ? "#10b981" : "#64748b" }}
          />
          {data?.last_run_at
            ? `Last run: ${new Date(data.last_run_at).toLocaleString()}`
            : "—"}
        </span>
      </div>

      {loading && !data ? (
        <div className="flex items-center gap-2 text-xs text-[#94a3b8] py-6">
          <Loader2 className="w-4 h-4 animate-spin" />
          加载 yuleASR 状态...
        </div>
      ) : !data?.available ? (
        <div className="py-6 text-center">
          <p className="text-sm text-[#94a3b8]">未接入 yuleASR</p>
          <p className="text-xs text-[#64748b] mt-1">
            配置 YULEASR_HOME 后将展示编译 / MISRA / 覆盖率 / QEMU 实时状态
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Compile */}
            <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17] p-3 text-center">
              <div className="text-lg mb-1">
                <StatusIcon v={data?.compile_status} />
              </div>
              <div
                className="text-lg font-extrabold"
                style={{ color: passColor(data?.compile_status) }}
              >
                {compilePassed ? "Pass" : data?.compile_status ?? "—"}
              </div>
              <div className="text-[10px] text-[#64748b] mt-1 uppercase">Compile</div>
            </div>

            {/* MISRA */}
            <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17] p-3 text-center">
              <div className="text-[10px] text-[#64748b] mt-1 mb-1">📐</div>
              <div
                className="text-lg font-extrabold"
                style={{
                  color:
                    misra == null
                      ? "#94a3b8"
                      : misra < 1000
                      ? "#10b981"
                      : misra < 5000
                      ? "#eab308"
                      : "#ff4d4f",
                }}
              >
                {misra ?? "—"}
              </div>
              <div className="text-[10px] text-[#64748b] mt-1 uppercase">
                MISRA Violations
              </div>
            </div>

            {/* Line Coverage */}
            <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17] p-3 text-center">
              <div className="text-[10px] text-[#64748b] mt-1 mb-1">📊</div>
              <div
                className="text-lg font-extrabold"
                style={{
                  color:
                    coveragePct == null
                      ? "#94a3b8"
                      : coveragePct >= 80
                      ? "#10b981"
                      : coveragePct >= 50
                      ? "#eab308"
                      : "#ff4d4f",
                }}
              >
                {coveragePct != null ? `${coveragePct.toFixed(1)}%` : "—"}
              </div>
              <div className="text-[10px] text-[#64748b] mt-1 uppercase">Line Coverage</div>
            </div>

            {/* QEMU / SIL */}
            <div className="rounded-lg border border-[#1e293b] bg-[#0a0e17] p-3 text-center">
              <div className="text-lg mb-1">
                <StatusIcon v={data?.qemu_status} />
              </div>
              <div
                className="text-lg font-extrabold"
                style={{ color: passColor(data?.qemu_status) }}
              >
                {data?.qemu_status === "passed"
                  ? "Pass"
                  : data?.qemu_status === "failed"
                  ? "Fail"
                  : data?.qemu_status ?? "—"}
              </div>
              <div className="text-[10px] text-[#64748b] mt-1 uppercase">QEMU / SIL</div>
            </div>
          </div>

          {/* Wide detail row */}
          <div className="flex items-center flex-wrap gap-x-5 gap-y-1 text-[11px] text-[#94a3b8] rounded-lg border border-[#1e293b] bg-[#0a0e17] px-3 py-2">
            <span>
              <span className="text-[#64748b]">Branch Cov:</span>{" "}
              <span className="font-semibold text-[#e2e8f0]">
                {data?.coverage?.branch_rate != null
                  ? `${(data.coverage.branch_rate * 100).toFixed(1)}%`
                  : "—"}
              </span>
            </span>
            <span>
              <span className="text-[#64748b]">Function Cov:</span>{" "}
              <span className="font-semibold text-[#e2e8f0]">
                {data?.coverage?.function_rate != null
                  ? `${(data.coverage.function_rate * 100).toFixed(1)}%`
                  : "—"}
              </span>
            </span>
            <span>
              <span className="text-[#64748b]">Recent Runs:</span>{" "}
              <span className="font-semibold text-[#e2e8f0]">
                {(data?.recent_autosar_runs?.length ?? 0)} in history
              </span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
