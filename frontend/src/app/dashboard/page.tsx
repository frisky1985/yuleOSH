"use client";

import Link from "next/link";
import {
  Plus,
  Search,
  GitBranch,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowRight,
  MoreHorizontal,
  FileText,
} from "lucide-react";
import { GithubIcon } from "@/components/github-icon";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

// Mock projects
const projects = [
  {
    id: "1",
    name: "STM32-BMS-Firmware",
    description: "BMS battery management firmware for STM32F4 series",
    status: "active",
    stage: "开发验证 (SWE.4)",
    stageColor: "#722ed1",
    progress: 65,
    lastRun: "2 分钟前",
    agents: 3,
    github: "stefanji/stm32-bms",
  },
  {
    id: "2",
    name: "ESP32-IoT-SensorHub",
    description: "Multi-sensor data collection hub with MQTT support",
    status: "idle",
    stage: "集成验证 (SWE.5)",
    stageColor: "#1677ff",
    progress: 32,
    lastRun: "15 分钟前",
    agents: 2,
    github: "stefanji/esp32-sensorhub",
  },
  {
    id: "3",
    name: "RISC-V-Core-TestSuite",
    description: "Comprehensive test suite for custom RISC-V core",
    status: "completed",
    stage: "系统验证 (SWE.6)",
    stageColor: "#10b981",
    progress: 100,
    lastRun: "1 小时前",
    agents: 3,
    github: "stefanji/riscv-testsuite",
  },
  {
    id: "4",
    name: "CAN-Bootloader-OTA",
    description: "CAN bus-based bootloader with OTA update capability",
    status: "failed",
    stage: "需求分析",
    stageColor: "#ff4d4f",
    progress: 18,
    lastRun: "3 小时前",
    agents: 1,
    github: "stefanji/can-bootloader",
  },
  {
    id: "5",
    name: "FreeRTOS-TaskMonitor",
    description: "Real-time task monitoring and profiling for FreeRTOS",
    status: "active",
    stage: "代码实现",
    stageColor: "#f59e0b",
    progress: 78,
    lastRun: "刚刚",
    agents: 2,
    github: "stefanji/freertos-monitor",
  },
  {
    id: "6",
    name: "I2C-Sensor-DriverLib",
    description: "Unified I2C sensor driver library for multiple platforms",
    status: "draft",
    stage: "未开始",
    stageColor: "#64748b",
    progress: 0,
    lastRun: "-",
    agents: 0,
    github: "",
  },
];

const statusConfig: Record<string, { label: string; icon: React.ReactNode; className: string }> = {
  active: { label: "运行中", icon: <Loader2 className="w-3 h-3 animate-spin" />, className: "bg-[#722ed1]/10 text-[#722ed1] border-[#722ed1]/20" },
  idle: { label: "就绪", icon: <Clock className="w-3 h-3" />, className: "bg-[#1677ff]/10 text-[#1677ff] border-[#1677ff]/20" },
  completed: { label: "已完成", icon: <CheckCircle2 className="w-3 h-3" />, className: "bg-[#10b981]/10 text-[#10b981] border-[#10b981]/20" },
  failed: { label: "失败", icon: <AlertCircle className="w-3 h-3" />, className: "bg-[#ff4d4f]/10 text-[#ff4d4f] border-[#ff4d4f]/20" },
  draft: { label: "草稿", icon: <FileText className="w-3 h-3" />, className: "bg-[#64748b]/10 text-[#64748b] border-[#64748b]/20" },
};

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      {/* Top Nav */}
      <nav className="sticky top-0 z-50 border-b border-[#1e293b]/60 nav-blur" style={{ background: "rgba(10,14,23,.85)" }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <Link href="/" className="text-lg font-black tracking-tight">
              <span className="text-[#10b981]">yule</span><span className="text-[#1677ff]">OSH</span>
            </Link>
            <div className="flex items-center gap-3">
              <Link href="/login"
                className="text-sm px-3 py-1.5 rounded-lg border border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#722ed1]/40 transition-all"
              >
                登录
              </Link>
              <Avatar className="w-8 h-8 border border-[#1e293b]">
                <AvatarFallback className="bg-[#722ed1]/20 text-[#722ed1] text-xs">YU</AvatarFallback>
              </Avatar>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-black text-[#e2e8f0]">我的项目</h1>
            <p className="text-sm text-[#94a3b8] mt-1">管理你的嵌入式开发项目与 AI Agent 流水线</p>
          </div>
          <Button className="bg-gradient-to-r from-[#722ed1] to-[#1677ff] text-white hover:from-[#722ed1]/90 hover:to-[#1677ff]/90 shadow-lg shadow-[#722ed1]/20 gap-2">
            <Plus className="w-4 h-4" />
            新建项目
          </Button>
        </div>

        {/* Search & Filter */}
        <div className="flex items-center gap-3 mb-6">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748b]" />
            <Input
              placeholder="搜索项目..."
              className="pl-9 border-[#1e293b] bg-[#111827] text-[#e2e8f0] placeholder:text-[#64748b] focus-visible:ring-[#722ed1]"
            />
          </div>
          <select className="h-10 px-3 rounded-lg border border-[#1e293b] bg-[#111827] text-sm text-[#94a3b8] focus:outline-none focus:ring-1 focus:ring-[#722ed1]">
            <option>全部状态</option>
            <option>运行中</option>
            <option>就绪</option>
            <option>已完成</option>
            <option>失败</option>
          </select>
        </div>

        {/* Project Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {projects.map((project) => {
            const status = statusConfig[project.status];
            return (
              <Link key={project.id} href={`/dashboard/projects/${project.id}`} className="group block">
                <Card className="h-full border-[#1e293b] bg-[#111827] hover:border-[#722ed1]/30 transition-all cursor-pointer">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <CardTitle className="text-base font-bold text-[#e2e8f0] truncate group-hover:text-[#722ed1] transition-colors">
                          {project.name}
                        </CardTitle>
                        <CardDescription className="text-xs text-[#94a3b8] mt-1 line-clamp-1">
                          {project.description}
                        </CardDescription>
                      </div>
                      <div className="relative group">
                        <button className="h-8 w-8 p-0 text-[#64748b] hover:text-white hover:bg-[#1e293b] rounded-lg transition-colors">
                          <MoreHorizontal className="w-4 h-4 mx-auto" />
                        </button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {/* Status Badge */}
                    <div className="flex items-center gap-2 mb-3">
                      <Badge variant="outline" className={`text-xs px-2 py-0.5 gap-1 ${status.className}`}>
                        {status.icon}
                        {status.label}
                      </Badge>
                      <Badge
                        variant="outline"
                        className="text-xs px-2 py-0.5"
                        style={{
                          background: `${project.stageColor}10`,
                          color: project.stageColor,
                          borderColor: `${project.stageColor}20`,
                        }}
                      >
                        {project.stage}
                      </Badge>
                    </div>

                    {/* Progress Bar */}
                    <div className="mb-3">
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="text-[#64748b]">进度</span>
                        <span className="text-[#94a3b8] font-medium">{project.progress}%</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${project.progress}%`,
                            background: `linear-gradient(90deg, ${project.stageColor}, ${project.progress >= 100 ? "#10b981" : project.stageColor})`,
                          }}
                        />
                      </div>
                    </div>

                    {/* Meta */}
                    <div className="flex items-center gap-4 text-xs text-[#64748b]">
                      <span className="flex items-center gap-1">
                        <GitBranch className="w-3 h-3" /> {project.agents} Agents
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" /> {project.lastRun}
                      </span>
                    </div>
                  </CardContent>
                  <CardFooter className="pt-0">
                    <div className="flex items-center justify-between w-full">
                      {project.github && (
                        <a
                          href={`https://github.com/${project.github}`}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="flex items-center gap-1 text-xs text-[#64748b] hover:text-[#1677ff] transition-colors"
                        >
                          <GithubIcon className="w-3 h-3" />
                          {project.github}
                        </a>
                      )}
                      <span className="flex items-center gap-1 text-xs text-[#722ed1] opacity-0 group-hover:opacity-100 transition-opacity ml-auto">
                        详情 <ArrowRight className="w-3 h-3" />
                      </span>
                    </div>
                  </CardFooter>
                </Card>
              </Link>
            );
          })}
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-10">
          {[
            { label: "项目总数", value: "6", color: "#722ed1" },
            { label: "运行中", value: "2", color: "#722ed1" },
            { label: "已完成", value: "1", color: "#10b981" },
            { label: "失败", value: "1", color: "#ff4d4f" },
          ].map((s, i) => (
            <div key={i} className="rounded-xl border border-[#1e293b] bg-[#111827] p-4 text-center">
              <div className="text-2xl font-black" style={{ color: s.color }}>{s.value}</div>
              <div className="text-xs text-[#64748b] mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
