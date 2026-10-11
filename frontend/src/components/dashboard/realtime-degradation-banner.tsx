"use client";

/** 实时同步降级提示横幅。
 *
 * 当 SSE 连接断开（connected=false）时显示黄色横幅，提示用户「实时同步已断开，
 * 降级到轮询模式」。SSE 重连成功后自动隐藏。
 *
 * 用法：仅在 <RealtimeProvider> 内使用（依赖 useRealtimeStore）。
 */
import { useRealtimeStore } from "@/lib/realtime-store";

export function RealtimeDegradationBanner() {
  const { connected } = useRealtimeStore();

  // SSE 已连接 → 不显示横幅
  if (connected) return null;

  return (
    <div className="bg-yellow-600/90 text-yellow-50 px-4 py-2 text-sm text-center border-b border-yellow-500/30">
      <div className="flex items-center justify-center gap-2">
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <span>实时同步已断开，降级到轮询模式（数据可能有几秒延迟）</span>
      </div>
    </div>
  );
}
