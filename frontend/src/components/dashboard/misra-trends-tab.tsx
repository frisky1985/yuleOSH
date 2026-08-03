"use client";

import { useState, useEffect } from "react";
import {
  TrendingUp, Loader2, AlertCircle, AlertTriangle,
  RefreshCw, Info, BarChart3, Target, CheckCircle2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getMISRATrend, type MisraTrendResponse } from "@/lib/api";

export function MisraTrendsTab() {
  const [trendData, setTrendData] = useState<MisraTrendResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError("");
      try {
        const res = await getMISRATrend();
        setTrendData(res);
      } catch (err: any) {
        setError(err.message || "加载 MISRA 趋势失败");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 text-[#722ed1] animate-spin" />
        <span className="ml-2 text-sm text-[#94a3b8]">加载 MISRA 趋势数据...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-[#ff4d4f]/20 bg-[#ff4d4f]/5 px-4 py-6 text-center">
        <AlertCircle className="w-6 h-6 text-[#ff4d4f] mx-auto mb-2" />
        <p className="text-sm text-[#ff4d4f]">{error}</p>
      </div>
    );
  }

  if (!trendData) return null;

  const { weekly_trend, distribution, recent_violations, note } = trendData;

  // Compute max values for scaling
  const maxViolations = Math.max(...weekly_trend.map((w) => w.violations), 1);
  const totalDist = distribution.required + distribution.advisory;

  return (
    <>
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-lg font-bold text-[#e2e8f0] flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-[#722ed1]" />
            MISRA 违规趋势
          </h1>
          <p className="text-xs text-[#64748b] mt-0.5">
            MISRA 违规数量周趋势与规则分布
          </p>
        </div>
        <Button
          onClick={() => window.location.reload()}
          variant="outline"
          className="border-[#1e293b] text-[#94a3b8] h-9 text-xs gap-1.5"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          刷新
        </Button>
      </div>

      {/* Note banner */}
      {note && (
        <div className="mb-4 rounded-lg bg-[#faad14]/10 border border-[#faad14]/20 px-4 py-2 text-xs text-[#faad14] flex items-center gap-2">
          <Info className="w-3.5 h-3.5 shrink-0" />
          <span>{note}</span>
        </div>
      )}

      {/* Trend chart + Distribution pie side by side */}
      <div className="grid lg:grid-cols-3 gap-5 mb-6">
        {/* Trend bar chart (spans 2 cols) */}
        <Card className="lg:col-span-2 border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-[#722ed1]" />
              周趋势
            </CardTitle>
          </CardHeader>
          <CardContent>
            {/* Bar chart */}
            <div className="flex items-end gap-3 h-48 px-2">
              {weekly_trend.map((point, i) => {
                const h = Math.max((point.violations / maxViolations) * 100, 4);
                return (
                  <div key={point.week} className="flex-1 flex flex-col items-center gap-1 h-full">
                    {/* Bar stack */}
                    <div className="flex-1 w-full flex flex-col justify-end gap-0.5">
                      {/* Advisory portion */}
                      <div
                        className="w-full rounded-t-sm transition-all duration-500"
                        style={{
                          height: `${Math.max((point.advisory / maxViolations) * 100, 2)}%`,
                          background: "#1677ff",
                          opacity: 0.6 + (i / weekly_trend.length) * 0.4,
                        }}
                        title={`Advisory: ${point.advisory}`}
                      />
                      {/* Required portion */}
                      <div
                        className="w-full rounded-t-sm transition-all duration-500"
                        style={{
                          height: `${Math.max(((point.required) / maxViolations) * 100, 2)}%`,
                          background: "#722ed1",
                          opacity: 0.5 + (i / weekly_trend.length) * 0.5,
                        }}
                        title={`Required: ${point.required}`}
                      />
                    </div>
                    {/* Label */}
                    <span className="text-[10px] text-[#64748b] whitespace-nowrap">
                      {point.week.slice(5)}
                    </span>
                    {/* Value */}
                    <span className="text-[10px] font-mono text-[#94a3b8]">
                      {point.violations}
                    </span>
                  </div>
                );
              })}
            </div>
            {/* Legend */}
            <div className="flex items-center justify-center gap-4 mt-4 text-[10px] text-[#94a3b8]">
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-sm" style={{ background: "#722ed1" }} />
                Required
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-sm" style={{ background: "#1677ff" }} />
                Advisory
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Distribution */}
        <Card className="border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
              <Target className="w-4 h-4 text-[#722ed1]" />
              规则分布
            </CardTitle>
          </CardHeader>
          <CardContent>
            {/* Simple donut-style visualization with pure CSS */}
            <div className="flex flex-col items-center">
              <div className="relative w-32 h-32 mb-4">
                {/* CSS donut: two overlapping semicircles + conic-gradient approach */}
                <svg viewBox="0 0 36 36" className="w-32 h-32 -rotate-90">
                  {/* Background ring */}
                  <circle
                    cx="18" cy="18" r="15.9"
                    fill="none"
                    stroke="#1e293b"
                    strokeWidth="3.2"
                  />
                  {/* Required segment */}
                  <circle
                    cx="18" cy="18" r="15.9"
                    fill="none"
                    stroke="#722ed1"
                    strokeWidth="3.2"
                    strokeDasharray={`${(distribution.required / totalDist) * 100} ${100 - (distribution.required / totalDist) * 100}`}
                    strokeLinecap="butt"
                  />
                  {/* Advisory segment */}
                  <circle
                    cx="18" cy="18" r="15.9"
                    fill="none"
                    stroke="#1677ff"
                    strokeWidth="3.2"
                    strokeDasharray={`${(distribution.advisory / totalDist) * 100} ${100 - (distribution.advisory / totalDist) * 100}`}
                    strokeDashoffset={-(distribution.required / totalDist) * 100}
                    strokeLinecap="butt"
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-center">
                    <div className="text-xl font-black text-[#e2e8f0]">{totalDist}</div>
                    <div className="text-[10px] text-[#64748b]">总计</div>
                  </div>
                </div>
              </div>

              <div className="w-full space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-[#94a3b8]">
                    <span className="w-2 h-2 rounded-full" style={{ background: "#722ed1" }} />
                    Required
                  </span>
                  <span className="font-mono text-[#722ed1]">{distribution.required}</span>
                </div>
                <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${(distribution.required / totalDist) * 100}%`,
                      background: "#722ed1",
                    }}
                  />
                </div>
                <div className="flex items-center justify-between text-xs mt-2">
                  <span className="flex items-center gap-1.5 text-[#94a3b8]">
                    <span className="w-2 h-2 rounded-full" style={{ background: "#1677ff" }} />
                    Advisory
                  </span>
                  <span className="font-mono text-[#1677ff]">{distribution.advisory}</span>
                </div>
                <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${(distribution.advisory / totalDist) * 100}%`,
                      background: "#1677ff",
                    }}
                  />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent violations */}
      <Card className="border-[#1e293b] bg-[#111827]">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-[#faad14]" />
            最近违规（最近 10 条）
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {recent_violations.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <CheckCircle2 className="w-6 h-6 text-[#10b981] mx-auto mb-2" />
              <p className="text-xs text-[#94a3b8]">暂无近期违规</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e293b]">
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider">
                      规则
                    </th>
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider">
                      类别
                    </th>
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider hidden sm:table-cell">
                      文件
                    </th>
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider hidden md:table-cell">
                      行
                    </th>
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider hidden lg:table-cell">
                      说明
                    </th>
                    <th className="text-left py-3 px-4 text-xs text-[#64748b] font-medium uppercase tracking-wider">
                      严重级别
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {recent_violations.map((v, idx) => (
                    <tr
                      key={idx}
                      className={`border-b border-[#1e293b] hover:bg-[#1e293b]/50 transition-colors ${
                        idx % 2 === 0 ? "bg-[#0a0e17]/30" : ""
                      }`}
                    >
                      <td className="py-3 px-4">
                        <Badge
                          variant="outline"
                          className="text-[10px] px-1.5 font-mono border-[#722ed1]/20 text-[#722ed1]"
                        >
                          {v.rule_id}
                        </Badge>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`text-xs font-medium ${
                            v.category === "Required" ? "text-[#722ed1]" : "text-[#1677ff]"
                          }`}
                        >
                          {v.category === "Required" ? "🔴 Required" : "🔵 Advisory"}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-xs text-[#94a3b8] font-mono hidden sm:table-cell">
                        <span className="truncate max-w-[120px] inline-block align-bottom">{v.file}</span>
                      </td>
                      <td className="py-3 px-4 text-xs text-[#64748b] font-mono hidden md:table-cell">
                        {v.line}
                      </td>
                      <td className="py-3 px-4 text-xs text-[#64748b] hidden lg:table-cell max-w-xs">
                        <span className="line-clamp-2">{v.message}</span>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`text-xs ${
                            v.severity === "high"
                              ? "text-[#ff4d4f]"
                              : v.severity === "medium"
                              ? "text-[#faad14]"
                              : "text-[#64748b]"
                          }`}
                        >
                          {v.severity === "high"
                            ? "🔴 高"
                            : v.severity === "medium"
                            ? "🟡 中"
                            : "🔵 低"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
