"use client";

/**
 * LiveSyncBar —— 常驻「实时同步中」指示条。
 *
 * 满足两个诉求:
 *  1. 让用户在 LLM / pipeline 后台运行时, 明确感知「前台页面在自动刷新」
 *     —— 左侧脉冲点 + 「实时同步中」+ 右侧「最近刷新 HH:MM:SS」(每秒走动)。
 *  2. 一旦有后台 run 在跑, 立刻多出一个绿色 chip: 「后台运行中 · 步骤 X/24 · <当前步骤>」,
 *     与阶段看板 / 活跃项目卡的「当前正在跑」横幅联动(同源 activeRuns)。
 *
 * 数据来自 RealtimeStore: activeRuns(轮询 + SSE 合并填充) + last_poll_at(轮询时间戳)。
 */
import { useEffect, useState } from "react";
import { useRealtimeStore } from "@/lib/realtime-store";

const TOTAL_STEPS = 24;

export function LiveSyncBar() {
  const realtime = useRealtimeStore();
  const running = Object.values(realtime.activeRuns).filter(
    (r) => r.status === "running",
  );
  const lastPoll = realtime.last_poll_at || 0;

  // 每秒强制重渲染, 让「最近刷新」时间与耗时倒计时持续走动
  const [, force] = useState(0);
  useEffect(() => {
    const t = setInterval(() => force((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  // 取 step_index 最大的作为 featured(最新推进的)
  const featured = running
    .slice()
    .sort((a, b) => (b.current_stage_index ?? -1) - (a.current_stage_index ?? -1))[0];

  const timeStr = lastPoll ? new Date(lastPoll).toLocaleTimeString() : "—";

  return (
    <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-[#1e293b] bg-[#0f1623] px-4 py-2.5">
      <div className="flex min-w-0 items-center gap-2">
        <span className="relative flex h-2.5 w-2.5 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#1677ff] opacity-60" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[#1677ff]" />
        </span>
        <span className="text-xs text-[#94a3b8]">实时同步中</span>

        {running.length > 0 && (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[#10b981]/25 bg-[#10b981]/15 px-2 py-0.5 text-[11px] text-[#10b981]">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#10b981]" />
            {running.length > 1 ? `${running.length} 个后台运行中` : "后台运行中"}
            {featured && (
              <span className="text-[#10b981]/80">
                · 步骤 {(featured.current_stage_index ?? 0) + 1}/{TOTAL_STEPS}
                {featured.current_stage_title ? ` · ${featured.current_stage_title}` : ""}
              </span>
            )}
          </span>
        )}
      </div>
      <span className="shrink-0 text-[10px] text-[#64748b]">最近刷新 {timeStr}</span>
    </div>
  );
}
