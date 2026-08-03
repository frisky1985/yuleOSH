"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { SWEStatus } from "@/lib/api";

// ─── Helpers (A6: moved with the component) ───────────────────────────
function statusLabel(status: string): string {
  const map: Record<string, string> = {
    completed: "已完成", passed: "通过", running: "运行中",
    failed: "失败", pending: "待处理", not_run: "未运行",
  };
  return map[status] ?? status;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  try { return new Date(dateStr).toLocaleString("zh-CN"); }
  catch { return dateStr; }
}

export function SWECard({ swe }: { swe: SWEStatus }) {
  return (
    <Link href={swe.details_url} className="group block">
      <Card
        className="h-full border-[#1e293b] bg-[#111827] hover:border-[#722ed1]/30 transition-all cursor-pointer overflow-hidden"
      >
        {/* Color top strip */}
        <div className="h-1 w-full" style={{ background: swe.color }} />
        <CardHeader className="pb-2 pt-3">
          <CardTitle className="text-sm font-bold text-[#e2e8f0] flex items-center justify-between">
            <span>{swe.short}</span>
            <Badge
              variant="outline"
              className="text-[10px] px-1.5 py-0 h-5"
              style={{
                background: `${swe.color}15`,
                color: swe.color,
                borderColor: `${swe.color}30`,
              }}
            >
              {statusLabel(swe.status)}
            </Badge>
          </CardTitle>
          <CardDescription className="text-xs text-[#94a3b8] line-clamp-2 mt-1">
            {swe.name}
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0 pb-3">
          <p className="text-xs text-[#64748b] line-clamp-2 mb-2 min-h-[2em]">
            {swe.description}
          </p>
          <div className="flex items-center justify-between text-[10px] text-[#64748b]">
            <span>更新: {formatDate(swe.last_updated)}</span>
            <span className="text-[#722ed1] opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5">
              详情 <ArrowRight className="w-2.5 h-2.5" />
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

// ─── Evidence Pack Modal ─────────────────────────────────────────────────────

