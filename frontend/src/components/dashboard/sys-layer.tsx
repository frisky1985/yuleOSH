"use client";

import { Badge } from "@/components/ui/badge";

// M1.5 链路D: 系统层 (SYS.1–SYS.5) + 门禁 (G0) 可视化区块。
// 数据来自后端 /api/v1/dashboard/swe-status 的 sys_status / gates 字段。

function statusColor(status?: string): string {
  switch (status) {
    case "completed":
    case "passed":
      return "#10b981";
    case "failed":
      return "#ff4d4f";
    case "generated":
    case "running":
      return "#722ed1";
    case "not-run":
    default:
      return "#64748b";
  }
}

function statusLabel(status?: string): string {
  const m: Record<string, string> = {
    completed: "已完成",
    passed: "通过",
    failed: "失败",
    generated: "已生成",
    running: "运行中",
    pending: "待处理",
    "not-run": "未运行",
  };
  return m[status ?? ""] ?? status ?? "-";
}

export function SysLayerSection({
  sysStatus,
  gates,
}: {
  sysStatus?: Record<string, { status: string; note: string }>;
  gates?: Array<{ gate: string; name: string; status: string; advisory?: boolean }>;
}) {
  const hasSys = sysStatus && Object.keys(sysStatus).length > 0;
  const hasGates = gates && gates.length > 0;
  if (!hasSys && !hasGates) return null;

  return (
    <div className="mt-6">
      {/* SYS.1–SYS.5 Cards */}
      {hasSys && (
        <div className="mb-4">
          <div className="text-xs font-bold text-[#e2e8f0] flex items-center gap-2 mb-2">
            <span>🔧 系统层 (SYS.1–SYS.5) — ASPICE V 模型左半</span>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {Object.entries(sysStatus!).map(([key, s]) => (
              <div
                key={key}
                className="border border-[#1e293b] bg-[#111827] rounded-lg p-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-[#e2e8f0]">{key}</span>
                  <Badge
                    variant="outline"
                    className="text-[10px] px-1.5 py-0 h-5"
                    style={{
                      background: `${statusColor(s.status)}15`,
                      color: statusColor(s.status),
                      borderColor: `${statusColor(s.status)}30`,
                    }}
                  >
                    {statusLabel(s.status)}
                  </Badge>
                </div>
                <p className="text-xs text-[#64748b] mt-1">{s.note}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Gates (含 G0) */}
      {hasGates && (
        <div>
          <div className="text-xs font-bold text-[#e2e8f0] mb-2">
            门禁状态 (Gates)
          </div>
          <div className="flex flex-wrap gap-2">
            {gates!.map((g) => (
              <Badge
                key={g.gate}
                variant="outline"
                className="text-[10px]"
                style={{
                  background: `${statusColor(g.status)}15`,
                  color: statusColor(g.status),
                  borderColor: `${statusColor(g.status)}30`,
                }}
              >
                {g.gate}: {statusLabel(g.status)}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
