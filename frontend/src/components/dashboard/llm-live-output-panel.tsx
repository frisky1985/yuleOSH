"use client";

import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { CheckCircle2, Loader2, TerminalSquare } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getDeltaSnapshot,
  subscribeDelta,
  type StepStream,
} from "@/lib/llm-stream-bus";

/** 单步渲染上限：总线最多留 200k 字符，DOM 只渲染尾部，避免长文卡顿。 */
const DISPLAY_TAIL = 30_000;

interface LLMLiveOutputPanelProps {
  stepDefs?: { key: string; name: string; agent: string }[];
}

function stepLabel(
  stepDefs: { key: string; name: string; agent: string }[],
  key: string,
): string {
  const def = stepDefs.find((d) => d.key === key);
  return def?.name || key || "?";
}

export function LLMLiveOutputPanel({ stepDefs = [] }: LLMLiveOutputPanelProps) {
  // getServerSnapshot：静态导出预渲染需要第三参；服务端只有空快照（面板空态），
  // 水合后客户端订阅接管。
  const snapshot = useSyncExternalStore(
    subscribeDelta,
    getDeltaSnapshot,
    getDeltaSnapshot,
  );
  const [pinnedKey, setPinnedKey] = useState<string | null>(null);

  const latestKey = snapshot.order[0] ?? null;
  const viewKey =
    pinnedKey && snapshot.steps.has(pinnedKey) ? pinnedKey : latestKey;
  const stream: StepStream | null = viewKey
    ? snapshot.steps.get(viewKey) ?? null
    : null;
  const streaming = stream ? !stream.done : false;
  const degraded = stream ? stream.done && stream.totalChars === 0 : false;

  // ── 自动滚动（用户上翻阅读时暂停跟随，回到底部恢复） ──
  const preRef = useRef<HTMLPreElement | null>(null);
  const stickRef = useRef(true);
  useEffect(() => {
    const el = preRef.current;
    if (!el || !stickRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [stream?.text, viewKey]);

  const full = stream?.text ?? "";
  const omitted = full.length > DISPLAY_TAIL ? full.length - DISPLAY_TAIL : 0;
  const shown = omitted ? full.slice(omitted) : full;

  return (
    <Card className="border-[#1e293b] bg-[#111827] mb-4">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
            <TerminalSquare className="w-4 h-4 text-[#6366f1]" />
            LLM 实时输出
            {streaming ? (
              <span className="text-[10px] text-[#10b981] inline-flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" /> 流式输出中
              </span>
            ) : (
              <span className="text-[10px] text-[#94a3b8]">空闲</span>
            )}
          </CardTitle>
          {stream && (
            <div className="flex items-center gap-3 text-[11px] text-[#94a3b8]">
              <span className="font-mono text-[#e2e8f0]">
                {stream.totalChars.toLocaleString()} 字符
              </span>
              {stream.model && (
                <span className="truncate max-w-[220px]">
                  {stream.model}
                  {stream.provider ? ` · ${stream.provider}` : ""}
                </span>
              )}
            </div>
          )}
        </div>
        {snapshot.order.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap mt-2">
            {snapshot.order.map((k) => {
              const s = snapshot.steps.get(k);
              if (!s) return null;
              const active = k === viewKey;
              return (
                <button
                  key={k}
                  type="button"
                  onClick={() =>
                    setPinnedKey(active && pinnedKey === k ? null : k)
                  }
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] border transition-colors ${
                    active
                      ? "border-[#6366f1] text-[#e2e8f0] bg-[#6366f1]/15"
                      : "border-[#1e293b] text-[#94a3b8] hover:text-[#e2e8f0]"
                  }`}
                  title={s.stepKey}
                >
                  {s.done ? (
                    <CheckCircle2 className="w-3 h-3 text-[#10b981]" />
                  ) : (
                    <Loader2 className="w-3 h-3 animate-spin text-[#faad14]" />
                  )}
                  {stepLabel(stepDefs, s.stepKey)}
                </button>
              );
            })}
          </div>
        )}
      </CardHeader>
      <CardContent className="pt-0">
        {!stream ? (
          <div className="text-xs text-gray-500 leading-relaxed">
            等待 LLM 流式输出… 从上方「运行」pipeline 后，大模型生成的内容会逐字
            显示在这里（需已配置 DeepSeek / OpenAI API key，且非 mock 运行）。
          </div>
        ) : (
          <>
            <pre
              ref={preRef}
              onScroll={(e) => {
                const el = e.currentTarget;
                stickRef.current =
                  el.scrollHeight - el.scrollTop - el.clientHeight < 48;
              }}
              className="text-[11px] leading-relaxed font-mono text-[#c9d4e3] whitespace-pre-wrap break-words rounded-md border border-[#1e293b] bg-[#0b1220] p-3 overflow-y-auto"
              style={{ maxHeight: 320, minHeight: 96 }}
            >
              {shown}
              {streaming && <span className="text-[#6366f1]">▌</span>}
            </pre>
            <div className="text-[10px] text-gray-600 mt-1.5 flex items-center gap-3">
              {omitted > 0 && <span>已省略前 {omitted.toLocaleString()} 字符（单步展示上限）</span>}
              {degraded && (
                <span className="text-[#faad14]">
                  本步未产生流式输出（LLM 调用可能走了非流式 / 本地兜底路径）
                </span>
              )}
              {stream.done && !degraded && <span>本步输出已完整</span>}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
