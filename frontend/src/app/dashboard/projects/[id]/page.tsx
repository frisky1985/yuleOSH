"use client";

import { useState, useEffect } from "react";
import { notFound, useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Clock,
  GitBranch,
  Shield,
  FileText,
  Cpu,
  Layers,
  ChevronRight,
  Download,
  Play,
  Activity,
} from "lucide-react";
import { GithubIcon } from "@/components/github-icon";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { api, type ProjectDetail, type PipelineSession } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PipelineStep {
  name: string;
  icon: string;
  status: "passed" | "failed" | "running" | "pending";
  phase: "design" | "verify" | "deliver";
  detail: string;
}

interface CiLayer {
  name: string;
  status: "passed" | "running" | "failed" | "pending";
  progress: number;
  description: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const statusIcon: Record<string, React.ReactNode> = {
  passed: <CheckCircle2 className="w-3.5 h-3.5 text-[#10b981]" />,
  failed: <AlertCircle className="w-3.5 h-3.5 text-[#ff4d4f]" />,
  running: <Loader2 className="w-3.5 h-3.5 text-[#722ed1] animate-spin" />,
  pending: <Clock className="w-3.5 h-3.5 text-[#64748b]" />,
};

const phaseColor: Record<string, { bg: string; color: string; border: string }> = {
  design: { bg: "rgba(114,46,209,.1)", color: "#722ed1", border: "rgba(114,46,209,.2)" },
  verify: { bg: "rgba(22,119,255,.08)", color: "#1677ff", border: "rgba(22,119,255,.2)" },
  deliver: { bg: "rgba(16,185,129,.08)", color: "#10b981", border: "rgba(16,185,129,.2)" },
};

const ciLayerColors: Record<string, string> = {
  passed: "#10b981",
  running: "#722ed1",
  failed: "#ff4d4f",
  pending: "#64748b",
};

const ciLayerNames = [
  "开发验证 (SWE.4)",
  "集成验证 (SWE.5)",
  "系统验证 (SWE.6)",
];

const ciLayerDescs = [
  "单元测试 · 静态分析 · 代码审查",
  "集成测试 · 接口测试 · 功能验证",
  "系统测试 · 验收测试 · 合规审计",
];

const defaultPipelineSteps: PipelineStep[] = [
  { name: "需求分析", icon: "📋", status: "pending", phase: "design", detail: "等待执行" },
  { name: "架构设计", icon: "🏗️", status: "pending", phase: "design", detail: "等待执行" },
  { name: "详细设计", icon: "📐", status: "pending", phase: "design", detail: "等待执行" },
  { name: "代码实现", icon: "⚡", status: "pending", phase: "design", detail: "等待执行" },
  { name: "单元测试", icon: "🧪", status: "pending", phase: "verify", detail: "等待执行" },
  { name: "静态分析", icon: "🔍", status: "pending", phase: "verify", detail: "等待执行" },
  { name: "集成测试", icon: "🔗", status: "pending", phase: "verify", detail: "等待执行" },
  { name: "系统测试", icon: "🖥️", status: "pending", phase: "deliver", detail: "等待执行" },
  { name: "验收测试", icon: "✅", status: "pending", phase: "deliver", detail: "等待执行" },
  { name: "审计报告", icon: "📊", status: "pending", phase: "deliver", detail: "等待执行" },
];

const defaultCiLayers: CiLayer[] = [
  { name: ciLayerNames[0], status: "pending", progress: 0, description: ciLayerDescs[0] },
  { name: ciLayerNames[1], status: "pending", progress: 0, description: ciLayerDescs[1] },
  { name: ciLayerNames[2], status: "pending", progress: 0, description: ciLayerDescs[2] },
];

function buildPipelineFromSessions(sessions: PipelineSession[]): PipelineStep[] {
  if (!sessions || sessions.length === 0) return defaultPipelineSteps;

  const latest = sessions[0];
  if (!latest || !latest.steps || latest.steps.length === 0) return defaultPipelineSteps;

  // Build pipeline steps from session data
  const steps: PipelineStep[] = defaultPipelineSteps.map((step) => {
    // Check if this step name appears in session steps
    const matched = latest.steps?.find(
      (s) => typeof s === "string" && s.toLowerCase().includes(step.name.toLowerCase().slice(0, 2))
    );
    if (matched) {
      return {
        ...step,
        status: "passed", // If it's in the steps list, mark as passed
        detail: `已执行`,
      };
    }
    return step;
  });

  // If status completed, mark all as passed
  if (latest.status === "completed" || latest.status === "passed") {
    return steps.map((s) => ({ ...s, status: "passed" as const, detail: "已完成" }));
  }

  return steps;
}

function buildCiLayers(sessions: PipelineSession[]): CiLayer[] {
  if (!sessions || sessions.length === 0) return defaultCiLayers;

  const latest = sessions[0];
  if (latest.status === "completed" || latest.status === "passed") {
    return ciLayerNames.map((name, i) => ({
      name,
      status: "passed" as const,
      progress: 100,
      description: ciLayerDescs[i],
    }));
  }

  if (latest.status === "running") {
    return ciLayerNames.map((name, i) => ({
      name,
      status: i === 0 ? ("running" as const) : ("pending" as const),
      progress: i === 0 ? 50 : 0,
      description: ciLayerDescs[i],
    }));
  }

  return defaultCiLayers;
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function ProjectDetailPage() {
  const params = useParams();
  const projectName = params.id as string;

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [sessions, setSessions] = useState<PipelineSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notFound_, setNotFound_] = useState(false);

  useEffect(() => {
    loadProjectDetail();
  }, [projectName]);

  async function loadProjectDetail() {
    if (!projectName) {
      setNotFound_(true);
      return;
    }

    setLoading(true);
    setError("");

    try {
      // Load project details from API v1
      const proj = await api.v1.projects.get(projectName);
      setProject(proj);

      // Load pipeline sessions
      try {
        const { sessions: pipelineSessions } = await api.v1.pipeline.status();
        setSessions(pipelineSessions || []);
      } catch {
        // Pipeline status not available — that's fine
        setSessions([]);
      }
    } catch (err: any) {
      if (err.message?.includes("404") || err.message?.includes("not found")) {
        setNotFound_(true);
      } else {
        setError(err.message || "加载失败");
      }
    } finally {
      setLoading(false);
    }
  }

  if (notFound_) {
    notFound();
  }

  const pipelineSteps = buildPipelineFromSessions(sessions);
  const ciLayers = buildCiLayers(sessions);
  const agents = sessions.filter((s) => s.status === "running").length || 0;
  const lastRun = sessions[0]?.updated_at || sessions[0]?.created_at || "-";
  const lastRunDisplay = lastRun !== "-" ? new Date(lastRun).toLocaleString("zh-CN") : "-";

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0] flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-8 h-8 text-[#722ed1] animate-spin mx-auto mb-3" />
          <p className="text-sm text-[#94a3b8]">加载项目信息...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      {/* Fixed Grid Background */}
      <div
        className="fixed inset-0 pointer-events-none z-0"
        style={{
          backgroundImage:
            "linear-gradient(rgba(114,46,209,.015) 1px, transparent 1px), linear-gradient(90deg, rgba(114,46,209,.015) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      {/* Nav */}
      <nav
        className="sticky top-0 z-50 border-b border-[#1e293b]/60"
        style={{ background: "rgba(17,24,39,.9)", backdropFilter: "blur(12px)" }}
      >
        <div className="max-w-[1360px] mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <Link href="/" className="text-base font-black tracking-tight">
              <span className="text-[#10b981]">yule</span><span className="text-[#1677ff]">OSH</span>
            </Link>
            <div className="flex items-center gap-5">
              <Link href="/dashboard" className="text-xs text-[#94a3b8] hover:text-white transition-colors">Dashboard</Link>
              <Link href="/login" className="text-xs text-[#94a3b8] hover:text-white transition-colors">登录</Link>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-[1360px] mx-auto px-4 sm:px-6 lg:px-8 py-6 relative z-[1]">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-xs text-[#64748b] mb-6">
          <Link href="/dashboard" className="hover:text-[#722ed1] transition-colors">Dashboard</Link>
          <ChevronRight className="w-3 h-3" />
          <span className="text-[#94a3b8]">{project?.name || projectName}</span>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 rounded-lg bg-[#ff4d4f]/10 border border-[#ff4d4f]/20 px-4 py-3 text-sm text-[#ff4d4f]">
            {error}
          </div>
        )}

        {/* Project Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
          <div className="flex items-center gap-4">
            <Link
              href="/dashboard"
              className="flex items-center justify-center w-9 h-9 rounded-lg border border-[#1e293b] text-[#64748b] hover:text-white hover:border-[#722ed1]/40 transition-all"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-xl sm:text-2xl font-black text-[#e2e8f0]">{project?.name || projectName}</h1>
                <Badge
                  className="text-xs px-2 py-0.5"
                  style={{
                    background: phaseColor.design.bg,
                    color: phaseColor.design.color,
                    borderColor: phaseColor.design.border,
                  }}
                >
                  待启动
                </Badge>
              </div>
              <p className="text-sm text-[#94a3b8] mt-0.5">{project?.description || "暂无描述"}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              className="border-[#1e293b] text-[#94a3b8] hover:text-white hover:bg-[#1e293b] text-xs h-9 gap-1.5"
            >
              <Play className="w-3.5 h-3.5" />
              运行 Pipeline
            </Button>
            <Button
              className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 text-xs h-9 gap-1.5"
            >
              <Download className="w-3.5 h-3.5" />
              导出审计包
            </Button>
          </div>
        </div>

        {/* V-Model Phase Bar */}
        <div className="flex items-center justify-center mb-6 gap-3 text-[11px] text-[#64748b]">
          <span className="px-3 py-1 rounded font-semibold" style={{ background: "rgba(114,46,209,.1)", color: "#722ed1" }}>
            ◢ 设计与实现
          </span>
          <span className="text-[#1e293b]">▸</span>
          <span className="px-3 py-1 rounded font-semibold" style={{ background: "rgba(22,119,255,.08)", color: "#1677ff" }}>
            ▽ 验证
          </span>
          <span className="text-[#1e293b]">▸</span>
          <span className="px-3 py-1 rounded font-semibold" style={{ background: "rgba(16,185,129,.08)", color: "#10b981" }}>
            ◣ 确认与交付
          </span>
        </div>

        {/* Pipeline Flow */}
        <Card className="border-[#1e293b] bg-[#111827] mb-8">
          <CardHeader className="pb-4">
            <CardTitle className="text-sm font-semibold text-[#e2e8f0] flex items-center gap-2">
              <Layers className="w-4 h-4 text-[#722ed1]" />
              Pipeline 流水线
            </CardTitle>
            <CardDescription className="text-xs text-[#64748b]">
              Agent 编排全流程 · {agents > 0 ? `${agents} 个活跃 Pipeline` : "暂无活跃 Pipeline"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-0 overflow-x-auto pb-2" style={{ scrollbarWidth: "thin" }}>
              {pipelineSteps.map((step, i) => (
                <div key={i} className="relative min-w-[130px] max-w-[150px] flex-1">
                  <div
                    className="rounded-lg border p-3 text-center transition-all hover:-translate-y-0.5 cursor-pointer"
                    style={{
                      background:
                        step.status === "running"
                          ? `linear-gradient(180deg, rgba(114,46,209,.04), #111827)`
                          : "#111827",
                      borderColor:
                        step.status === "running"
                          ? "rgba(114,46,209,.3)"
                          : step.status === "passed"
                          ? "rgba(16,185,129,.2)"
                          : step.status === "failed"
                          ? "rgba(255,77,79,.2)"
                          : "#1e293b",
                      borderTop: `3px solid ${
                        step.status === "passed"
                          ? "#10b981"
                          : step.status === "running"
                          ? "#722ed1"
                          : step.status === "failed"
                          ? "#ff4d4f"
                          : "#1e293b"
                      }`,
                    }}
                  >
                    <div
                      className="inline-flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-bold mb-1"
                      style={{
                        background:
                          step.status === "running"
                            ? "rgba(114,46,209,.08)"
                            : step.status === "passed"
                            ? "rgba(16,185,129,.08)"
                            : step.status === "failed"
                            ? "rgba(255,77,79,.08)"
                            : "#1e293b",
                        color:
                          step.status === "passed"
                            ? "#10b981"
                            : step.status === "running"
                            ? "#722ed1"
                            : step.status === "failed"
                            ? "#ff4d4f"
                            : "#64748b",
                      }}
                    >
                      {step.status === "passed" ? "✓" : step.status === "failed" ? "✗" : i + 1}
                    </div>
                    <div className="text-lg mb-1">{step.icon}</div>
                    <div className="text-[11px] font-semibold leading-tight text-[#e2e8f0]">{step.name}</div>
                    <div className="flex items-center justify-center gap-1 mt-1">
                      {statusIcon[step.status]}
                      <span
                        className="text-[10px] font-semibold"
                        style={{
                          color:
                            step.status === "passed"
                              ? "#10b981"
                              : step.status === "running"
                              ? "#722ed1"
                              : step.status === "failed"
                              ? "#ff4d4f"
                              : "#64748b",
                        }}
                      >
                        {step.status === "passed"
                          ? "通过"
                          : step.status === "running"
                          ? "运行中"
                          : step.status === "failed"
                          ? "失败"
                          : "等待"}
                      </span>
                    </div>
                    <div className="text-[10px] text-[#64748b] mt-1 leading-tight">{step.detail}</div>
                  </div>
                  {i < pipelineSteps.length - 1 && (
                    <div className="hidden sm:block absolute right-[-4px] top-1/2 -translate-y-1/2 text-[#1e293b] text-xs pointer-events-none">
                      ▸
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* CI/CD Layers */}
        <div className="grid md:grid-cols-3 gap-4 mb-8">
          {ciLayers.map((layer, i) => (
            <Card key={i} className="border-[#1e293b] bg-[#111827]">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold text-[#e2e8f0]">{layer.name}</CardTitle>
                  <Badge
                    className="text-xs"
                    style={{
                      background: `${ciLayerColors[layer.status]}15`,
                      color: ciLayerColors[layer.status],
                      borderColor: `${ciLayerColors[layer.status]}20`,
                    }}
                  >
                    {layer.status === "passed" ? "通过" : layer.status === "running" ? "运行中" : layer.status === "failed" ? "失败" : "等待"}
                  </Badge>
                </div>
                <CardDescription className="text-xs text-[#64748b]">{layer.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-[#64748b]">进度</span>
                  <span className="text-[#94a3b8] font-medium">{layer.progress}%</span>
                </div>
                <div className="relative h-1.5 w-full rounded-full bg-[#1e293b] overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${layer.progress}%`,
                      background: `linear-gradient(90deg, ${ciLayerColors[layer.status]}, ${
                        layer.progress >= 100 ? "#10b981" : ciLayerColors[layer.status]
                      })`,
                    }}
                  />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Pipeline Sessions / Execution Logs */}
        {sessions.length > 0 && (
          <Card className="border-[#1e293b] bg-[#111827] mb-8">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold text-[#e2e8f0] flex items-center gap-2">
                <Activity className="w-4 h-4 text-[#1677ff]" />
                执行日志
              </CardTitle>
              <CardDescription className="text-xs text-[#64748b]">
                共 {sessions.length} 次 Pipeline 执行记录
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 max-h-64 overflow-y-auto">
              {sessions.map((s, i) => (
                <div
                  key={i}
                  className="flex items-start gap-3 rounded-lg border border-[#1e293b] p-3 text-xs"
                >
                  <div className="mt-0.5">
                    {statusIcon[s.status === "completed" ? "passed" : s.status === "failed" ? "failed" : "running"]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-[#e2e8f0]">
                      {s.name || s.spec_path || `Pipeline #${i + 1}`}
                    </div>
                    <div className="text-[#64748b] mt-0.5">
                      状态:{" "}
                      {s.status === "completed"
                        ? "已完成"
                        : s.status === "failed"
                        ? "失败"
                        : s.status === "running"
                        ? "运行中"
                        : s.status || "未知"}
                      {s.created_at && ` · ${new Date(s.created_at).toLocaleString("zh-CN")}`}
                    </div>
                    {/* Errors */}
                    {s.errors && s.errors.length > 0 && (
                      <div className="mt-1 text-[#ff4d4f]">
                        {s.errors.slice(0, 3).map((err, j) => (
                          <div key={j} className="truncate">{err}</div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Project Info & Meta */}
        <Card className="border-[#1e293b] bg-[#111827]">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold text-[#e2e8f0]">项目信息</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-xs text-[#64748b]">状态</span>
                <p className="text-[#e2e8f0] font-medium mt-0.5 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-[#64748b]" /> 就绪
                </p>
              </div>
              <div>
                <span className="text-xs text-[#64748b]">AI Agents</span>
                <p className="text-[#e2e8f0] font-medium mt-0.5 flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5 text-[#722ed1]" /> {agents} 个 Pipeline
                </p>
              </div>
              <div>
                <span className="text-xs text-[#64748b]">上次运行</span>
                <p className="text-[#e2e8f0] font-medium mt-0.5 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-[#64748b]" /> {lastRunDisplay}
                </p>
              </div>
              <div>
                <span className="text-xs text-[#64748b]">创建时间</span>
                <p className="text-[#e2e8f0] font-medium mt-0.5 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-[#64748b]" />
                  {project?.created_at
                    ? new Date(project.created_at).toLocaleDateString("zh-CN")
                    : "未知"}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Back link */}
        <div className="mt-8 text-center">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#722ed1] transition-colors"
          >
            <ArrowLeft className="w-3 h-3" />
            返回项目列表
          </Link>
        </div>
      </div>
    </div>
  );
}
