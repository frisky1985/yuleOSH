"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-fetch";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { VModelDiagram } from "@/components/dashboard/v-model-diagram";
import type { ASPICEStatusResponse, OverviewResponse } from "@/lib/api";

// ─── Status helpers ──────────────────────────────────────────────────────

function statusColor(status?: string): string {
  switch (status) {
    case "good": return "#10b981";
    case "warning": return "#f59e0b";
    case "critical": return "#ef4444";
    default: return "#64748b";
  }
}

function statusLabel(status?: string): string {
  switch (status) {
    case "good": return "良好";
    case "warning": return "警告";
    case "critical": return "不足";
    case "unknown": return "未知";
    default: return status ?? "-";
  }
}

function dimensionLabel(key: string): string {
  const m: Record<string, string> = {
    coverage: "覆盖率",
    test_pass_rate: "测试通过率",
    misra: "MISRA 合规",
    traceability: "可追溯性",
    evidence: "证据完整度",
  };
  return m[key] ?? key;
}

function dimensionColor(status?: string): string {
  switch (status) {
    case "good": return "#10b981";
    case "warning": return "#f59e0b";
    default: return "#ef4444";
  }
}

// ─── Node detail panel ───────────────────────────────────────────────────

const NODE_INFO: Record<string, { name: string; desc: string; artifacts: string[] }> = {
  "SYS.1": { name: "System Requirements Elicitation", desc: "获取系统需求，理解利益相关方期望", artifacts: ["系统需求规范 (SRS)", "利益相关方需求记录"] },
  "SYS.2": { name: "System Requirements Analysis", desc: "分析系统需求，形成可验证的需求规范", artifacts: ["系统需求规范", "需求验证记录"] },
  "SYS.3": { name: "System Architectural Design", desc: "设计系统架构，分配需求到各子系统", artifacts: ["系统架构文档", "架构验证记录"] },
  "SWE.1": { name: "Software Requirements Analysis", desc: "分析软件需求，建立与系统需求的追溯", artifacts: ["软件需求规范 (SwRS)", "追溯矩阵"] },
  "SWE.2": { name: "Software Architectural Design", desc: "设计软件架构，定义组件接口", artifacts: ["软件架构文档", "接口规范"] },
  "SWE.3": { name: "Software Detailed Design", desc: "详细设计软件单元，定义数据结构与算法", artifacts: ["详细设计文档", "单元验证规范"] },
  "SWE.4": { name: "Software Unit Verification", desc: "单元测试验证每个软件单元", artifacts: ["单元测试报告", "覆盖率报告"] },
  "SWE.5": { name: "Software Integration & Verification", desc: "集成测试验证组件间接口", artifacts: ["集成测试报告", "接口测试记录"] },
  "SWE.6": { name: "Software Qualification", desc: "软件合格性测试，验证满足软件需求", artifacts: ["合格性测试报告", "需求覆盖矩阵"] },
  "SYS.4": { name: "System Integration & Verification", desc: "系统集成验证各子系统协作", artifacts: ["系统集成测试报告", "验证记录"] },
  "SYS.5": { name: "System Qualification", desc: "系统合格性测试，验证满足系统需求", artifacts: ["系统合格性测试报告", "验收报告"] },
};

// ─── Page ────────────────────────────────────────────────────────────────

export default function VModelPage() {
  const [aspice, setAspice] = useState<ASPICEStatusResponse | null>(null);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [aspiceData, overviewData] = await Promise.all([
        apiFetch<ASPICEStatusResponse>("/api/v1/dashboard-v2/aspice-status"),
        apiFetch<OverviewResponse>("/api/v1/dashboard-v2/overview"),
      ]);
      setAspice(aspiceData);
      setOverview(overviewData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const selectedInfo = selected ? NODE_INFO[selected] : null;
  const selectedStatus = selected && aspice?.families
    ? aspice.families[selected.split(".")[0]]?.status
    : undefined;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#e2e8f0]">ASPICE V-Model</h1>
          <p className="text-sm text-[#94a3b8] mt-1">
            V 模型全流程可视化 — 需求 → 开发 → 测试验证闭环
          </p>
        </div>
        <button
          onClick={fetchData}
          className="px-3 py-1.5 text-xs rounded-md border border-[#334155] text-[#94a3b8] hover:text-[#e2e8f0] hover:border-[#722ed1]/50 transition-colors"
        >
          刷新数据
        </button>
      </div>

      {error && (
        <Card className="border-[#ef4444]/30 bg-[#ef4444]/10">
          <CardContent className="py-3 text-sm text-[#ef4444]">{error}</CardContent>
        </Card>
      )}

      {/* Top metrics row */}
      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Card className="border-[#1e293b] bg-[#111827]">
            <CardHeader className="pb-1 pt-3 px-4">
              <CardDescription className="text-xs">合规总分</CardDescription>
            </CardHeader>
            <CardContent className="pt-0 px-4 pb-3">
              <div className="text-2xl font-bold" style={{ color: dimensionColor(overview.compliance_score >= 80 ? "good" : overview.compliance_score >= 60 ? "warning" : "critical") }}>
                {overview.compliance_score.toFixed(1)}
              </div>
            </CardContent>
          </Card>
          {overview.dimensions.map((dim) => (
            <Card key={dim.key} className="border-[#1e293b] bg-[#111827]">
              <CardHeader className="pb-1 pt-3 px-4">
                <CardDescription className="text-xs">{dimensionLabel(dim.key)}</CardDescription>
              </CardHeader>
              <CardContent className="pt-0 px-4 pb-3">
                <div className="flex items-center justify-between">
                  <span className="text-lg font-bold" style={{ color: dimensionColor(dim.status) }}>
                    {dim.score.toFixed(0)}
                  </span>
                  <Badge
                    variant="outline"
                    className="text-[10px] px-1.5 py-0"
                    style={{
                      color: dimensionColor(dim.status),
                      borderColor: `${dimensionColor(dim.status)}30`,
                      background: `${dimensionColor(dim.status)}15`,
                    }}
                  >
                    {(dim.weight * 100).toFixed(0)}%
                  </Badge>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Main content: V-diagram + detail panel */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* V-Diagram */}
        <Card className="lg:col-span-2 border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-bold text-[#e2e8f0]">
              V 模型流程图
            </CardTitle>
            <CardDescription className="text-xs">
              点击节点查看详细状态 · 虚线箭头表示验证追溯关系
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center h-[400px] text-[#64748b] text-sm">
                加载中...
              </div>
            ) : (
              <VModelDiagram
                data={aspice ?? undefined}
                selectedNode={selected}
                onSelectNode={setSelected}
              />
            )}
          </CardContent>
        </Card>

        {/* Detail panel */}
        <Card className="border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-bold text-[#e2e8f0]">
              {selectedInfo ? `${selected} — ${selectedInfo.name}` : "过程详情"}
            </CardTitle>
            {selected && (
              <CardDescription className="text-xs flex items-center gap-2">
                {selectedInfo?.desc}
                {selectedStatus && (
                  <Badge
                    variant="outline"
                    className="text-[10px] px-1.5 py-0 ml-auto"
                    style={{
                      color: statusColor(selectedStatus),
                      borderColor: `${statusColor(selectedStatus)}30`,
                      background: `${statusColor(selectedStatus)}15`,
                    }}
                  >
                    {statusLabel(selectedStatus)}
                  </Badge>
                )}
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            {!selected ? (
              <div className="text-sm text-[#64748b] py-8 text-center">
                点击左侧 V 模型中的节点查看详细信息
              </div>
            ) : selectedInfo ? (
              <div className="space-y-4">
                <div>
                  <div className="text-xs font-bold text-[#94a3b8] mb-2">预期产物</div>
                  <ul className="space-y-1">
                    {selectedInfo.artifacts.map((a) => (
                      <li key={a} className="text-xs text-[#e2e8f0] flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#722ed1]" />
                        {a}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Family dimensions if available */}
                {aspice?.families && (() => {
                  const familyKey = selected.split(".")[0];
                  const family = aspice.families[familyKey];
                  if (!family) return null;
                  const dims = Object.entries(family.dimensions || {});
                  if (dims.length === 0) return null;
                  return (
                    <div>
                      <div className="text-xs font-bold text-[#94a3b8] mb-2">评估维度</div>
                      <div className="space-y-2">
                        {dims.map(([key, val]) => (
                          <div key={key} className="flex items-center justify-between text-xs">
                            <span className="text-[#e2e8f0]">{key}</span>
                            <span className="text-[#94a3b8]">{val.coverage_pct?.toFixed(0) ?? 0}%</span>
                          </div>
                        ))}
                        <div className="flex items-center justify-between text-xs pt-1 border-t border-[#1e293b]">
                          <span className="text-[#94a3b8]">平均覆盖率</span>
                          <span className="font-bold" style={{ color: statusColor(family.status) }}>
                            {family.avg_coverage?.toFixed(1) ?? 0}%
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {/* Family summary cards */}
      {aspice?.families && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {Object.entries(aspice.families).map(([key, family]) => (
            <Card key={key} className="border-[#1e293b] bg-[#111827]">
              <CardHeader className="pb-1 pt-3 px-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-bold text-[#e2e8f0]">{key}</CardTitle>
                  <Badge
                    variant="outline"
                    className="text-[10px] px-1.5 py-0"
                    style={{
                      color: statusColor(family.status),
                      borderColor: `${statusColor(family.status)}30`,
                      background: `${statusColor(family.status)}15`,
                    }}
                  >
                    {statusLabel(family.status)}
                  </Badge>
                </div>
                <CardDescription className="text-xs">{family.label}</CardDescription>
              </CardHeader>
              <CardContent className="pt-0 px-4 pb-3">
                <div className="text-lg font-bold" style={{ color: statusColor(family.status) }}>
                  {family.avg_coverage?.toFixed(1) ?? 0}%
                </div>
                <div className="text-[10px] text-[#64748b]">
                  {Object.keys(family.dimensions || {}).length} 个过程域
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Note */}
      {aspice?.note && (
        <div className="text-xs text-[#64748b] border-t border-[#1e293b] pt-3">
          {aspice.note}
        </div>
      )}
    </div>
  );
}
