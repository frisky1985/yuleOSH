"use client";

// 组合视图 & 合规就绪评分（决策者 Quick Win）。
// 纯前端聚合已有 /api/v1/dashboard/* 端点，无需新增后端：
//   - /dashboard/projects        → 多项目列表（含每项目 SWE 完成计数）
//   - /dashboard/swe-status       → SWE.1–SWE.6 合规就绪度
//   - /dashboard/coverage         → 代码行/分支覆盖率
//   - /dashboard/gap-analysis      → 差距项（critical/major/minor）
// 输出一张组合表 + 每项目红绿灯「合规就绪评分」。

import { useEffect, useState } from "react";
import {
  getDashboardProjects,
  getSWEStatus,
  getCoverage,
  getGapAnalysis,
} from "@/lib/api";
import type {
  DashboardProject,
  SWEStatusResponse,
  CoverageResponse,
  GapAnalysisResponse,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Loader2 } from "lucide-react";

interface ProjectRow {
  id: string;
  name: string;
  slug: string;
  swePct: number;
  covPct: number;
  critical: number;
  major: number;
  minor: number;
  score: number;
}

function scoreColor(score: number): { text: string; bg: string; border: string; label: string } {
  if (score >= 80) return { text: "#10b981", bg: "#10b9811f", border: "#10b9814d", label: "就绪" };
  if (score >= 60) return { text: "#faad14", bg: "#faad141f", border: "#faad144d", label: "进行中" };
  return { text: "#ff4d4f", bg: "#ff4d4f1f", border: "#ff4d4f4d", label: "风险" };
}

export function PortfolioCompliance() {
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<ProjectRow[]>([]);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const projRes = await getDashboardProjects();
        const projects: DashboardProject[] = projRes.projects || [];
        const built: ProjectRow[] = await Promise.all(
          projects.map(async (p) => {
            const pid = p.id;
            const [swe, cov, gap] = await Promise.all([
              getSWEStatus(pid).catch(() => null),
              getCoverage(pid).catch(() => null),
              getGapAnalysis({ projectId: pid, limit: 1 }).catch(() => null),
            ]);
            const sweData = (swe ?? null) as SWEStatusResponse | null;
            const covData = (cov ?? null) as CoverageResponse | null;
            const gapData = (gap ?? null) as GapAnalysisResponse | null;

            const sweTotal = p.swe_total || sweData?.total_count || 0;
            const sweDone = p.swe_completed_count || sweData?.completed_count || 0;
            const swePct = sweTotal > 0 ? Math.round((sweDone / sweTotal) * 100) : 0;
            const covPct = covData?.line_pct != null ? Math.round(covData.line_pct) : 0;
            const critical = gapData?.summary?.critical || 0;
            const major = gapData?.summary?.major || 0;
            const minor = gapData?.summary?.minor || 0;
            const gapScore = Math.max(0, 100 - (critical * 8 + major * 3 + minor * 1));
            const score = Math.round(0.45 * swePct + 0.3 * covPct + 0.25 * gapScore);

            return {
              id: pid,
              name: p.name,
              slug: p.slug,
              swePct,
              covPct,
              critical,
              major,
              minor,
              score,
            };
          })
        );
        if (cancelled) return;
        setRows(built);
        setNote(projRes.note || null);
      } catch (e) {
        if (!cancelled) setNote(`加载组合视图失败：${(e as Error).message}`);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card className="border-[#1e293b] bg-[#111827] mb-4">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center gap-2">
          <span className="text-[#1677ff]">◧</span>
          组合视图 &amp; 合规就绪评分
        </CardTitle>
        <CardDescription className="text-xs text-[#64748b] mt-1">
          跨项目聚合 SWE 完成度 / 覆盖率 / 差距项，输出每项目合规红绿灯
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-[#64748b]">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            加载中…
          </div>
        ) : rows.length === 0 ? (
          <div className="py-8 text-center text-xs text-[#64748b]">
            暂无项目（先创建 / 加载示例项目）
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[#64748b] border-b border-[#1e293b]">
                  <th className="text-left font-normal py-2 pr-3">项目</th>
                  <th className="text-right font-normal py-2 px-3">SWE 完成</th>
                  <th className="text-right font-normal py-2 px-3">覆盖率</th>
                  <th className="text-right font-normal py-2 px-3">差距(C/M)</th>
                  <th className="text-right font-normal py-2 pl-3">合规就绪</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const c = scoreColor(r.score);
                  return (
                    <tr key={r.id} className="border-b border-[#1e293b]/60">
                      <td className="py-2 pr-3">
                        <div className="text-[#e2e8f0] truncate max-w-[200px]">{r.name}</div>
                        <div className="text-[10px] text-[#475569] font-mono">{r.slug}</div>
                      </td>
                      <td className="text-right px-3 text-[#cbd5e1]">{r.swePct}%</td>
                      <td className="text-right px-3 text-[#cbd5e1]">
                        {r.covPct > 0 ? `${r.covPct}%` : "—"}
                      </td>
                      <td className="text-right px-3">
                        <span className="text-[#ff4d4f]">{r.critical}</span>
                        <span className="text-[#64748b]"> / </span>
                        <span className="text-[#faad14]">{r.major}</span>
                      </td>
                      <td className="text-right pl-3">
                        <span
                          className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-medium"
                          style={{ color: c.text, background: c.bg, border: `1px solid ${c.border}` }}
                        >
                          <span
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ background: c.text }}
                          />
                          {r.score}
                          <span className="text-[10px] opacity-70">{c.label}</span>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {note && <div className="text-[10px] text-[#475569] mt-2">{note}</div>}
      </CardContent>
    </Card>
  );
}
