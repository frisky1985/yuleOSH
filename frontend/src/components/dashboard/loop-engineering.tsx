"use client";

// Loop Engineering — real-time closed-loop widgets.
// Reuses the backend /api/loops/{1-4}/data endpoints (src/yuleosh/api/loops.py).
// Design reference: archived dashboard-v5.html "Loop Engineering" section.
import { useState, useEffect, useCallback } from "react";
import { RefreshCw, Loader2 } from "lucide-react";

const LOOP_IDS = [1, 2, 3, 4] as const;

const LOOP_META: Record<number, { color: string; badgeBg: string }> = {
  1: { color: "#3b82f6", badgeBg: "rgba(59,130,246,.12)" },
  2: { color: "#22c55e", badgeBg: "rgba(34,197,94,.12)" },
  3: { color: "#eab308", badgeBg: "rgba(234,179,8,.12)" },
  4: { color: "#a855f7", badgeBg: "rgba(168,85,247,.12)" },
};

const LOOP_KPIS: Record<number, (m: any) => { v: string; l: string }[]> = {
  1: (m) => [
    { v: String(m.total_ci_failures_24h ?? 0), l: "24h CI失败" },
    { v: String(m.spec_deltas_generated ?? 0), l: "SpecDelta" },
    { v: `${(m.traceability_rate_7d ?? 0)}%`, l: "追溯率" },
  ],
  2: (m) => [
    { v: String(m.total_field_defects_30d ?? 0), l: "30d 现场缺陷" },
    { v: String(m.active_fmea_entries ?? 0), l: "活跃 FMEA" },
    { v: String(m.safety_alerts_active ?? 0), l: "安全告警" },
  ],
  3: (m) => [
    { v: `${(m.closure_rate_30d ?? 0)}%`, l: "闭环率" },
    { v: String(m.active_rca_count ?? 0), l: "活跃 RCA" },
    { v: String(m.open_tickets ?? 0), l: "待处理工单" },
  ],
  4: (m) => [
    { v: String(m.total_kg_entries ?? 0), l: "KG 条目" },
    { v: Number(m.avg_confidence ?? 0).toFixed(2), l: "平均置信度" },
    { v: String(m.needs_review_count ?? 0), l: "需审查" },
  ],
};

function sevColor(s?: number): string {
  if (!s) return "#94a3b8";
  return s >= 8 ? "#ff4d4f" : s >= 5 ? "#f59e0b" : s >= 3 ? "#eab308" : "#10b981";
}

function statusColor(st?: string): string {
  if (!st) return "#94a3b8";
  if (["resolved", "closed", "mitigated", "passed", "completed"].includes(st))
    return "#10b981";
  if (["active", "in_progress", "triggered"].includes(st)) return "#f59e0b";
  if (["new", "open", "failed"].includes(st)) return "#ff4d4f";
  return "#94a3b8";
}

// ── Mini SVG charts ────────────────────────────────────────────────

function GroupedBars({
  data,
  series,
}: {
  data: any[];
  series: { key: string; color: string }[];
}) {
  if (!data || data.length === 0)
    return <div className="text-[10px] text-[#64748b] py-4 text-center">无趋势数据</div>;
  const n = data.length;
  const max = Math.max(1, ...data.flatMap((d) => series.map((s) => d[s.key] ?? 0)));
  const groupW = 300 / n;
  const barW = Math.min(13, (groupW - 6) / series.length);
  const gap = (groupW - barW * series.length) / 2;
  return (
    <svg viewBox="0 0 300 88" className="w-full h-[88px]" preserveAspectRatio="none">
      {data.map((d, i) => (
        <g key={i} transform={`translate(${i * groupW + gap},0)`}>
          {series.map((s, si) => {
            const v = d[s.key] ?? 0;
            const h = (v / max) * (88 - 12);
            const x = si * barW;
            const y = 88 - h - 4;
            return (
              <rect
                key={si}
                x={x}
                y={y}
                width={Math.max(barW - 1.5, 2)}
                height={h}
                rx={1.5}
                fill={s.color}
                opacity={0.85}
              />
            );
          })}
        </g>
      ))}
    </svg>
  );
}

function LineChart({
  points,
  color,
  area,
}: {
  points: number[];
  color: string;
  area?: boolean;
}) {
  if (!points || points.length === 0)
    return <div className="text-[10px] text-[#64748b] py-4 text-center">无趋势数据</div>;
  const max = Math.max(...points, 0.0001);
  const min = Math.min(...points, 0);
  const range = max - min || 1;
  const W = 300,
    H = 88,
    pad = 6;
  const pts = points.map((v, i) => {
    const x = pad + (i * (W - 2 * pad)) / (points.length - 1 || 1);
    const y = H - pad - ((v - min) / range) * (H - 2 * pad);
    return [x, y] as [number, number];
  });
  const path = pts
    .map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1))
    .join(" ");
  const areaPath = area
    ? `${path} L ${pts[pts.length - 1][0].toFixed(1)} ${H - pad} L ${pts[0][0].toFixed(1)} ${H - pad} Z`
    : null;
  return (
    <svg viewBox="0 0 300 88" className="w-full h-[88px]" preserveAspectRatio="none">
      {area && areaPath && <path d={areaPath} fill={color} opacity={0.12} />}
      <path d={path} fill="none" stroke={color} strokeWidth={1.8} />
    </svg>
  );
}

function LoopChart({ id, data }: { id: number; data: any }) {
  const charts = data.charts || {};
  if (id === 1 && charts.traceability_7d)
    return (
      <GroupedBars
        data={charts.traceability_7d}
        series={[
          { key: "ci_failures", color: "#3b82f6" },
          { key: "kg_traces", color: "#8b5cf6" },
          { key: "spec_deltas", color: "#f59e0b" },
        ]}
      />
    );
  if (id === 2 && charts.monthly_trend)
    return (
      <GroupedBars
        data={charts.monthly_trend}
        series={[
          { key: "defects", color: "#ef4444" },
          { key: "fmea_updates", color: "#22c55e" },
          { key: "safety_alerts", color: "#f59e0b" },
        ]}
      />
    );
  if (id === 3 && charts.kpi_trend)
    return <LineChart points={charts.kpi_trend.map((d: any) => d.coverage)} color="#22c55e" />;
  if (id === 4 && charts.confidence_trend)
    return (
      <LineChart
        points={charts.confidence_trend.map((d: any) => d.avg_confidence)}
        color="#a855f7"
        area
      />
    );
  return <div className="text-[10px] text-[#64748b] py-4 text-center">无趋势数据</div>;
}

// ── Expandable detail ──────────────────────────────────────────────

function LoopDetail({ id, data }: { id: number; data: any }) {
  if (id === 1) {
    const events = data.events || [];
    return (
      <div>
        <div className="text-[11px] font-semibold mb-1.5 text-[#94a3b8]">回溯时间线</div>
        {events.map((e: any, i: number) => (
          <div key={i} className="flex items-start gap-2 py-1 text-[11px]">
            <span
              className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0"
              style={{
                background:
                  e.event_type === "CI_FAILURE"
                    ? "#3b82f6"
                    : e.event_type === "KG_TRACE"
                    ? "#8b5cf6"
                    : "#f59e0b",
              }}
            />
            <div>
              <span className="text-[#64748b]">
                {e.timestamp?.slice(5, 16)?.replace("T", " ")}
              </span>
              <span className="text-[#cbd5e1] ml-1.5">{e.summary}</span>
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (id === 2) {
    const root = data.impact_chain?.root;
    const children = data.impact_chain?.children || [];
    return (
      <div>
        <div className="text-[11px] font-semibold mb-1.5 text-[#94a3b8]">影响链</div>
        <div className="text-[11px] text-[#cbd5e1] mb-1">
          {root?.name} <span className="text-[#64748b]">×{root?.count ?? 0}</span>
        </div>
        {children.map((c: any, i: number) => (
          <div
            key={i}
            className="flex items-center justify-between py-1 text-[11px] border-t border-[#1e293b]"
          >
            <span style={{ color: sevColor(c.severity) }}>
              {c.name}{" "}
              <span className="text-[#64748b]">RPN:{c.rpn ?? "—"}</span>
            </span>
            <span className="text-[10px]" style={{ color: statusColor(c.status) }}>
              {c.status}
            </span>
          </div>
        ))}
      </div>
    );
  }
  if (id === 3) {
    const rca = data.rca_records || [];
    const tickets = data.improvement_tickets || [];
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <div className="text-[11px] font-semibold mb-1 text-[#94a3b8]">RCA 记录</div>
          {rca.map((r: any, i: number) => (
            <div
              key={i}
              className="flex justify-between py-1 text-[11px] border-t border-[#1e293b]"
            >
              <span className="text-[#64748b]">{r.metric}</span>
              <span style={{ color: statusColor(r.status) }}>{r.status}</span>
            </div>
          ))}
        </div>
        <div>
          <div className="text-[11px] font-semibold mb-1 text-[#94a3b8]">改进工单</div>
          {tickets.map((t: any, i: number) => (
            <div
              key={i}
              className="flex justify-between py-1 text-[11px] border-t border-[#1e293b]"
            >
              <span className="text-[#64748b]">{t.id}</span>
              <span style={{ color: statusColor(t.status) }}>{t.status}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  // id === 4
  const buckets = data.confidence_buckets || [];
  const low = data.low_confidence_items || [];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <div>
        <div className="text-[11px] font-semibold mb-1 text-[#94a3b8]">置信度分布</div>
        {buckets.map((b: any, i: number) => (
          <div key={i} className="flex items-center gap-2 text-[10px] py-0.5">
            <span className="w-14 text-[#64748b] shrink-0">{b.range}</span>
            <div className="flex-1 h-2 rounded bg-[#1e293b] overflow-hidden">
              <div
                className="h-full rounded"
                style={{ width: `${Math.max(b.pct * 1.8, 3)}%`, background: "#a855f7" }}
              />
            </div>
            <span className="w-6 text-right text-[#94a3b8]">{b.count}</span>
          </div>
        ))}
      </div>
      <div>
        <div className="text-[11px] font-semibold mb-1 text-[#94a3b8]">低分条目</div>
        {low.slice(0, 5).map((it: any, i: number) => (
          <div
            key={i}
            className="flex justify-between py-1 text-[11px] border-t border-[#1e293b]"
          >
            <span className="text-[#64748b] truncate">{it.entity?.slice(0, 22)}…</span>
            <span className="text-[#ff4d4f]">
              {(Number(it.confidence) * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Card ───────────────────────────────────────────────────────────

function LoopCard({
  id,
  data,
  expanded,
  onToggle,
}: {
  id: number;
  data: any;
  expanded: boolean;
  onToggle: () => void;
}) {
  const meta = LOOP_META[id];
  const kpis = LOOP_KPIS[id](data.metrics || {});
  return (
    <div
      className="rounded-lg border border-[#1e293b] bg-[#0a0e17] p-3.5 cursor-pointer hover:border-[#722ed1]/40 transition-colors"
      style={expanded ? { borderColor: "#334155" } : undefined}
      onClick={onToggle}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#e2e8f0]">
          <span>{data.emoji}</span>
          <span>{data.label}</span>
        </div>
        <span
          className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
          style={{ background: meta.badgeBg, color: meta.color }}
        >
          Loop {id}
        </span>
      </div>

      <div className="flex gap-4 mb-3">
        {kpis.map((k, i) => (
          <div key={i} className="flex-1 min-w-0">
            <div className="text-lg font-extrabold" style={{ color: meta.color }}>
              {k.v}
            </div>
            <div className="text-[10px] text-[#64748b] mt-0.5 truncate">{k.l}</div>
          </div>
        ))}
      </div>

      <LoopChart id={id} data={data} />

      {expanded && (
        <div className="mt-3 pt-3 border-t border-[#1e293b] max-h-[320px] overflow-y-auto">
          <LoopDetail id={id} data={data} />
        </div>
      )}
    </div>
  );
}

// ── Section ─────────────────────────────────────────────────────────

export function LoopEngineering() {
  const [loops, setLoops] = useState<Record<number, any>>({});
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const results = await Promise.allSettled(
        LOOP_IDS.map((id) =>
          fetch(`/api/loops/${id}/data`, { credentials: "same-origin" }).then((r) =>
            r.json()
          )
        )
      );
      const next: Record<number, any> = {};
      results.forEach((res, i) => {
        const id = LOOP_IDS[i];
        if (res.status === "fulfilled" && res.value?.ok) next[id] = res.value;
      });
      setLoops(next);
    } catch (e) {
      console.warn("loop load failed", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
    const t = setInterval(loadAll, 30000);
    return () => clearInterval(t);
  }, [loadAll]);

  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-4 sm:p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
          <RefreshCw className="w-4 h-4 text-[#722ed1]" />
          Loop Engineering · 闭环工程
        </h2>
        <span className="text-[10px] text-[#64748b] flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#10b981] animate-pulse" />
          Auto-refresh 30s
        </span>
      </div>

      {loading && Object.keys(loops).length === 0 ? (
        <div className="flex items-center gap-2 text-xs text-[#94a3b8] py-6">
          <Loader2 className="w-4 h-4 animate-spin" />
          加载闭环数据...
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {LOOP_IDS.map((id) => {
            const data = loops[id];
            if (!data)
              return (
                <div
                  key={id}
                  className="rounded-lg border border-[#1e293b] bg-[#0a0e17] p-3.5 text-xs text-[#64748b]"
                >
                  Loop {id} 数据不可用
                </div>
              );
            return (
              <LoopCard
                key={id}
                id={id}
                data={data}
                expanded={expanded === id}
                onToggle={() => setExpanded(expanded === id ? null : id)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
