"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getLLMHealth, type LLMHealth, type LLMProviderHealth } from "@/lib/api";

const STATUS_META: Record<
  LLMProviderHealth["status"],
  { label: string; color: string; bg: string }
> = {
  ok: { label: "可用", color: "#10b981", bg: "#10b98114" },
  error: { label: "失败", color: "#ff4d4f", bg: "#ff4d4f14" },
  configured: { label: "已配置", color: "#faad14", bg: "#faad1414" },
  unconfigured: { label: "未配置", color: "#94a3b8", bg: "#94a3b814" },
};

export function LLMHealthCard() {
  const [health, setHealth] = useState<LLMHealth | null>(null);
  const [loading, setLoading] = useState(false);
  const [probing, setProbing] = useState(false);

  const load = useCallback(async (live: boolean) => {
    if (live) setProbing(true);
    else setLoading(true);
    try {
      const data = await getLLMHealth(live);
      setHealth(data);
    } catch {
      /* 忽略：诊断失败不阻塞页面 */
    } finally {
      setLoading(false);
      setProbing(false);
    }
  }, []);

  // 项⑪：挂载即做一次配置级诊断（不发网络请求），让用户一眼看到真实 LLM
  // 链路是否就绪；点「在线探测」才对每个已配置 provider 发极短实测。
  useEffect(() => {
    void load(false);
  }, [load]);

  return (
    <Card className="border-[#1e293b] bg-[#111827]">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-gray-200">
          <Activity className="w-4 h-4 text-[#6366f1]" />
          真实 LLM 链路状态
        </CardTitle>
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          disabled={probing}
          onClick={() => void load(true)}
        >
          <RefreshCw className={`w-3 h-3 mr-1 ${probing ? "animate-spin" : ""}`} />
          {probing ? "探测中" : "在线探测"}
        </Button>
      </CardHeader>
      <CardContent className="pt-0">
        {!health ? (
          <div className="text-xs text-gray-500">
            {loading ? "诊断中…" : "暂无可诊断的 LLM provider"}
          </div>
        ) : (
          <>
            <div className="text-xs text-gray-400 mb-3">{health.summary}</div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {health.providers.map((p) => {
                const meta = STATUS_META[p.status];
                return (
                  <div
                    key={p.provider}
                    className="rounded-md border border-[#1e293b] bg-[#0b1220] px-3 py-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-gray-200 capitalize">
                        {p.provider}
                      </span>
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded"
                        style={{
                          color: meta.color,
                          background: meta.bg,
                          border: `1px solid ${meta.color}30`,
                        }}
                      >
                        {meta.label}
                      </span>
                    </div>
                    <div className="text-[10px] text-gray-500 mt-1 truncate">
                      {p.model}
                    </div>
                    {p.key_preview && (
                      <div className="text-[10px] text-gray-500">
                        key: {p.key_preview}
                      </div>
                    )}
                    {p.detail && (
                      <div
                        className="text-[10px] mt-1 leading-snug"
                        style={{ color: meta.color }}
                      >
                        {p.detail}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="text-[10px] text-gray-600 mt-2">
              当前生效：{health.active_provider} / {health.active_model}
              {health.live ? "（已在线探测）" : "（仅配置检查）"}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
