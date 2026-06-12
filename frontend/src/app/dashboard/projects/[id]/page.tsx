"use client";

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
} from "lucide-react";
import { GithubIcon } from "@/components/github-icon";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

// Mock project database
const mockProjects: Record<string, {
  id: string;
  name: string;
  description: string;
  status: string;
  stage: string;
  github: string;
  progress: number;
  lastRun: string;
  agents: number;
  ciLayers: { name: string; status: string; progress: number; description: string }[];
  pipeline: { name: string; icon: string; status: string; phase: string; detail: string }[];
}> = {
  "1": {
    id: "1",
    name: "STM32-BMS-Firmware",
    description: "BMS battery management firmware for STM32F4 series",
    status: "active",
    stage: "开发验证 (SWE.4)",
    github: "stefanji/stm32-bms",
    progress: 65,
    lastRun: "2 分钟前",
    agents: 3,
    ciLayers: [
      { name: "Layer 1: 开发验证 (SWE.4)", status: "running", progress: 65, description: "单元测试 · 静态分析 · 代码审查" },
      { name: "Layer 2: 集成验证 (SWE.5)", status: "pending", progress: 0, description: "集成测试 · 接口测试 · 功能验证" },
      { name: "Layer 3: 系统验证 (SWE.6)", status: "pending", progress: 0, description: "系统测试 · 验收测试 · 合规审计" },
    ],
    pipeline: [
      { name: "需求分析", icon: "📋", status: "passed", phase: "design", detail: "12 项需求通过 AI 评审" },
      { name: "架构设计", icon: "🏗️", status: "passed", phase: "design", detail: "生成 SDD 文档" },
      { name: "详细设计", icon: "📐", status: "passed", phase: "design", detail: "生成 DDD 文档" },
      { name: "代码实现", icon: "⚡", status: "running", phase: "design", detail: "68% 代码完成" },
      { name: "单元测试", icon: "🧪", status: "running", phase: "verify", detail: "42/68 测试通过" },
      { name: "静态分析", icon: "🔍", status: "pending", phase: "verify", detail: "等待执行" },
      { name: "集成测试", icon: "🔗", status: "pending", phase: "verify", detail: "等待执行" },
      { name: "系统测试", icon: "🖥️", status: "pending", phase: "deliver", detail: "等待执行" },
      { name: "验收测试", icon: "✅", status: "pending", phase: "deliver", detail: "等待执行" },
      { name: "审计报告", icon: "📊", status: "pending", phase: "deliver", detail: "等待执行" },
    ],
  },
  "2": {
    id: "2",
    name: "ESP32-IoT-SensorHub",
    description: "Multi-sensor data collection hub with MQTT support",
    status: "idle",
    stage: "集成验证 (SWE.5)",
    github: "stefanji/esp32-sensorhub",
    progress: 32,
    lastRun: "15 分钟前",
    agents: 2,
    ciLayers: [
      { name: "Layer 1: 开发验证 (SWE.4)", status: "passed", progress: 100, description: "单元测试 · 静态分析 · 代码审查" },
      { name: "Layer 2: 集成验证 (SWE.5)", status: "running", progress: 32, description: "集成测试 · 接口测试 · 功能验证" },
      { name: "Layer 3: 系统验证 (SWE.6)", status: "pending", progress: 0, description: "系统测试 · 验收测试 · 合规审计" },
    ],
    pipeline: [
      { name: "需求分析", icon: "📋", status: "passed", phase: "design", detail: "8 项需求通过 AI 评审" },
      { name: "架构设计", icon: "🏗️", status: "passed", phase: "design", detail: "生成 SDD 文档" },
      { name: "详细设计", icon: "📐", status: "passed", phase: "design", detail: "生成 DDD 文档" },
      { name: "代码实现", icon: "⚡", status: "passed", phase: "design", detail: "代码完成" },
      { name: "单元测试", icon: "🧪", status: "passed", phase: "verify", detail: "45/45 测试通过" },
      { name: "静态分析", icon: "🔍", status: "passed", phase: "verify", detail: "无严重警告" },
      { name: "集成测试", icon: "🔗", status: "running", phase: "verify", detail: "12/38 测试通过" },
      { name: "系统测试", icon: "🖥️", status: "pending", phase: "deliver", detail: "等待执行" },
      { name: "验收测试", icon: "✅", status: "pending", phase: "deliver", detail: "等待执行" },
      { name: "审计报告", icon: "📊", status: "pending", phase: "deliver", detail: "等待执行" },
    ],
  },
  "3": {
    id: "3",
    name: "RISC-V-Core-TestSuite",
    description: "Comprehensive test suite for custom RISC-V core",
    status: "completed",
    stage: "系统验证 (SWE.6)",
    github: "stefanji/riscv-testsuite",
    progress: 100,
    lastRun: "1 小时前",
    agents: 3,
    ciLayers: [
      { name: "Layer 1: 开发验证 (SWE.4)", status: "passed", progress: 100, description: "单元测试 · 静态分析 · 代码审查" },
      { name: "Layer 2: 集成验证 (SWE.5)", status: "passed", progress: 100, description: "集成测试 · 接口测试 · 功能验证" },
      { name: "Layer 3: 系统验证 (SWE.6)", status: "passed", progress: 100, description: "系统测试 · 验收测试 · 合规审计" },
    ],
    pipeline: [
      { name: "需求分析", icon: "📋", status: "passed", phase: "design", detail: "15 项需求通过 AI 评审" },
      { name: "架构设计", icon: "🏗️", status: "passed", phase: "design", detail: "生成 SDD 文档" },
      { name: "详细设计", icon: "📐", status: "passed", phase: "design", detail: "生成 DDD 文档" },
      { name: "代码实现", icon: "⚡", status: "passed", phase: "design", detail: "代码完成" },
      { name: "单元测试", icon: "🧪", status: "passed", phase: "verify", detail: "89/89 测试通过" },
      { name: "静态分析", icon: "🔍", status: "passed", phase: "verify", detail: "无严重警告" },
      { name: "集成测试", icon: "🔗", status: "passed", phase: "verify", detail: "156/156 测试通过" },
      { name: "系统测试", icon: "🖥️", status: "passed", phase: "deliver", detail: "42/42 测试通过" },
      { name: "验收测试", icon: "✅", status: "passed", phase: "deliver", detail: "全部通过" },
      { name: "审计报告", icon: "📊", status: "passed", phase: "deliver", detail: "已生成合规包" },
    ],
  },
  "4": {
    id: "4",
    name: "CAN-Bootloader-OTA",
    description: "CAN bus-based bootloader with OTA update capability",
    status: "failed",
    stage: "需求分析",
    github: "stefanji/can-bootloader",
    progress: 18,
    lastRun: "3 小时前",
    agents: 1,
    ciLayers: [
      { name: "Layer 1: 开发验证 (SWE.4)", status: "failed", progress: 18, description: "需求评审未通过" },
      { name: "Layer 2: 集成验证 (SWE.5)", status: "pending", progress: 0, description: "等待 Layer 1 通过" },
      { name: "Layer 3: 系统验证 (SWE.6)", status: "pending", progress: 0, description: "等待 Layer 2 通过" },
    ],
    pipeline: [
      { name: "需求分析", icon: "📋", status: "failed", phase: "design", detail: "3 项需求未通过 AI 评审" },
      { name: "架构设计", icon: "🏗️", status: "pending", phase: "design", detail: "等待需求通过" },
      { name: "详细设计", icon: "📐", status: "pending", phase: "design", detail: "等待" },
      { name: "代码实现", icon: "⚡", status: "pending", phase: "design", detail: "等待" },
      { name: "单元测试", icon: "🧪", status: "pending", phase: "verify", detail: "等待" },
      { name: "静态分析", icon: "🔍", status: "pending", phase: "verify", detail: "等待" },
      { name: "集成测试", icon: "🔗", status: "pending", phase: "verify", detail: "等待" },
      { name: "系统测试", icon: "🖥️", status: "pending", phase: "deliver", detail: "等待" },
      { name: "验收测试", icon: "✅", status: "pending", phase: "deliver", detail: "等待" },
      { name: "审计报告", icon: "📊", status: "pending", phase: "deliver", detail: "等待" },
    ],
  },
};

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

export default function ProjectDetailPage() {
  const params = useParams();
  const project = mockProjects[params.id as string];

  if (!project) {
    notFound();
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
          <span className="text-[#94a3b8]">{project.name}</span>
        </div>

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
                <h1 className="text-xl sm:text-2xl font-black text-[#e2e8f0]">{project.name}</h1>
                <Badge
                  className="text-xs px-2 py-0.5"
                  style={{
                    background: phaseColor[project.pipeline.find((p) => p.status === "running" || p.status === "passed")?.phase ?? "design"].bg,
                    color: phaseColor[project.pipeline.find((p) => p.status === "running" || p.status === "passed")?.phase ?? "design"].color,
                    borderColor: phaseColor[project.pipeline.find((p) => p.status === "running" || p.status === "passed")?.phase ?? "design"].border,
                  }}
                >
                  {project.stage}
                </Badge>
              </div>
              <p className="text-sm text-[#94a3b8] mt-0.5">{project.description}</p>
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
              Agent 编排全流程 · {project.agents} 个 AI Agent 参与
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-0 overflow-x-auto pb-2" style={{ scrollbarWidth: "thin" }}>
              {project.pipeline.map((step, i) => (
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
                  {i < project.pipeline.length - 1 && (
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
          {project.ciLayers.map((layer, i) => (
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
                  {project.status === "active" ? (
                    <><Loader2 className="w-3.5 h-3.5 text-[#722ed1] animate-spin" /> 运行中</>
                  ) : project.status === "idle" ? (
                    <><Clock className="w-3.5 h-3.5 text-[#1677ff]" /> 就绪</>
                  ) : project.status === "completed" ? (
                    <><CheckCircle2 className="w-3.5 h-3.5 text-[#10b981]" /> 已完成</>
                  ) : (
                    <><AlertCircle className="w-3.5 h-3.5 text-[#ff4d4f]" /> 失败</>
                  )}
                </p>
              </div>
              <div>
                <span className="text-xs text-[#64748b]">AI Agents</span>
                <p className="text-[#e2e8f0] font-medium mt-0.5 flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5 text-[#722ed1]" /> {project.agents} 个 Agent 编排
                </p>
              </div>
              <div>
                <span className="text-xs text-[#64748b]">上次运行</span>
                <p className="text-[#e2e8f0] font-medium mt-0.5 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-[#64748b]" /> {project.lastRun}
                </p>
              </div>
              <div>
                <span className="text-xs text-[#64748b]">代码仓库</span>
                <a
                  href={`https://github.com/${project.github}`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[#1677ff] font-medium mt-0.5 flex items-center gap-1.5 hover:underline"
                >
                  <GithubIcon className="w-3.5 h-3.5" />
                  {project.github}
                </a>
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
