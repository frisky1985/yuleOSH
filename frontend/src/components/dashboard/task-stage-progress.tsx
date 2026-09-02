"use client";

import { AlertCircle, CheckCircle2, Circle, Loader2 } from "lucide-react";

interface TaskStageProgressProps {
  /** Ordered list of stage labels, e.g. ["准备", "收集证据", "打包", "完成"]. */
  stages: string[];
  /**
   * Overall progress percentage (0–100). Used both to highlight the active
   * stage and to render the bottom progress bar. Should clamp to [0, 100].
   */
  progressPct: number;
  /** When true the whole flow turns red and the bar is red. */
  isFailed?: boolean;
  /**
   * Optional progress breakpoints that map progressPct → current stage index.
   * Length MUST equal stages.length + 1 (one entry per "fence post" including
   * 0 and 100). Defaults to evenly spaced fences.
   */
  breakpoints?: number[];
  /**
   * Optional description of the current stage (rendered under the bar). When
   * omitted we fall back to the active stage label.
   */
  currentNote?: string;
}

const DEFAULT_BREAKPOINTS = (n: number) =>
  Array.from({ length: n + 1 }, (_, i) => Math.round((i * 100) / n));

/**
 * 水平阶段步骤进度条
 *
 * 把后台任务从「一个百分比」升级为「明确告诉你现在卡在哪一步」。后端不需要
 * 上报 stage 字段，前端按 progressPct 落在哪个区间自动激活对应步骤；当前
 * 步骤用 loader 旋转图标表示「正在执行」，已完成步骤打勾，未来步骤灰显。
 *
 * 设计选择：阶段是水平排布，宽度自适应（基于 min-w + flex-1），这样不会因
 * 阶段名字长短不同而崩。最适合在 modal 顶部或进度面板使用。
 */
export function TaskStageProgress({
  stages,
  progressPct,
  isFailed = false,
  breakpoints,
  currentNote,
}: TaskStageProgressProps) {
  const pct = Math.max(0, Math.min(100, progressPct));
  const fences =
    breakpoints && breakpoints.length === stages.length + 1
      ? breakpoints
      : DEFAULT_BREAKPOINTS(stages.length);

  // 当前阶段索引：progressPct 跨过的最后一个 fence 之前
  let activeIdx = 0;
  for (let i = 0; i < fences.length - 1; i++) {
    if (pct >= fences[i] && pct < fences[i + 1]) {
      activeIdx = i;
      break;
    }
    if (pct >= fences[fences.length - 1]) {
      activeIdx = stages.length - 1;
    }
  }
  // 100% 时最后阶段视为完成（不再是「进行中」）
  if (pct >= 100) activeIdx = stages.length - 1;

  const stageState = (i: number): "done" | "active" | "pending" => {
    if (isFailed) {
      // 失败时：进行中（activeIdx）= failed；之前的为 done；之后的 pending
      if (i < activeIdx) return "done";
      if (i === activeIdx) return "active";
      return "pending";
    }
    if (i < activeIdx) return "done";
    if (i === activeIdx) return pct >= 100 ? "done" : "active";
    return "pending";
  };

  return (
    <div className="space-y-3">
      {/* 步骤列表 */}
      <div className="px-1">
        <div className="flex items-start">
          {stages.map((label, i) => {
            const state = stageState(i);
            const isLast = i === stages.length - 1;
            const nextState = !isLast ? stageState(i + 1) : "pending";

            const dotCls =
              state === "done"
                ? "bg-[#10b981]/15 border-[#10b981] text-[#10b981]"
                : state === "active"
                  ? isFailed
                    ? "bg-[#ff4d4f]/15 border-[#ff4d4f] text-[#ff4d4f]"
                    : "bg-[#722ed1]/15 border-[#722ed1] text-[#722ed1]"
                  : "bg-[#0a0e17] border-[#1e293b] text-[#475569]";

            // 连接线：当前已 done 或 next 已 done/active，则连线"已通过"
            const linePassed = state === "done" || (state === "active" && pct >= fences[i + 1]);
            const lineCls = linePassed
              ? isFailed
                ? "bg-[#ff4d4f]/40"
                : "bg-gradient-to-r from-[#10b981] to-[#722ed1]/60"
              : "bg-[#1e293b]";

            return (
              <div
                key={`${label}-${i}`}
                className="flex items-start flex-1 last:flex-none"
              >
                <div className="flex flex-col items-center min-w-0">
                  <div
                    className={`w-6 h-6 rounded-full border flex items-center justify-center shrink-0 ${dotCls}`}
                    aria-current={state === "active" ? "step" : undefined}
                  >
                    {state === "done" && <CheckCircle2 className="w-3.5 h-3.5" />}
                    {state === "active" &&
                      (isFailed ? (
                        <AlertCircle className="w-3.5 h-3.5" />
                      ) : (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ))}
                    {state === "pending" && <Circle className="w-3 h-3" />}
                  </div>
                  <div
                    className={`text-[10px] mt-1.5 text-center max-w-[72px] leading-tight ${
                      state === "done"
                        ? "text-[#10b981]"
                        : state === "active"
                          ? isFailed
                            ? "text-[#ff4d4f]"
                            : "text-[#722ed1] font-mono"
                          : "text-[#475569]"
                    }`}
                  >
                    {label}
                  </div>
                </div>
                {!isLast && (
                  <div
                    className={`h-0.5 flex-1 mx-1 mt-2.5 rounded-full transition-all duration-500 ${lineCls}`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 整体进度条 + 文案 */}
      <div>
        <div className="flex items-center justify-between text-[11px] mb-1">
          <span
            className={
              isFailed
                ? "text-[#ff4d4f]"
                : pct >= 100
                  ? "text-[#10b981]"
                  : "text-[#94a3b8]"
            }
          >
            {isFailed
              ? "执行失败"
              : pct >= 100
                ? "已完成"
                : `正在「${currentNote ?? stages[activeIdx]}」…`}
          </span>
          <span className="text-[#64748b] font-mono">{Math.round(pct)}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${pct}%`,
              background: isFailed
                ? "#ff4d4f"
                : pct >= 100
                  ? "#10b981"
                  : "linear-gradient(90deg, #722ed1, #1677ff)",
            }}
          />
        </div>
      </div>
    </div>
  );
}