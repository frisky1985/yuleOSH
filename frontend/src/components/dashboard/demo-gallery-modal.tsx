"use client";

import { useState } from "react";
import { Cpu, Lightbulb, Radio, Sparkles, Loader2, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";

/** Slugs the backend seeds under `seed-demo` — shared so the Dashboard list
 *  can badge demo projects and the gallery can tell what's already loaded. */
export const DEMO_SLUGS = ["uart-demo", "gpio-demo", "can-demo"];

type DemoMeta = {
  slug: string;
  name: string;
  tag: string;
  desc: string;
  Icon: typeof Cpu;
  color: string;
};

const DEMO_LIST: DemoMeta[] = [
  {
    slug: "uart-demo",
    name: "UART 驱动演示项目",
    tag: "车规 UART",
    desc: "串口驱动合规流水线演示：波特率可配置、发送 FIFO 溢出保护、接收中断丢帧防护。",
    Icon: Cpu,
    color: "#1677ff",
  },
  {
    slug: "gpio-demo",
    name: "GPIO 流水灯演示",
    tag: "GPIO",
    desc: "GPIO 流水灯合规流水线演示：LED 引脚输出可控、流水灯时序正确、低功耗休眠模式。",
    Icon: Lightbulb,
    color: "#f59e0b",
  },
  {
    slug: "can-demo",
    name: "CAN 通信演示",
    tag: "CAN 总线",
    desc: "CAN 总线通信合规流水线演示：报文收发可靠、总线错误恢复、波特率自适应。",
    Icon: Radio,
    color: "#722ed1",
  },
];

export function DemoGalleryModal({
  open,
  onClose,
  existingSlugs,
  onLoaded,
}: {
  open: boolean;
  onClose: () => void;
  existingSlugs: string[];
  onLoaded: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const loaded = new Set(existingSlugs);

  const handleLoadAll = async () => {
    setLoading(true);
    try {
      await api.v1.projects.seed({});
      onLoaded();
    } catch (e) {
      console.error("seed demo failed:", e);
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-xl border border-[#1e293b] bg-[#111827] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1e293b]">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-[#1677ff]" />
            <h3 className="text-sm font-semibold text-white">加载示例项目</h3>
          </div>
          <button
            onClick={onClose}
            className="text-[#64748b] hover:text-white text-lg leading-none"
            aria-label="关闭"
          >
            &times;
          </button>
        </div>

        <div className="p-5">
          <p className="text-xs text-[#94a3b8] mb-4">
            一键注入下列可直接运行合规流水线的示例项目。已注入的会标记「已加载」。
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {DEMO_LIST.map((d) => {
              const isLoaded = loaded.has(d.slug);
              return (
                <div
                  key={d.slug}
                  className="rounded-lg border border-[#1e293b] bg-[#0a0e17] p-3 flex flex-col"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className="w-8 h-8 rounded-md flex items-center justify-center shrink-0"
                      style={{ background: `${d.color}1a`, color: d.color }}
                    >
                      <d.Icon className="w-4 h-4" />
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1e293b] text-[#94a3b8] whitespace-nowrap">
                      {d.tag}
                    </span>
                    {isLoaded && (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 ml-auto shrink-0" />
                    )}
                  </div>
                  <div className="text-sm font-medium text-white truncate">
                    {d.name}
                  </div>
                  <div className="text-[11px] text-[#64748b] mt-1 leading-relaxed flex-1">
                    {d.desc}
                  </div>
                  <div
                    className={`mt-2 text-[10px] ${
                      isLoaded ? "text-emerald-400" : "text-[#64748b]"
                    }`}
                  >
                    {isLoaded ? "已加载 ✓" : "未加载"}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-[#1e293b]">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs text-[#94a3b8] hover:text-white rounded border border-[#1e293b] transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleLoadAll}
            disabled={loading}
            className="px-3 py-1.5 text-xs text-white rounded bg-gradient-to-r from-[#722ed1] to-[#1677ff] hover:opacity-90 disabled:opacity-60 flex items-center gap-1.5 transition-opacity"
          >
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5" />
            )}
            一键加载全部示例
          </button>
        </div>
      </div>
    </div>
  );
}
